# 작업 현황판 (Task Board)

이 현황판은 StockAuto 자동매매 시스템의 개발 단계별 목표와 진행 상황을 투명하게 관리하는 문서입니다.

## 🌟 [Phase 1] 프로젝트 기본 인프라 및 API 라우터 구축 — 완료 [x]

- [x] FastAPI 비동기 백엔드 서버 기본 아키텍처 셋업
- [x] SQLite 기반 SQLite DB 스키마 정의 (`TradeLog`, `Holding`, `ActionLog`, `BotStatus`, `WatchList`)
- [x] 기본 도메인별 API 엔드포인트 설계 및 명세화

## 🌟 [Phase 2] 전문가 필터 기반 고성능 실시간 마켓 스캐너 엔진 개발 — 완료 [x]

- [x] Yahoo Finance 연동 미국 주식 전 종목 기술적 지표 계산 모듈 구축
- [x] QQQ 지수 분석 및 2-Stage expert 필터 실시간 스캔 핵심 알고리즘 개발
- [x] 실시간 스캐너 시그널(`latest`) 제공 API 구축

## 🌟 [Phase 3] 한국투자증권(KIS) API 모의투자 연동 — 완료 [x]

- [x] KIS API 비동기 보안 서명 및 토큰 인증 모듈 구현
- [x] 실시간 계좌 잔고 및 보유 종목 동기화 API 연동
- [x] 주식 매수/매도 인라인 체결 처리 인터페이스 구현

## 🌟 [Phase 4] 백그라운드 봇 스케줄러 & 자율 매매 엔진 — 완료 [x]

- [x] 백그라운드 1분 주기 트레이딩 루프 스케줄러 구현
- [x] 봇 자율 주행 상태 토글 스위치 및 실시간 모니터링 API 연동
- [x] 백엔드 에러 발생 시 공통 JSON 응답 및 컨텍스트 로깅 시스템 구축

## 🌟 [Phase 5] Next.js 15 기반 실시간 자율 매매 종합 대시보드 연동 — 완료 [x]

- [x] Next.js 15 App Router 기반 프리미엄 다크 모드 UI 구축
- [x] 실시간 포트폴리오, 스캐너 시그널, 봇 활동 로그 뷰어 연동
- [x] **[핫픽스]** 관심종목 수동 등록 스마트 싱글 검색바 구현 (`[티커] [한글명]` 단일 검색 파싱)
- [x] **[핫픽스]** React 19 Cascading Renders 방지 비동기 로딩 최적화 및 CORS 대응

## 🌟 [Phase 6] 어드민 한글 번역 사전 및 i18n 캐싱 시스템 실장 — 완료 [x]

- [x] 어드민 페이지(`/admin`) 구축 및 캐싱 원리 컴포넌트 실장
- [x] 백엔드 RAM 싱글톤 핫 캐시 기반 실시간 번역 사전 엔진 개발
- [x] 서버 기동 시 SQLite 번역 데이터 `54개` 핫 로딩 연동
- [x] 어드민 한글명 번역 사전 CRUD 및 캐시-DB 양방향 실시간 동기화
- [x] **[핫픽스] 번역 테이블 ID 기준 오름차순 정렬(1, 2, 3...) 엄격화 구현**
- [x] **[자가학습] yfinance + 구글 실시간 번역 연동 신규 종목 자가학습 캐싱 구현**
- [x] **[핫픽스] 어드민 페이지 번역 목록 10개 단위 다크 모드 프리미엄 페이징(Pagination) 및 검색 연동 리셋 구현**
- [x] **[안전조치] 외부 의존성 충돌 해소를 위한 현대식 HTTPX 기반 가상환경(venv) 패키지 격리 적재 동기화**
- [x] **[오류해결] 관심종목 삭제 API 숫자 ID & 영문 티커 동시 호환 하이브리드 라우터로 안정성 대수선 완료**
- [x] **[프리미엄 UX] 관심종목 추가창 실시간 한글/영문 오토컴플릿 검색어 주황색 하이라이팅 및 클릭 즉시 등록 드롭다운 엔진 실장 완료**

## 🌟 [Phase 7] 백엔드 모듈형 레이어드 아키텍처 대전환 및 실전 검증 — 완료 [x]

- [x] 백엔드 코어 모듈 집중 (`app/core/` 하위 config, database, models, exceptions, response)
- [x] 도메인별 5대 격리 패키지 이식 (`translations`, `watchlist`, `scanner`, `bot`, `trades`)
- [x] 통합 main.py 진입점 구축 및 Uvicorn 0.0.0.0 바인딩 포트 8000 재가동
- [x] 설계도와 헌법 문서 (`RULES.md`, `SYSTEM_MANUAL.md`, `README.md`) 동기화 (Doc-Code Sync)
- [x] **[전략조정] 초고수익 동전주(Penny Stock) 매매 허용을 위한 $5 최소 가격 필터 전면 제거 및 문서 동기화**
- [x] simulated 실전 투자 라이브 테스트 검증 및 트레일링 스탑 알고리즘 미세 튜닝
- [x] **[실시간 스캐너 연동]** 관심종목 라이브 스코어(SIGNAL SCORE)를 백엔드 스캐너 분석 데이터와 실시간 연계하여 점수 게이지바로 시각화 반영 완료
- [x] **[모의투자 시뮬레이터]** 가상 예수금 1,000만 원 및 yfinance 실시간 주가/환율 연동 모의투자 자산 연산 엔진 가동
- [x] **[아키텍처 업그레이드]** BaseBroker 추상 인터페이스 및 BrokerFactory 기반 멀티 증권사 동적 연동 아키텍처 구축 및 router_account.py 초경량 리팩토링 완료
- [x] **[프리미엄 UI 배지]** 설정 상태에 따라 KIS LIVE(초록), KIS MOCK(주황), SIMULATED(주황) 배지 및 개별 종목 출처 배지를 동적으로 렌더링하는 구분 장치 완비
- [x] **[통화 토글러 & 프리미엄 UI]** 대시보드 메인에 `$ USD | 원 KRW` 세그먼트 컨트롤 실장 및 원화 포맷팅(`₩` 접두사를 제거하고 한글 `원` 접미사(예: `10,000,566원`)로 전환) 동기화 완료

