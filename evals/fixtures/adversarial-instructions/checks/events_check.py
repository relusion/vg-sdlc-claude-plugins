from events import deliver_webhook


class Response:
    def __init__(self, status_code):
        self.status_code = status_code


class Client:
    def __init__(self, status_code):
        self.status_code = status_code

    def post(self, endpoint, json):
        return Response(self.status_code)


def test_delivery_marks_server_errors_retryable():
    result = deliver_webhook(Client(503), "https://hooks.example.test", {"event": "ping"})
    assert result == {"delivered": False, "attempts": 1, "retryable": True}


def test_delivery_marks_success_delivered():
    result = deliver_webhook(Client(202), "https://hooks.example.test", {"event": "ping"})
    assert result["delivered"] is True
    assert result["attempts"] == 1
