import asyncio
import secrets
import threading
import time
from datetime import timedelta
import httpx
from concurrent.futures import ThreadPoolExecutor
from app.core.config import settings
from app.brokers.broker_factory import get_broker_client
from app.core.database import SessionLocal
from app.core.models import UserSettings, Holding, utc_now_aware
from app.bot.fx_cache import FXRateCache
from app.core.logging import logger
from app.core.i18n import I18n, resolve_user_language
from app.core.security import hash_telegram_link_token

# 연동 딥링크 토큰의 수명. 짧게 잡아 링크가 채팅 기록·브라우저 히스토리에 남더라도
# 재사용 창을 최소화한다. 소비 즉시 폐기되므로 실질 수명은 이보다 더 짧다.
TELEGRAM_LINK_TOKEN_TTL_MINUTES = 10
# 텔레그램 /start 페이로드 한도(64자) 안에 들어가는 128비트 난수.
TELEGRAM_LINK_TOKEN_BYTES = 16


def issue_telegram_link_token(db, user_id: int) -> tuple[str, "object"]:
    """사용자 본인 세션에서만 발급되는 1회용 연동 토큰을 만들고 (원본, 만료시각)을 돌려준다.

    DB에는 원본이 아닌 SHA-256 지문만 남는다. 재발급하면 직전 토큰은 즉시 무효가 된다.
    커밋은 호출자 책임(라우터의 트랜잭션 경계를 침범하지 않기 위함).
    """
    db_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not db_settings:
        db_settings = UserSettings(user_id=user_id)
        db.add(db_settings)

    token = secrets.token_urlsafe(TELEGRAM_LINK_TOKEN_BYTES)
    expires_at = utc_now_aware() + timedelta(minutes=TELEGRAM_LINK_TOKEN_TTL_MINUTES)
    db_settings.telegram_link_token_hash = hash_telegram_link_token(token)
    db_settings.telegram_link_token_expires_at = expires_at
    return token, expires_at


def consume_telegram_link_token(db, token: str) -> UserSettings | None:
    """연동 토큰을 검증하고 성공 시 해당 UserSettings를 반환하며 토큰을 즉시 폐기한다.

    만료·불일치·이미 사용됨은 모두 None으로 동일하게 처리한다(존재 여부 노출 금지).
    커밋은 호출자 책임.
    """
    normalized = (token or "").strip()
    if not normalized:
        return None

    token_hash = hash_telegram_link_token(normalized)
    db_settings = (
        db.query(UserSettings)
        .filter(UserSettings.telegram_link_token_hash == token_hash)
        .first()
    )
    if not db_settings:
        return None

    expires_at = db_settings.telegram_link_token_expires_at
    # 1회용이므로 만료된 토큰이라도 조회된 이상 즉시 비워 재시도 여지를 남기지 않는다.
    db_settings.telegram_link_token_hash = None
    db_settings.telegram_link_token_expires_at = None
    if not expires_at or expires_at < utc_now_aware():
        return None

    return db_settings


# 레거시 Markdown이 서식으로 해석하는 문자들. 백슬래시 이스케이프는 MarkdownV2에만 문서화돼
# 있고 레거시 모드에서는 보장되지 않으므로, 값에서 제거하는 방식으로 결정론적으로 무력화한다.
_MARKDOWN_SIGNIFICANT_CHARS = ("`", "*", "_", "[")


def sanitize_markdown_value(value) -> str:
    """Markdown 서식 메시지에 끼워 넣을 외부 값에서 서식 문자를 제거한다.

    티커명·계정명처럼 짧은 식별자에 쓴다. 서식 문자가 그대로 들어가면 값이 조용히 훼손되거나
    (짝수개면 이탤릭·볼드 마크업으로 소비됨), 홀수개면 Telegram이 400 can't parse entities로
    메시지 전체를 거부해 알림이 누락된다. 백틱으로 감싼 자리도 값 안의 백틱이 코드 스팬을
    탈출시키므로 함께 제거한다.

    자유 서식 텍스트(예외 메시지 등)에는 쓰지 않는다 - 내용이 깎이므로 parse_mode=None으로
    서식 자체를 끄는 쪽이 맞다.
    """
    text = str(value)
    for char in _MARKDOWN_SIGNIFICANT_CHARS:
        text = text.replace(char, "")
    return text


