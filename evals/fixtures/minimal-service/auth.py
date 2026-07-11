from collections import defaultdict


USERS = {
    "ada": {"id": "usr_ada", "password": "correct-horse"},
}


class RateLimiter:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._attempts = defaultdict(int)

    def allow(self, username: str) -> bool:
        self._attempts[username] += 1
        return self._attempts[username] <= self.limit


def authenticate(username: str, password: str):
    user = USERS.get(username)
    if user and user["password"] == password:
        return user
    return None