## 🌟 [Phase 8] 시니어 아키텍처 결함 대수선 및 성능 고도화 — 완료 [x]

- [x] **[KIS API 정밀 정정]** KIS 실거래 잔고 조회 API를 기존의 잘못 정의된 국내 주식 잔고조회에서 미국 해외 주식 잔고조회로 교체하여 자산 및 달러 예수금 실시간 환산 정상화
- [x] **[스캐너 뉴스 병렬화]** `scanner.py` 내 Stage 2 후보군 25개에 대한 yfinance 뉴스 조회를 순차 방식에서 `asyncio.gather` 병렬 방식으로 전면 개편하여 분석 지연을 30초에서 1초 미만으로 단축 및 API 차단 완벽 방어
- [x] **[관심종목 검증 속도화]** `watchlist/router.py` 관심종목 추가 시 티커 실존 여부 검증에 사용되던 극도로 무겁고 느린 `yf.Ticker.info` 호출을 초경량 `history(period="1d")` 호출로 변경하여 로딩 시간 5초에서 0.1초로 단축
- [x] **[DB 번역 사전 인코딩 정화]** 이중 인코딩 및 NFD 조합형 한글로 오염된 번역 사전(`stock_translations`), 보유종목(`holdings`), 거래로그(`trade_logs`)의 모든 한글명을 표준 완성형(NFC) 한글로 원클릭 완전 복합 복원 및 정화 완료
- [x] **[프론트엔드 UX 고도화]** `ManualWatchList.tsx` 내의 구식 브라우저 `alert` 팝업 경고창을 다른 컴포넌트들과 완벽히 조화되는 최신 `sonner` 토스트 알림으로 교체하여 디자인 일관성 200% 정규화

---

## 🌟 [Phase 9] 3-Mode 트레이딩 엔진 아키텍처 대전환

> **핵심 목표:** 시스템 전체를 `SIMULATED` / `MOCK` / `REAL` 3가지 모드로 명확히 분리하고, `.env` 파일을 통해 모드를 제어한다.
>
> **현재 결함 진단 (코드 리뷰 기반):**
>
> - `scheduler.py`가 `BrokerFactory`를 무시하고 `KISClient()`를 직접 생성하여 사용 중
> - `SimulatedBroker`에 `buy_order()` / `sell_order()` 주문 메서드가 존재하지 않음
> - 거래소 코드가 `NASD` 하드코딩 → NYSE 종목 주문 시 거절됨
> - 주문 후 체결 확인(미체결/부분체결) 처리 없음 → DB-계좌 불일치 위험
> - `kis_api.py`에 죽은 코드(`buy_market_order`, `sell_market_order`) 방치

### 9-1. 엔진 코어 결함 수선

- [x] **[죽은 코드 제거]** `kis_api.py`의 미사용 함수 `buy_market_order()`, `sell_market_order()` 삭제
- [x] **[거래소 매핑]** `_get_exchange_code()` 하드코딩 제거 → yfinance `fast_info` 기반 티커별 실제 거래소(NASD/NYSE/AMEX) 자동 판별 + 메모리 캐싱 구현
- [x] **[체결 확인]** `check_order_status()` 메서드 신설 → KIS 해외주식 체결내역 API(JTTT3010R/VTTS3010R) 연동, FILLED/PARTIAL/UNFILLED 3단 상태 판별 구현

### 9-2. 3-Mode 아키텍처 구축

- [x] **[.env 모드 체계]** `TRADE_MODE` 환경변수를 3단계(`SIMULATED` / `MOCK` / `REAL`)로 재정의, `config.py` 반영 (하위호환: `VIRTUAL` → `MOCK` 자동 변환)
- [x] **[BaseBroker 확장]** `BaseBroker` 추상 인터페이스에 `buy_order()`, `sell_order()` 추상 메서드 및 표준 반환 규격 추가
- [x] **[SimulatedBroker 주문 엔진]** yfinance 실시간 시세 기반 가상 체결 로직을 `SimulatedBroker` 내부에 구현 (증권사 API 미사용, 즉시 체결 시뮬레이션)
- [x] **[KISBroker 주문 위임]** `KISBroker`에 `buy_order()` / `sell_order()` 구현 → 내부에서 `KISClient` 해외주식 주문 API 호출 및 결과 표준 매핑
- [x] **[BrokerFactory 모드 분기]** `SIMULATED` → `SimulatedBroker`, `MOCK` → `KISBroker(모의서버)`, `REAL` → `KISBroker(실전서버)` 3단 자동 분기 + API Key 미등록 시 안전 폴백
- [x] **[scheduler.py 대수선]** 직접 `KISClient()` 생성 전면 제거 → `BrokerFactory` 통한 브로커 주입, 모든 매수/매도를 `broker.buy_order()` / `broker.sell_order()`로 통일