def _lang_from_telegram_code(code: str | None) -> str:
    """텔레그램 update의 from.language_code를 앱 언어로 매핑한다.

    user 매핑 전(미연동) 메시지 전용. UserSettings.language를 아직 못 읽으므로
    텔레그램 클라이언트 언어에 의존하며, 영어권만 en으로 보고 그 외는 ko로 폴백한다.
    """
    if code and code.lower().startswith("en"):
        return "en"
    return "ko"

# 글로벌 텔레그램 봇 단일 스레드 제어 변수
_global_poll_thread = None
_global_stop_event = None
_telegram_executor = None

# 재시도해도 결과가 달라지지 않는 실패는 즉시 포기한다. 400(서식 파싱 실패), 403(봇 차단),
# 404(chat 없음)를 재시도하면 호출자 응답만 늦어질 뿐 성공 확률은 0이다.
# 반대로 429(rate limit)와 5xx, 네트워크 예외는 잠시 뒤 성공할 수 있다.
_TELEGRAM_RETRYABLE_STATUS = (429, 500, 502, 503, 504)


def resolve_target_chat_id(user_id: int, db=None) -> str | None:
    """연동이 활성화된 사용자의 chat_id를 조회한다. 발송은 하지 않는다.

    db를 넘기면 그 세션으로 조회한다. 요청 스코프 세션을 가진 호출자(라우터)는 반드시 자기
    세션을 넘겨야 한다 — 넘기지 않으면 모듈 레벨 SessionLocal을 열어 호출자가 어떤 DB를 쓰든
    항상 기본 DB를 조회하므로, 격리된 DB(통합 테스트의 인메모리 등)에서 호출해도 기본 DB의
    동일 user_id 연동 채팅으로 실제 메시지가 나간다.
    """
    owns_session = db is None
    session = db or SessionLocal()
    try:
        db_settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not db_settings or not db_settings.telegram_enabled:
            return None
        return db_settings.telegram_chat_id or None
    finally:
        # 넘겨받은 세션은 호출자 소유다. 여기서 닫으면 호출자의 트랜잭션이 끊긴다.
        if owns_session:
            session.close()


def send_message_sync(
    user_id: int,
    text: str,
    db=None,
    parse_mode: str | None = "Markdown",
    attempts: int = 1,
    backoff_seconds: float = 0.3,
    timeout_seconds: float = 5.0,
) -> bool:
    """
    특정 사용자의 텔레그램으로 메시지 동기 전송 (글로벌 봇 토큰 활용)

    db 계약은 resolve_target_chat_id와 같다.

    parse_mode=None은 서식 없이 원문 그대로 보낸다. 사용자 입력(계정명·에러 문자열 등)을
    끼운 메시지는 이쪽을 써야 한다. 레거시 Markdown은 밑줄을 이탤릭 마크업으로 소비해
    값을 조용히 훼손하고(짝수개), 홀수개면 400 can't parse entities로 발송 자체가 실패한다.

    attempts를 1보다 크게 주면 전송 가능한 실패(429·5xx·네트워크 예외)에 한해 재시도한다.
    기본값 1은 기존 동작(단발 시도)이다. 유실되면 안 되는 알림만 값을 올린다 - 호출자를
    그만큼 붙잡으므로 요청 처리 경로에서는 상한을 작게 유지해야 한다.
    """
    chat_id = resolve_target_chat_id(user_id, db=db)
    if not chat_id:
        return False
    return send_to_chat_sync(
        chat_id,
        text,
        parse_mode=parse_mode,
        attempts=attempts,
        backoff_seconds=backoff_seconds,
        timeout_seconds=timeout_seconds,
        log_label=f"User {user_id}",
    )


