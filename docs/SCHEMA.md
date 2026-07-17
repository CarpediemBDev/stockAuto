# 📋 StockAuto 데이터베이스 스키마 명세서 (Schema Specification)

본 문서는 StockAuto 자동매매 시스템의 데이터베이스 관계 모델 및 테이블 상세 규격을 기술합니다.
시스템은 사용자별 멀티테넌시(Multi-tenancy)를 지원하며, Alembic 자동 부트스트래핑 시스템을 통해 서버 기동 시 스키마가 자율적으로 마이그레이션 및 동기화됩니다.

---

## 🗺️ 1. 관계형 데이터 모델 개요 (ERD Outline)

```mermaid
erDiagram
    users ||--|| user_settings : "1:1 Has"
    users ||--o{ holdings : "1:N Owns"
    users ||--o{ trade_logs : "1:N Generates"
    users ||--o{ action_logs : "1:N Writes"
    users ||--o{ watch_lists : "1:N Tracks"

    users {
        int id PK
        string username UK
        string hashed_password
        datetime created_at
    }

    strategies {
        string strategy_type PK
        string name_ko
        string name_en
        string description
        boolean is_active
        string tier
        string regime
        string summary_ko
        int sort_order
        boolean is_selectable
    }

    user_settings {
        int id PK
        int user_id FK
        string trade_mode
        string broker_provider
        string kis_app_key
        string kis_app_secret
        string kis_account_no
        string telegram_chat_id
        boolean telegram_enabled
        boolean is_running
        datetime updated_at
    }

    holdings {
        int id PK
        int user_id FK
        string ticker INDEX
        string ticker_name
        float avg_price
        int quantity
        float highest_price
        float last_price
        datetime last_price_updated_at
        string regime_mode
        int buy_stage
        datetime updated_at
    }

    trade_logs {
        int id PK
        int user_id FK
        string ticker INDEX
        string ticker_name
        string trade_type
        float price
        int quantity
        string order_no
        string regime_mode
        int signal_score
        datetime executed_at
    }

    action_logs {
        int id PK
        int user_id FK
        string level
        string message
        datetime created_at
    }

    watch_lists {
        int id PK
        int user_id FK
        string ticker INDEX
        string ticker_name
        datetime added_at
    }

    stock_translations {
        int id PK
        string ticker UK
        string name_ko
    }
```

---

## 🗂️ 2. 테이블 상세 명세 (Table Specifications)

### ① `users` (사용자 계정 정보)
사용자 가입 및 인증 처리를 위한 핵심 테이블입니다.
* `id` (INTEGER, PK): 기본 키
* `username` (VARCHAR, Unique, Index): 사용자 고유 아이디 (로그인 ID)
* `hashed_password` (VARCHAR): Bcrypt 암호화 처리된 비밀번호 해시값
* `created_at` (DATETIME): 가입 일시

### ② `strategies` (전략 카탈로그 메타데이터)
사용자가 선택할 수 있는 자동매매 전략 목록과 속성을 관리합니다.
* `strategy_type` (VARCHAR, PK, Index): 전략 고유 키 (예: `complex`, `senior_simple`)
* `name_ko` (VARCHAR): 전략 한글 표시명
* `name_en` (VARCHAR, Nullable): 전략 영문 표시명
* `description` (TEXT, Nullable): 전략 상세 설명 (Markdown)
* `is_active` (BOOLEAN, Default: True): 전략 사용 가능 여부 (전역 비활성화 스위치)
* `tier` (VARCHAR, Default: 'single'): 전략 등급 (`gold`, `silver`, `bronze`, `sandbox`, `single`)
* `regime` (VARCHAR, Default: 'ALL'): 활성 장세 (`ALL`, `BULLISH`, `BEARISH`, `NEUTRAL`)
* `summary_ko` (TEXT, Nullable): UI 카드에 표시될 한 줄 요약
* `sort_order` (INTEGER, Default: 0): 카탈로그 화면 정렬 순서
* `is_selectable` (BOOLEAN, Default: True): 카탈로그 화면에 사용자 선택용으로 노출할지 여부 (슬롯형이나 내부용은 False)

### ③ `user_settings` (사용자별 통합 설정)
사용자 개인별 트레이딩 모드, 증권사 API Key, 텔레그램 연동 및 봇 기동 제어 스위치를 관리합니다.
* `id` (INTEGER, PK): 기본 키
* `user_id` (INTEGER, FK -> `users.id`, Unique): 사용자 외래 키 (1:1 관계, CASCADE 삭제)
* `trade_mode` (VARCHAR, Default: 'SIMULATED'): 현재 매매 모드 (`SIMULATED`, `MOCK`, `REAL`)
* `broker_provider` (VARCHAR, Default: 'KIS'): 증권사 연동 벤더 (`KIS` 등)
* `kis_app_key` (VARCHAR, Nullable): 한국투자증권 APP Key (암호화 권장)
* `kis_app_secret` (VARCHAR, Nullable): 한국투자증권 APP Secret (암호화 권장)
* `kis_account_no` (VARCHAR, Nullable): 한국투자증권 계좌번호
* `telegram_chat_id` (VARCHAR, Nullable): 텔레그램 CHAT ID
* `telegram_enabled` (BOOLEAN, Default: False): 텔레그램 알림 활성화 여부
* `is_running` (BOOLEAN, Default: False): 사용자가 선택한 자동매매 실행 의도. 주문 처리·재조정·강제 청산은 이 값을 자동으로 변경하지 않습니다.
* `updated_at` (DATETIME): 마지막 갱신 시간

