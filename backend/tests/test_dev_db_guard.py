"""개발 DB 오염 가드(conftest.guard_dev_database_untouched)의 판정 로직 회귀.

2026-09-09: 라이브 봇이 스캐너 경로에서 stock_translations 에 신규 종목명을
append 하는데(Translator.translate 자가학습), 가드가 행 수 동일성으로 보는 바람에
테스트가 전량 통과했는데도 teardown 이 실패했다. append 는 통과시키되 유실은
그대로 잡는다는 계약을 여기서 고정한다.
"""

from tests.conftest import detect_dev_db_pollution


def _snapshot(users: int, strategies: int, baseline_rows: int) -> dict:
    return {
        "users": users,
        "strategies": strategies,
        "stock_translations": {"baseline_rows": baseline_rows},
    }


def test_bot_append_to_translation_cache_is_not_pollution():
    """봇이 신규 종목명을 추가해도(기존 행 그대로) 오염이 아니다."""
    before = _snapshot(users=13, strategies=100, baseline_rows=2417)
    after = _snapshot(users=13, strategies=100, baseline_rows=2417)
    assert detect_dev_db_pollution(before, after) == {}


def test_losing_preexisting_translation_rows_is_pollution():
    """스냅샷 시점에 있던 행이 사라지면 append 관용 테이블도 오염으로 잡는다."""
    before = _snapshot(users=13, strategies=100, baseline_rows=2417)
    after = _snapshot(users=13, strategies=100, baseline_rows=2416)
    assert detect_dev_db_pollution(before, after) == {"stock_translations": (2417, 2416)}


def test_user_row_change_is_still_pollution():
    """2026-08-24 사고의 실제 피해 양상(유저 데이터 변동)은 종전대로 즉시 실패."""
    before = _snapshot(users=13, strategies=100, baseline_rows=2417)
    after = _snapshot(users=12, strategies=100, baseline_rows=2417)
    assert detect_dev_db_pollution(before, after) == {"users": (13, 12)}


def test_missing_snapshot_is_not_pollution():
    """스냅샷을 못 뜬 환경(비 SQLite 등)에서는 가드가 개입하지 않는다."""
    assert detect_dev_db_pollution(None, _snapshot(13, 100, 2417)) == {}
    assert detect_dev_db_pollution(_snapshot(13, 100, 2417), None) == {}