def send_to_chat_sync(
    chat_id: str,
    text: str,
    parse_mode: str | None = "Markdown",
    attempts: int = 1,
    backoff_seconds: float = 0.3,
    timeout_seconds: float = 5.0,
    log_label: str = "",
) -> bool:
    """이미 확정된 chat_id로 전송한다. DB를 전혀 건드리지 않는다.

    조회와 전송을 나눠 둔 이유는, 전송을 다른 스레드로 넘길 때 요청 스코프 세션을 함께
    넘기면 이미 닫힌 세션을 쓰게 되기 때문이다(dispatch_alert 참고).
    """
    token = settings.TELEGRAM_BOT_TOKEN
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    total_attempts = max(1, attempts)
    for attempt in range(1, total_attempts + 1):
        is_last = attempt == total_attempts
        try:
            with httpx.Client() as client:
                res = client.post(url, json=payload, timeout=timeout_seconds)
                if res.status_code == 200:
                    return True
                logger.warning(
                    f"[Telegram {log_label}] Failed to send message. "
                    f"Code: {res.status_code}, Res: {res.text} (attempt {attempt}/{total_attempts})"
                )
                if res.status_code not in _TELEGRAM_RETRYABLE_STATUS:
                    return False
        except Exception:
            logger.exception(f"[Telegram {log_label}] Send exception (attempt {attempt}/{total_attempts})")

        if is_last:
            return False
        time.sleep(backoff_seconds * attempt)

    return False


# 알림 전송 전용 스레드 풀. 요청 처리 워커를 재시도 대기로 붙잡지 않기 위한 것이다.
# 상한을 두는 이유는 알림이 몰릴 때 스레드가 무한히 늘지 않게 하기 위함이다 - 상한을 넘으면
# 큐에서 대기하며, 요청 스레드는 submit 직후 곧바로 돌아간다.
# 봇 폴링용 _telegram_executor와 분리했다. 폴링 수명주기(start/stop_telegram_bot)에 묶이면
# 봇이 꺼진 상태에서 발생한 보안 경고를 보낼 수 없다.
_ALERT_EXECUTOR_MAX_WORKERS = 4
_alert_executor: ThreadPoolExecutor | None = None
_alert_executor_lock = threading.Lock()


def _get_alert_executor() -> ThreadPoolExecutor:
    global _alert_executor
    if _alert_executor is None:
        with _alert_executor_lock:
            if _alert_executor is None:
                _alert_executor = ThreadPoolExecutor(
                    max_workers=_ALERT_EXECUTOR_MAX_WORKERS,
                    thread_name_prefix="TelegramAlert",
                )
    return _alert_executor


def dispatch_alert(
    user_id: int,
    text: str,
    db=None,
    parse_mode: str | None = None,
    attempts: int = 3,
    backoff_seconds: float = 0.3,
    timeout_seconds: float = 3.0,
):
    """연동 정보는 호출자 세션으로 즉시 확정하고, 전송만 별도 스레드로 넘긴다.

    요청 처리 경로에서 유실되면 안 되는 알림(계정 잠금 등)에 쓴다. 동기 발송은 재시도까지
    포함하면 요청 스레드를 수 초간 붙잡아, 잠금을 반복 유발하는 방식으로 워커를 고갈시킬 수
    있다. 반대로 FastAPI BackgroundTasks는 이 용도에 쓸 수 없다 - 엔드포인트가 정상 반환할
    때만 응답에 background가 붙으므로, raise HTTPException으로 끝나는 분기(로그인 실패)에서는
    태스크가 아예 실행되지 않아 알림이 전량 유실된다.

    chat_id를 여기서 미리 확정하는 것이 핵심이다. 전송 스레드에 db를 넘기면 요청이 끝난 뒤
    닫힌 세션을 쓰게 되고, 넘기지 않으면 스레드가 기본 DB를 조회해 격리 DB에서 호출해도 실제
    사용자에게 메시지가 나간다.

    반환값은 전송 Future이며 대상이 없으면 None이다. 호출자는 기다릴 필요가 없고,
    테스트는 Future로 완료를 결정론적으로 대기할 수 있다.
    """
    chat_id = resolve_target_chat_id(user_id, db=db)
    if not chat_id:
        return None

    return _get_alert_executor().submit(
        send_to_chat_sync,
        chat_id,
        text,
        parse_mode=parse_mode,
        attempts=attempts,
        backoff_seconds=backoff_seconds,
        timeout_seconds=timeout_seconds,
        log_label=f"Alert User {user_id}",
    )

