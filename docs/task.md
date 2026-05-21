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

## 🌟 [Phase 10] 어드민 시스템 설정 대시보드

> **핵심 목표:** `.env` 수동 편집 없이 관리자 웹 UI에서 트레이딩 모드, 증권사 선택, API Key 등을 실시간으로 설정할 수 있게 한다.

- [x] **[백엔드 설정 API]** `models.py`에 `SystemSettings` 모델 추가 및 `/api/v1/admin` CRUD REST API 구축 완료
- [x] **[어드민 설정 페이지]** `/admin/settings` 페이지 신설, 트레이딩 모드 3단 세그먼트(SIMULATED/MOCK/REAL) UI 구현 완료
- [x] **[증권사 선택 UI]** 증권사 드롭다운(KIS) 및 APP KEY, SECRET, ACCOUNT NO 입력 폼 구현 완료
- [x] **[설정 즉시 반영]** POST 요청 시 `settings` 싱글톤 객체 메모리를 즉시 업데이트하여 서버 재시작 없이 핫 리로드 적용 완료
- [x] **[안전 잠금장치]** `REAL` 모드 전환 시 강력한 시각적 경고가 포함된 모달 다이얼로그 팝업 및 강제 확인 로직 적용 완료

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