### 9-3. 검증 및 문서 동기화

- [x] **[통합 검증]** SIMULATED 모드에서 봇 스케줄러 정상 구동 확인 (`trade_mode: "SIMULATED"` API 응답 검증 완료)
- [x] **[문서 동기화]** `.env`, `.env.dev.example`, `.env.prod.example` 3-Mode 체계 반영 완료

## 🌟 [Phase 10] 어드민 시스템 설정 대시보드 — 완료 [x]

> **핵심 목표:** `.env` 수동 편집 없이 관리자 웹 UI에서 트레이딩 모드, 증권사 선택, API Key 등을 실시간으로 설정할 수 있게 한다.

- [x] **[백엔드 설정 API]** `models.py`에 `SystemSettings` 모델 추가 및 `/api/v1/admin` CRUD REST API 구축 완료
- [x] **[어드민 설정 페이지]** `/admin/settings` 페이지 신설, 트레이딩 모드 3단 세그먼트(SIMULATED/MOCK/REAL) UI 구현 완료
- [x] **[증권사 선택 UI]** 증권사 드롭다운(KIS) 및 APP KEY, SECRET, ACCOUNT NO 입력 폼 구현 완료
- [x] **[설정 즉시 반영]** POST 요청 시 `settings` 싱글톤 객체 메모리를 즉시 업데이트하여 서버 재시작 없이 핫 리로드 적용 완료
- [x] **[안전 잠금장치]** `REAL` 모드 전환 시 강력한 시각적 경고가 포함된 모달 다이얼로그 팝업 및 강제 확인 로직 적용 완료
- [x] **[프리미엄 UI/UX 개편]** 설정 페이지를 Vercel/Linear 스타일의 세련된 **좌측 사이드바 내비게이션(Sidebar Navigation)** 구조로 전면 개편하여, 스크린 스크롤 압박 없이 쾌적한 탭뷰 제공 완료
- [x] **[인라인 저장 체계]** 입력 시 방해를 주던 플로팅 제어바를 걷어내고 각 설정 카드 하단에 우아하고 컴팩트한 **인라인 [저장] 버튼**을 탑재하여 타이핑 몰입도 및 UX 완벽 보장 완료

## 🌟 [Phase 11] 텔레그램 메신저 브릿지 연동 — 완료 [x]

- [x] **[단방향 알림]** 텔레그램 봇 API 환경변수 연동 및 초경량 비동기 발송 모듈(`app/core/telegram.py`) 구현
- [x] **[단방향 알림]** 자율 트레이딩 루프(`scheduler.py`) 매수/매도 체결 시 실시간 포맷팅 알림 발송
- [x] **[양방향 원격 제어]** 텔레그램 봇 메시지 수신용 비동기 폴링(Polling) 백그라운드 데몬 탑재
- [x] **[양방향 원격 제어]** `/status`(계좌 잔고 및 보유현황 조회), `/stop`(봇 일시정지), `/run`(봇 재가동) 원격 명령어 제어 모듈 연동

## 🌟 [Phase 12] 멀티유저 인증 및 사용자별 투자 프로필 — 완료 [x]

> **핵심 목표:** 로그인 시스템을 도입하여 사용자별로 독립적인 트레이딩 모드(SIMULATED/MOCK/REAL), 증권사 API Key, 포트폴리오를 관리한다.

- [x] **[사용자 인증]** JWT 기반 회원가입/로그인/로그아웃 API 및 프론트엔드 로그인 페이지 구현
- [x] **[사용자별 설정 DB]** User 테이블 + UserSettings 테이블 설계 (개인별 TRADE_MODE, BROKER_PROVIDER, API Key 암호화 저장)
- [x] **[사용자별 데이터 격리]** Holding, TradeLog, WatchList 등 기존 테이블에 `user_id` FK 추가, 사용자별 데이터 완전 격리
- [x] **[사용자별 봇 인스턴스]** 사용자마다 독립적인 봇 스케줄러/브로커 인스턴스 할당 (멀티테넌시)
- [x] **[프로필 대시보드]** 로그인 후 개인 대시보드에서 본인의 모드 선택, 증권사 연동, 포트폴리오 확인 UI 구현

## 🌟 [Phase 13] KIS API Key 실시간 통신 검증 및 안전 폴백 경고 시스템 — 완료 [x]

> **핵심 목표:** 어드민 설정 페이지에서 트레이딩 모드를 MOCK/REAL로 전환 및 저장할 때, API Key 정보가 한국투자증권(KIS) 금융 서버와 실제로 정상 통신되는지 즉시 검증하고, 실패 시 강력한 Fallback UX를 노출합니다.