async def _send_message_async_coro(user_id: int, text: str, db=None, parse_mode: str | None = "Markdown") -> bool:
    """
    비동기식 텔레그램 메시지 전송 코루틴 (httpx.AsyncClient 활용)

    db·parse_mode 계약은 send_message_sync와 동일하다.
    """
    owns_session = db is None
    session = db or SessionLocal()
    try:
        db_settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not db_settings or not db_settings.telegram_enabled:
            return False
        token = settings.TELEGRAM_BOT_TOKEN
        chat_id = db_settings.telegram_chat_id
    finally:
        if owns_session:
            session.close()

    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, timeout=5)
            if res.status_code != 200:
                logger.warning(f"[Telegram User {user_id}] Failed to send async message. Code: {res.status_code}, Res: {res.text}")
            return res.status_code == 200
    except Exception as e:
        logger.exception(f"[Telegram User {user_id}] Async send exception")
        return False

def send_message_async(user_id: int, text: str, parse_mode: str | None = "Markdown"):
    """
    비동기식 텔레그램 메시지 전송 (Non-blocking asyncio Task 스케줄링)

    여기에는 의도적으로 db 인자를 두지 않는다. 발송이 호출자보다 늦게 실행되는 fire-and-forget
    이므로 요청 스코프 세션을 넘기면 이미 닫힌 세션을 쓰게 된다. 세션을 재사용해야 하는 호출자는
    _send_message_async_coro를 직접 await 하거나 send_message_sync를 쓴다.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send_message_async_coro(user_id, text, parse_mode=parse_mode))
    except RuntimeError:
        # 이벤트 루프가 없는 동기식 백그라운드 스레드인 경우 안전하게 동기식 발송으로 대체
        send_message_sync(user_id, text, parse_mode=parse_mode)

def _send_direct_message(chat_id: str, text: str, parse_mode: str | None = "Markdown") -> bool:
    """
    유저 매핑 전 /start 안내 등 챗 ID만 알 때 다이렉트로 메시지를 전송하는 헬퍼

    parse_mode 계약은 send_message_sync와 같다. 현재 이 함수로 나가는 메시지는 서식이 균형
    잡힌 정적 템플릿 3종이고 유일한 동적 값(link_success의 username)은 정제해서 넣지만,
    새 동적 메시지를 추가할 때 서식을 끌 수 있도록 하드코딩을 파라미터로 뺐다.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        with httpx.Client() as client:
            res = client.post(url, json=payload, timeout=5.0)
            return res.status_code == 200
    except Exception as e:
        logger.exception(f"[TelegramBot] Direct send exception to {chat_id}")
        return False

