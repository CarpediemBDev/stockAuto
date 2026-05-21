import threading
import time
import requests
import asyncio
from concurrent.futures import ThreadPoolExecutor
from app.core.config import settings
from app.bot.broker_factory import get_broker_client
from app.core.database import SessionLocal
from app.core.models import BotStatus, Holding
from app.bot.fx_cache import FXRateCache

# 비동기 전송을 위한 백그라운드 스레드풀
executor = ThreadPoolExecutor(max_workers=5)

_stop_event = threading.Event()
_poll_thread = None

def send_message_sync(text: str) -> bool:
    """
    텔레그램 메시지 동기 전송 (보안 및 차단 방지 목적)
    """
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
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
            print(f"[Telegram] Failed to send message. Code: {res.status_code}, Res: {res.text}")
        return res.status_code == 200
    except Exception as e:
        print(f"[Telegram] Send exception: {e}")
        return False

def send_message_async(text: str):
    """
    비동기식 텔레그램 메시지 전송.
    스레드풀에 작업을 던져 메인 자동매매 루프가 API 지연으로 멈추는 현상을 방지합니다.
    """
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return
    executor.submit(send_message_sync, text)

def _poll_updates_loop():
    """
    양방향 원격 제어 메시지 수신을 위한 백그라운드 롱폴링(Long-Polling) 데몬.
    """
    print("[TelegramBot] Polling daemon started.")
    offset = 0
    
    while not _stop_event.is_set():
        token = settings.TELEGRAM_BOT_TOKEN
        chat_id = settings.TELEGRAM_CHAT_ID
        
        # 설정이 유효하지 않으면 5초간 대기 후 다시 확인
        if not token or not chat_id:
            _stop_event.wait(5)
            continue
            
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
                            
                        # 🔐 보안 검증: 환경설정에 등록된 Chat ID를 가진 관리자의 명령만 접수
                        if str(msg_chat_id) != str(chat_id):
                            print(f"[TelegramBot] Blocked unauthorized chat message from {msg_chat_id}: {text}")
                            continue
                            
                        _process_command(text)
            elif res.status_code == 404:
                # 토큰이 잘못된 경우 (10초 대기 후 루프 재개)
                print("[TelegramBot] 404 Error detected. Token might be invalid. Sleeping 10s...")
                _stop_event.wait(10)
            else:
                _stop_event.wait(5)
        except Exception as e:
            print(f"[TelegramBot] Polling loop error: {e}")
            _stop_event.wait(5)
            
    print("[TelegramBot] Polling daemon stopped.")

def _process_command(text: str):
    """
    수신한 텔레그램 명령어를 분석하고 처리합니다.
    """
    # 첫 단어를 명령어 기호로 분석
    parts = text.split()
    if not parts:
        return
    cmd = parts[0].lower()
    
    db = SessionLocal()
    try:
        status = db.query(BotStatus).first()
        if not status:
            status = BotStatus(is_running=False)
            db.add(status)
            db.commit()
            db.refresh(status)
            
        if cmd == "/start":
            msg = (
                "👋 *안녕하세요! StockAuto 트레이딩 브릿지입니다.*\n\n"
                "사용 가능한 명령어 목록:\n"
                "• `/status` - 현재 시스템 동작 모드, 계좌 잔고 및 보유 종목 조회\n"
                "• `/run` - 자율 트레이딩 자동매매 루프 가동\n"
                "• `/stop` - 자율 트레이딩 자동매매 루프 정지"
            )
            send_message_sync(msg)
            
        elif cmd == "/run":
            if status.is_running:
                send_message_sync("⚠️ *이미 자동매매 루프가 가동 중입니다.*")
            else:
                status.is_running = True
                db.commit()
                send_message_sync("🟢 *자율 트레이딩 자동매매 루프를 가동했습니다.*")
                
        elif cmd == "/stop":
            if not status.is_running:
                send_message_sync("⚠️ *이미 자동매매 루프가 정지되어 있습니다.*")
            else:
                status.is_running = False
                db.commit()
                send_message_sync("🔴 *자율 트레이딩 자동매매 루프를 정지했습니다.*")
                
        elif cmd == "/status":
            mode = settings.TRADE_MODE
            broker_name = settings.BROKER_PROVIDER
            
            # 실시간 예수금 조회
            broker = get_broker_client()
            try:
                balance = broker.get_account_balance()
                total_asset = balance.get("total_asset", 0)
                cash_balance = balance.get("cash_balance", 0)
                stock_balance = balance.get("stock_balance", 0)
                profit_rate = balance.get("profit_rate", 0.0)
            except Exception as e:
                total_asset, cash_balance, stock_balance, profit_rate = 0, 0, 0, 0.0
                print(f"[TelegramBot] Account balance fetch failed: {e}")
                
            fx_rate = FXRateCache.get_rate()
            holdings = db.query(Holding).all()
            status_text = "🟢 *가동 중*" if status.is_running else "🔴 *정지됨*"
            
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
                    # 수익률 계산
                    profit_pct = 0.0
                    # KIS 또는 가상 체결로부터 실시간 데이터를 긁어와 수익률 표기 가능
                    # 단순하게 현재 평단 및 보유량 노출
                    msg += (
                        f"• *{h.ticker}* ({h.ticker_name})\n"
                        f"  └ 수량: `{h.quantity}주` | 평단: `${h.avg_price:,.2f}`\n"
                    )
            send_message_sync(msg)
            
        else:
            send_message_sync("❓ *알 수 없는 명령어입니다.*\n사용 가능한 명령어: `/status`, `/run`, `/stop`")
            
    except Exception as e:
        print(f"[TelegramBot] Command execution error: {e}")
        send_message_sync(f"⚠️ *명령어 실행 중 오류 발생:* {str(e)}")
    finally:
        db.close()

def start_telegram_bot():
    """
    텔레그램 봇 백그라운드 스레드 시동
    """
    global _poll_thread, _stop_event
    
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        print("[TelegramBot] Bot Token or Chat ID is not configured. Polling skipped.")
        return
        
    if _poll_thread and _poll_thread.is_alive():
        return
        
    _stop_event.clear()
    _poll_thread = threading.Thread(target=_poll_updates_loop, name="TelegramPollThread", daemon=True)
    _poll_thread.start()
    print("[TelegramBot] Polling thread started successfully.")

def stop_telegram_bot():
    """
    텔레그램 봇 백그라운드 스레드 중지
    """
    global _poll_thread, _stop_event
    if _poll_thread and _poll_thread.is_alive():
        _stop_event.set()
        _poll_thread.join(timeout=3)
        print("[TelegramBot] Polling thread stopped successfully.")
