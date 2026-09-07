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
| `MCP_COMMAND_NOT_ALLOWED` | 화이트리스트 밖 `command_type` | 400 에러 |
| `MCP_EXECUTION_NOT_IMPLEMENTED` | MCP 명령 실행 워커 미구현 | 501 에러. 명령은 접수·적재되지 않는다 |

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


---

## 6. 보유 종목 관할권 계약 (Holding Management Contract)

봇이 매수하지 않은 보유 종목을 봇의 매도·추가매수 대상에서 분리하는 계약입니다. 값의 정본은 `Holding.management`이며 스키마 설명은 `docs/SCHEMA.md`, 설계 배경과 후속 단계는 `docs/plans/holding_management_modes.md`가 소유합니다.

- **`GET /api/v1/account/holdings`**: 각 보유 항목에 `management` 필드가 추가됩니다. 값은 `BOT_OWNED` 또는 `EXTERNAL`이며, DB에 대응 행이 없는 항목은 `BOT_OWNED`로 채웁니다. 같은 티커를 봇 슬롯과 `EXTERNAL`로 동시에 보유한 경우 브로커 응답은 티커 하나로 합쳐 오므로 `BOT_OWNED`로 표기합니다 — 봇이 매도하지 않을 것으로 오인하게 만드는 쪽이 반대 오류보다 위험하기 때문입니다.
- **매도 대상 지정 키는 `(ticker, strategy_type)`입니다.** 응답의 `id`는 표시용이며 매도·설정 요청의 키로 쓰면 안 됩니다 - 브로커 경로마다 의미가 다릅니다. 시뮬레이터는 DB `Holding.id`를 그대로 주지만, KIS 경로는 목록 순번(`idx + 1000`)을 발급하므로 한 종목이 청산되면 나머지 행의 id가 전부 밀리고, Toss 경로는 `id` 필드 자체가 없습니다. 폴링 사이에 목록이 바뀌면 순번 id로 보낸 요청이 엉뚱한 종목을 지정하게 됩니다.
- **경로 티커는 접두사 없는 심볼입니다.** `POST /holdings/{ticker}/sell`과 `PATCH /holdings/{ticker}/management`의 경로 티커는 `Holding.ticker`와 문자 그대로 일치해야 하며, 그 값은 거래소 접두사가 붙지 않은 심볼(`AAPL`)입니다. 서버는 `Holding.ticker == ticker` 로 매칭하므로 클라이언트가 임의로 접두사를 붙이거나 떼면 `404`가 됩니다. 새 브로커 어댑터를 추가할 때도 `ticker`에 접두사를 실어 보내지 마십시오 - `GET /holdings`의 `ticker`와 매도 경로의 키가 갈라집니다.
- **`slices` 배열**: 각 보유 항목에 `slices: [{strategy_type, management, quantity}]`가 함께 반환됩니다. 브로커 응답은 티커 하나로 합쳐 오지만 DB는 슬라이스별로 나뉘므로, 클라이언트가 매도 대상을 미리 특정하려면 이 배열을 봐야 합니다. 원소가 2개 이상이면 매도 요청에 `strategy_type`을 지정해야 합니다(지정하지 않으면 `400`).
- **`EXTERNAL` 항목의 `strategy_name`**: 전략이 아니라 관할권이므로 전략 번역기를 타지 않고 `"봇 관리 안 함"`으로 고정 반환합니다. `strategy_type`은 `"external"`이며 어떤 전략 슬롯 키와도 겹치지 않습니다.
- **`POST /api/v1/account/force-liquidate`**: 쿼리 파라미터 `include_external`(boolean, 기본 `false`)이 추가됩니다. 기본값에서는 `EXTERNAL` 보유분을 청산 대상에서 제외합니다. 응답에 `excluded_external_count`와 `liquidated_tickers`가 추가되며, 제외분이 있으면 `message`에 `include_external=true` 재요청 안내가 포함됩니다. 청산 대상이 `EXTERNAL`뿐이라 남는 것이 없으면 주문을 내지 않고 안내 메시지만 반환합니다.
- **기본값 방향**: 위험한 동작(외부 보유분까지 청산)은 호출자가 명시적으로 의도를 드러내야 하고, 기본값은 항상 안전한 쪽입니다.

### 6.1 개별 종목 수동 매도 (`POST /api/v1/account/holdings/{ticker}/sell`)

