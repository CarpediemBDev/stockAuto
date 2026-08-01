import asyncio
import threading
import httpx
from concurrent.futures import ThreadPoolExecutor
from app.core.config import settings
from app.brokers.broker_factory import get_broker_client
from app.core.database import SessionLocal
from app.core.models import UserSettings, Holding
from app.bot.fx_cache import FXRateCache
from app.core.logging import logger
from app.core.i18n import I18n, resolve_user_language


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

def send_message_sync(user_id: int, text: str) -> bool:
    """
    특정 사용자의 텔레그램으로 메시지 동기 전송 (글로벌 봇 토큰 활용)
    """
    db = SessionLocal()
    try:
        db_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not db_settings or not db_settings.telegram_enabled:
            return False
        token = settings.TELEGRAM_BOT_TOKEN
        chat_id = db_settings.telegram_chat_id
    finally:
        db.close()

    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        with httpx.Client() as client:
            res = client.post(url, json=payload, timeout=5.0)
            if res.status_code != 200:
                logger.warning(f"[Telegram User {user_id}] Failed to send message. Code: {res.status_code}, Res: {res.text}")
            return res.status_code == 200
    except Exception as e:
        logger.exception(f"[Telegram User {user_id}] Send exception")
        return False

async def _send_message_async_coro(user_id: int, text: str) -> bool:
    """
    비동기식 텔레그램 메시지 전송 코루틴 (httpx.AsyncClient 활용)
    """
    db = SessionLocal()
    try:
        db_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not db_settings or not db_settings.telegram_enabled:
            return False
        token = settings.TELEGRAM_BOT_TOKEN
        chat_id = db_settings.telegram_chat_id
    finally:
        db.close()

    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, timeout=5)
            if res.status_code != 200:
                logger.warning(f"[Telegram User {user_id}] Failed to send async message. Code: {res.status_code}, Res: {res.text}")
            return res.status_code == 200
    except Exception as e:
        logger.exception(f"[Telegram User {user_id}] Async send exception")
        return False

def send_message_async(user_id: int, text: str):
    """
    비동기식 텔레그램 메시지 전송 (Non-blocking asyncio Task 스케줄링)
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send_message_async_coro(user_id, text))
    except RuntimeError:
        # 이벤트 루프가 없는 동기식 백그라운드 스레드인 경우 안전하게 동기식 발송으로 대체
        send_message_sync(user_id, text)

def _send_direct_message(chat_id: str, text: str) -> bool:
    """
    유저 매핑 전 /start 안내 등 챗 ID만 알 때 다이렉트로 메시지를 전송하는 헬퍼
    """
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
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
        # 1. 딥링크 연동 시도 (/start username) 우선 처리
        if cmd == "/start" and len(parts) > 1:
            auth_username = parts[1].strip()
            from app.core.models import User
            user = db.query(User).filter(User.username == auth_username).first()
            if user:
                # 동일한 chat_id를 가지고 있던 다른 계정들의 연동 해제 및 정리 (1:1 매핑 보장)
                existing_others = db.query(UserSettings).filter(
                    UserSettings.telegram_chat_id == msg_chat_id,
                    UserSettings.user_id != user.id
                ).all()
                for other_setting in existing_others:
                    other_setting.telegram_chat_id = ""
                    other_setting.telegram_enabled = False

                u_settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
                if not u_settings:
                    u_settings = UserSettings(user_id=user.id)
                    db.add(u_settings)

                u_settings.telegram_chat_id = msg_chat_id
                u_settings.telegram_enabled = True
                db.commit()

                # 방금 연동된 계정이라 UserSettings.language를 SSOT로 사용한다.
                direct_message = I18n.get_msg(
                    resolve_user_language(db, user.id),
                    "telegram.link_success",
                    username=user.username,
                )
                logger.info(f"[TelegramBot] Successfully linked Chat ID {msg_chat_id} to User: {user.username}")
            else:
                direct_message = I18n.get_msg(_lang_from_telegram_code(tg_lang_code), "telegram.link_user_not_found")
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

    def send_reply(message: str) -> bool:
        close_db()
        return send_message_sync(user_id, message)

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
                    msg += I18n.get_msg(
                        lang,
                        "telegram.status.holding_line",
                        ticker=h.ticker,
                        ticker_name=h.ticker_name,
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
        send_reply(I18n.get_msg(lang, "telegram.command_error", error=str(e)))
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
