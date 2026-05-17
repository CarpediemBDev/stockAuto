# StockAuto 시스템 매뉴얼 (System Manual)

본 문서는 StockAuto 자동매매 시스템의 전체 구조와 소스 코드 구성을 설명하는 최종 기술 매뉴얼입니다.

## 📂 프로젝트 파일 맵

### 1. 백엔드 코어 모듈 (`/backend/app/core`)

- **`config.py`**: `.env` 환경 변수를 부모 경로 추적을 통해 안정적으로 로드하여 실전/모의 거래 환경을 설정합니다.
- **`database.py`**: SQLAlchemy 기반 DB 연결 설정 및 SQLite 경로를 프로젝트 루트 절대 경로로 자동 오차 보정합니다.
- **`models.py`**: 모든 SQLAlchemy DB 테이블 모델 중앙 관리 (`TradeLog`, `Holding`, `ActionLog`, `BotStatus`, `WatchList`, `StockTranslation`).
- **`exceptions.py`**: 표준 규격 전역 예외 처리 핸들러 (`StockAutoException`).
- **`response.py`**: 프론트엔드 통신용 성공 API JSON 응답 포맷 통일 헬퍼.

### 2. 백엔드 도메인 패키지 (`/backend/app`)

- **`main.py`**: 서비스 기동 및 Lifespan 시작점. 핫 번역 메모리 캐시 및 백그라운드 봇 스케줄러 자동 가동.
- **`translations/`**: 번역 도메인. 어드민 CRUD API(`router.py`) 및 RAM 싱글톤 핫 캐시 기반 번역기(`translator.py`).
- **`watchlist/`**: 관심종목 도메인. 종목 추가/삭제 및 신규 주식 등록 시 한글 번역 자동 연동 자가학습 API(`router.py`).
- **`scanner/`**: 스캐너 도메인. 최신 봇 시그널 제공 API(`router.py`) 및 QQQ 나스닥 지수 기반의 2-Stage expert 필터 핵심 스캔 모듈(`scanner.py`).
- **`bot/`**: 자동매매 제어 도메인. 봇 구동 제어 API(`router.py`), 하이브리드 트레이딩 메인 루프 스케줄러(`scheduler.py`), 한국투자증권 API 통신 및 보안 서명 클라이언트(`kis_api.py`).
- **`trades/`**: 거래 및 계좌 도메인. 실시간 매매 및 시스템 활동 로그 API(`router_trades.py`), 실시간 계좌 잔고 및 보유 종목 API(`router_account.py`), 지수 및 시장 종합 센티먼트 API(`router_market.py`).

### 4. 프론트엔드 대시보드 (`/frontend`)

- **`components/MarketHeader.tsx`**: 실시간 시장 지수 및 심리 상태 표시.
- **`components/PortfolioView.tsx`**: 보유 종목 현황 및 트레일링 스탑 시각화.
- **`components/BotSignals.tsx`**: 봇이 실시간 탐지한 상위 시그널 표시 (Bot's View).
- **`components/ManualWatchList.tsx`**: 사용자 등록 관심종목 및 개별 점수 표시 (User's View).
- **`components/LiveLogViewer.tsx`**: 봇 활동 내역 실시간 터미널 뷰.

## ⚙️ 시스템 핵심 동작 원리

1. **인증**: 모든 통신은 `kis_api.py`에서 OAuth 2.0 및 Hashkey 보안 과정을 거쳐 처리됩니다.
2. **분석**: `scanner.py`가 전체 시장 상황을 먼저 판단(Sentiment Check)한 후 개별 종목을 정밀 분석합니다.
3. **매매**: `TRADING_STRATEGY.md`에 정의된 하이브리드 전략에 따라 `scheduler.py`가 자율적으로 판단하여 주문을 전송합니다.
4. **모니터링**: 봇의 모든 판단 과정은 `ActionLog`에 기록되어 대시보드에 실시간으로 출력됩니다.

## 🌐 실시간 AI 자가학습 번역 시스템 (Self-Learning i18n System)

StockAuto는 8,000개가 넘는 나스닥 상장 주식의 한글명을 자동으로 번역하고 최적화하여 보관하는 독자적인 자가학습 캐싱 시스템을 제공합니다.

### 🔄 데이터 조회 및 자동 학습 파이프라인
신규 종목(예: `CTNT`)이 추가되거나 조회될 때 시스템은 아래의 4단계 파이프라인을 거치며 **0ms 속도로 초고속 서빙 및 자가학습**을 수행합니다:

1. **1단계: 메모리 캐시 조회 (0ms)**
   - 백엔드 RAM 내부에 상주하고 있는 핫 캐시(`Translator._cache`)에서 즉시 조회하여 반환합니다.
2. **2단계: 로컬 DB 조회 및 메모리 캐시 동적 싱크**
   - 메모리에 없을 경우 로컬 SQLite DB (`StockTranslation` 테이블)를 쿼리하여 번역을 획득하고, 이를 메모리 캐시에 적재하여 다음 요청부터는 0ms로 서빙되도록 만듭니다.
3. **3단계: 미국 금융 데이터 실시간 추적 (yfinance Fallback)**
   - DB에도 없을 경우 실시간으로 yfinance를 통해 미국의 주식 상장 데이터베이스에 접속하여 실상장 여부를 검증하고, 영문 법인명(ShortName/LongName)을 가져옵니다.
4. **4단계: AI 실시간 번역 및 자가학습 캐싱 가동**
   - 불필요한 법인 꼬리표(예: `Inc.`, `Corp.`, `Ltd.`, `plc.`)를 정규식으로 안전하게 도려낸 뒤, **Google Translation OpenAPI**를 연동하여 깔끔한 한글 주식명(예: `치타넷 공급망 서비스`)으로 번역합니다.
   - 번역된 결과를 로컬 DB에 영구 기록(자가학습)하고, 메모리 캐시에도 즉각 동기화하여 평생 보관합니다.

### 🎁 시스템 전역 낙수 효과 (Cascade Effect)
이 자가학습 번역기(`Translator.translate`)는 전역 미들웨어 형태로 캡슐화되어 있습니다. 따라서 **관심종목(Watchlist)**, **마켓 스캐너(Market Scanner)**, **트레이딩 봇 매매 일지** 등 어떤 모듈에서든 신규 주식을 건드리는 즉시 단 한 번의 번역만으로 시스템 전체가 한글 이름 혜택을 동시에 누립니다.


## 🚀 시스템 실행 방법 (System Execution)

### 1. 백엔드 실행 (Backend Startup)

백엔드는 **모듈형 레이어드 아키텍처**로 구성되어 있으므로, `/backend` 폴더에서 `app` 패키지 진입점을 지정하여 실행해야 합니다.

```bash
# 가상환경 활성화 후 실행
uvicorn app.main:app --host 0.0.0.0 --reload
```

> [!IMPORTANT]
> 루트에 남겨진 레거시 `backend/main.py`가 아닌, 반드시 **`app.main:app`** 경로를 지정해 주어야 임포트 에러가 발생하지 않습니다.

### 2. 프론트엔드 실행 (Frontend Startup)

`/frontend` 폴더에서 실행합니다.

```bash
npm run dev
```

---

> 상세한 트레이딩 전략 규칙은 [TRADING_STRATEGY.md](file:///d:/dev/workspace/stockAuto/docs/TRADING_STRATEGY.md)를 참고하세요.
> Vue 개발자를 위한 React Hooks 직관 가이드는 [REACT_GUIDE.md](file:///d:/dev/workspace/stockAuto/docs/REACT_GUIDE.md)를 참고하세요.
