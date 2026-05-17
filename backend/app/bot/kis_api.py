import requests
import json
from datetime import datetime, timedelta
from app.core.config import settings

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
        token = self.get_access_token()
        if not token or not self.app_key or self.app_key in ["YOUR_APP_KEY_HERE", "your_virtual_app_key_here"]:
            # API 키가 없거나 토큰 발급 실패 시 UI 테스트를 위한 멋진 가짜(Mock) 데이터를 반환합니다.
            print(f"[KIS API] Using mock data for account balance (Mode: {settings.TRADE_MODE})")
            return {
                "total_asset": 15420000,
                "cash_balance": 4500000,
                "stock_balance": 10920000,
                "profit_rate": 8.45
            }

        account_prefix = self.account_no.split("-")[0] if "-" in self.account_no else self.account_no[:8]
        account_suffix = self.account_no.split("-")[1] if "-" in self.account_no else self.account_no[8:]

        headers = self._get_default_headers(settings.TR_ID_BALANCE)
        
        params = {
            "CANO": account_prefix,
            "ACNT_PRDT_CD": account_suffix,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                output2 = data.get("output2", [{}])[0]
                
                total_asset = int(output2.get("tot_evlu_amt", 0))
                stock_balance = int(output2.get("scts_evlu_amt", 0))
                cash_balance = int(output2.get("prvs_rcdl_excc_amt", 0))
                profit_rate = float(output2.get("evlu_pfls_rt", 0.0))
                
                return {
                    "total_asset": total_asset,
                    "cash_balance": cash_balance,
                    "stock_balance": stock_balance,
                    "profit_rate": profit_rate
                }
            else:
                print(f"[KIS API] Balance check failed: {res.text}")
                return {"total_asset": 0, "cash_balance": 0, "stock_balance": 0, "profit_rate": 0.0}
        except Exception as e:
            print(f"[KIS API] Error checking balance: {e}")
            return {"total_asset": 0, "cash_balance": 0, "stock_balance": 0, "profit_rate": 0.0}

    def buy_market_order(self, ticker: str, quantity: int):
        # TODO: 실제 한국투자증권 매수 API 연동 구현
        print(f"[KIS API] Buying {quantity} of {ticker} at market price")
        return {"rt_cd": "0", "msg1": "Success", "price": 50000} # Mock response

    def sell_market_order(self, ticker: str, quantity: int):
        # TODO: 실제 한국투자증권 매도 API 연동 구현
        print(f"[KIS API] Selling {quantity} of {ticker} at market price")
        return {"rt_cd": "0", "msg1": "Success", "price": 50000} # Mock response

    def _get_exchange_code(self, ticker: str):
        """
        심볼을 기반으로 KIS 해외 거래소 코드를 반환합니다.
        기본적으로 NASD(나스닥)를 반환하며, 향후 DB나 메타데이터 기반으로 고도화 가능합니다.
        """
        # TODO: 실제 종목별 거래소 매핑 로직 추가 필요
        # 현재는 대부분의 기술주가 나스닥에 있으므로 NASD를 기본값으로 사용
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