`EXTERNAL` 보유분의 계약은 "봇이 안 건드림 = 사용자가 직접 관리"인데, 기존에는 전량 청산만 있고 종목을 지정해 파는 경로가 없어 앱 안에서 그 관리를 이행할 수단이 없었습니다. 이 엔드포인트가 그 수단입니다.

- **요청 본문**: `quantity`(int, 생략 시 전량), `strategy_type`(string, 생략 가능), `confirm`(boolean, 기본 `false`).
- **`confirm` 게이트**: 되돌릴 수 없는 금융 액션이므로 기본값에서는 **주문을 내지 않고 프리뷰만** 반환합니다. 응답은 `preview: true`와 함께 `held_quantity`, `sell_quantity`, `estimated_price`, `estimated_proceeds`, `estimated_realized_pnl`, `estimated_return_rate`, `management`를 포함합니다. 실제 주문은 호출자가 `confirm: true`로 다시 요청해야 나갑니다.
- **사용자 식별**: `user_id`는 인증 세션에서만 도출하며 요청 본문의 사용자 식별자는 받지 않습니다(크로스유저 주문 주입 차단).
- **슬라이스 특정**: 같은 티커를 여러 `strategy_type`으로 보유한 경우 대상을 임의로 고르지 않고 `400`으로 거절하며, `detail`에 후보 슬라이스 목록(수량·관할권)을 담습니다. `strategy_type`을 지정해 재요청해야 합니다.
- **동시성**: 실행 경로는 사용자 작업 락과 심볼 주문 락을 모두 경유합니다. 해당 티커에 미해결 증권사 주문이 있으면 `409`, 락 획득 실패는 `409`, 락 서비스 장애는 `503`입니다. 프리뷰는 주문을 내지 않으므로 이 가드들을 타지 않습니다.
- **검증**: 보유하지 않은 종목은 `404`, 보유 수량을 초과한 매도 수량은 `400`, KIS 모드에서 장 마감 시 `400`입니다.
- **성공 응답**: `preview: false`, `status`(`filled`/`pending`/`unresolved`/`rejected`), `sold_quantity`, `remaining_quantity`, `filled_price`, `realized_pnl`, `return_rate`, `message`.
- **관할권과의 관계**: `management`는 **봇의 자율 매도**를 가르는 값이지 사용자의 수동 매도를 막지 않습니다. `EXTERNAL` 보유분도 사용자가 직접 지시하면 팔 수 있습니다.

### 6.2 수확 모드 스위치 (`PATCH /api/v1/account/holdings/{ticker}/management`)

봇 관할 밖(`EXTERNAL`) 보유분의 위임 스위치를 켜고 끕니다. 스위치 변경은 주문을 내지 않고 되돌릴 수 있으므로 `confirm` 게이트가 없습니다.

- **요청 본문**: `strategy_type`(string, 생략 가능), `harvest_enabled`(boolean, 생략 가능).
- **대상 제한**: `BOT_OWNED` 보유분에 호출하면 `400`입니다. 봇이 자기 규칙으로 산 포지션을 규칙에서 빼면 계좌에 좀비 포지션이 쌓이고 전략 성과 측정이 깨지기 때문입니다.
- **끄면 무장도 해제**: `harvest_enabled=false`는 `harvest_armed`도 함께 `false`로 되돌립니다. 다시 켰을 때 예전 무장 상태를 물려받으면 급등 판정 없이 곧바로 매도 판정 구간에 들어갑니다.
- **응답**: `ticker`, `strategy_type`, `management`, `harvest_enabled`, `harvest_armed`, `observed_base_price`.
- **`GET /holdings` 추가 필드**: `EXTERNAL` 행이 있는 티커에는 `harvest_enabled`, `harvest_armed`, `observed_base_price`가 함께 반환됩니다.

- **수확·방어 상태의 부착 기준**: `harvest_*`와 `guard_*` 필드는 그 티커에 `EXTERNAL` 행이 하나라도 있으면 붙습니다. 합쳐진 항목의 `management`가 `BOT_OWNED`로 표시되는 혼합 티커(같은 종목을 봇 슬롯과 `EXTERNAL`로 동시 보유)에도 붙으며, 이는 의도된 동작입니다. 스위치는 티커가 아니라 `EXTERNAL` 슬라이스에 속하기 때문입니다. 클라이언트는 스위치 노출 여부를 항목의 `management`가 아니라 `slices`에 `EXTERNAL` 원소가 있는지로 판정하고, `PATCH` 요청에는 그 슬라이스의 `strategy_type`을 실어야 합니다.

