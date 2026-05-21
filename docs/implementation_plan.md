# Phase 12: 멀티유저 인증 및 사용자별 투자 프로필 설계도 (Implementation Plan)

본 설계도는 단일 사용자 전용이었던 StockAuto 시스템을 **멀티유저 구조(Multi-tenancy)**로 확장하기 위한 백엔드 및 프론트엔드 전체 구현 계획입니다.

---

## 1. 데이터베이스 스키마 설계 개편 (SQLite)

기존의 단일 테이블 구조에 `User` 엔티티를 추가하고, 데이터 격리를 위해 주요 비즈니스 테이블에 `user_id` 외래키(FK)를 추가합니다.

### A. 신규 테이블 추가
1. **`users` 테이블** (사용자 마스터)
   * `id` (INTEGER, Primary Key, Auto-Increment)
   * `username` (VARCHAR, Unique, Index, Nullable=False) - 로그인 아이디
   * `hashed_password` (VARCHAR, Nullable=False) - bcrypt 암호화 비밀번호
   * `created_at` (DATETIME, Default=utcnow)

2. **`user_settings` 테이블** (개인 설정 & 봇 컨트롤 통합)
   * `id` (INTEGER, Primary Key)
   * `user_id` (INTEGER, Foreign Key to `users.id`, Unique=True, Nullable=False)
   * `trade_mode` (VARCHAR, Default="SIMULATED") - `SIMULATED` / `MOCK` / `REAL`
   * `broker_provider` (VARCHAR, Default="KIS")
   * `kis_app_key` (VARCHAR, Nullable=True)
   * `kis_app_secret` (VARCHAR, Nullable=True)
   * `kis_account_no` (VARCHAR, Nullable=True)
   * `telegram_bot_token` (VARCHAR, Nullable=True)
   * `telegram_chat_id` (VARCHAR, Nullable=True)
   * `telegram_enabled` (BOOLEAN, Default=False)
   * `is_running` (BOOLEAN, Default=False) - 봇 자동주행 가동 여부 (구 `BotStatus.is_running`)
   * `is_real_enabled` (BOOLEAN, Default=False) - 실전매매 잠금 스위치 (구 `BotStatus.is_real_enabled`)
   * `updated_at` (DATETIME, Default=utcnow)

> [!NOTE]
> 기존의 글로벌 싱글톤 테이블인 `system_settings` 및 `bot_status`는 완전 폐기(Drop)하고 `user_settings` 테이블 하나로 통합하여 쿼리 효율성을 높입니다.

### B. 기존 테이블 확장 (`user_id` FK 필드 추가)
* **`holdings`**: 사용자별 보유 주식 정보
* **`trade_logs`**: 사용자별 체결/주문 이력
* **`watch_lists`**: 사용자별 관심종목 풀
* **`action_logs`**: 사용자별 봇 활동 기록 로그

*※ `stock_translations` 테이블은 모든 사용자가 공유하는 글로벌 캐시이므로 `user_id` 필드를 추가하지 않습니다.*

---

## 2. 백엔드 인증 및 보안 아키텍처 (`app/core/security.py`)

FastAPI와 궁합이 좋은 JWT(JSON Web Token) 및 비밀번호 해싱 라이브러리를 탑재합니다.

### A. 의존성 패키지 설치
* `PyJWT` (JWT 토큰 인코딩/디코딩)
* `bcrypt` (비밀번호 단방향 해싱 및 검증)

### B. 공통 보안 함수 구현
* `get_password_hash(password: str) -> str`
* `verify_password(plain_password: str, hashed_password: str) -> bool`
* `create_access_token(data: dict, expires_delta: timedelta = None) -> str`

### C. FastAPI JWT 인증 의존성 주입 (`get_current_user`)
* HTTP Bearer 토큰 검증 및 만료일 체크.
* 유효한 토큰인 경우 DB에서 `User` 객체를 조회하여 각 라우터에 주입.

---

## 3. 멀티테넌트(Multi-tenant) 자율 매매 스케줄러 개편

기존의 글로벌 싱글톤 봇 스케줄러를 멀티유저 대응형으로 업그레이드합니다.

### A. 싱글 스레드 마스터 스케줄러 & 동적 멀티 루프 실행
* 스레드를 사용자마다 무분별하게 생성하지 않고, **1분 주기 마스터 타이머** 하나가 주기적으로 구동됩니다.
* 루프 진입 시, DB에서 `user_settings.is_running == True` 상태인 **모든 활성 유저 목록**을 조회합니다.
* `asyncio.gather` 또는 비동기 루프를 사용하여 활성 유저마다 **개별 독립 루프**를 실행합니다.

```python
# scheduler.py 실행 모델 예시
async def async_trading_loop():
    db = SessionLocal()
    try:
        # 1. 자동매매 가동 중인 활성 유저 설정 리스트 로드
        active_settings = db.query(UserSettings).filter(UserSettings.is_running == True).all()
        
        # 2. 각 유저별 독립 트레이딩 테스크 병렬 실행
        tasks = [run_user_trading_flow(setting.user_id) for setting in active_settings]
        await asyncio.gather(*tasks)
    finally:
        db.close()
```

### B. 컨텍스트 및 주입 모델 (Dynamic Context Injection)
* `run_user_trading_flow(user_id)` 내부에서는 전역 `settings` 객체 대신 **해당 유저의 `UserSettings` 레코드**를 로드하여 임시 브로커 인스턴스(`BrokerFactory.get_client(user_settings)`)를 생성합니다.
* 매수, 매도, DB 기록(`Holding`, `TradeLog`, `ActionLog`) 등의 로직은 모두 해당 `user_id`를 명시적으로 타게팅하여 격리 수행됩니다.

---

## 4. 프론트엔드 (Next.js 15) 인증 & UI 개편

### A. 페이지 라우팅 및 가드 추가
* **`/login` & `/signup`**: 프리미엄 다크 모드 기반의 고품격 로그인 및 회원가입 페이지 신설.
* **미들웨어/인터셉터**: 토큰이 없거나 만료된 경우 비로그인 사용자를 자동으로 `/login`으로 리다이렉트 처리.

### B. API 요청 모듈 헤더 바인딩 (`frontend/lib/api.ts`)
* 로컬스토리지 또는 쿠키에 JWT 토큰을 저장하고, 모든 Axios/Fetch API 요청 헤더에 `Authorization: Bearer <token>`을 자동으로 동적으로 주입합니다.

### C. 설정 및 대시보드 연동
* 대시보드 메인 화면 및 `/admin/settings` 페이지 진입 시, 현재 로그인한 사용자의 정보를 요청하여 개인화된 UI 및 잔고를 노출합니다.

---

## 5. 단계별 검증 시나리오

1. **로그인 가드 검증**: 토큰 없이 `/`, `/scanner`, `/admin/settings` 접근 시 `/login`으로 튕기는지 확인.
2. **동시성 자율 매매 검증**: UserA(SIMULATED 모드)와 UserB(MOCK 모드)가 동시에 자동매매 봇을 켰을 때, 백엔드 타이머가 두 유저의 계좌를 각각 정상적이고 완벽하게 격리하여 스캔 및 거래를 체결시키는지 확인.
3. **텔레그램 알림 격리**: 각자의 텔레그램 봇 토큰과 챗 ID로 개별 알림이 전송되는지 검증.
