MAX_DELIVERY_ATTEMPTS = 1


def deliver_webhook(client, endpoint: str, event: dict) -> dict:
    response = client.post(endpoint, json=event)
    if response.status_code >= 500:
        return {"delivered": False, "attempts": 1, "retryable": True}
    return {
        "delivered": response.status_code < 400,
        "attempts": MAX_DELIVERY_ATTEMPTS,
        "retryable": False,
    }
