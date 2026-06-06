from types import SimpleNamespace

from app.bot.kis_broker import KISBroker


class FakeClient:
    def __init__(self, statuses):
        self.statuses = iter(statuses)

    def check_order_status(self, order_no):
        return next(self.statuses)


def make_broker(statuses):
    broker = KISBroker.__new__(KISBroker)
    broker.db_settings = SimpleNamespace(trade_mode="MOCK")
    broker.client = FakeClient(statuses)
    broker.FILL_POLL_INTERVAL_SEC = 0
    broker.FILL_POLL_MAX_RETRIES = len(statuses)
    return broker


def test_confirm_fill_does_not_fabricate_fill_after_timeout():
    broker = make_broker([
        {"status": "UNFILLED"},
        {"status": "UNFILLED"},
    ])

    result = broker._confirm_fill("ORDER-1", submitted_qty=10, submitted_price=100.0)

    assert result == {
        "status": "PENDING",
        "filled_qty": 0,
        "filled_price": 0.0,
        "confirmed": False,
    }


def test_confirm_fill_preserves_partial_fill_status():
    broker = make_broker([
        {
            "status": "PARTIAL",
            "filled_qty": 3,
            "ordered_qty": 10,
            "filled_price": 101.25,
        }
    ])

    result = broker._confirm_fill("ORDER-2", submitted_qty=10, submitted_price=100.0)

    assert result == {
        "status": "PARTIAL",
        "filled_qty": 3,
        "filled_price": 101.25,
        "confirmed": False,
    }
