import asyncio
import threading
import httpx
from app.core.config import settings
from app.bot.broker_factory import get_broker_client
from app.core.database import SessionLocal
from app.core.models import UserSettings, Holding
from app.bot.fx_cache import FXRateCache
from app.core.logging import logger

# 글로벌 텔레그램 봇 단일 스레드 제어 변수
_global_poll_thread = None
_global_stop_event = None

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

                            if not text:
                                continue

                            _process_global_message(msg_chat_id, text)
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

def _process_global_message(msg_chat_id: str, text: str):
    """
    글로벌 봇으로 들어온 메시지를 분석하여 알맞은 유저의 명령으로 분기하거나 자동 연동을 수행합니다.
    """
    parts = text.split()
    if not parts:
        return
    cmd = parts[0].lower()

    db = SessionLocal()
    try:
        # 1. 이미 이 챗 ID를 사용하는 유저가 있는지 조회
        db_settings = db.query(UserSettings).filter(UserSettings.telegram_chat_id == msg_chat_id).first()

        if not db_settings:
            # 미연동 유저의 딥링크 가입 시도 (/start username)
            if cmd == "/start" and len(parts) > 1:
                auth_username = parts[1].strip()
                from app.core.models import User
                user = db.query(User).filter(User.username == auth_username).first()
                if user:
                    u_settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
                    if not u_settings:
                        u_settings = UserSettings(user_id=user.id)
                        db.add(u_settings)

                    u_settings.telegram_chat_id = msg_chat_id
                    u_settings.telegram_enabled = True
                    db.commit()

                    msg = (
                        f"🎉 *연동 성공!*\n\n"
                        f"`{user.username}`님 계정과 텔레그램 연동이 정상 완료되었습니다.\n"
                        f"이제 시스템 자동매매 매수/매도 알림이 실시간으로 발송됩니다.\n\n"
                        f"🤖 *사용 가능 원격 명령어:*\n"
                        f"• `/status` - 현재 시스템 동작 모드 및 포트폴리오 조회\n"
                        f"• `/run` - 자율 트레이딩 자동매매 루프 가동\n"
                        f"• `/stop` - 자율 트레이딩 자동매매 루프 정지"
                    )
                    _send_direct_message(msg_chat_id, msg)
                    logger.info(f"[TelegramBot] Successfully linked Chat ID {msg_chat_id} to User: {user.username}")
                else:
                    _send_direct_message(msg_chat_id, "⚠️ 존재하지 않는 사용자명입니다. 웹의 연동 시작 링크를 통해 다시 접속해 주세요.")
            else:
                # 일반적인 /start 호출 등 가입되지 않은 경우 안내
                msg = (
                    "👋 *안녕하세요! StockAuto 트레이딩 브릿지입니다.*\n\n"
                    "아직 본 계정의 텔레그램 연동이 완료되지 않았습니다.\n"
                    "우리 주식 자동매매 웹 페이지의 **개인 투자 설정 ➔ Telegram Bridge** 탭에서 제공하는 "
                    "**[🔗 텔레그램 연동 시작]** 버튼을 클릭하여 간편하게 연동을 마무리해 주세요!"
                )
                _send_direct_message(msg_chat_id, msg)
            return

        # 2. 이미 연동된 유저의 경우 활성화 여부(telegram_enabled) 검증
        if not db_settings.telegram_enabled:
            _send_direct_message(msg_chat_id, "⚠️ 텔레그램 알림 연동이 비활성화 상태입니다. 웹 페이지의 개인 투자 설정에서 활성화해 주세요.")
            return

        _process_command(db_settings.user_id, text)

    except Exception as e:
        logger.exception("[TelegramBot] Global message processing error")
    finally:
        db.close()

