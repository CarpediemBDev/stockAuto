import threading
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from app.core.config import settings
from app.bot.broker_factory import get_broker_client
from app.core.database import SessionLocal
from app.core.models import UserSettings, Holding
from app.bot.fx_cache import FXRateCache
from app.core.logging import logger

# 비동기 전송을 위한 백그라운드 스레드풀
executor = ThreadPoolExecutor(max_workers=10)

# 사용자별 텔레그램 봇 스레드 레지스트리 (하위 호환용)
_poll_threads = {}  # [Deprecated]
_stop_events = {}   # [Deprecated]

# 글로벌 텔레그램 봇 단일 스레드 제어 변수
_global_poll_thread = None
_global_stop_event = None

def send_message_sync(user_id: int, text: str) -> bool:
    """
    특정 사용자의 텔레그램으로 메시지 동기 전송 (글로벌 봇 토큰 활용)
    """
    db = SessionLocal()
    try:
        user_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not user_settings or not user_settings.telegram_enabled:
            return False
        token = settings.TELEGRAM_BOT_TOKEN
        chat_id = user_settings.telegram_chat_id
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
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code != 200:
            logger.warning(f"[Telegram User {user_id}] Failed to send message. Code: {res.status_code}, Res: {res.text}")
        return res.status_code == 200
    except Exception as e:
        logger.exception(f"[Telegram User {user_id}] Send exception")
        return False

def send_message_async(user_id: int, text: str):
    """
    비동기식 텔레그램 메시지 전송.
    """
    executor.submit(send_message_sync, user_id, text)

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
        res = requests.post(url, json=payload, timeout=5)
        return res.status_code == 200
    except Exception as e:
        logger.exception(f"[TelegramBot] Direct send exception to {chat_id}")
        return False

def _poll_global_updates_loop():
    """
    전역 단일 공식 봇 토큰을 이용한 롱폴링(Long-Polling) 데몬.
    """
    logger.info("[TelegramBot] Global polling daemon started.")
    token = settings.TELEGRAM_BOT_TOKEN
    offset = 0
    
    while _global_stop_event and not _global_stop_event.is_set():
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        try:
            params = {"offset": offset, "timeout": 5}
            res = requests.get(url, params=params, timeout=10)
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
        user_settings = db.query(UserSettings).filter(UserSettings.telegram_chat_id == msg_chat_id).first()
        
        if not user_settings:
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
        if not user_settings.telegram_enabled:
            _send_direct_message(msg_chat_id, "⚠️ 텔레그램 알림 연동이 비활성화 상태입니다. 웹 페이지의 개인 투자 설정에서 활성화해 주세요.")
            return
            
        _process_command(user_settings.user_id, text)
        
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
        user_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not user_settings:
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
            if user_settings.is_running:
                send_message_sync(user_id, "⚠️ *이미 자동매매 루프가 가동 중입니다.*")
            else:
                user_settings.is_running = True
                db.commit()
                send_message_sync(user_id, "🟢 *자율 트레이딩 자동매매 루프를 가동했습니다.*")
                
        elif cmd == "/stop":
            if not user_settings.is_running:
                send_message_sync(user_id, "⚠️ *이미 자동매매 루프가 정지되어 있습니다.*")
            else:
                user_settings.is_running = False
                db.commit()
                send_message_sync(user_id, "🔴 *자율 트레이딩 자동매매 루프를 정지했습니다.*")
                
        elif cmd == "/status":
            mode = user_settings.trade_mode
            broker_name = user_settings.broker_provider
            
            # 사용자 맞춤형 브로커 인스턴스 획득
            broker = get_broker_client(user_settings)
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
            status_text = "🟢 *가동 중*" if user_settings.is_running else "🔴 *정지됨*"
            
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

def start_telegram_bot_for_user(user_id: int, token: str, chat_id: str):
    """
    [Deprecated] 이전 다중 봇 기반의 개별 시동 함수 (하위 호환성 유지용)
    """
    pass

def stop_telegram_bot_for_user(user_id: int):
    """
    [Deprecated] 이전 다중 봇 기반의 개별 중지 함수 (하위 호환성 유지용)
    """
    pass

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
