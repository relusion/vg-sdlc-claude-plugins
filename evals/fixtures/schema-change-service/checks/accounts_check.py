from accounts import account_summary


def test_account_summary_includes_email_and_status():
    assert account_summary({"email": "a@example.com", "status": "active"}) == "a@example.com (active)"