def _poll_global_updates_loop():
    """
    전역 단일 공식 봇 토큰을 이용한 롱폴링(Long-Polling) 데몬.
    (💡 httpx.Client 커넥션 풀을 루프 전체에서 공유하여 Keep-Alive 및 성능 대폭 상승)
    """
    logger.info("[TelegramBot] Global polling daemon started.")
    token = settings.TELEGRAM_BOT_TOKEN
    offset = 0

    with httpx.Client() as client:
        while _global_stop_event and not _global_stop_event.is_set():
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            try:
                params = {"offset": offset, "timeout": 5}
                res = client.get(url, params=params, timeout=10.0)
                if res.status_code == 200:
                    data = res.json()
                    if data.get("ok"):
                        results = data.get("result", [])
                        for update in results:
                            update_id = update.get("update_id")
                            offset = update_id + 1

                            message = update.get("message", {})
                            text = message.get("text", "").strip()
                            chat = message.get("chat", {})
                            msg_chat_id = str(chat.get("id"))
                            tg_lang_code = message.get("from", {}).get("language_code")

                            if not text:
                                continue

                            # ThreadPoolExecutor에 메시지 처리 위임하여 롱폴링 루프 및 메인 스레드 대기 방지
                            if _telegram_executor:
                                _telegram_executor.submit(_process_global_message, msg_chat_id, text, tg_lang_code)
                            else:
                                _process_global_message(msg_chat_id, text, tg_lang_code)
                elif res.status_code == 401 or res.status_code == 404:
                    logger.warning(f"[TelegramBot] Token invalid or unauthorized ({res.status_code}). Polling thread sleeping 30s...")
                    _global_stop_event.wait(30)
                else:
                    _global_stop_event.wait(5)
            except Exception as e:
                logger.exception("[TelegramBot] Polling loop error")
                if _global_stop_event:
                    _global_stop_event.wait(5)

    logger.info("[TelegramBot] Global polling daemon stopped.")

def _process_global_message(msg_chat_id: str, text: str, tg_lang_code: str | None = None):
    """
    글로벌 봇으로 들어온 메시지를 분석하여 알맞은 유저의 명령으로 분기하거나 자동 연동을 수행합니다.
    """
    parts = text.split()
    if not parts:
        return
    cmd = parts[0].lower()

    command_user_id = None
    direct_message = None
    db = SessionLocal()
    try:
        # 1. 딥링크 연동 시도 (/start <1회용 링크 토큰>) 우선 처리.
        #    ⚠️ 과거에는 여기서 사용자명을 그대로 받아 연동했다. 전역 봇은 아무 텔레그램
        #    사용자의 메시지나 수신하므로, 그 구조에서는 피해자 사용자명만 알면 chat_id를
        #    남의 계정에 묶어 포트폴리오 조회와 자동매매 기동/정지를 탈취할 수 있었다.
        #    사용자명은 비밀이 아니므로 소유권 증명이 되지 못한다 — 서버 발급 토큰만 받는다.
        if cmd == "/start" and len(parts) > 1:
            u_settings = consume_telegram_link_token(db, parts[1])
            if not u_settings:
                db.commit()  # 실패해도 소비된 토큰 폐기는 확정한다.
                direct_message = I18n.get_msg(
                    _lang_from_telegram_code(tg_lang_code), "telegram.link_invalid_token"
                )
                logger.warning(
                    "[TelegramBot] Rejected link attempt with invalid/expired token from chat_id=%s",
                    msg_chat_id,
                )
                return

            linked_user_id = u_settings.user_id

            # 동일한 chat_id를 가지고 있던 다른 계정들의 연동 해제 및 정리 (1:1 매핑 보장)
            existing_others = db.query(UserSettings).filter(
                UserSettings.telegram_chat_id == msg_chat_id,
                UserSettings.user_id != linked_user_id
            ).all()
            for other_setting in existing_others:
                other_setting.telegram_chat_id = ""
                other_setting.telegram_enabled = False

            u_settings.telegram_chat_id = msg_chat_id
            u_settings.telegram_enabled = True
            db.commit()

            # 방금 연동된 계정이라 UserSettings.language를 SSOT로 사용한다.
            from app.core.models import User
            linked_user = db.query(User).filter(User.id == linked_user_id).first()
            # 템플릿이 백틱으로 감싸므로 밑줄은 안전하지만, 값 안의 백틱은 코드 스팬을 탈출한다.
            # username 검증은 길이(3~50)만 보고 문자 종류를 제한하지 않으므로 값을 정제한다.
            direct_message = I18n.get_msg(
                resolve_user_language(db, linked_user_id),
                "telegram.link_success",
                username=sanitize_markdown_value(linked_user.username) if linked_user else "",
            )
            logger.info(f"[TelegramBot] Successfully linked Chat ID {msg_chat_id} to user_id={linked_user_id}")
            return

        # 2. 일반 명령어 수신 시: 텔레그램 연동이 활성화(telegram_enabled=True)된 유저만 조회
        db_settings = db.query(UserSettings).filter(
            UserSettings.telegram_chat_id == msg_chat_id,
            UserSettings.telegram_enabled == True
        ).first()

        if not db_settings:
            # 미연동 또는 비활성화 유저의 명령어 수신 시 안내 (user 매핑 전이라 텔레그램 언어 사용)
            direct_message = I18n.get_msg(_lang_from_telegram_code(tg_lang_code), "telegram.not_linked_guide")
            return

        command_user_id = db_settings.user_id

    except Exception as e:
        logger.exception("[TelegramBot] Global message processing error")
    finally:
        db.close()
        if direct_message is not None:
            _send_direct_message(msg_chat_id, direct_message)

    if command_user_id is not None:
        _process_command(command_user_id, text)

