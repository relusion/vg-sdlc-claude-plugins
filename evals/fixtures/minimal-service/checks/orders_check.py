from app import orders_report


def test_orders_report_renders_text_table():
    report = orders_report("usr_ada")
    assert "Order ID | Status | Total" in report
    assert "ord_1 | paid | $12.99" in report
