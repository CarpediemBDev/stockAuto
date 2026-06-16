from app.bot.broker_factory import BROKER_REGISTRY, get_broker_catalog
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