### ③ `trade_logs` (매매 체결 기록)
봇이 자동 또는 수동으로 집행한 매수/매도 이력을 관리하는 테이블입니다.
* `id` (INTEGER, PK): 기본 키
* `user_id` (INTEGER, FK -> `users.id`): 사용자 외래 키 (CASCADE 삭제)
* `ticker` (VARCHAR, Index): 종목 영문 티커 (예: `AAPL`, `TSLA`)
* `ticker_name` (VARCHAR): 종목명 (한글 번역명 우선 저장)
* `trade_type` (VARCHAR): 거래 유형 (`BUY` 또는 `SELL`)
* `price` (FLOAT): 체결 가격 (USD)
* `quantity` (INTEGER): 체결 수량
* `order_no` (VARCHAR, Nullable): 증권사 주문 ID (JTTT3010R/VTTS3010R 등 매핑용)
* `regime_mode` (VARCHAR, Nullable): ⭐ **[v2.0]** 진입 시점의 QQQ 장세 레짐 (`BULLISH`, `BEARISH`, `NEUTRAL`)
* `signal_score` (INTEGER, Nullable): ⭐ **[v2.0]** 스캔 당시 퀀트 필터 채점 점수 (80점~100점)
* `executed_at` (DATETIME): 체결 일시

### ④ `holdings` (보유 종목 및 트레일링 스탑)
사용자가 현재 보유하고 있는 주식 자산 및 피라미딩 평단가, 트레일링 스탑 추적용 테이블입니다.
* `id` (INTEGER, PK): 기본 키
* `user_id` (INTEGER, FK -> `users.id`): 사용자 외래 키 (CASCADE 삭제)
* `ticker` (VARCHAR, Index): 종목 영문 티커
* `ticker_name` (VARCHAR): 종목명
* `avg_price` (FLOAT): 매수 평단가 (피라미딩 시 가중평균 갱신)
* `quantity` (INTEGER): 보유 수량
* `highest_price` (FLOAT): **매수 이후 최고가 (Trailing Stop 고점 기준점)**
* `last_price` (NUMERIC(20,4), Nullable): 스케줄러가 관측·영속화한 최근 현재가 (`avg_price`와 동일한 USD 기준). 유저 대면 잔고/보유종목 API가 외부 시세 호출 없이 평가금을 계산하는 원천.
* `last_price_updated_at` (DATETIME, Nullable): `last_price` 관측 시각. 백그라운드 잡이 10분 이상 낡은 종목만 벌크 시세로 재갱신하는 신선도 기준.
* `regime_mode` (VARCHAR, Nullable): ⭐ **[v2.0]** 최초 진입 당시 장세 레짐
* `buy_stage` (INTEGER, Default: 1): ⭐ **[v2.0]** 후지모토 시게루식 1:2:6 피라미딩 매수 단계 (1=정찰, 2=확인, 3=승부)
* `updated_at` (DATETIME): 마지막 보유 현황 동기화 일시
* *제약 조건:* 동일 사용자가 동일 티커를 중복 보유할 수 없도록 복합 유니크 제약(`user_id`, `ticker`) 적용.

### ⑤ `action_logs` (실시간 봇 활동 로그)
사용자 계정별 봇의 타점 포착, 매매 판단, 에러 통신 등 실시간 동작 로그를 기록합니다.
* `id` (INTEGER, PK): 기본 키
* `user_id` (INTEGER, FK -> `users.id`): 사용자 외래 키 (CASCADE 삭제)
* `level` (VARCHAR, Default: 'INFO'): 로그 등급 (`INFO`, `WARN`, `ERROR`, `SIGNAL`)
* `message` (VARCHAR): 세부 활동 로그 내용
* `created_at` (DATETIME): 로그 생성 일시

### ⑥ `watch_lists` (관심 종목 리스트)
사용자가 모니터링 대상으로 지정하여 마켓 스캐너에서 집중 분석하게 유도하는 종목 리스트입니다.
* `id` (INTEGER, PK): 기본 키
* `user_id` (INTEGER, FK -> `users.id`): 사용자 외래 키 (CASCADE 삭제)
* `ticker` (VARCHAR, Index): 관심 등록한 종목 영문 티커
* `ticker_name` (VARCHAR, Nullable): 관심 종목 한글 번역명
* `added_at` (DATETIME): 등록 일시
* *제약 조건:* 동일 사용자가 동일 티커를 관심 목록에 이중 추가하지 못하도록 복합 유니크 제약(`user_id`, `ticker`) 적용.