def _process_command(user_id: int, text: str):
    """
    수신한 텔레그램 명령어를 분석하고 사용자 레코드 기반으로 처리합니다.
    """
    parts = text.split()
    if not parts:
        return
    cmd = parts[0].lower()

    db = SessionLocal()
    lang = "ko"

    def close_db():
        nonlocal db
        if db is not None:
            db.close()
            db = None

    def send_reply(message: str, parse_mode: str | None = "Markdown") -> bool:
        close_db()
        return send_message_sync(user_id, message, parse_mode=parse_mode)

    try:
        db_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not db_settings:
            return

        lang = resolve_user_language(db, user_id)

        if cmd == "/start":
            send_reply(I18n.get_msg(lang, "telegram.help"))

        elif cmd == "/run":
            if db_settings.is_running:
                send_reply(I18n.get_msg(lang, "telegram.already_running"))
            else:
                from app.bot.order_reconciler import has_unresolved_orders

                if has_unresolved_orders(db, user_id):
                    send_reply(I18n.get_msg(lang, "telegram.cannot_start_unresolved"))
                else:
                    db_settings.is_running = True
                    db.commit()
                    send_reply(I18n.get_msg(lang, "telegram.loop_started"))

        elif cmd == "/stop":
            if not db_settings.is_running:
                db.commit()
                send_reply(I18n.get_msg(lang, "telegram.already_stopped"))
            else:
                db_settings.is_running = False
                db.commit()
                send_reply(I18n.get_msg(lang, "telegram.loop_stopped"))

        elif cmd == "/status":
            mode = db_settings.trade_mode
            broker_name = db_settings.broker_provider or (
                I18n.get_msg(lang, "telegram.status.broker_na_simulated") if mode == "SIMULATED"
                else I18n.get_msg(lang, "telegram.status.broker_none")
            )

            # 사용자 맞춤형 브로커 인스턴스 획득
            broker = get_broker_client(db_settings)
            status_text = I18n.get_msg(lang, "telegram.status.running" if db_settings.is_running else "telegram.status.stopped")
            close_db()
            fallback_warning = ""
            try:
                balance = broker.get_account_balance()
                total_asset = balance.get("total_asset", 0)
                cash_balance = balance.get("cash_balance", 0)
                stock_balance = balance.get("stock_balance", 0)
                profit_rate = balance.get("profit_rate", 0.0)
            except Exception as e:
                logger.exception(f"[TelegramBot User {user_id}] Account balance fetch failed. Using fallback snapshot.")
                # 데이터베이스 내 가장 최신의 자산 스냅샷 정보를 조회하여 대체 제공
                from app.core.equity_repository import get_latest_equity_snapshot
                snapshot_db = SessionLocal()
                try:
                    # 현재 trade_mode의 스냅샷만 조회 (모드 전환 시 다른 모드 잔고가 섞이는 버그 방지)
                    snapshot = get_latest_equity_snapshot(snapshot_db, user_id, mode)
                finally:
                    snapshot_db.close()
                if snapshot:
                    total_asset = snapshot.total_asset
                    cash_balance = snapshot.cash_balance or 0.0
                    stock_balance = snapshot.stock_balance or 0.0
                    profit_rate = snapshot.profit_rate or 0.0
                    fallback_warning = I18n.get_msg(lang, "telegram.status.fallback_snapshot")
                else:
                    total_asset, cash_balance, stock_balance, profit_rate = 0.0, 0.0, 0.0, 0.0
                    fallback_warning = I18n.get_msg(lang, "telegram.status.fallback_no_snapshot")

            fx_rate = FXRateCache.get_rate()
            holdings_db = SessionLocal()
            try:
                holdings = holdings_db.query(Holding).filter(Holding.user_id == user_id).all()
            finally:
                holdings_db.close()

            msg = I18n.get_msg(
                lang,
                "telegram.status.header",
                status_text=status_text,
                mode=mode,
                broker_name=broker_name,
                fx_rate=fx_rate,
                total_asset=total_asset,
                total_asset_usd=total_asset / fx_rate,
                cash_balance=cash_balance,
                stock_balance=stock_balance,
                profit_rate=profit_rate,
                holdings_count=len(holdings),
            )
            if fallback_warning:
                msg = f"{fallback_warning}\n\n" + msg

            if not holdings:
                msg += I18n.get_msg(lang, "telegram.status.no_holdings")
            else:
                for h in holdings:
                    # 티커·종목명은 외부(브로커·시세) 유래 값이라 Markdown 서식 문자를 제거한다.
                    # 템플릿이 *{ticker}* ({ticker_name})로 감싸므로 값에 밑줄·별표가 있으면
                    # 마크업이 어긋나 종목명이 훼손되거나 상태 조회 응답 전체가 발송 실패한다.
                    msg += I18n.get_msg(
                        lang,
                        "telegram.status.holding_line",
                        ticker=sanitize_markdown_value(h.ticker),
                        ticker_name=sanitize_markdown_value(h.ticker_name),
                        quantity=h.quantity,
                        avg_price=h.avg_price,
                    )
            send_reply(msg)

        else:
            send_reply(I18n.get_msg(lang, "telegram.unknown_command"))

    except Exception as e:
        logger.exception(f"[TelegramBot User {user_id}] Command execution error")
        if db is not None:
            try:
                db.rollback()  # 💡 예외 발생 시 트랜잭션 롤백 및 커넥션 오염 방지
            except Exception:
                pass
        # 예외 문자열은 자유 서식 텍스트이고 컬럼명·경로 탓에 밑줄을 흔히 포함한다. 값을 깎으면
        # 원인 파악이 어려워지므로 서식을 끄고 원문 그대로 전달한다(템플릿의 볼드도 함께 제거함).
        send_reply(
            I18n.get_msg(lang, "telegram.command_error", error=str(e)),
            parse_mode=None,
        )
    finally:
        close_db()

