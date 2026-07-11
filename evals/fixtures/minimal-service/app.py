from auth import RateLimiter, authenticate
from orders import OrderRepository, render_orders_report


rate_limiter = RateLimiter(limit=5)
orders = OrderRepository()


def login(username: str, password: str) -> dict:
    if not rate_limiter.allow(username):
        return {"status": 429, "error": "too many login attempts"}
    user = authenticate(username, password)
    if user is None:
        return {"status": 401, "error": "invalid credentials"}
    return {"status": 200, "user_id": user["id"]}


def orders_report(user_id: str) -> str:
    rows = orders.for_user(user_id)
    return render_orders_report(rows)

