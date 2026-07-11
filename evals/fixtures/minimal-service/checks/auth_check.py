from app import login, rate_limiter


def test_login_rate_limit_blocks_after_limit():
    for _ in range(rate_limiter.limit):
        assert login("ada", "wrong")["status"] == 401
    assert login("ada", "wrong")["status"] == 429
