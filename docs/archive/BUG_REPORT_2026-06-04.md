# StockAuto 전체 스캔 버그 리포트

- 작성일: 2026-06-04
- 목적: 리팩토링 착수 전 실제 장애, 잠복 버그, 보안/운영 리스크를 우선순위별로 정리
- 범위: `backend/app`, `backend/tests`, `frontend/app`, `frontend/components`, `frontend/lib`, 설정/하네스 문서
- Git 명령: AGENTS 지침에 따라 실행하지 않음

## 핵심 결론

현재 최우선 장애는 백엔드 스케줄러 파일 손상입니다. `backend/app/bot/scheduler.py`가 문법 오류 상태라서 FastAPI 서버 import, 스캐너 라우터 import, pytest 수집이 모두 막힙니다.

프론트엔드는 최신 기준 `npm run lint`, `npx tsc --noEmit`, `npm run build`가 통과했습니다. 다만 백엔드 스캐너 API가 `POST`로 변경된 반면, `backend/tests/test_scanner_router.py`는 아직 구버전 `GET` 기대값을 사용합니다.

## 검증 결과

| 구분 | 명령 | 결과 |
|---|---|---|
| Backend compile | `python -m compileall -q app tests` | 실패: `backend/app/bot/scheduler.py:307` SyntaxError |
| Backend pytest | `python -m pytest` | 실패: scheduler SyntaxError 때문에 4개 테스트 모듈 수집 중단 |
| Frontend lint | `npm run lint` | 통과 |
| Frontend typecheck | `npx tsc --noEmit` | 통과 |
| Frontend build | `npm run build` | 통과, Next.js 16.2.6 Turbopack |
| Project harness | `python scripts/verify_harness.py` | 실패: backend compile/pytest 실패, frontend/Playwright smoke 통과 |

## P0. 즉시 수정 필요

### BUG-001. `scheduler.py` 중복 삽입/절단으로 백엔드 import 불가

- 위치: `backend/app/bot/scheduler.py:290-322`
- 증상: `process_exit_signals()` 내부 `try` 블록이 `except/finally` 없이 끊긴 뒤, `TradingFlowContext` 필드처럼 보이는 라인이 함수 내부 잘못된 들여쓰기로 삽입되어 있습니다.
- 재현: `python -m compileall -q app tests`
- 오류: `SyntaxError: expected 'except' or 'finally' block`
- 영향:
  - `app.bot.scheduler` import 실패
  - `app.main`의 `from app.bot.scheduler import start_scheduler` 때문에 서버 기동 실패
  - `tests/test_scanner_router.py`, `tests/test_scheduler_cycle_context.py`, `tests/test_scheduler_order_safety.py`, `tests/test_trading_flow_scenarios.py` 수집 실패
- 권장 조치:
  - 중복된 `prepare_trading_flow_context`, `migrate_legacy_holdings`, `sync_broker_holdings`, `calculate_slot_allocations`, `build_target_signals`, `process_exit_signals` 블록을 하나로 정리
  - 손상된 `process_exit_signals()` 앞쪽 블록 제거 또는 완전 복구
  - 수정 직후 `python -m py_compile app\bot\scheduler.py` 실행

### BUG-002. `async_trading_loop()`에서 미정의 변수 사용

- 위치: `backend/app/bot/scheduler.py:1092-1102`
- 증상: `signal_map`, `all_signals`, `sentiment`가 함수 내에서 생성되지 않았는데 `run_user_trading_flow()`에 전달됩니다.
- 현재는 BUG-001의 SyntaxError가 먼저 막지만, 문법 오류만 고치면 다음 런타임 장애가 될 가능성이 큽니다.
- 영향: 자동매매 루프 실행 시 `NameError` 또는 잘못된 스캔 컨텍스트로 전체 사용자 플로우 실패
- 권장 조치:
  - 루프 시작 시 캐시된 `latest_scanned_signals`로 `all_signals`와 `signal_map` 생성
  - `sentiment`를 `check_market_sentiment()` 또는 시장 개요 캐시에서 명시적으로 주입
  - `test_scheduler_cycle_context.py`에 이 변수 준비 경로를 검증하는 회귀 테스트 추가

## P1. 보안/자산 보호 리스크

### BUG-003. 기본 admin 계정과 자동 실행 시딩

- 위치: `backend/app/core/migrator.py:72-128`
- 증상:
  - `admin`부터 `admin10`까지 경쟁 유저를 자동 생성
  - 기본 비밀번호가 `admin123`
  - 신규/기존 설정에서 `is_running=True`로 자동매매를 강제 활성화
- 영향: 초기 DB 또는 운영 DB에서 예측 가능한 관리자 계정과 자동매매 실행 상태가 생길 수 있습니다.
- 권장 조치:
  - 운영/프로덕션에서는 기본 계정 시딩 차단
  - 시딩은 별도 CLI 또는 테스트 fixture로 분리
  - 기본 비밀번호 제거, 최초 로그인 시 강제 변경 또는 랜덤 one-time secret 사용

