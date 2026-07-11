from app import receive_webhook, validate_webhook


def test_rejects_missing_webhook_token():
    ok, status = validate_webhook({})
    assert ok is False
    assert status == 401


def test_accepts_matching_webhook_token(monkeypatch):
    monkeypatch.setenv("WEBHOOK_TOKEN", "secret")
    response = receive_webhook({"X-Webhook-Token": "secret"}, {"event": "ping"})
    assert response["accepted"] is True
    assert response["status"] == 200