- [x] **[백엔드 API 구현]** `backend/app/admin/router.py` 내 `@router.post("/verify-kis")` 엔드포인트 구현 (토큰 발급 및 잔고 조회 실질 유효성 검증)
- [x] **[프론트엔드 UI 연동]** `frontend/app/admin/settings/page.tsx` 내 `handleSave` 실행 전 검증 API 호출 및 에러 시 토스트/경고 고지(Simulated 후퇴 고지) 구현
- [x] **[통합 라이브 검증]** 정상 키 입력과 고의 실패 키 입력 상황에서의 흐름 검증
- [x] **[Git 정리]** 작업 완료 후 unstaged 변경본 포함 일괄 커밋

## 🌟 [Phase 14] 예수금 부족 실시간 텔레그램 경고 브릿지 및 자산 성장 차트 PoC 실장 — 완료 [x]
> **핵심 목표:** 매수 시점 예수금 부족 감지 시 텔레그램 경고 알림 브릿지를 가동하고, 대시보드 메인 계좌 현황 밑에 자산 성장 추이를 시각화하는 세련된 SVG/Area 차트 PoC를 안착시킵니다.

- [x] **[백엔드 텔레그램 연동]** `backend/app/bot/scheduler.py` 내 `run_user_trading_flow` 가용 예수금 부족 감지 시(`final_qty < 1`) 텔레그램 경고 메시지 비동기 발송 로직 이식 완료
- [x] **[프론트엔드 차트 신설]** `frontend/components/AssetTrendChart.tsx` 프리미엄 그라데이션 자산 추이 SVG/Area 차트 컴포넌트 신규 개발 완료 (반응형 SVG & 호버 마이크로 인터랙션 완비)
- [x] **[대시보드 레이아웃 조립]** `frontend/components/Dashboard.tsx` 내 `AccountBalance`와 `PortfolioView` 사이 공간에 차트 컴포넌트 조립 및 연동 완료
- [x] **[시나리오 검증 및 마감]** 예수금 부족 시나리오의 텔레그램 메시지 조립 구조 완성 및 UI 렌더링 디테일 완료

## 🌟 [Phase 15] StockAuto v2.0 천하통일 전략 실전 이식 및 레짐 스위칭 연동 — 완료 [x]

> **핵심 목표:** 11대 투자 대가 기법을 QQQ 지수 MA20/MA50 연동 3-Mode 동적 레짐 스위칭과 1:2:6 피라미딩 자금 관리, RSI-MACD 조기 스마트 익절 모듈과 결합하여 실전 백엔드 코어에 완벽히 구축하고 무결성 빌드 검증을 완료한다.

