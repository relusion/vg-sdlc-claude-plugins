from dataclasses import dataclass


@dataclass
class Order:
    id: str
    user_id: str
    total_cents: int
    status: str


class OrderRepository:
    def __init__(self) -> None:
        self._orders = [
            Order(id="ord_1", user_id="usr_ada", total_cents=1299, status="paid"),
            Order(id="ord_2", user_id="usr_ada", total_cents=2400, status="open"),
        ]

    def for_user(self, user_id: str) -> list[Order]:
        return [order for order in self._orders if order.user_id == user_id]


def render_orders_report(rows: list[Order]) -> str:
    lines = ["Order ID | Status | Total"]
    for row in rows:
        total = f"${row.total_cents / 100:.2f}"
        lines.append(f"{row.id} | {row.status} | {total}")
    return "\n".join(lines)

