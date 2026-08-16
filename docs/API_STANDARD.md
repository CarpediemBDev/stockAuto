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
- **에러 핸들링**: 에러 발생 시 인터셉터가 `error.message`에 백엔드의 `message` 값을 주입하며, UI 컴포넌트에서는 `getApiErrorMessage(err, fallback)` 공통 헬퍼를 사용하여 `429 Too Many Requests`(Rate Limit), `403 Forbidden`(계정 잠금), 유효성 검사 실패(`422`) 메시지를 일관되게 토스트/모달에 출력합니다.


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

---

## 5. 인증 및 보안 계약 (Auth & Security Contract)

- **회원가입 Rate Limit (`POST /api/v1/auth/signup`)**: Bcrypt CPU 자원 고갈(DoS) 및 무한 계정 생성 방어를 위해 동일 IP당 60초 내 최대 30회, 동일 username당 60초 내 최대 10회로 호출이 제한되며 초과 시 `429 Too Many Requests`를 반환합니다.
- **로그인 Brute-force 방어 및 실시간 보안 알림 (`POST /api/v1/auth/login`)**: 동일 계정 기준 60초 내 5회 호출 제한(RateLimiter) 및 연속 5회 비밀번호 불일치 시 15분간 계정이 자동 잠금(`403 Forbidden`)되며, 텔레그램 연동 사용자에게 실시간 보안 경고 알림을 발송합니다(알림 실패 시에도 인증 트랜잭션이 영향받지 않도록 Fail-Safe 격리).
- **쿠키 기반 인증 요청 출처 검증 (`POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`)**: 크로스 사이트 CSRF 방어를 위해 `Sec-Fetch-Site: cross-site` 요청을 즉시 `403 Forbidden`으로 차단하며, `Origin`/`Referer` 헤더가 제공될 경우 `get_allowed_origins()` 화이트리스트와 일치 여부를 검증합니다.
- **텔레그램 연동 소유권 증명 (`POST /api/v1/admin/telegram/link-token`)**: 전역 단일 봇은 아무 텔레그램 사용자의 메시지나 수신하므로, 딥링크 페이로드는 반드시 서버가 발급한 1회용·만료형 토큰이어야 합니다. 사용자명은 비밀이 아니므로 연동 인증 수단으로 사용하지 않습니다(과거 `/start <사용자명>` 방식은 사용자명만 아는 제3자가 피해자 계정에 자기 chat_id를 묶어 포트폴리오 조회와 자동매매 기동·정지를 탈취할 수 있었습니다). 계약 — 인증된 본인 계정에만 발급, IP당 60초 내 최대 10회(`429 Too Many Requests`), 유효기간 10분, 1회 사용 시 즉시 폐기, 재발급 시 직전 토큰 무효화. 응답은 `deep_link`·`expires_at`·`expires_in_minutes`이며 원본 토큰은 이 응답에서 한 번만 노출되고 DB에는 SHA-256 지문만 저장됩니다. 봇 측에서 토큰이 불일치·만료·재사용이면 모두 동일한 안내(`telegram.link_invalid_token`)로 응답해 계정 존재 여부를 노출하지 않습니다.
- **텔레그램 chat_id 배타적 소유 (`POST /api/v1/admin`)**: 수동 `telegram_chat_id` 입력이 이미 다른 계정에 연동된 chat_id를 가로채지 못하도록 중복 바인딩을 `409 Conflict`로 차단합니다. 딥링크 연동은 토큰으로 소유권을 증명하지만 이 입력란은 임의 문자열을 받기 때문입니다.