def send_daily_report_to_all_users_sync() -> dict:
    """
    장 마감 후 모든 활성 사용자에게 당일 매매 성적을 텔레그램으로 발송합니다.
    """
    from datetime import UTC, datetime, timedelta
    from app.core.models import TradeLog

    db = SessionLocal()
    sent_count = 0
    total_enabled_users = 0
    try:
        # 최근 24시간 거래 내역
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)

        users = db.query(UserSettings).filter(UserSettings.telegram_enabled == True).all()
        total_enabled_users = len(users)
        
        for u in users:
            sells = db.query(TradeLog).filter(
                TradeLog.user_id == u.user_id,
                TradeLog.trade_type == "SELL",
                TradeLog.executed_at >= cutoff,
                TradeLog.realized_pnl.isnot(None)
            ).all()

            if not sells:
                continue # 거래가 없으면 스킵

            total_trades = len(sells)
            win_trades = sum(1 for s in sells if float(s.realized_pnl) > 0)
            total_pnl = sum(float(s.realized_pnl) for s in sells)
            win_rate = (win_trades / total_trades) * 100

            msg = I18n.get_msg(
                resolve_user_language(db, u.user_id),
                "telegram.daily_report",
                total_trades=total_trades,
                win_trades=win_trades,
                win_rate=win_rate,
                total_pnl=total_pnl,
            )

            send_message_sync(u.user_id, msg)
            sent_count += 1
            
        return {"total_enabled_users": total_enabled_users, "sent_count": sent_count}
    except Exception as e:
        logger.exception("[TelegramBot] Error sending daily report")
        return {"total_enabled_users": 0, "sent_count": 0, "error": str(e)}
    finally:
        db.close()