### BUG-004. KIS API Secret 평문 저장 및 응답 노출

- 위치:
  - `backend/app/core/models.py:35-36`
  - `backend/app/admin/router.py:102-109`
- 증상: `kis_app_secret`이 DB 컬럼에 평문으로 저장되고, 설정 조회 API가 그대로 반환합니다.
- 영향: DB 백업, 로그, 브라우저 메모리, XSS, API 응답 탈취 시 증권사 API Secret 유출 가능
- 권장 조치:
  - DB 저장 전 암호화 또는 OS secret store 연동
  - 조회 응답에서는 `kis_app_secret` 마스킹
  - secret 변경은 별도 write-only 필드로 처리

### BUG-005. 관리자 권한이 `username == "admin"`에 의존

- 위치:
  - `backend/app/admin/router.py:162-169`
  - `frontend/app/admin/page.tsx:25-38`
- 증상: 별도 role/permission 모델 없이 문자열 사용자명으로 관리자 권한을 판정합니다.
- 영향: 기본 admin 계정 정책과 결합하면 권한 경계가 취약합니다. 프론트 권한 가드는 표시 제어일 뿐 서버 권한을 대체하지 못합니다.
- 권장 조치:
  - `users` 또는 별도 role 테이블에 `role`/`is_admin` 도입
  - `require_admin_user` 의존성 함수로 서버 권한 검사를 단일화
  - 프론트는 `/auth/me` 또는 권한 API 응답 기준으로 메뉴 노출만 제어

### BUG-006. 번역 사전 CRUD API가 인증 없이 열려 있음

- 위치: `backend/app/translations/router.py:25-76`
- 증상: `GET/POST/PUT/DELETE /api/v1/translations`에 `get_current_user` 또는 admin 권한 의존성이 없습니다.
- 영향: 외부 호출자가 번역 사전을 조작하거나 삭제할 수 있습니다.
- 권장 조치:
  - 읽기 공개 여부를 정책으로 확정
  - 쓰기/수정/삭제는 최소 인증, 가능하면 admin 전용으로 제한

### BUG-007. 수동 리포트 API가 전체 사용자 발송 함수를 호출

- 위치: `backend/app/report/router.py:76-84`
- 증상: 로그인 사용자 누구나 `send_daily_report_to_all_users_sync()`를 실행할 수 있습니다.
- 영향: 전체 사용자에게 텔레그램 리포트 스팸/오발송 가능
- 권장 조치:
  - 일반 사용자는 본인 리포트만 발송
  - 전체 사용자 발송은 admin 전용 엔드포인트로 분리

### BUG-008. 전역 예외 응답에 traceback 노출

- 위치: `backend/app/main.py:56-65`
- 증상: 모든 일반 예외 500 응답에 `message: str(exc)`와 `traceback.format_exc()`를 포함합니다.
- 영향: 내부 파일 경로, 모듈 구조, 예외 메시지, 잠재적 민감 정보가 클라이언트에 노출됩니다.
- 권장 조치:
  - 클라이언트에는 안정적인 에러 코드와 일반 메시지만 반환
  - 상세 traceback은 서버 로그에만 기록
  - 로컬 개발 모드에서만 debug 응답 허용

## P2. API 계약/테스트/운영 안정성

### BUG-009. 스캐너 API 테스트가 구버전 HTTP 메서드를 기대

- 위치:
  - 백엔드 현재 라우터: `backend/app/scanner/router.py:38-45`, `backend/app/scanner/router.py:58-63`
  - 테스트: `backend/tests/test_scanner_router.py:70-77`, `backend/tests/test_scanner_router.py:115-119`, `backend/tests/test_scanner_router.py:187-190`
- 증상: 실제 라우터는 수동 실행/갱신을 `POST`로 제공하지만 테스트는 `GET`을 호출합니다.
- 영향: BUG-001을 해결한 뒤에도 테스트가 API 계약 변경을 따라가지 못해 실패할 가능성이 큽니다.
- 권장 조치:
  - 테스트를 `client.post()`로 수정
  - `/scanner/overseas`는 백그라운드 시작 메시지와 이후 `/latest` 갱신을 분리해 검증
  - 인증 요구 여부도 테스트에 명시

### BUG-010. 앱 import 시 마이그레이션/시딩 부작용 실행

- 위치:
  - `backend/app/main.py:27-29`
  - `backend/app/core/migrator.py:43-61`
- 증상: `app.main` import 단계에서 Alembic migration과 경쟁 유저 seeding이 실행됩니다.
- 영향:
  - 테스트 import가 DB 상태를 바꿀 수 있음
  - 운영 시작 시 스키마 drift를 `stamp head`로 숨길 수 있음
  - 서버 시작과 데이터 관리 책임이 강하게 결합됨
- 권장 조치:
  - migration은 lifespan startup으로 이동하거나 별도 boot step으로 분리
  - seeding은 환경 플래그와 명령형 CLI로 제한
  - 기존 DB `stamp head`는 drift 검증 후 명시 승인 방식으로 변경

### BUG-011. 관심종목 수집이 모든 사용자를 섞음