def _process_command(user_id: int, text: str):
    """
    수신한 텔레그램 명령어를 분석하고 사용자 레코드 기반으로 처리합니다.
    """
    parts = text.split()
    if not parts:
        return
    cmd = parts[0].lower()

    db = SessionLocal()
    try:
        db_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not db_settings:
            return

        if cmd == "/start":
            msg = (
                f"👋 *안녕하세요! StockAuto 트레이딩 브릿지입니다.*\n\n"
                f"사용 가능한 명령어 목록:\n"
                f"• `/status` - 현재 시스템 동작 모드, 계좌 잔고 및 보유 종목 조회\n"
                f"• `/run` - 자율 트레이딩 자동매매 루프 가동\n"
                f"• `/stop` - 자율 트레이딩 자동매매 루프 정지"
            )
            send_message_sync(user_id, msg)

        elif cmd == "/run":
            if db_settings.is_running:
                send_message_sync(user_id, "⚠️ *이미 자동매매 루프가 가동 중입니다.*")
            else:
                from app.bot.order_reconciler import has_unresolved_orders

                if has_unresolved_orders(db, user_id):
                    send_message_sync(
                        user_id,
                        "⚠️ *미해결 증권사 주문이 있어 시작할 수 없습니다.*\n"
                        "자동 재조정이 완료될 때까지 기다려 주세요.",
                    )
                else:
                    db_settings.is_running = True
                    db.commit()
                    send_message_sync(user_id, "🟢 *자율 트레이딩 자동매매 루프를 가동했습니다.*")

        elif cmd == "/stop":
            from app.bot.order_reconciler import disable_auto_resume_for_user

            disable_auto_resume_for_user(db, user_id)
            if not db_settings.is_running:
                db.commit()
                send_message_sync(user_id, "⚠️ *이미 자동매매 루프가 정지되어 있습니다.*")
            else:
                db_settings.is_running = False
                db.commit()
                send_message_sync(user_id, "🔴 *자율 트레이딩 자동매매 루프를 정지했습니다.*")

        elif cmd == "/status":
            mode = db_settings.trade_mode
            broker_name = db_settings.broker_provider or ("N/A (Simulated)" if mode == "SIMULATED" else "None")

            # 사용자 맞춤형 브로커 인스턴스 획득
            broker = get_broker_client(db_settings)
            try:
                balance = broker.get_account_balance()
                total_asset = balance.get("total_asset", 0)
                cash_balance = balance.get("cash_balance", 0)
                stock_balance = balance.get("stock_balance", 0)
                profit_rate = balance.get("profit_rate", 0.0)
            except Exception as e:
                total_asset, cash_balance, stock_balance, profit_rate = 0, 0, 0, 0.0
                logger.exception(f"[TelegramBot User {user_id}] Account balance fetch failed")

            fx_rate = FXRateCache.get_rate()
            holdings = db.query(Holding).filter(Holding.user_id == user_id).all()
            status_text = "🟢 *가동 중*" if db_settings.is_running else "🔴 *정지됨*"

            msg = (
                f"🤖 *StockAuto 실시간 시스템 상태*\n"
                f"───────────────────\n"
                f"• *트레이딩 루프 상태:* {status_text}\n"
                f"• *동작 모드:* `{mode}` (Broker: {broker_name})\n"
                f"• *원/달러 환율:* `1$ = {fx_rate:,.1f}원`\n\n"
                f"📊 *계좌 자산 정보*\n"
                f"• *총 자산:* `₩{total_asset:,.0f}` (약 `${total_asset/fx_rate:,.2f}`)\n"
                f"• *예수금:* `₩{cash_balance:,.0f}`\n"
                f"• *주식 평가액:* `₩{stock_balance:,.0f}`\n"
                f"• *실시간 누적 수익률:* `{profit_rate:+.2f}%`\n\n"
                f"📈 *보유 포트폴리오 (총 {len(holdings)}개)*\n"
            )

            if not holdings:
                msg += "• 보유 중인 해외주식이 없습니다."
            else:
                for h in holdings:
                    msg += (
                        f"• *{h.ticker}* ({h.ticker_name})\n"
                        f"  └ 수량: `{h.quantity}주` | 평단: `${h.avg_price:,.2f}`\n"
                    )
            send_message_sync(user_id, msg)

        else:
            send_message_sync(user_id, "❓ *알 수 없는 명령어입니다.*\n사용 가능한 명령어: `/status`, `/run`, `/stop`")

    except Exception as e:
        logger.exception(f"[TelegramBot User {user_id}] Command execution error")
        send_message_sync(user_id, f"⚠️ *명령어 실행 중 오류 발생:* {str(e)}")
    finally:
        db.close()

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

            msg = (
                f"📊 *[일일 자동매매 마감 리포트]*\n\n"
                f"지난 24시간 동안의 자동매매 정산 결과를 안내해 드립니다.\n"
                f"───────────────────\n"
                f"• *총 매도 횟수:* `{total_trades}회`\n"
                f"• *승리 횟수:* `{win_trades}회`\n"
                f"• *일일 승률:* `{win_rate:.1f}%`\n"
                f"• *일일 실현 수익금:* `${total_pnl:,.2f}`\n"
                f"───────────────────\n"
                f"더 상세한 누적 성적표 및 수익금 우상향 곡선은 웹 대시보드의 **[📊 성적표]** 메뉴에서 직접 확인하실 수 있습니다!"
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
    특정 사용자에게만 당일 매매 성적을 텔레그램으로 발송합니다. (수동 트리거용)
    """
    from datetime import UTC, datetime, timedelta
    from app.core.models import TradeLog

    db = SessionLocal()
    try:
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)

        u = db.query(UserSettings).filter(UserSettings.user_id == user_id, UserSettings.telegram_enabled == True).first()
        if not u:
            return

        sells = db.query(TradeLog).filter(
            TradeLog.user_id == user_id,
            TradeLog.trade_type == "SELL",
            TradeLog.executed_at >= cutoff,
            TradeLog.realized_pnl.isnot(None)
        ).all()

        if not sells:
            send_message_sync(user_id, "⚠️ 최근 24시간 동안 매도(수익 실현) 내역이 없어 리포트를 발송할 수 없습니다.")
            return

        total_trades = len(sells)
        win_trades = sum(1 for s in sells if float(s.realized_pnl) > 0)
        total_pnl = sum(float(s.realized_pnl) for s in sells)
        win_rate = (win_trades / total_trades) * 100

        msg = (
            f"📊 *[일일 매매 리포트 (수동 요청)]*\n\n"
            f"요청하신 지난 24시간 거래 결과를 안내해 드립니다.\n"
            f"───────────────────\n"
            f"• *총 매도 횟수:* `{total_trades}회`\n"
            f"• *승리 횟수:* `{win_trades}회`\n"
            f"• *일일 승률:* `{win_rate:.1f}%`\n"
            f"• *일일 실현 수익금:* `${total_pnl:,.2f}`\n"
            f"───────────────────\n"
            f"더 상세한 누적 성적표 및 수익금 우상향 곡선은 웹 대시보드의 **[📊 성적표]** 메뉴에서 직접 확인하실 수 있습니다!"
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
    global _global_poll_thread, _global_stop_event

    token = settings.TELEGRAM_BOT_TOKEN
    if not token or token == "your_telegram_bot_token_here":
        logger.warning("[TelegramBot] Global TELEGRAM_BOT_TOKEN is not configured or is default. Polling skipped.")
        return

    if _global_poll_thread and _global_poll_thread.is_alive():
        return

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
    global _global_poll_thread, _global_stop_event
    if _global_stop_event:
        _global_stop_event.set()
    if _global_poll_thread and _global_poll_thread.is_alive():
        _global_poll_thread.join(timeout=3)
        logger.info("[TelegramBot] Global Polling thread stopped successfully.")