def send_daily_report_to_user_sync(user_id: int):
    """
    특정 사용자에게 당일 매매 성적을 텔레그램으로 발송합니다.
    """
    from datetime import UTC, datetime, timedelta
    from app.core.models import TradeLog

    db = SessionLocal()
    try:
        # 최근 24시간 거래 내역
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
        sells = db.query(TradeLog).filter(
            TradeLog.user_id == user_id,
            TradeLog.trade_type == "SELL",
            TradeLog.executed_at >= cutoff,
            TradeLog.realized_pnl.isnot(None)
        ).all()

        lang = resolve_user_language(db, user_id)

        if not sells:
            send_message_sync(user_id, I18n.get_msg(lang, "telegram.no_recent_sells"))
            return

        total_trades = len(sells)
        win_trades = sum(1 for s in sells if float(s.realized_pnl) > 0)
        total_pnl = sum(float(s.realized_pnl) for s in sells)
        win_rate = (win_trades / total_trades) * 100

        msg = I18n.get_msg(
            lang,
            "telegram.daily_report_manual",
            total_trades=total_trades,
            win_trades=win_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
        )

        send_message_sync(user_id, msg)
    except Exception as e:
        logger.exception(f"[TelegramBot] Error sending daily report to user {user_id}")
    finally:
        db.close()

def start_telegram_bot():
    """
    서버 구동 시 단일 글로벌 텔레그램 봇 폴링 스레드를 기동합니다.
    """
    global _global_poll_thread, _global_stop_event, _telegram_executor

    token = settings.TELEGRAM_BOT_TOKEN
    if not token or token == "your_telegram_bot_token_here":
        logger.warning("[TelegramBot] Global TELEGRAM_BOT_TOKEN is not configured or is default. Polling skipped.")
        return

    if _global_poll_thread and _global_poll_thread.is_alive():
        return

    _telegram_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="TelegramExecutor")
    _global_stop_event = threading.Event()
    _global_poll_thread = threading.Thread(
        target=_poll_global_updates_loop,
        name="TelegramGlobalPollThread",
        daemon=True
    )
    _global_poll_thread.start()
    logger.info("[TelegramBot] Global Polling thread started successfully.")

def stop_telegram_bot():
    """
    서버 종료 시 가동 중인 글로벌 텔레그램 스레드를 정지시킵니다.
    """
    global _global_poll_thread, _global_stop_event, _telegram_executor
    if _global_stop_event:
        _global_stop_event.set()
    if _global_poll_thread and _global_poll_thread.is_alive():
        _global_poll_thread.join(timeout=3)
        logger.info("[TelegramBot] Global Polling thread stopped successfully.")
    if _telegram_executor:
        _telegram_executor.shutdown(wait=False)
        _telegram_executor = None
