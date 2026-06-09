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

### ② `user_settings` (사용자별 통합 설정)
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
* `is_running` (BOOLEAN, Default: False): 백그라운드 봇 스케줄러 가동 여부
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

---

## 💾 3. 클라우드 배포 시 데이터 영속성 관리 (Data Persistence)

Google Cloud Run은 **무상태(Stateless) 서버리스 환경**이므로 인스턴스가 재생성되거나 종료될 때 컨테이너 로컬 파일(`stockauto.db`)이 유실됩니다. 데이터 보전을 위해 아래 2가지 솔루션을 지원합니다.

### 💡 옵션 A: Google Cloud Storage (GCS) 볼륨 FUSE 마운트 (권장)
* Cloud Run 서비스 구성에서 **[볼륨(Volumes)] ➔ [Google Cloud Storage]**를 마운트하여 `/app/db/`에 전용 버킷을 바인딩합니다.
* 데이터베이스 경로를 `/app/db/stockauto.db`로 세팅하여 안전하게 로컬 비용으로 상태를 영구 저장합니다.

### 🚀 옵션 B: 외부 RDB 연동 (Google Cloud SQL)
* 고가용성 멀티 인스턴스 스케일링 환경이 필요할 경우, `backend/app/core/database.py`에서 환경변수 `DATABASE_URL`을 통해 외부 **Google Cloud SQL PostgreSQL** 등으로 접속 주소를 즉시 치환하여 연동할 수 있도록 설계되어 있습니다.
