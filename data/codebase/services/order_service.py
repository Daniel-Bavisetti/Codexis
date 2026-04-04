from itertools import count

from models.order import Order, OrderLine
from repositories.memory_store import InMemoryStore
from utils.validators import validate_customer_name, validate_order_items


class OrderService:
    _counter = count(1001)

    def __init__(self, repository: InMemoryStore) -> None:
        self.repository = repository

    def create_order(self, customer_name: str, items: list[dict]) -> Order:
        validate_customer_name(customer_name)
        validate_order_items(items)

        lines: list[OrderLine] = []
        for item in items:
            sku = item["sku"].strip().upper()
            quantity = item["quantity"]
            book = self.repository.get_book(sku)
            if not book:
                raise ValueError(f"Book with SKU {sku} was not found")
            if book.quantity < quantity:
                raise ValueError(f"Not enough copies available for {book.title}")
            book.quantity -= quantity
            self.repository.save_book(book)
            lines.append(
                OrderLine(
                    sku=book.sku,
                    title=book.title,
                    quantity=quantity,
                    unit_price=book.price,
                )
            )

        order = Order(
            order_id=f"ORD-{next(self._counter)}",
            customer_name=customer_name.strip(),
            items=lines,
        )
        return self.repository.save_order(order)

    def list_orders(self) -> list[Order]:
        return self.repository.list_orders()
