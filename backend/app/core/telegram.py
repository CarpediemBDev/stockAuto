import threading
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from app.core.config import settings
from app.bot.broker_factory import get_broker_client
from app.core.database import SessionLocal
from app.core.models import UserSettings, Holding
from app.bot.fx_cache import FXRateCache

# 비동기 전송을 위한 백그라운드 스레드풀
executor = ThreadPoolExecutor(max_workers=10)

# 사용자별 텔레그램 봇 스레드 레지스트리
_poll_threads = {}  # {user_id: threading.Thread}
_stop_events = {}   # {user_id: threading.Event}

def send_message_sync(user_id: int, text: str) -> bool:
    """
    특정 사용자의 텔레그램으로 메시지 동기 전송
    """
    db = SessionLocal()
    try:
        user_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not user_settings or not user_settings.telegram_enabled:
            return False
        token = user_settings.telegram_bot_token
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
            print(f"[Telegram User {user_id}] Failed to send message. Code: {res.status_code}, Res: {res.text}")
        return res.status_code == 200
    except Exception as e:
        print(f"[Telegram User {user_id}] Send exception: {e}")
        return False

def send_message_async(user_id: int, text: str):
    """
    비동기식 텔레그램 메시지 전송.
    """
    executor.submit(send_message_sync, user_id, text)

def _poll_updates_loop_for_user(user_id: int, token: str, chat_id: str):
    """
    개별 사용자별 메시지 수신을 위한 백그라운드 롱폴링(Long-Polling) 데몬.
    """
    print(f"[TelegramBot User {user_id}] Polling daemon started.")
    offset = 0
    stop_event = _stop_events.get(user_id)
    
    while stop_event and not stop_event.is_set():
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
                        msg_chat_id = chat.get("id")
                        
                        if not text:
                            continue
                            
                        # 🔐 보안 검증: 해당 사용자로 설정된 Chat ID와 일치할 때만 명령 접수
                        if str(msg_chat_id) != str(chat_id):
                            print(f"[TelegramBot User {user_id}] Blocked unauthorized chat message from {msg_chat_id}: {text}")
                            continue
                            
                        _process_command(user_id, text)
            elif res.status_code == 404:
                print(f"[TelegramBot User {user_id}] 404 Error detected. Token might be invalid. Sleeping 10s...")
                stop_event.wait(10)
            else:
                stop_event.wait(5)
        except Exception as e:
            print(f"[TelegramBot User {user_id}] Polling loop error: {e}")
            if stop_event:
                stop_event.wait(5)
            
    print(f"[TelegramBot User {user_id}] Polling daemon stopped.")

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
                print(f"[TelegramBot User {user_id}] Account balance fetch failed: {e}")
                
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
        print(f"[TelegramBot User {user_id}] Command execution error: {e}")
        send_message_sync(user_id, f"⚠️ *명령어 실행 중 오류 발생:* {str(e)}")
    finally:
        db.close()

def start_telegram_bot_for_user(user_id: int, token: str, chat_id: str):
    """
    특정 사용자의 텔레그램 봇 데몬 시동
    """
    global _poll_threads, _stop_events
    
    if not token or not chat_id:
        return
        
    if user_id in _poll_threads and _poll_threads[user_id].is_alive():
        return
        
    stop_event = threading.Event()
    _stop_events[user_id] = stop_event
    
    thread = threading.Thread(
        target=_poll_updates_loop_for_user,
        args=(user_id, token, chat_id),
        name=f"TelegramPollThread-{user_id}",
        daemon=True
    )
    _poll_threads[user_id] = thread
    thread.start()
    print(f"[TelegramBot User {user_id}] Polling thread started successfully.")

def stop_telegram_bot_for_user(user_id: int):
    """
    특정 사용자의 텔레그램 봇 데몬 중지
    """
    global _poll_threads, _stop_events
    stop_event = _stop_events.get(user_id)
    thread = _poll_threads.get(user_id)
    
    if stop_event:
        stop_event.set()
    if thread and thread.is_alive():
        thread.join(timeout=3)
        print(f"[TelegramBot User {user_id}] Polling thread stopped successfully.")
        
    _poll_events_pop_result = _stop_events.pop(user_id, None)
    _poll_threads_pop_result = _poll_threads.pop(user_id, None)

def start_telegram_bot():
    """
    서버 구동 시 모든 활성 유저의 텔레그램 봇을 기동합니다.
    """
    db = SessionLocal()
    try:
        active_settings = db.query(UserSettings).filter(UserSettings.telegram_enabled == True).all()
        for s in active_settings:
            if s.telegram_bot_token and s.telegram_chat_id:
                start_telegram_bot_for_user(s.user_id, s.telegram_bot_token, s.telegram_chat_id)
    except Exception as e:
        print(f"[TelegramBot Registry] Startup failed: {e}")
    finally:
        db.close()

def stop_telegram_bot():
    """
    서버 종료 시 모든 가동 중인 텔레그램 스레드를 정지시킵니다.
    """
    for user_id in list(_poll_threads.keys()):
        stop_telegram_bot_for_user(user_id)