- 위치: `backend/app/scanner/discovery.py:6-13`, `backend/app/scanner/discovery.py:79-84`
- 증상: `WatchList`를 사용자 필터 없이 전체 조회해 글로벌 스캔 universe에 합칩니다.
- 영향: 멀티유저 데이터 격리 원칙과 충돌합니다. 사용자 관심종목이 다른 사용자/공용 스캔에 간접 반영될 수 있습니다.
- 권장 조치:
  - 공용 seed universe와 사용자별 watchlist universe를 분리
  - 스케줄러 공용 스캔과 사용자 맞춤 스윙 예측을 별도 경로로 설계

### BUG-012. async 라우트 내부 동기 브로커 호출

- 위치:
  - `backend/app/trades/router_account.py:131-168`
  - `backend/app/bot/kis_broker.py`의 `time.sleep` 기반 체결 확인
  - `backend/app/bot/kis_api.py`의 동기 `requests` 호출
- 증상: `force_liquidate()`는 async 라우트지만 `broker.sell_order()`를 직접 호출합니다. KIS 경로는 동기 네트워크 I/O와 sleep을 포함합니다.
- 영향: 요청 처리 이벤트 루프 블로킹, 다중 사용자 청산/조회 시 응답 지연
- 권장 조치:
  - `safe_broker_call()` 또는 `asyncio.to_thread()`로 통일
  - KISClient를 httpx async 기반으로 점진 전환
  - 체결 확인 폴링은 백그라운드 job 또는 async retry로 분리

### BUG-013. 하드코딩된 개인 로컬 경로

- 위치: `backend/app/admin/router.py:249-254`
- 증상: 백테스트 토너먼트 캐시 경로가 `C:\Users\Im\.gemini\...`로 고정되어 있습니다.
- 영향: 다른 PC, 컨테이너, 서버에서 기본 캐시 로드 실패
- 권장 조치:
  - `backend/cache/tournament_results.json` 또는 env 설정으로 이동
  - 파일 부재 시 API 응답에 상태 메시지 포함

### BUG-014. AGENTS 표준과 실제 프론트 스택 불일치

- 위치:
  - AGENTS 표준: Next.js 15
  - 실제: `frontend/package.json:23-25`에서 Next.js 16.2.6, React 19.2.4
- 영향: 작업자/문서가 Next 15 기준으로 판단하면 Next 16 규칙과 충돌할 수 있습니다.
- 권장 조치:
  - 실제 스택을 유지할지, 표준을 Next 15로 되돌릴지 결정
  - 유지한다면 AGENTS와 `docs/NEXTJS_GUIDE.md`를 Next 16 기준으로 현행화

## P3. 코드 품질/유지보수성

### BUG-015. ESLint 우회 주석과 `any` 사용 잔존

- 위치:
  - `frontend/components/admin/BacktestTournament.tsx:281-285`
  - `frontend/app/admin/settings/page.tsx:83-86`
- 증상: `eslint-disable-next-line`으로 규칙을 우회합니다.
- 영향: AGENTS의 No Hacks 표준과 충돌합니다.
- 권장 조치:
  - Recharts `Tooltip` formatter 타입을 명시
  - effect 내부 상태 갱신 우회 주석 대신 데이터 로딩 패턴 정리

### BUG-016. polling 훅이 요청 중첩을 막지 않음

- 위치: `frontend/hooks/usePolling.ts:14-28`
- 증상: `setInterval(tick, interval)`이 이전 tick 완료 여부와 무관하게 다음 tick을 실행할 수 있습니다.
- 영향: 느린 API에서 중복 요청, race condition, 뒤늦은 응답으로 상태 역전 가능
- 권장 조치:
  - in-flight guard 추가
  - 각 tick마다 새 `AbortController` 생성
  - 긴 요청은 다음 주기를 skip하거나 마지막 요청 완료 후 delay 방식으로 전환

## 권장 리팩토링 순서

1. `scheduler.py` 파일 손상 복구 및 단일 함수 블록 정리
2. `async_trading_loop()`의 `signal_map/all_signals/sentiment` 준비 로직 복구
3. 백엔드 py_compile, pytest 전체 복구
4. 스캐너 API 테스트를 POST/인증/백그라운드 계약으로 갱신
5. 기본 admin 시딩과 권한 모델 분리
6. KIS secret 저장/조회 정책 보강
7. 무인증 번역 CRUD, 전체 리포트 발송, traceback 노출 차단
8. 사용자 watchlist와 공용 scanner universe 분리
9. 동기 KIS 호출을 async-safe wrapper로 일괄 정리
10. AGENTS/문서/실제 Next 버전 표준 동기화

## 리팩토링 착수 전 최소 통과 기준

- `python -m py_compile backend\app\bot\scheduler.py`
- `python -m compileall -q backend\app backend\tests`
- `cd backend; python -m pytest`
- `cd frontend; npm run lint`
- `cd frontend; npx tsc --noEmit`
- `cd frontend; npm run build`
- `python scripts\verify_harness.py`
