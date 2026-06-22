import pytest
from app.core.redis_client import ping_redis
from app.core.locks import acquire_user_operation_lock, acquire_symbol_order_lock

@pytest.mark.asyncio
async def test_redis_locks_integration():
    """
    [통합 테스트] 실제 구동 중인 Redis (또는 Memurai) 서버에 접속하여 
    '가상 잔고 잠금'과 '종목별 칸막이' 기능이 정상 작동하는지 검증합니다.
    """
    # 1. Redis 서버 구동 여부 확인
    is_alive = await ping_redis()
    if not is_alive:
        pytest.skip("로컬 Redis 서버가 구동되지 않아 통합 테스트를 건너뜁니다.")

    # 2. '돈부터 미리 빼놓기 (가상 잔고 잠금)' 통합 검증
    user_id = 9999
    lock1 = await acquire_user_operation_lock(user_id, "test-req-1", 5)
    assert lock1 is not None, "첫 번째 요청의 유저 락 획득 실패"
    
    # 락이 유지되는 동안 동일 유저의 중복 요청은 차단되어야 함
    lock2 = await acquire_user_operation_lock(user_id, "test-req-2", 5)
    assert lock2 is None, "중복 요청이 차단되지 않고 락을 획득함 (초과 매수 위험)"
    
    await lock1.release()

    # 3. '종목별 칸막이 치기 (종목 단위 락)' 통합 검증
    symbol = "TEST-AAPL"
    lock3 = await acquire_symbol_order_lock(user_id, symbol, "test-req-3", 5)
    assert lock3 is not None, "애플 종목 락 획득 실패"
    
    # 동일 종목(AAPL)의 중복 주문은 튕겨내야 함
    lock4 = await acquire_symbol_order_lock(user_id, symbol, "test-req-4", 5)
    assert lock4 is None, "동일 종목의 중복 요청이 차단되지 않음"
    
    # 하지만 다른 종목(TSLA) 주문은 락에 구애받지 않고 통과되어야 함 (병렬 처리 확인)
    lock5 = await acquire_symbol_order_lock(user_id, "TEST-TSLA", "test-req-5", 5)
    assert lock5 is not None, "다른 종목(TSLA) 락 획득 실패 (칸막이 분리 오류)"
    
    await lock5.release()
    await lock3.release()
