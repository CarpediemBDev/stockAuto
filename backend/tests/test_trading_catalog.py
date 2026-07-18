from types import SimpleNamespace

import pytest

from app.brokers.broker_factory import (
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


def test_catalog_exposes_supported_modes():
    catalog = {item["id"]: item for item in get_broker_catalog()}

    assert catalog["KIS"]["supported_modes"] == list(VALID_TRADE_MODES)
    assert catalog["TOSS"]["supported_modes"] == list(VALID_TRADE_MODES)


