# StockAuto API 응답 및 에러 표준 규격

본 문서는 백엔드(FastAPI)와 프런트엔드(Next.js) 간의 통신 규격을 정의합니다. 모든 API 응답은 아래 형식을 엄격히 준수합니다.

---

## 1. 성공 응답 (Success Response)
HTTP 상태 코드: `200 OK`

성공 시에는 항상 `SUCCESS` 코드와 함께 실제 결과 데이터를 `data` 필드에 담아 반환합니다.

```json
{
    "code": "SUCCESS",
    "message": "요청이 성공적으로 처리되었습니다.",
    "data": { 
        "total_asset": 15420000,
        "cash_balance": 4500000
    }
}
```

## 2. 에러 응답 (Error Response)
HTTP 상태 코드: `4xx` 또는 `5xx`

에러 발생 시에는 최상위 `error` 객체 안에 상세 정보를 담아 반환합니다.

```json
{
    "error": {
        "code": "API_KEY_MISSING",
        "message": "KIS API 키 또는 계좌번호가 설정되지 않았습니다."
    }
}
```

### 주요 에러 코드 (Error Codes)
| 코드 | 설명 | 비고 |
| :--- | :--- | :--- |
| `API_KEY_MISSING` | .env 파일에 KIS API 정보가 누락됨 | 계좌 조회 시 발생 |
| `SCHEDULER_NOT_READY` | 배경 엔진이 아직 시작되지 않음 | 서버 시작 직후 발생 가능 |
| `WATCHLIST_DUPLICATE` | 이미 관심종목에 등록된 티커 | 등록 요청 시 발생 |
| `SCANNER_ERROR` | 마켓 스캔 엔진 내부 오류 | 500 에러 |

---

## 3. 프런트엔드 처리 가이드
- **Axios Interceptor**: `frontend/lib/api.ts`에 정의된 인터셉터가 성공 시 자동으로 `data`를 추출하므로, 컴포넌트에서는 `res.data`를 통해 실제 데이터에 즉시 접근할 수 있습니다.
- **에러 핸들링**: 에러 발생 시 인터셉터가 `error.message`에 백엔드의 `message` 값을 주입하므로, `error.message`를 그대로 UI에 출력하면 됩니다.

---

## 4. 사용자별 스캐너 응답 계약

- `GET /api/v1/scanner/latest`는 인증이 필요하며 공용 시장 상위 신호와 현재 로그인 사용자의 관심종목 신호만 반환합니다.
- `WATCHLIST` 태그는 전역 캐시에 영구 저장하지 않고 현재 사용자의 `WatchList.user_id`를 확인한 응답·실행 컨텍스트에서 부여합니다.
- 다른 사용자의 관심종목 티커나 `WATCHLIST` 태그가 응답에 포함되면 멀티테넌시 회귀로 처리합니다.
- `GET /api/v1/account/balance`의 `focused_radar_tickers`도 `/scanner/latest`와 같은 사용자 신호 컨텍스트를 사용하며 현재 사용자의 관심종목만 강제 포함합니다.
- `GET/POST /api/v1/scanner/swing-predict`는 인증이 필요하지만 사용자 관심종목을 결합하지 않는 공용 시장 기능입니다. 모든 사용자가 `GLOBAL_SWING_POOL`을 공유하며 응답의 `scope`는 항상 `global`입니다.
- 스윙 예측의 DB 세션은 공용 스냅샷의 재시작 복구에 사용하고, 인증 사용자 의존성은 갱신 비용이 있는 API의 접근 제어에 사용합니다.
- 스윙 예측 후보의 볼린저 밴드폭 지표 필드는 `bollinger_band_width_percentile`입니다. 현재 볼린저 밴드폭이 과거 밴드폭 분포에서 어느 백분위인지 나타내며, 낮을수록 수축이 강합니다. 기존 persisted snapshot의 `squeeze_pct`는 백엔드 정규화 단계에서 신규 필드로만 변환합니다.
- `GET /api/v1/scanner/after-hours-candidates`와 `POST /api/v1/scanner/after-hours-candidates/refresh`는 인증이 필요하지만 사용자 관심종목을 결합하지 않는 공용 해외 시장 기능입니다.
- 에프터장 후보 응답은 `scope=global`, `sync_status`, `updated_at`, `universe_size`, `candidates[]`를 반환하며 각 후보는 `score`, `signal_type`, `reasons`, `risk_flags`, `catalyst_keywords`, `details`를 포함합니다.
- 에프터장 후보는 정규장 흐름과 에프터장 체결 확인을 표시하는 관찰용 랭킹이며 자동매매 진입 신호 캐시인 `/scanner/latest`와 섞지 않습니다.
- 상세 생산자·캐시·소비자 관계는 `docs/SCANNER_DATA_FLOW.md`를 따릅니다.
