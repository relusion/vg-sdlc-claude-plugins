import os

WEBHOOK_TOKEN = os.environ.get("WEBHOOK_TOKEN", "local-dev-token")


def validate_webhook(headers: dict[str, str]) -> tuple[bool, int]:
    supplied = headers.get("X-Webhook-Token")
    if supplied != WEBHOOK_TOKEN:
        return False, 401
    return True, 200


def receive_webhook(headers: dict[str, str], payload: dict) -> dict:
    ok, status = validate_webhook(headers)
    if not ok:
        return {"status": status, "accepted": False}
    return {"status": status, "accepted": True, "event": payload.get("event")}
