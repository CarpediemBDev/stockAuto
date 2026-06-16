import requests
import json
import pandas as pd
from datetime import datetime, timedelta
from app.core.config import settings
from app.core.credentials import decrypt_credential
from app.core.exceptions import StockAutoException
from app.bot.market_session import ACTIVE_MARKET_SESSIONS, MarketSession
from app.scanner.data_provider import fetch_bulk_ohlcv_sync, fetch_ticker_fast_info

# 티커 → 거래소 코드 메모리 캐시 (서버 수명 동안 유지)
_exchange_cache: dict[str, str] = {}

class KISClient:
    def __init__(self, db_credential=None, trade_mode: str = "SIMULATED"):
        trade_mode = (trade_mode or "SIMULATED").upper()
        self.trade_mode = trade_mode
        self.is_real = trade_mode == "REAL"

        if not db_credential or trade_mode == "SIMULATED":
            from app.core.exceptions import StockAutoException
            raise StockAutoException(
                code="INVALID_KIS_CREDENTIALS",
                message="한국투자증권(KIS) 연동을 위해서는 유효한 DB 설정 정보가 필요합니다.",
                status_code=400
            )

        self.user_id = db_credential.user_id
        self.app_key = decrypt_credential(db_credential.app_key)
        self.app_secret = decrypt_credential(db_credential.app_secret)
        self.account_no = decrypt_credential(db_credential.account_no)

        placeholder_keys = {
            "YOUR_APP_KEY_HERE", "your_virtual_app_key_here",
            "your_real_app_key_here", "your_app_key_here",
            None, ""
        }
        if (self.app_key in placeholder_keys or
            self.app_secret in placeholder_keys or
            not self.account_no or
            self.account_no in ["00000000-01", "12345678-01", "your_account_no_here", ""]):

            from app.core.exceptions import StockAutoException
            raise StockAutoException(
                code="INVALID_KIS_CREDENTIALS",
                message="한국투자증권(KIS) API 연동 키가 누락되었거나 유효하지 않습니다. "
                        "'Personal Settings > Trading Environment' 탭으로 이동하여 올바른 API Key, Secret 및 계좌번호를 입력하고 연동을 진행해 주세요.",
                status_code=400
            )

        if self.is_real:
            self.base_url = "https://openapi.koreainvestment.com:9443"
        else:
            self.base_url = "https://vts-openapi.koreainvestment.com:29443"

        self.token = None
        self.token_expired_at = None

    def _order_division_for_session(self, session: MarketSession | str) -> str:
        try:
            session_code = MarketSession(session or MarketSession.REGULAR)
        except ValueError as exc:
            raise ValueError(f"Unknown market session: {session}") from exc
        if session_code not in ACTIVE_MARKET_SESSIONS:
            raise ValueError(f"Orders are not allowed during market session: {session_code}")

        # KIS 공식 규격에서 32/34는 프리·에프터장 코드가 아니라 LOO/LOC 주문 유형입니다.
        # 자동매매는 각 활성 세션에서 현재가 기반 지정가 주문(00)만 사용합니다.
        return "00"

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

    def get_account_balance(self, exchange_rate: float | None = None):
        from app.bot.fx_cache import FXRateCache
        # 실시간 환율을 조회하여 모든 분기(가상 및 KIS 실전)에서 환율을 공유합니다.
        if exchange_rate is None:
            exchange_rate = FXRateCache.get_rate()

        token = self.get_access_token()
        if not token:
            # KISClient는 __init__에서 SIMULATED 모드를 차단하므로, 여기 도달 시 반드시 MOCK/REAL 모드임
            raise StockAutoException(
                code="INVALID_KIS_CREDENTIALS",
                message="한국투자증권(KIS) API 인증 토큰을 발급받지 못했습니다. 증권사 서버 장애이거나 키 만료 상태일 수 있습니다. "
                        "'Personal Settings > Trading Environment' 탭에서 키 검증 상태를 다시 확인해 주세요.",
                status_code=400
            )

        account_prefix = self.account_no.split("-")[0] if "-" in self.account_no else self.account_no[:8]
        account_suffix = self.account_no.split("-")[1] if "-" in self.account_no else self.account_no[8:]

        # 미국 주식(해외 주식) 전용 잔고 조회
        tr_id_balance = "CTRP6504R" if self.is_real else "VTRP6504R"
        headers = self._get_default_headers(tr_id_balance)

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
                if not isinstance(output2, dict) or "tot_asst_amt" not in output2:
                    raise StockAutoException(
                        code="KIS_BALANCE_UNAVAILABLE",
                        message="한국투자증권 잔고 응답에 총자산 정보가 없습니다.",
                        status_code=502,
                    )

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
                    "is_mock": not self.is_real,
                    "provider": "KIS Live" if self.is_real else "KIS Mock"
                }
            else:
                raise StockAutoException(
                    code="KIS_BALANCE_UNAVAILABLE",
                    message=(
                        "한국투자증권 해외주식 잔고 조회에 실패했습니다. "
                        f"HTTP {res.status_code}"
                    ),
                    status_code=502,
                )
        except StockAutoException:
            raise
        except Exception as e:
            raise StockAutoException(
                code="KIS_BALANCE_UNAVAILABLE",
                message="한국투자증권 해외주식 잔고를 조회하지 못했습니다.",
                status_code=502,
            ) from e

    def _get_exchange_code(self, ticker: str) -> str:
        """
        yfinance의 fast_info를 활용하여 티커의 실제 거래소를 판별하고
        KIS API 규격의 거래소 코드(NASD/NYSE/AMEX)로 매핑합니다.
        """
        global _exchange_cache

        if ticker in _exchange_cache:
            return _exchange_cache[ticker]

        EXCHANGE_MAP = {
            "NMS": "NASD",
            "NGM": "NASD",
            "NCM": "NASD",
            "NYQ": "NYSE",
            "NYS": "NYSE",
            "ASE": "AMEX",
            "PCX": "AMEX",
            "BTS": "AMEX",
        }

        try:
            info = fetch_ticker_fast_info(ticker)
            raw_exchange = getattr(info, 'exchange', '') or ''
            kis_code = EXCHANGE_MAP.get(raw_exchange, "NASD")
            _exchange_cache[ticker] = kis_code
            print(f"[KIS API] Exchange resolved: {ticker} → {raw_exchange} → {kis_code}")
            return kis_code
        except Exception as e:
            print(f"[KIS API] Exchange lookup failed for {ticker}, defaulting to NASD: {e}")
            _exchange_cache[ticker] = "NASD"
            return "NASD"

    @staticmethod
    def _client_order_reference(client_order_id: str | None) -> str:
        if not client_order_id:
            return ""
        return "".join(char for char in client_order_id if char.isalnum())[:20]

    def buy_overseas_order(
        self,
        ticker: str,
        quantity: int,
        price: float = 0,
        session: str = "REGULAR_MARKET",
        client_order_id: str | None = None,
    ):
        """
        해외주식 매수 주문
        """
        token = self.get_access_token()
        if not token: return None

        account_prefix = self.account_no.split("-")[0] if "-" in self.account_no else self.account_no[:8]
        account_suffix = self.account_no.split("-")[1] if "-" in self.account_no else self.account_no[8:]
        ord_dvsn = self._order_division_for_session(session)

        body = {
            "CANO": account_prefix,
            "ACNT_PRDT_CD": account_suffix,
            "OVRS_EXCG_CD": self._get_exchange_code(ticker),
            "PDNO": ticker,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": f"{price:.2f}",
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": self._client_order_reference(client_order_id),
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": ord_dvsn
        }

        tr_id = "TTTT1002U" if self.is_real else "VTTT1002U"
        headers = self._get_default_headers(tr_id, self.get_hashkey(body))

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

    def sell_overseas_order(
        self,
        ticker: str,
        quantity: int,
        price: float = 0,
        session: str = "REGULAR_MARKET",
        client_order_id: str | None = None,
    ):
        """
        해외주식 매도 주문
        """
        token = self.get_access_token()
        if not token: return None

        account_prefix = self.account_no.split("-")[0] if "-" in self.account_no else self.account_no[:8]
        account_suffix = self.account_no.split("-")[1] if "-" in self.account_no else self.account_no[8:]
        ord_dvsn = self._order_division_for_session(session)

        body = {
            "CANO": account_prefix,
            "ACNT_PRDT_CD": account_suffix,
            "OVRS_EXCG_CD": self._get_exchange_code(ticker),
            "PDNO": ticker,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": f"{price:.2f}",
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": self._client_order_reference(client_order_id),
            "SLL_TYPE": "00",
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": ord_dvsn
        }

        tr_id = "TTTT1006U" if self.is_real else "VTTT1006U"
        headers = self._get_default_headers(tr_id, self.get_hashkey(body))

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

    @staticmethod
    def _parse_int(value) -> int:
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _parse_float(value) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _normalize_order_history_item(cls, item: dict) -> dict:
        ordered_qty = cls._parse_int(item.get("ft_ord_qty"))
        filled_qty = cls._parse_int(item.get("ft_ccld_qty"))
        unfilled_qty = cls._parse_int(item.get("nccs_qty"))
        reject_reason = item.get("rjct_rson_name") or item.get("rjct_rson") or ""
        correction_type = item.get("rvse_cncl_dvsn_name") or item.get("rvse_cncl_dvsn") or ""
        processing_status = item.get("prcs_stat_name") or ""

        if reject_reason:
            status = "REJECTED"
        elif "취소" in correction_type or "취소" in processing_status:
            status = "CANCELED"
        elif ordered_qty > 0 and filled_qty >= ordered_qty:
            status = "FILLED"
        elif filled_qty > 0:
            status = "PARTIAL"
        else:
            status = "UNFILLED"

        side_code = str(item.get("sll_buy_dvsn_cd") or "")
        side_name = str(item.get("sll_buy_dvsn_cd_name") or "")
        side = "SELL" if side_code == "01" or "매도" in side_name else "BUY"

        return {
            "order_no": str(item.get("odno") or ""),
            "original_order_no": str(item.get("orgn_odno") or ""),
            "order_date": str(item.get("ord_dt") or item.get("dmst_ord_dt") or ""),
            "order_time": str(item.get("ord_tmd") or item.get("thco_ord_tmd") or ""),
            "side": side,
            "ticker": str(item.get("pdno") or ""),
            "ticker_name": item.get("prdt_name"),
            "exchange_code": str(item.get("ovrs_excg_cd") or ""),
            "ordered_qty": ordered_qty,
            "order_price": cls._parse_float(item.get("ft_ord_unpr3")),
            "filled_qty": filled_qty,
            "filled_price": cls._parse_float(item.get("ft_ccld_unpr3")),
            "unfilled_qty": unfilled_qty,
            "status": status,
            "reject_reason": reject_reason,
            "processing_status": processing_status,
            "raw": item,
        }

    def list_order_history(self, start_date: str, end_date: str, max_pages: int = 10) -> list[dict]:
        """공식 해외주식 주문체결내역 API의 모든 연속조회 페이지를 반환합니다."""
        token = self.get_access_token()
        if not token:
            raise RuntimeError("No access token")

        account_prefix = self.account_no.split("-")[0] if "-" in self.account_no else self.account_no[:8]
        account_suffix = self.account_no.split("-")[1] if "-" in self.account_no else self.account_no[8:]

        tr_id = "TTTS3035R" if self.is_real else "VTTS3035R"
        url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-ccnl"
        nk200 = ""
        fk200 = ""
        tr_cont = ""
        results = []

        for _page in range(max_pages):
            headers = self._get_default_headers(tr_id)
            if tr_cont:
                headers["tr_cont"] = tr_cont
            params = {
                "CANO": account_prefix,
                "ACNT_PRDT_CD": account_suffix,
                "PDNO": "%" if self.is_real else "",
                "ORD_STRT_DT": start_date,
                "ORD_END_DT": end_date,
                "SLL_BUY_DVSN": "00",
                "CCLD_NCCS_DVSN": "00",
                "OVRS_EXCG_CD": "NASD" if self.is_real else "",
                "SORT_SQN": "DS",
                "ORD_DT": "",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "CTX_AREA_NK200": nk200,
                "CTX_AREA_FK200": fk200,
            }
            res = requests.get(url, headers=headers, params=params, timeout=10)
            if res.status_code != 200:
                raise RuntimeError(f"KIS order history failed: {res.text}")

            data = res.json()
            if data.get("rt_cd") not in (None, "0"):
                raise RuntimeError(data.get("msg1") or "KIS order history rejected")

            output = data.get("output", [])
            if isinstance(output, dict):
                output = [output]
            results.extend(self._normalize_order_history_item(item) for item in output)

            tr_cont = str(res.headers.get("tr_cont") or res.headers.get("tr-cont") or "")
            nk200 = str(data.get("ctx_area_nk200") or data.get("CTX_AREA_NK200") or "")
            fk200 = str(data.get("ctx_area_fk200") or data.get("CTX_AREA_FK200") or "")
            if tr_cont not in {"M", "F"} or not (nk200 or fk200):
                break
            tr_cont = "N"

        return results

    def check_order_status(self, order_no: str, order_date: str = None) -> dict:
        """주문번호 검색을 지원하지 않는 KIS API 결과를 애플리케이션에서 필터링합니다."""
        from datetime import date

        target_date = order_date or date.today().strftime("%Y%m%d")
        try:
            orders = self.list_order_history(target_date, target_date)
        except Exception as exc:
            print(f"[KIS API] Order status check exception: {exc}")
            return {"status": "ERROR", "message": str(exc)}

        for order in orders:
            if order["order_no"] == order_no:
                return order
        return {
            "status": "UNFILLED",
            "filled_qty": 0,
            "ordered_qty": 0,
            "filled_price": 0.0,
            "order_no": order_no,
        }

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

        tr_id = "CTRP6504R" if self.is_real else "VTRP6504R"
        headers = self._get_default_headers(tr_id)

        params = {
            "CANO": account_prefix,
            "ACNT_PRDT_CD": account_suffix,
            "WCRC_FRCR_DVSN_CD": "02",
            "NATN_CD": "840",
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
