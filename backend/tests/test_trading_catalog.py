from types import SimpleNamespace

import pytest

from app.bot.broker_factory import (
    BROKER_REGISTRY,
    ensure_broker_supports_trade_mode,
    get_broker_catalog,
    get_broker_client,
)
from app.core.config import TRADE_MODE_CATALOG, VALID_TRADE_MODES


def test_trade_mode_catalog_is_the_validation_source():
    assert VALID_TRADE_MODES == tuple(
        item["id"]
        for item in TRADE_MODE_CATALOG
    )
    assert all(item["description"] for item in TRADE_MODE_CATALOG)


def test_broker_catalog_is_derived_from_runtime_registry():
    catalog = get_broker_catalog()

    assert {item["id"] for item in catalog} == set(BROKER_REGISTRY)
    for item in catalog:
        definition = BROKER_REGISTRY[item["id"]]
        assert item["label"] == definition["label"]
        assert item["supported_modes"] == [
            mode
            for mode in VALID_TRADE_MODES
            if mode in definition["broker_classes"]
        ]


def test_toss_catalog_exposes_only_supported_simulated_mode():
    catalog = {item["id"]: item for item in get_broker_catalog()}

    assert catalog["KIS"]["supported_modes"] == list(VALID_TRADE_MODES)
    assert catalog["TOSS"]["supported_modes"] == ["SIMULATED"]


def test_toss_mock_and_real_modes_are_rejected_before_broker_creation():
    ensure_broker_supports_trade_mode("TOSS", "SIMULATED")

    for mode in ("MOCK", "REAL"):
        with pytest.raises(ValueError, match=f"TOSS 증권사는 {mode} 모드를 지원하지 않습니다."):
            ensure_broker_supports_trade_mode("TOSS", mode)

        with pytest.raises(ValueError, match=f"TOSS 증권사는 {mode} 모드를 지원하지 않습니다."):
            get_broker_client(
                SimpleNamespace(
                    trade_mode=mode,
                    broker_provider="TOSS",
                    credentials=[],
                )
            )
