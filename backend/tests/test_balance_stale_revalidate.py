"""
계좌 잔고 stale-while-revalidate 트리거 로직 단위 테스트.

읽기 경로는 항상 스냅샷을 즉시 반환하고, 스냅샷이 모드별 임계값 이상 낡았을 때만
백그라운드 갱신을 발화한다. 두 화면(대시보드·봇시그널)이 동시에 폴링해도 유저·모드별
디바운스로 한 번만 트리거되어야 한다.
"""
import pytest

from app.trades import router_account
from app.trades.router_account import (
    _DEFAULT_REFRESH_THRESHOLD_SEC,
    _SNAPSHOT_REFRESH_THRESHOLD_SEC,
    _should_trigger_refresh,
)


@pytest.fixture(autouse=True)
def _clear_debounce_state():
    """각 테스트가 깨끗한 디바운스 상태에서 시작하도록 모듈 전역을 초기화."""
    router_account._last_refresh_trigger.clear()
    yield
    router_account._last_refresh_trigger.clear()


def test_fresh_snapshot_does_not_trigger():
    # SIMULATED 임계값(10초)보다 어리면 갱신하지 않는다.
    assert _should_trigger_refresh(1, "SIMULATED", snapshot_age_sec=5.0) is False


def test_stale_snapshot_triggers_once():
    # 임계값 이상 낡은 첫 요청은 트리거된다.
    assert _should_trigger_refresh(1, "SIMULATED", snapshot_age_sec=30.0) is True


def test_debounce_suppresses_immediate_retrigger():
    # 두 화면 동시 폴링 시나리오: 첫 요청만 트리거, 곧바로 온 두 번째는 디바운스로 억제.
    assert _should_trigger_refresh(7, "REAL", snapshot_age_sec=120.0) is True
    assert _should_trigger_refresh(7, "REAL", snapshot_age_sec=120.0) is False


def test_thresholds_are_mode_specific():
    # 동일한 20초 낡음이라도 모드별 임계값에 따라 판정이 갈린다.
    # SIMULATED(10초) → 트리거, REAL(45초) → 아직 아님.
    assert _should_trigger_refresh(10, "SIMULATED", snapshot_age_sec=20.0) is True
    assert _should_trigger_refresh(11, "REAL", snapshot_age_sec=20.0) is False


def test_unknown_mode_uses_default_threshold():
    # 미정의 모드는 기본 임계값(45초)로 폴백한다.
    assert _DEFAULT_REFRESH_THRESHOLD_SEC == 45.0
    assert _should_trigger_refresh(20, "WEIRD", snapshot_age_sec=30.0) is False
    assert _should_trigger_refresh(21, "WEIRD", snapshot_age_sec=50.0) is True


def test_different_users_are_independent():
    # 디바운스는 유저·모드 키별로 격리된다.
    assert _should_trigger_refresh(100, "SIMULATED", snapshot_age_sec=30.0) is True
    assert _should_trigger_refresh(101, "SIMULATED", snapshot_age_sec=30.0) is True


def test_threshold_table_covers_all_trade_modes():
    # 회귀 방어: 지원 3모드가 모두 임계값 테이블에 존재해야 한다.
    for mode in ("SIMULATED", "MOCK", "REAL"):
        assert mode in _SNAPSHOT_REFRESH_THRESHOLD_SEC
