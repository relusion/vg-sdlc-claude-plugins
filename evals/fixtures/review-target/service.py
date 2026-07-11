class Order:
    def __init__(self, order_id: str, owner_id: str) -> None:
        self.order_id = order_id
        self.owner_id = owner_id
        self.cancelled = False


def cancel_order(order: Order, actor_id: str) -> Order:
    order.cancelled = True
    return order

