"""스캐너 릴레이 파이프라인(watchlist_relay) 회귀 테스트.

핵심 불변식:
1. 소스 실패/노후화 시 해당 몫만 비우고 예외를 전파하지 않는다 (자연 강등).
2. 점수 하한·소스당 상한·중복 제거가 지켜진다.
3. Stage 2 예약 슬롯은 순수 추가형 — 기존 상위 컷의 구성과 순서를 바꾸지 않는다.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.scanner import watchlist_relay as relay


@pytest.fixture(autouse=True)
def relay_enabled(monkeypatch):
    """킬 스위치 조회가 로컬 DB 상태에 좌우되지 않도록 기본 ON으로 고정한다.

    스위치 자체를 검증하는 테스트는 이 픽스처를 다시 덮어쓴다.
    """
    monkeypatch.setattr(relay, "is_system_setting_enabled", lambda key: True)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class TestFreshness:
    def test_recent_timestamp_is_fresh(self):
        assert relay._is_fresh(_iso(datetime.now(timezone.utc) - timedelta(hours=10)))

    def test_stale_timestamp_is_rejected(self):
        stale = datetime.now(timezone.utc) - timedelta(hours=relay.MAX_AGE_HOURS + 1)
        assert not relay._is_fresh(_iso(stale))

    def test_none_and_garbage_are_rejected(self):
        assert not relay._is_fresh(None)
        assert not relay._is_fresh("")
        assert not relay._is_fresh("not-a-date")

    def test_naive_timestamp_is_treated_as_utc(self):
        naive = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None)
        assert relay._is_fresh(naive.isoformat())


class TestTopTickers:
    def test_score_floor_and_descending_order(self):
        candidates = [
            {"ticker": "aaa", "score": 70.0},
            {"ticker": "BBB", "score": 64.9},
            {"ticker": "CCC", "score": 90.0},
        ]
        assert relay._top_tickers(candidates, 65.0) == ["CCC", "AAA"]

    def test_per_source_cap(self):
        candidates = [{"ticker": f"T{i}", "score": 80.0 + i} for i in range(relay.MAX_PER_SOURCE + 10)]
        assert len(relay._top_tickers(candidates, 60.0)) == relay.MAX_PER_SOURCE

    def test_duplicates_and_malformed_entries_are_skipped(self):
        candidates = [
            {"ticker": "AAA", "score": 80.0},
            {"ticker": "AAA", "score": 75.0},
            {"ticker": "", "score": 99.0},
            {"score": 99.0},
            "not-a-dict",
            {"ticker": "BBB", "score": "abc"},
        ]
        assert relay._top_tickers(candidates, 60.0) == ["AAA"]


class TestPriorityMap:
    def test_merges_both_sources_with_tags(self, monkeypatch):
        monkeypatch.setattr(relay, "_collect_after_hours", lambda: ["AAA", "BBB"])
        monkeypatch.setattr(relay, "_collect_swing", lambda: ["BBB", "CCC"])
        result = relay.get_relay_priority_map()
        assert result == {
            "AAA": [relay.RELAY_SOURCE_AFTER_HOURS],
            "BBB": [relay.RELAY_SOURCE_AFTER_HOURS, relay.RELAY_SOURCE_SWING],
            "CCC": [relay.RELAY_SOURCE_SWING],
        }

    def test_one_source_failure_keeps_the_other(self, monkeypatch):
        def boom():
            raise RuntimeError("cache down")

        monkeypatch.setattr(relay, "_collect_after_hours", boom)
        monkeypatch.setattr(relay, "_collect_swing", lambda: ["CCC"])
        assert relay.get_relay_priority_map() == {"CCC": [relay.RELAY_SOURCE_SWING]}

    def test_total_failure_returns_empty(self, monkeypatch):
        def boom():
            raise RuntimeError("down")

        monkeypatch.setattr(relay, "_collect_after_hours", boom)
        monkeypatch.setattr(relay, "_collect_swing", boom)
        assert relay.get_relay_priority_map() == {}

    def test_after_hours_collector_respects_freshness_and_score(self, monkeypatch):
        fresh_cache = {
            "candidates": [
                {"ticker": "HOT", "score": 82.0},
                {"ticker": "LUKE", "score": 64.0},
            ],
            "updated_at": _iso(datetime.now(timezone.utc) - timedelta(hours=8)),
        }
        import app.scanner.after_hours_scanner as ah

        monkeypatch.setattr(ah, "read_after_hours_candidate_cache", lambda: fresh_cache)
        assert relay._collect_after_hours() == ["HOT"]

        stale_cache = dict(fresh_cache)
        stale_cache["updated_at"] = _iso(datetime.now(timezone.utc) - timedelta(hours=relay.MAX_AGE_HOURS + 5))
        monkeypatch.setattr(ah, "read_after_hours_candidate_cache", lambda: stale_cache)
        assert relay._collect_after_hours() == []


class TestRelaySourceTag:
    def test_detects_relay_tags(self):
        assert relay.is_relay_source([relay.RELAY_SOURCE_AFTER_HOURS])
        assert relay.is_relay_source(["MARKET", relay.RELAY_SOURCE_SWING])

    def test_rejects_non_relay_inputs(self):
        assert not relay.is_relay_source(["MARKET", "WATCHLIST"])
        assert not relay.is_relay_source([])
        assert not relay.is_relay_source(None)
        assert not relay.is_relay_source("RELAY_SWING")  # 문자열 단독은 목록이 아님
        assert not relay.is_relay_source([123])


class TestReservedSlots:
    def _cand(self, ticker, rvol, relay_tag=False):
        source = ["RELAY_AFTER_HOURS"] if relay_tag else ["MARKET"]
        return {"ticker": ticker, "rvol": rvol, "source": source}

    def test_top_cut_is_unchanged_without_relay(self):
        ranked = [self._cand(f"T{i}", 100 - i) for i in range(30)]
        merged = relay.merge_reserved_candidates(ranked, base_limit=25)
        assert merged == ranked[:25]

    def test_overflow_relay_candidates_are_appended(self):
        ranked = [self._cand(f"T{i}", 100 - i) for i in range(25)]
        ranked += [self._cand("R1", 1.0, relay_tag=True), self._cand("N1", 0.9), self._cand("R2", 0.8, relay_tag=True)]
        merged = relay.merge_reserved_candidates(ranked, base_limit=25)
        assert merged[:25] == ranked[:25]
        assert [c["ticker"] for c in merged[25:]] == ["R1", "R2"]

    def test_reserved_slot_cap(self):
        ranked = [self._cand(f"T{i}", 100 - i) for i in range(25)]
        ranked += [self._cand(f"R{i}", 1.0 - i * 0.01, relay_tag=True) for i in range(relay.RELAY_RESERVED_SLOTS + 3)]
        merged = relay.merge_reserved_candidates(ranked, base_limit=25)
        assert len(merged) == 25 + relay.RELAY_RESERVED_SLOTS

    def test_relay_candidate_inside_top_cut_is_not_duplicated(self):
        ranked = [self._cand("R0", 100, relay_tag=True)] + [self._cand(f"T{i}", 90 - i) for i in range(24)]
        ranked += [self._cand("N1", 0.5)]
        merged = relay.merge_reserved_candidates(ranked, base_limit=25)
        assert [c["ticker"] for c in merged].count("R0") == 1
        assert len(merged) == 25


class TestKillSwitch:
    def test_disabled_switch_returns_empty_map_without_touching_sources(self, monkeypatch):
        def boom():
            raise AssertionError("스위치가 꺼지면 소스를 조회하지 않아야 한다")

        monkeypatch.setattr(relay, "is_system_setting_enabled", lambda key: False)
        monkeypatch.setattr(relay, "_collect_after_hours", boom)
        monkeypatch.setattr(relay, "_collect_swing", boom)
        assert relay.get_relay_priority_map() == {}

    def test_enabled_switch_collects_normally(self, monkeypatch):
        monkeypatch.setattr(relay, "is_system_setting_enabled", lambda key: True)
        monkeypatch.setattr(relay, "_collect_after_hours", lambda: ["AAA"])
        monkeypatch.setattr(relay, "_collect_swing", lambda: [])
        assert relay.get_relay_priority_map() == {"AAA": [relay.RELAY_SOURCE_AFTER_HOURS]}

    def test_switch_is_queried_with_the_relay_key(self, monkeypatch):
        seen = []
        monkeypatch.setattr(relay, "is_system_setting_enabled", lambda key: seen.append(key) or True)
        monkeypatch.setattr(relay, "_collect_after_hours", lambda: [])
        monkeypatch.setattr(relay, "_collect_swing", lambda: [])
        relay.get_relay_priority_map()
        assert seen == [relay.SETTING_ENABLE_SCANNER_RELAY]

    def test_spec_default_is_on_so_db_failure_keeps_relay_alive(self):
        from app.core.system_settings import (
            SETTING_ENABLE_SCANNER_RELAY,
            SYSTEM_SETTING_SPECS,
        )

        spec = SYSTEM_SETTING_SPECS[SETTING_ENABLE_SCANNER_RELAY]
        # 조회 실패 시 get_system_setting이 default로 폴백하므로, 기본값이 ON이어야
        # 일시적 DB 장애가 매매 대상을 조용히 축소하지 않는다.
        assert spec.default is True
        assert spec.value_type == "bool"
        assert spec.is_runtime is True