수확 판정 규칙 자체(무장 임계, 트레일링 폭, 하한 가드)는 `docs/plans/holding_management_modes.md` 5.2절이 소유합니다.

### 6.3 방어 경보 스위치 (`PATCH /api/v1/account/holdings/{ticker}/management`)

6.2절과 같은 엔드포인트에 `guard_enabled`(boolean) 필드가 추가됩니다. **이 스위치는 경보만 보내며 어떤 경우에도 주문을 내지 않습니다.**

- **켤 때마다 기준선이 재설정됩니다.** `guard_baseline_score`와 `guard_baseline_low`는 `null`로 비워지고, 시세를 아는 스케줄러가 다음 사이클에 채웁니다. 껐다 켤 때 예전 기준선을 물려받으면 꺼져 있던 동안의 하락이 전부 "추가 악화"로 잡혀 켜자마자 경보가 나갑니다.
- **`GET /holdings` 추가 필드**: `EXTERNAL` 행이 있는 티커에 `guard_enabled`, `guard_baseline_score`, `guard_baseline_low`가 반환됩니다. 켠 직후에는 기준선 두 필드가 `null`입니다.
- **응답**: 6.2절의 필드에 `guard_enabled`, `guard_baseline_score`, `guard_baseline_low`가 추가됩니다.
- **대상 제한**: 6.2절과 동일하게 `BOT_OWNED` 보유분에 호출하면 `400`입니다.

발동 조건(점수 추가 악화 + 신저가 갱신), 유예기간, 쿨다운은 `docs/plans/holding_management_modes.md` 5.3절이 소유합니다. 클라이언트는 이 스위치를 "손실 방어"가 아니라 "알림"으로 표시해야 합니다 — 봇은 팔지 않습니다.

### 6.4 방어 조치 모드 (`PATCH /api/v1/account/holdings/{ticker}/management`)

6.3절과 같은 엔드포인트에 `guard_action`과 `guard_sell_ratio`가 추가됩니다. **기본값은 `ALERT_ONLY`이며, 실제 매도는 사용자가 명시적으로 켜야 합니다.**

| `guard_action` | 동작 | 주문 |
| :--- | :--- | :--- |
| `ALERT_ONLY` (기본) | 알림만 | 없음 |
| `SHADOW` | "팔았다면 이랬을 것"을 로그로 기록 | 없음 |
| `LIQUIDATE` | `guard_sell_ratio` 비율만큼 부분 청산 | 있음 |

- **`guard_sell_ratio`**: 0 초과 1 이하, 기본 `0.5`. `LIQUIDATE`에서만 쓰입니다. 비율로 나눈 결과가 0주가 되어도 최소 1주는 매도합니다.
- **`guard_enabled`가 꺼진 상태에서 `ALERT_ONLY` 외의 모드로 바꾸면 `400`입니다.** 방어 경보를 먼저 켜야 합니다.
- **모드를 바꾸면 연속 충족 카운터가 리셋됩니다.** 알림만으로 쌓인 연속 충족이 청산 모드 전환 즉시 조치 임계를 넘기면 사용자가 켠 직후 바로 팔리기 때문입니다.
- 허용되지 않은 값은 `400`이며 `detail`에 허용 목록을 담습니다.
- **`GET /holdings` 추가 필드**: `EXTERNAL` 행이 있는 티커에 `guard_action`, `guard_sell_ratio`가 반환됩니다.

조치는 경보보다 훨씬 보수적인 가드를 통과해야 합니다 — 조건 10사이클 연속 충족, 보유분당 24시간 1회. 경보의 최악은 헛울림이지만 조치의 최악은 되돌릴 수 없는 손실 확정이기 때문입니다. 상세는 `docs/plans/holding_management_modes.md` 5.4절이 소유합니다.

**클라이언트는 `LIQUIDATE`를 "손실 방어"로 표시해서는 안 됩니다.** 이 신호가 실제 붕괴를 예측한다는 근거는 아직 없으며, `SHADOW` 모드가 그 근거를 수집하기 위해 존재합니다.