### ⑦ `stock_translations` (글로벌 한글 번역 사전)
글로벌 시장 전체 종목의 영문 티커와 매핑되는 완성형 한글명을 관리하는 테이블입니다. **사용자 불문 시스템 전역 공유 캐시** 역할을 수행합니다.
* `id` (INTEGER, PK): 기본 키
* `ticker` (VARCHAR, Unique, Index): 영문 티커 (예: `NVDA`)
* `name_ko` (VARCHAR): 완성형 한글 정식 명칭 (예: `엔비디아`)

### ⑧ `broker_orders` (증권사 주문 영구 원장)
증권사 주문 의도, 접수 번호, 누적 체결량과 DB 반영량을 저장하여 프로세스 재시작 후에도 중복 주문과 이중 체결 반영을 차단합니다.
* `user_id` (INTEGER, FK -> `users.id`): 주문 소유 사용자
* `intent_id` (VARCHAR, Unique): 증권사 전송 전에 생성되는 내부 주문 식별자
* `broker_order_no` (VARCHAR, Nullable): 증권사 접수 번호
* `status` (VARCHAR): `INTENT_CREATED`, `SUBMITTING`, `ACK_UNKNOWN`, `PENDING`, `PARTIAL`, `FILLED` 등 주문 상태
* `requested_qty`, `broker_filled_qty`, `applied_filled_qty`: 요청·증권사 누적 체결·DB 적용 수량
* `strategy_type`: 체결을 반영할 보유 전략 슬롯
* 과거 `resume_after_resolution` 컬럼은 제거되었습니다. 봇 실행 의도는 `user_settings.is_running`에서만 관리합니다.

### ⑨ `account_equity_snapshots` (계좌 자산 스냅샷)
백그라운드 스케줄러(`admin_balance_cache_sync`)가 주기 기록하는 사용자별 잔고 스냅샷입니다.
관리자 자산 곡선뿐 아니라 **유저 대면 `GET /account/balance`의 유일한 읽기 소스**로 사용되어, 대시보드 조회 경로에서 외부 증권사/시세 API 호출을 제거합니다.
* `user_id` (INTEGER, FK -> `users.id`): 사용자 외래 키 (CASCADE 삭제)
* `total_asset`, `cash_balance`, `stock_balance` (NUMERIC(20,4)): 총자산·예수금·주식 평가금 (KRW)
* `profit_rate` (NUMERIC(20,4), Nullable): 수익률(%)
* `profit_loss` (NUMERIC(20,4), Nullable): 평가손익 (KRW, 대시보드 표시용)
* `fx_rate` (NUMERIC(20,4), Nullable): 기록 당시 USD/KRW 환율
* `trade_mode` (VARCHAR): 기록 당시 모드 (`SIMULATED`/`MOCK`/`REAL`). **조회 시 반드시 현재 모드로 필터**하여 모드 전환 시 잔고가 섞이지 않게 합니다.
* `captured_at` (DATETIME, Index): 기록 시각. API 응답에 포함되어 프론트 신선도 배지의 기준이 됩니다.
* *보존 정책:* 사용자·모드별 최신 500건 유지, 평시 60초 dedup (체결·초기화·청산 직후에는 `force=True`로 즉시 기록).

---

## 💾 3. 클라우드 배포 시 데이터 영속성 관리 (Data Persistence)

Google Cloud Run은 **무상태(Stateless) 서버리스 환경**이므로 인스턴스가 재생성되거나 종료될 때 컨테이너 로컬 파일(`stockauto.db`)이 유실됩니다. 데이터 보전을 위해 아래 2가지 솔루션을 지원합니다.

### 💡 옵션 A: Google Cloud Storage (GCS) 볼륨 FUSE 마운트 (권장)
* Cloud Run 서비스 구성에서 **[볼륨(Volumes)] ➔ [Google Cloud Storage]**를 마운트하여 `/app/db/`에 전용 버킷을 바인딩합니다.
* 데이터베이스 경로를 `/app/db/stockauto.db`로 세팅하여 안전하게 로컬 비용으로 상태를 영구 저장합니다.

### 🚀 옵션 B: 외부 RDB 연동 (Google Cloud SQL)
* 고가용성 멀티 인스턴스 스케일링 환경이 필요할 경우, `backend/app/core/database.py`에서 환경변수 `DATABASE_URL`을 통해 외부 **Google Cloud SQL PostgreSQL** 등으로 접속 주소를 즉시 치환하여 연동할 수 있도록 설계되어 있습니다.
