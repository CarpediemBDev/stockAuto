# StockAuto V2 Architecture (Micro-Session Pattern)

## 1. 개요
기존 StockAuto 시스템은 사용자의 매매 플로우(`run_user_trading_flow`)가 시작될 때부터 끝날 때까지 1개의 데이터베이스 커넥션을 쥐고 있는 **"1 User = 1 Long-lived Connection"** 모델을 사용했습니다.
하지만 사용자 수가 많아지고 증권사 네트워크 통신(API 대기)이 수 초간 지속될 경우, 대기하는 시간 동안 DB 커넥션이 아무 일도 하지 않고 묶여 있게 되어 SQLite의 `QueuePool` 한계(15개)를 초과하는 병목이 발생했습니다.

이를 해결하기 위해, DB 커넥션을 네트워크 대기 시간 동안 풀어주는 **"Micro-Session Pattern"**을 도입하여 기본기를 강화합니다.

## 2. 매매 흐름 3단계 (Three-Phase Execution)

매매 사이클은 다음과 같이 3단계로 분리되어 실행됩니다.

### Phase 1: Fetch Phase (데이터 조회 및 커넥션 반납)
- **목적:** 이번 사이클에 필요한 유저의 최신 상태(잔고, 설정 등)를 읽어옵니다.
- **방식:** `db = SessionLocal()`로 세션을 열고 데이터를 조회한 뒤, SQLAlchemy의 `db.expunge_all()` 또는 개별 `expunge()`를 사용해 객체들을 세션에서 분리(Detached 상태)시킵니다.
- **소요 시간:** 0.01초 내외
- **종료 액션:** `db.close()`를 호출해 DB 커넥션을 풀(Pool)에 즉시 반납합니다.

### Phase 2: Async Network Phase (비동기 네트워크 I/O)
- **목적:** 증권사(KIS/TOSS)와 통신하여 잔고 동기화, 매수, 매도를 실행합니다.
- **방식:** DB 커넥션이 **없는** 상태로 `await execute_buy_logic()` 등을 호출합니다.
- **소요 시간:** 1~3초 (비동기 병렬 실행이므로 N명이 동시에 진행되어도 3초 이내)
- **이점:** 이 공백기 동안 DB 커넥션 풀은 100% 여유 상태가 되며, 다른 유저들의 Phase 1, Phase 3 작업이 병목 없이 실행됩니다.

### Phase 3: Commit Phase (결과 저장 및 로그 기록)
- **목적:** 네트워크 통신 결과(성공, 실패, 잔고 변화 등)를 DB에 최종 반영합니다.
- **방식:** `db = SessionLocal()`로 다시 커넥션을 짧게 열고, Phase 2에서 수집한 결과 데이터를 바탕으로 DB를 업데이트한 후 `db.commit()`합니다.
- **소요 시간:** 0.01초 내외
- **종료 액션:** `db.close()`

## 3. 핵심 아키텍처 원칙
- **격리성 유지 (Isolation):** 대규모 Bulk 처리 방식이 갖는 "연대 책임(한 유저의 에러로 전체 트랜잭션 롤백)" 리스크를 피하기 위해, 여전히 **1인 단위로 커넥션을 맺고 닫습니다.**
- **Offline Lock:** Phase 2 진행 도중 유저가 UI에서 수동 개입하는 것을 막기 위해, 기존에 구현된 `RedisLock`(`acquire_user_operation_lock`)을 적극 활용하여 트랜잭션 무결성을 보장합니다.
- **Lazy Loading 금지:** Phase 1에서 세션을 닫기 때문에, 필요한 연관 데이터(예: `User.settings`, `Holding.user`)는 반드시 조회 시점(Phase 1)에 Eager Loading(`joinedload` 등)으로 미리 모두 가져오거나, 세션 분리 전에 접근해 두어야 `DetachedInstanceError`가 발생하지 않습니다.

## 4. 고성능 동시성 제어 3중 방어선 (Lock-Free 지향)

위의 Micro-Session Pattern을 기반으로 트랜잭션을 분리했을 때 필연적으로 발생하는 **Lost Update (중복 차감)** 및 **Double Fill (중복 체결)** 이슈를 완벽히 막아내기 위해, 시스템을 느리게 만드는 수동 비관적 락(`FOR UPDATE`)이나 캐시 맹신 꼼수(`expire_on_commit=False`)를 배제하고 글로벌 금융 표준 방어선을 채택했습니다.

### 방어선 1: 애플리케이션 분산 락 (Redis)
*   **역할**: 가장 바깥쪽에서 동일 종목/동일 사용자의 동시 접근을 1차로 줄 세우는 방어막.
*   **구현**: `acquire_symbol_order_lock()`, `acquire_user_operation_lock()`
*   **한계 보완**: 서버 재시작, 파이썬 GC 정지 등에 의해 락이 풀리는 찰나의 순간을 막기 위해 아래의 DB 레벨 방어선(2, 3)을 반드시 병행합니다.

### 방어선 2: DB 엔진의 원자적 업데이트 (Atomic In-place Update) + 멱등성 (Idempotency)
*   **적용 영역**: 잔고(`Holding` 수량 증감), 주문 체결과 같은 **핵심 금융 연산 영역**.
*   **원자적 연산 (Atomic Update)**:
    파이썬이 값을 읽고 계산해서 다시 넣는(Read-Modify-Write) 비관적 방식을 버렸습니다. 대신 `UPDATE holdings SET quantity = quantity - X WHERE quantity >= X` 라는 단일 SQL 쿼리를 날려, **DB 엔진이 찰나의 순간(0.001초 미만)에 직접 락을 걸고 계산과 검증까지 끝내도록** 위임합니다.
*   **멱등성 키 검증 (Idempotency Key)**:
    증권사 주문 체결을 DB에 기록하기 전, 고유한 주문 번호(`order_no`)를 기반으로 `TradeLog`를 조회합니다. 네트워크 지연으로 인해 동일한 체결 요청이 2번 들어오더라도 여기서 100% 튕겨냅니다.

### 방어선 3: 낙관적 락 (Optimistic Locking)
*   **적용 영역**: 사용자 설정(`UserSettings`), 종목 뷰 상태 등 충돌이 잦지만 돈과 직결되지 않는 상태 관리 영역.
*   **구현 원리**: `models.py`의 테이블에 `version_id_col`을 추가했습니다. 두 스레드가 동시에 읽고 쓸 때, 간발의 차이로 늦게 도착한 업데이트 쿼리는 `version_id`가 맞지 않아 `StaleDataError`를 내며 튕겨나갑니다. 대기(Wait) 시간 없이 가장 빠르고 쾌적하게 충돌을 방지합니다.

이러한 **3단 콤보 하이브리드 방어선** 구축을 통해, 파이썬 서버의 네트워크 지연이 DB 락 병목으로 이어지는 참사를 원천 차단하고 향후 PostgreSQL 환경에서도 극강의 처리량을 보장합니다.
