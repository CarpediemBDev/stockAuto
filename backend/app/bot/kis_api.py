import requests
import json
from datetime import datetime, timedelta
from app.core.config import settings

# 티커 → 거래소 코드 메모리 캐시 (서버 수명 동안 유지)
_exchange_cache: dict[str, str] = {}

class KISClient:
    def __init__(self):
        self.app_key = settings.KIS_APP_KEY
        self.app_secret = settings.KIS_APP_SECRET
        self.account_no = settings.KIS_ACCOUNT_NO
        self.base_url = settings.KIS_BASE_URL
        self.token = None
        self.token_expired_at = None

    def get_hashkey(self, body):
        """
        POST 요청 시 데이터의 무결성을 검증하기 위한 Hashkey를 발급받습니다.
        """
        url = f"{self.base_url}/uapi/hashkey"
        headers = {
            "content-type": "application/json",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        if res.status_code == 200:
            return res.json().get("HASH")
        else:
            print(f"[KIS API] Failed to get hashkey: {res.text}")
            return None

    def _get_default_headers(self, tr_id: str, hashkey: str = None):
        """
        KIS API 공통 헤더를 생성합니다.
        """
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.get_access_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }
        if hashkey:
            headers["hashkey"] = hashkey
        return headers

    def get_access_token(self):
        # API 키가 설정되지 않았거나 기본값인 경우 토큰 요청을 건너뜁니다.
        if not self.app_key or self.app_key in ["YOUR_APP_KEY_HERE", "your_virtual_app_key_here"]:
            return None

        if self.token and self.token_expired_at and datetime.now() < self.token_expired_at:
            return self.token

        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        url = f"{self.base_url}/oauth2/tokenP"
        try:
            res = requests.post(url, headers=headers, data=json.dumps(body), timeout=5)
            if res.status_code == 200:
                data = res.json()
                self.token = data.get("access_token")
                # 토큰 만료 시간 설정 (보통 24시간, 여기서는 23시간으로 안전하게 설정)
                self.token_expired_at = datetime.now() + timedelta(hours=23)
                return self.token
            else:
                print(f"[KIS API] Failed to get KIS token: {res.text}")
                return None
        except Exception as e:
            print(f"[KIS API] Token request exception: {e}")
            return None
    def get_account_balance(self):
        from app.bot.fx_cache import FXRateCache
        # 실시간 환율을 조회하여 모든 분기(가상 및 KIS 실전)에서 환율을 공유합니다.
        exchange_rate = FXRateCache.get_rate()

        token = self.get_access_token()
        if not token or not self.app_key or self.app_key in ["YOUR_APP_KEY_HERE", "your_virtual_app_key_here"]:
            # API 키가 없거나 토큰 발급 실패 시 가상 모의 투자(Paper Trading) 데이터를 동적 계산하여 반환합니다.
            print(f"[KIS API] Generating dynamic virtual balance (Mode: {settings.TRADE_MODE})")
            import yfinance as yf
            import pandas as pd
            from app.core.database import SessionLocal
            from app.core.models import Holding

            db = SessionLocal()
            try:
                holdings = db.query(Holding).all()
            finally:
                db.close()

            initial_cash = 10000000.0  # 가상 시작 예수금: 1,000만 원 (10,000,000 KRW)

            total_purchase_krw = 0.0
            total_eval_krw = 0.0

            if holdings:
                tickers = [h.ticker for h in holdings]
                try:
                    data = yf.download(tickers, period="1d", interval="1m", group_by="ticker", progress=False)
                    for h in holdings:
                        current_price = h.avg_price  # 기본 폴백값
                        try:
                            if len(tickers) == 1:
                                if isinstance(data.columns, pd.MultiIndex):
                                    df = data[h.ticker].dropna() if h.ticker in data.columns.levels[0] else data.dropna()
                                else:
                                    df = data.dropna()
                            else:
                                if isinstance(data.columns, pd.MultiIndex):
                                    df = data[h.ticker].dropna() if h.ticker in data.columns.levels[0] else pd.DataFrame()
                                else:
                                    df = data.dropna()
                            
                            if not df.empty:
                                current_price = float(df['Close'].iloc[-1])
                        except Exception as e:
                            print(f"[Virtual Balance] Failed to parse price for {h.ticker}: {e}")

                        # KRW 기준 누적금 계산
                        total_purchase_krw += (h.avg_price * h.quantity) * exchange_rate
                        total_eval_krw += (current_price * h.quantity) * exchange_rate
                except Exception as e:
                    print(f"[Virtual Balance] Failed to download prices: {e}")
                    # 실패 시 평단가 기준으로 가치 환산
                    for h in holdings:
                        total_purchase_krw += (h.avg_price * h.quantity) * exchange_rate
                        total_eval_krw += (h.avg_price * h.quantity) * exchange_rate

            # 남은 예수금 = 1천만 원 - 주식 매입 원금 (원화)
            cash_balance = max(0.0, initial_cash - total_purchase_krw)
            stock_balance = total_eval_krw
            total_asset = cash_balance + stock_balance
            
            # 수익률 = ((전체 자산 - 투자 원금) / 투자 원금) * 100
            profit_rate = round(((total_asset - initial_cash) / initial_cash) * 100, 2)

            return {
                "total_asset": int(total_asset),
                "cash_balance": int(cash_balance),
                "stock_balance": int(stock_balance),
                "profit_rate": profit_rate,
                "profit_loss": int(total_asset - initial_cash),
                "fx_rate": exchange_rate,
                "is_mock": True,
                "provider": "Simulated"
            }

        account_prefix = self.account_no.split("-")[0] if "-" in self.account_no else self.account_no[:8]
        account_suffix = self.account_no.split("-")[1] if "-" in self.account_no else self.account_no[8:]

        # 미국 주식(해외 주식) 전용 잔고 조회로 대수선하여 국내 계좌 API 호출 오류 방지
        headers = self._get_default_headers(settings.TR_ID_OVERSEAS_BALANCE)
        
        params = {
            "CANO": account_prefix,
            "ACNT_PRDT_CD": account_suffix,
            "WCRC_FRCR_DVSN_CD": "02", # 02: 외화 기준 (USD)
            "NATN_CD": "840",          # 840: 미국
            "TR_P_CS_DVSN_CD": "00",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": ""
        }
        
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-present-balance"
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                output2 = data.get("output2", {})
                
                # KIS 해외 주식 잔고 API output2 매핑
                total_asset = int(float(output2.get("tot_asst_amt", 0)))
                usd_cash = float(output2.get("frcr_use_psbl_amt", 0))
                cash_balance = int(usd_cash * exchange_rate)
                stock_balance = int(float(output2.get("tot_evlu_amt", 0)))
                
                profit_rate = float(output2.get("tot_evlu_pfls_rt", 0.0))
                
                try:
                    profit_loss = int(float(output2.get("tot_evlu_pft_amt", 0)))
                except Exception:
                    initial_capital = total_asset / (1.0 + profit_rate / 100.0) if profit_rate != -100.0 else 0
                    profit_loss = int(total_asset - initial_capital)

                return {
                    "total_asset": total_asset,
                    "cash_balance": cash_balance,
                    "stock_balance": stock_balance,
                    "profit_rate": profit_rate,
                    "profit_loss": profit_loss,
                    "fx_rate": exchange_rate,
                    "is_mock": not settings.IS_REAL,
                    "provider": "KIS Live" if settings.IS_REAL else "KIS Mock"
                }
            else:
                print(f"[KIS API] Overseas balance check failed: {res.text}")
                return {"total_asset": 0, "cash_balance": 0, "stock_balance": 0, "profit_rate": 0.0}
        except Exception as e:
            print(f"[KIS API] Error checking overseas balance: {e}")
            return {"total_asset": 0, "cash_balance": 0, "stock_balance": 0, "profit_rate": 0.0}

    def _get_exchange_code(self, ticker: str) -> str:
        """
        yfinance의 fast_info를 활용하여 티커의 실제 거래소를 판별하고
        KIS API 규격의 거래소 코드(NASD/NYSE/AMEX)로 매핑합니다.
        결과는 메모리에 캐싱하여 동일 티커에 대한 반복 조회를 방지합니다.
        """
        global _exchange_cache

        if ticker in _exchange_cache:
            return _exchange_cache[ticker]

        # yfinance 거래소명 → KIS 거래소 코드 매핑 테이블
        EXCHANGE_MAP = {
            "NMS": "NASD",   # NASDAQ Global Select Market
            "NGM": "NASD",   # NASDAQ Global Market
            "NCM": "NASD",   # NASDAQ Capital Market
            "NYQ": "NYSE",   # New York Stock Exchange
            "NYS": "NYSE",   # NYSE 별칭
            "ASE": "AMEX",   # American Stock Exchange (NYSE AMEX)
            "PCX": "AMEX",   # NYSE Arca (AMEX 계열)
            "BTS": "AMEX",   # BATS Exchange → AMEX로 분류
        }

        try:
            import yfinance as yf
            info = yf.Ticker(ticker).fast_info
            raw_exchange = getattr(info, 'exchange', '') or ''
            kis_code = EXCHANGE_MAP.get(raw_exchange, "NASD")
            _exchange_cache[ticker] = kis_code
            print(f"[KIS API] Exchange resolved: {ticker} → {raw_exchange} → {kis_code}")
            return kis_code
        except Exception as e:
            print(f"[KIS API] Exchange lookup failed for {ticker}, defaulting to NASD: {e}")
            _exchange_cache[ticker] = "NASD"
            return "NASD"

    def buy_overseas_order(self, ticker: str, quantity: int, price: float = 0):
        """
        해외주식 매수 주문 (Hashkey 보안 인증 적용)
        """
        token = self.get_access_token()
        if not token: return None

        account_prefix = self.account_no.split("-")[0] if "-" in self.account_no else self.account_no[:8]
        account_suffix = self.account_no.split("-")[1] if "-" in self.account_no else self.account_no[8:]

        body = {
            "CANO": account_prefix,
            "ACNT_PRDT_CD": account_suffix,
            "OVRS_EXCG_CD": self._get_exchange_code(ticker),
            "PDNO": ticker,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": f"{price:.2f}",
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": "00" # 00: 지정가
        }

        headers = self._get_default_headers(settings.TR_ID_BUY_OVERSEAS, self.get_hashkey(body))

        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/order"
        try:
            res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
            data = res.json()
            if data.get("rt_cd") != "0":
                print(f"[KIS API] Order Rejected: {data.get('msg1')} ({data.get('msg_cd')})")
            return data
        except Exception as e:
            print(f"[KIS API] Order Exception: {e}")
            return None

    def sell_overseas_order(self, ticker: str, quantity: int, price: float = 0):
        """
        해외주식 매도 주문 (Hashkey 보안 인증 적용)
        """
        token = self.get_access_token()
        if not token: return None

        account_prefix = self.account_no.split("-")[0] if "-" in self.account_no else self.account_no[:8]
        account_suffix = self.account_no.split("-")[1] if "-" in self.account_no else self.account_no[8:]

        body = {
            "CANO": account_prefix,
            "ACNT_PRDT_CD": account_suffix,
            "OVRS_EXCG_CD": self._get_exchange_code(ticker),
            "PDNO": ticker,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": f"{price:.2f}",
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": "00" # 00: 지정가
        }

        headers = self._get_default_headers(settings.TR_ID_SELL_OVERSEAS, self.get_hashkey(body))

        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/order"
        try:
            res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
            data = res.json()
            if data.get("rt_cd") != "0":
                print(f"[KIS API] Order Rejected: {data.get('msg1')} ({data.get('msg_cd')})")
            return data
        except Exception as e:
            print(f"[KIS API] Order Exception: {e}")
            return None

    def check_order_status(self, order_no: str, order_date: str = None) -> dict:
        """
        해외주식 주문 체결 상태를 조회합니다.
        KIS 해외주식 주문체결내역 API (JTTT3010R / VTTS3010R)를 호출하여
        주문번호(ODNO)에 해당하는 체결 상태(전량 체결 / 부분 체결 / 미체결)를 확인합니다.

        반환:
        {
            "status": "FILLED" | "PARTIAL" | "UNFILLED" | "ERROR",
            "filled_qty": int,     # 체결된 수량
            "ordered_qty": int,    # 주문한 수량
            "filled_price": float, # 체결 단가
            "order_no": str
        }
        """
        token = self.get_access_token()
        if not token:
            return {"status": "ERROR", "message": "No access token"}

        account_prefix = self.account_no.split("-")[0] if "-" in self.account_no else self.account_no[:8]
        account_suffix = self.account_no.split("-")[1] if "-" in self.account_no else self.account_no[8:]

        # 실전/모의 TR_ID 분기
        tr_id = "JTTT3010R" if settings.IS_REAL else "VTTS3010R"
        headers = self._get_default_headers(tr_id)

        # 조회 기간: 기본값은 오늘
        from datetime import date
        today = order_date or date.today().strftime("%Y%m%d")

        params = {
            "CANO": account_prefix,
            "ACNT_PRDT_CD": account_suffix,
            "PDNO": "",               # 전체 종목
            "ORD_STRT_DT": today,
            "ORD_END_DT": today,
            "SLL_BUY_DVSN_CD": "00",  # 00: 전체
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": ""
        }

        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-ccnl"
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                orders = data.get("output", [])

                # 주문번호가 일치하는 건 찾기
                for order in orders:
                    if order.get("odno") == order_no:
                        ordered_qty = int(float(order.get("ft_ord_qty", 0)))
                        filled_qty = int(float(order.get("ft_ccld_qty", 0)))
                        filled_price = float(order.get("ft_ccld_unpr3", 0))

                        if filled_qty >= ordered_qty:
                            status = "FILLED"
                        elif filled_qty > 0:
                            status = "PARTIAL"
                        else:
                            status = "UNFILLED"

                        return {
                            "status": status,
                            "filled_qty": filled_qty,
                            "ordered_qty": ordered_qty,
                            "filled_price": filled_price,
                            "order_no": order_no
                        }

                # 주문번호를 찾지 못한 경우
                return {"status": "UNFILLED", "filled_qty": 0, "ordered_qty": 0, "filled_price": 0, "order_no": order_no}
            else:
                print(f"[KIS API] Order status check failed: {res.text}")
                return {"status": "ERROR", "message": res.text}
        except Exception as e:
            print(f"[KIS API] Order status check exception: {e}")
            return {"status": "ERROR", "message": str(e)}

    def get_overseas_ranking(self, exchange: str = "NAS", rank_type: str = "2"):
        """
        해외주식 실시간 순위 조회
        """
        headers = self._get_default_headers("HHDFS76200200")

        params = {
            "AUTH": "",
            "EXCD": exchange,
            "RANK_DVSN": rank_type,
        }

        url = f"{self.base_url}/uapi/overseas-stock/v1/quotations/ranking"
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                return data.get("output", [])
            else:
                print(f"[KIS API] Ranking check failed: {res.text}")
                return None
        except Exception as e:
            print(f"[KIS API] Error checking ranking: {e}")
            return None

    def get_overseas_present_balance(self):
        """
        해외주식 현재 체결기준 잔고 및 수익률을 조회합니다.
        """
        account_prefix = self.account_no.split("-")[0] if "-" in self.account_no else self.account_no[:8]
        account_suffix = self.account_no.split("-")[1] if "-" in self.account_no else self.account_no[8:]

        headers = self._get_default_headers(settings.TR_ID_OVERSEAS_BALANCE)
        
        params = {
            "CANO": account_prefix,
            "ACNT_PRDT_CD": account_suffix,
            "WCRC_FRCR_DVSN_CD": "02", # 01: 원화, 02: 외화
            "NATN_CD": "840", # 840: 미국
            "TR_P_CS_DVSN_CD": "00",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": ""
        }
        
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-present-balance"
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                output1 = data.get("output1", [])
                
                holdings = []
                for item in output1:
                    holdings.append({
                        "ticker": item.get("pdno"),
                        "name": item.get("prdt_name"),
                        "qty": int(float(item.get("ccl_qty", 0))),
                        "buy_price": float(item.get("pchs_avg_pric", 0)),
                        "current_price": float(item.get("now_pric", 0)),
                        "profit_rate": float(item.get("evlu_pfls_rt", 0))
                    })
                return holdings
            else:
                print(f"[KIS API] Overseas balance check failed: {res.text}")
                return []
        except Exception as e:
            print(f"[KIS API] Error checking overseas balance: {e}")
            return []