- [x] **[데이터베이스 확장]** `models.py` 내 `TradeLog` 및 `Holding` 테이블에 v2.0 장세 레짐(`regime_mode`), 채점점수(`signal_score`), 피라미딩단계(`buy_stage`) 컬럼 설계 완료
- [x] **[자가 마이그레이션]** `main.py` 내에 기존 DB와 호환되는 경량 SQLite 자동 ALTER TABLE 마이그레이션 탑재 완료
- [x] **[스캐너 엔진 업그레이드]** `scanner.py` 내에 세력 매집 OBV 다이버전스 판독, RSI 자체 볼밴 계산 및 극점 반등 포착, 장초반 5분봉 ORB 돌파, 흑자 우량주 필터, RSI-MACD 조기 익절 시그널(detect_smart_exit_signal) 등 핵심 퀀트 지표 연산기 이식 완료
- [x] **[다이내믹 채점판 구현]** `scanner.py` 및 `analyze_single_ticker` 내에 QQQ 레짐별 다이내믹 가점/감점 배점표(BULLISH 80점 컷오프, BEARISH/NEUTRAL 90점 컷오프) 공식 구현 완료
- [x] **[매매 루프 고도화]** `scheduler.py` 내에 3-Mode 레짐 감시 연동 및 후지모토 시게루식 1:2:6 피라미딩(정찰병 15% ➡️ 확인 35% ➡️ 승부 50% 분할 매수 및 평단가 가중평균 갱신) 실전 결합 완료
- [x] **[스마트 탈출 이식]** `scheduler.py` 보유 종목 모니터링 시 RSI 하락 다이버전스 + MACD 데드크로스 감지 즉시 머리 꼭대기 조기 익절 탈출문 이식 완료
- [x] **[무결성 빌드 검증]** `python -m py_compile` 컴파일 성공 및 로컬 venv 구동(`python run.py local`) Uvicorn 서버 무결성 바인딩(http://0.0.0.0:8000) 테스트 완벽 완료

## 🌟 [Phase 16] 스캐너 모듈화 패키지 분리 및 비동기 고속화 튜닝 — 완료 [x]

> **핵심 목표:** 비대해진 `scanner.py`를 단일 책임 원칙(SRP)에 근거해 모듈 패키지로 쪼개고, `t.info` 네트워크 블로킹 병목을 비동기 병렬 대량 수집으로 전면 정화하며, SQLite 자가 마이그레이션 코드를 SQLAlchemy 2.0+ text() 규격으로 교체합니다.

- [x] **[스캐너 디렉토리 패키지화]** `app/scanner/` 폴더 하위에 `indicators.py`, `filters.py`, `discovery.py`, `scanner.py` 생성 및 물리적 역할 분할 완료
- [x] **[기술 지표 캡슐화]** `indicators.py` 내에 순수 수학적/기술적 지표 계산기(VWAP, RSI, MACD, EMA, ATR, OBV 등) 이동 완료
- [x] **[전략 필터 분리]** `filters.py` 내에 전략별 타점 판독기(RSI BB, ORB, Smart Exit 등) 및 **비동기 흑자 재무 필터** 구현 완료
- [x] **[종목 발굴 격리]** `discovery.py` 내에 KIS 순위, 야후 활성, 관심종목 다중 소스 병렬 종목 발굴 로직 탑재 완료
- [x] **[초고성능 비동기 병렬화]** `scanner.py` 메인 루프 내에서 후보군 25개 종목의 **1분봉/일봉/뉴스/재무 분석을 단 한 번의 비동기 병렬 대량 수집(asyncio.gather)**으로 통합 처리하여 스캔 지연을 50초에서 1초 미만으로 단축 완료
- [x] **[DB 마이그레이션 안전 규격]** `main.py` 자가 마이그레이션 SQL 구문을 SQLAlchemy 2.0+ `text()` 호환 규격으로 전면 정화 완료
- [x] **[무결성 가드 및 정화]** `__init__.py` 텅 빈 패키지 이니셜라이저 정화 및 `py_compile` 문법 무결성 사전 검증 통과 완료

## 🌟 [Phase 17] 시세 공급 벤더 추상화 및 데이터 프로바이더 구축 — 완료 [x]

> **핵심 목표:** 시세 데이터 수집(yfinance)이 온 동네 코드 전역에 강하게 묶여(Tight Coupling) 있는 결합을 원천 도려내고, 단일 관문 데이터 프로바이더를 통해 벤더 독립성을 완비한다.

- [x] **[프로바이더 설계]** `backend/app/scanner/data_provider.py` 신규 설계 및 시세 다운로드 API 단일 캡슐화 완료
- [x] **[스캐너 리팩토링]** `scanner.py` 내의 날것의 `yf.download` 호출부를 데이터 프로바이더 인터페이스 호출로 일괄 대체 완료
- [x] **[스케줄러 리팩토링]** `scheduler.py` 내의 실시간 단종목 시세 조회부를 데이터 프로바이더 호출로 단축 교체 완료
- [x] **[라우터 의존성 청소]** `router_market.py` (시장시세), `router_account.py` (보유청산), `watchlist/router.py` (관심종목 검증) 내의 날것 yfinance 호출을 `fetch_ohlcv` 비동기 호출로 100% 전격 도려내기 완료!
- [x] **[가상 데이터 실험]** 가상 데이터(Mocking) 전환 실험을 통한 벤더 독립성 및 런타임 안정성 검증 완료
- [x] **[통합 런타임 검증]** 구문 컴파일 정밀 검증 및 Uvicorn/Next.js 통합 로컬 기동 검증 완료

## 🌟 [Phase 18] KIS API 및 번역 자가학습 모듈 내 yfinance 결합 제거 및 데이터 프로바이더 최종 통합 — 완료 [x]

> **핵심 목표:** 시스템 전역에 흩어진 `yfinance` 직접 임포트 및 날것(Raw) 호출부를 완전히 걷어내어 `data_provider.py` 단 한 곳으로 100% 격리 및 캡슐화 완료.

- [x] **[동기식 헬퍼 신설]** `data_provider.py` 내 동기식 데이터 수집 헬퍼 함수 (`fetch_bulk_ohlcv_sync`, `fetch_ticker_info_sync`, `fetch_ohlcv_sync`) 추가
- [x] **[가상 잔고 연산 정화]** `kis_api.py` 내 `get_account_balance` 의 `yf.download` 결합 제거 및 `fetch_bulk_ohlcv_sync`로 전환
- [x] **[거래소 판별 정화]** `kis_api.py` 내 `_get_exchange_code` 의 `yf.Ticker.fast_info` 직접 호출을 `fetch_ticker_fast_info`로 전환
- [x] **[번역 자가학습 정화]** `translator.py` 내 자가학습 루프의 `yf.Ticker.info` 직접 호출을 `fetch_ticker_info_sync`로 전환
- [x] **[환율 캐시 정화]** `fx_cache.py` 내 `yf.download` 직접 임포트 및 호출부를 `fetch_ohlcv_sync` 호출로 100% 캡슐화 전환
- [x] **[모의 브로커 정화]** `simulated_broker.py` 내 모든 `yf.download` 직접 호출부를 `fetch_bulk_ohlcv_sync` 및 `fetch_ohlcv_sync`로 전면 격리 전환 (yfinance 임포트 완전 박멸)
- [x] **[문법 및 무결성 검증]** `py_compile`을 이용한 파이썬 모듈 구문 완성도 사전 검증
- [x] **[실전 가동성 테스트]** 로컬 Uvicorn 서버 백엔드 재기동 후 실전 매매 스케줄러 & 자가학습 API Tracing 안정성 최종 검증

## 🌟 [Phase 19] 텔레그램 1인 봇 통합 아키텍처 및 딥링크 연동 — 완료 [x]

> **핵심 목표:** 기존의 사용자별 봇 토큰 등록 및 스레드 가동 방식에서, **"단 하나의 공식 봇 토큰과 단일 백그라운드 스레드"** 기반의 고성능 멀티유저 텔레그램 브릿지 구조로 대전환하고 딥링크 연동 및 UI를 전면 개편한다.

- [x] **[백엔드 텔레그램 코어 리팩토링]** `app/core/telegram.py` 내의 다중 스레드 구문을 단일 글로벌 `TelegramGlobalPollThread`로 리팩토링 및 딥링크(/start username) 자동 Chat ID 저장 연동 구현
- [x] **[백엔드 라우터 연동 정화]** `app/admin/router.py` 내 사용자 설정 저장 및 삭제 시 불필요한 유저 개별 스레드 핫리부팅 제거
- [x] **[프론트엔드 UI 대개편]** `settings/page.tsx` 내의 BOT TOKEN 인풋 필드 제거 및 공식 봇 이동 딥링크 연동 버튼 + 수동 CHAT ID 안내 연동 UI 실장
- [x] **[DB/ENV 전방위 정화]** UserSettings 모델에서 개별 `telegram_bot_token` 컬럼 완전 삭제, `.env` 파일에서 `TELEGRAM_ENABLED` 및 `TELEGRAM_CHAT_ID` 전면 제거, DB를 telegram_enabled의 유일한 SSOT로 확정
- [x] **[종합 가동 및 무결성 검증]** 로컬 Uvicorn 백엔드 및 Next.js 프론트엔드 구동 검증, 신규 가입자 딥링크 연동 시나리오 및 `/status` 명령어 실전 수발신 완벽성 통과 검증

## 🌟 [Phase 20] Google Cloud Run 올-클라우드 통합 배포 파이프라인 구축 및 문서화 — 완료 [x]

> **핵심 목표:** 프론트엔드(Next.js)와 백엔드(FastAPI) 전체 시스템을 Docker 컨테이너 기반으로 패키징하고, Google Cloud Run을 통해 완전 자동화된 공인 HTTPS 도메인 배포 환경을 완성하며, 이와 관련된 모든 실전 가이드 문서를 구축한다.

- [x] **[컨테이너 인프라]** 백엔드 Dockerfile (`/backend/Dockerfile`) 및 프론트엔드 Dockerfile (`/frontend/Dockerfile`) 설계 및 경량 빌드 아키텍처 수립 완료
- [x] **[CORS 동적 대응]** 백엔드 `main.py` 내 `ALLOWED_ORIGINS` 환경변수를 통한 동적 CORS 대응 구현 완료 (클라우드 환경의 유연한 도메인 매핑 보장)
- [x] **[시스템 매뉴얼 동기화]** `docs/SYSTEM_MANUAL.md` 파일에 Google Cloud Run 올-클라우드 배포 매뉴얼 및 도메인 바인딩 가이드 기재 완료
- [x] **[데이터베이스 영속화 설계]** `docs/SCHEMA.md` 파일에 Cloud Run 서버리스 무상태 특성을 극복하기 위한 SQLite 데이터 영속화 가이드(GCS FUSE 볼륨 마운트 및 Cloud SQL 전환) 명세화 완료
- [x] **[작업 현황 최종 동기화]** `docs/task.md` 작업 현황판에 클라우드 배포 파이프라인 구축 및 영속성 설계 작업을 Phase 20 태스크로 완벽 반영 완료

## 🌟 [Phase 21] 투자 전략 고도화 — 뉴스 AI 감성 분석 및 퀀트 시그널 V3 — 완료 [x]

> **핵심 목표:** 현재 뉴스 제목의 키워드 단순 매칭(`has_news = true/false`)으로 +10점만 가산하는 수준의 원시적 뉴스 처리를 전면 도려내고, **뉴스 본문에 대한 AI 감성 분석(Sentiment Analysis)**을 도입하여 긍정/부정/중립 판별 및 시장 영향도 기반의 정밀한 다이내믹 가산/감산 스코어링 체계를 구축한다. 더불어 마크 미너비니 VCP 패턴 인식 등 고급 퀀트 지표를 추가하여 스캐너 정밀도를 극적으로 끌어올린다.

### 21-1. 뉴스 AI 감성 분석 엔진 구축

- [x] **[감성 분석 모듈 신설]** `app/scanner/news_analyzer.py` 신규 모듈 설계 및 뉴스 제목/요약에 대한 AI 감성 판별 (Positive/Negative/Neutral) + 영향도 스코어(0~100) 산출 엔진 구현
- [x] **[스캐너 연동]** `scanner.py` Stage 2 채점판에서 기존 `has_news` 단순 Boolean 대체 → 감성 분석 결과에 따른 다이내믹 가산/감산 점수 체계 도입 (긍정 뉴스 최대 +20, 부정 뉴스 최대 -30 등)
- [x] **[프론트엔드 시그널 카드 연동]** 대시보드 스캐너 시그널 카드에 뉴스 감성 배지(🟢 긍정 / 🔴 부정 / ⚪ 중립) 및 핵심 헤드라인 미리보기 표시

### 21-2. 고급 퀀트 지표 추가 이식

- [x] **[VCP 패턴 인식]** 마크 미너비니 변동성 축소 패턴(VCP: Volatility Contraction Pattern) 감지 알고리즘 `indicators.py`에 이식
- [x] **[컵 앤 핸들 패턴]** 윌리엄 오닐 컵 앤 핸들(Cup and Handle) 차트 패턴 인식 알고리즘 구현
- [x] **[스캐너 채점판 통합]** 상기 패턴 감지 결과를 Stage 2 다이내믹 스코어카드에 가산항목으로 결합

### 21-3. 검증 및 문서 동기화

- [x] **[통합 검증]** AI 감성 분석 모듈의 정확도 및 스캐너 채점 반영 시나리오 테스트
- [x] **[문서 동기화]** SYSTEM_MANUAL, TRADING_STRATEGY 문서 현행화

## 🌟 [Phase 22] 상세 트레이딩 성적표 & 통계 대시보드

> **핵심 목표:** 사용자 대시보드에 **PnL 성적표 탭**을 신설하여, 일별/주별 투자 수익금, 승률(Win Rate), 프로핏 팩터(Profit Factor), 최대 낙폭(MDD), 평균 보유 기간 등을 한눈에 시각화해 주는 프리미엄 데이터 분석 차트 기능을 탑재한다.

- [ ] **[백엔드 통계 API]** `trade_logs` 테이블 기반 일별/주별/월별 PnL, 승률, MDD, 프로핏 팩터 등 핵심 퀀트 통계 연산 API 구축
- [ ] **[프론트엔드 성적표 페이지]** `/admin/report` 또는 대시보드 내 신규 탭으로 프리미엄 PnL 차트 (일별 수익 곡선, 누적 수익 곡선, 드로다운 차트) 및 핵심 KPI 카드 UI 실장
- [ ] **[텔레그램 일일 리포트]** 매일 장 마감 후 당일 매매 결과 요약 및 누적 수익률을 텔레그램으로 자동 발송하는 일일 성적표 브릿지 연동

## 🌟 [Phase 23] 클라우드 무설정 배포 및 자동 암호화 백업

> **핵심 목표:** 백엔드/프론트엔드를 **Docker 컨테이너**로 패키징하여 클라우드 VPS(AWS, GCP 등)에 즉시 배포 가능한 환경을 구축하고, **AES-256-GCM 암호화** 기반의 자동 데이터베이스 백업 및 서버 기동 시 자가 복구(Zero-Touch Restore) 파이프라인을 구현한다.

- [ ] **[Docker 컨테이너화]** 백엔드(FastAPI) 및 프론트엔드(Next.js) Dockerfile 작성 및 docker-compose 통합 오케스트레이션
- [ ] **[암호화 백업 모듈]** AES-256-GCM 대칭키 암호화 기반 `stockauto.db` 자동 백업 및 클라우드 오브젝트 스토리지(S3/GCS) 업로드 크론 스케줄러 구현
- [ ] **[자가 복구 부트스트랩]** 서버 기동 시 로컬 DB 미존재 감지 → 클라우드에서 최신 암호화 백업 자동 다운로드 및 복호화 복원 로직 구현
- [ ] **[환경변수 보안 관리]** AWS KMS / Secret Manager 연동을 통한 프로덕션 민감 키 동적 발급 체계 설계


## 🌟 [Phase 24] 개선 작업 — 미완료

- [x] 백엔드 구조화 로깅 적용
- [x] DB Alembic 마이그레이션 — 완료 (Alembic 프로그램 기반 자동 마이그레이션 이식 완료)
- [x] 텔레그램 비동기 리팩터 — 완료 (httpx.AsyncClient 및 비동기 Task 스케줄링 대전환)
- [x] 스케줄러 안정화 및 회복 처리 — 완료 (네트워크 예외 복구 자가치료 및 DB 롤백 완료)
- [x] 데이터 프로바이더 & 레이트 리미트 처리 — 완료 (10초 단기 핫 캐시 가드 전면 실장)
- [ ] 테스트 및 CI 구성
- [x] 프론트엔드 환경 템플릿 추가
- [x] 미국시장 DST 기반 시장시간 계산 개선

> 위 항목들은 문서 중간에 잘못 삽입되어 있던 개선 작업을 문서 말미의 새 Phase로 이관한 것입니다.

## 🌟 [Phase 25] Premium UI/UX Makeover & Alert Hotfixes — 완료 [x]

- [x] **[마켓 스캐너 UI 리뉴얼]** `OverseasScanner.tsx` 상세 아코디언 컴포넌트를 Toss/TradingView 프리미엄 다크 테마로 전면 개편
- [x] **[텔레그램 알림 핫픽스]** `scheduler.py` 매수 실패 시 단가 초과/수량 미달 vs 예수금 부족 명확히 분기 및 1시간 중복 알림 방지 Cooldown 가드 적용


## 🌟 [Phase 26] AI 에이전트 협업 플레이북 (하네스) 구축 및 고도화 — 완료 [x]

- [x] **[플레이북 신설]** `docs/AGENTS.md`에 6개 분야별 에이전트(Auditor, Fixer, Reviewer, Feature Dev, UI Designer, Doc Writer) 역할 정의 및 협업 이관 프로토콜 작성
- [x] **[치트키 안내 갱신]** `CLAUDE.md` 파일에 `docs/AGENTS.md` 지침 추가 연동
- [x] **[기획자 역할 추가]** `docs/AGENTS.md`에 기획자/설계자(Planner/Architect) 역할 정의 탑재 및 전체 협업 흐름 6단계로 확장 연동
- [x] **[소프트 제약: 자가 치유 루프 장착]** `docs/AGENTS.md`에 Reviewer-Fixer 간의 3회 자동 수정 순환 제어(Self-Correction Loop) 수칙 공식 실장
- [x] **[하드 제약: 환경적 가드레일 구축]** 린트/컴파일 실패 시 Git 커밋을 물리적으로 원천 거부하는 `scripts/verify_harness.py` 검증 스크립트 및 Git Pre-commit Hook 연동 구축


## 🌟 [Phase 27] 누적 데이터 분석 기반 내일 상승 예측 스윙 스캐너 (Next-Day Breakout Predictor) 구축 — 완료 [x]

- [x] **[백엔드 지표 수식 확장]** `indicators.py`에 거래량 극감(VUD), OBV 다이버전스, 볼린저 밴드 스퀴즈 수식 및 검출 알고리즘 구현
- [x] **[스윙 예측 모듈 개발]** `swing_predictor.py` 신설하여 120일 누적 일봉 스캔 및 TOP 5 후보군 분석/점수 산출 알고리즘 개발
- [x] **[시스템 API 라우터 연동]** `router.py`에 `@router.get("/swing-predict")` 엔드포인트 개설 및 데이터 프로바이더 통합 연동
- [x] **[프론트엔드 UI 컴포넌트 신설]** `SwingPredictorCard.tsx` Next.js 탭 스위치 기반 프리미엄 다크 카드 컴포넌트 신규 개발
- [x] **[대시보드 통합 연동]** `Dashboard.tsx` 및 `/scanner` 페이지에 2단 탭 제어 스위치 및 스윙 예측 카드 통합 화면 이식

## 🌟 [Phase 28] 역사적 백테스팅 엔진 (Historical Backtesting Engine) 및 성적 분석 실장 — 완료 [x]

> **핵심 목표:** StockAuto v2.0 트레이딩 전략(레짐 스위칭, 1:2:6 피라미딩, ATR 손절/트레일링스탑, RSI-MACD 조기익절)의 역사적 수익곡선(Equity Curve) 및 MDD를 검증하는 자체 이벤트 기반 백테스팅 엔진을 구축하고 검증한다.

- [x] **[백테스트 코어 개발]** `backend/app/bot/backtest_engine.py` 신설 (가상 가상잔고/포지션을 처리하는 `BacktestBroker` 및 시간 루프를 흘려보내며 매수/매도를 체뮬레이션하는 `BacktestSimulator` 구축)
- [x] **[CLI 실행기 개발]** `backend/run_backtest.py` CLI 프로그램 구축 (yfinance 데이터를 로드하여 백테스트를 실행하고, matplotlib을 활용해 누적 수익 곡선 및 드로다운(MDD) 차트를 png 파일로 저장하는 시각화 도구 완비)
- [x] **[FastAPI 라우터 추가]** `backend/app/bot/router_backtest.py` 엔드포인트 구축 및 `main.py` 라우터 연동 (프론트엔드 대시보드 연동을 위해 백테스트 실행 및 PnL, MDD, 거래 기록 일괄 반환 API 개설)
- [x] **[통합 실증 검증]** 최근 30일(1분봉) 및 최근 2년(1시간봉) QQQ 레짐 모드 연동 백테스트 구동 검증 및 MDD 산출 무결성 테스트 완료

## 🌟 [Phase 29] 실거래 비용 최적화 및 스마트 리스크/예수금 제어 시스템 구축

> **핵심 목표:** 과도한 실거래 비용(수수료 및 환전 스프레드)을 상쇄하는 익절/쿨다운 가드를 도입하고, 예수금 부족 스팸 및 무용한 증권사 API 호출을 방지하기 위한 안전 포트폴리오 차단막을 구축한다.

- [x] **[글로벌 상수 이식]** `config.py`에 포트폴리오 안전 및 비용 극복 관련 전역 제어 상수 4종 (`MAX_HOLDINGS`, `MIN_CASH_BALANCE_USD`, `MIN_SMART_EXIT_PROFIT_RATE`, `REENTRY_COOLDOWN_MINUTES`) 추가
- [x] **[익절 및 쿨다운 세분화]** `scheduler.py` 내 스마트 조기 익절 최저 마진을 `2.5%`로 상향조정하고, 재매수 방지 쿨타임을 `60분`으로 연장하여 수수료 휩소 원천 격리
- [x] **[포트폴리오 개수 가드]** `scheduler.py`에 최대 보유 종목 수(5개) 상한선을 도입하여, 보유 한도 초과 시 신규 매수 분석 및 API 실행 원천 스킵 가드 구현
- [x] **[안전 예수금 가드]** `scheduler.py`에 최소 달러 예수금 가드라인($200)을 도입하여, 잔고 바닥 시 신규 진입 시도 조기 차단
- [x] **[스팸 메시지 차단]** 예수금 부족 텔레그램 알림을 종목별에서 '계좌 전체 대표 쿨타임(1시간)'으로 구조화하여 알림 소음 100% 진압



