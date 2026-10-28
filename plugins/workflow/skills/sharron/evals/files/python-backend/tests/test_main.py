from app.main import ORDERS, get_order


def test_known_order_is_returned():
    assert get_order(1) == ORDERS[1]


def test_unknown_order_reports_not_found():
    assert get_order(99) == {"error": "not found"}
