from dataclasses import dataclass, field
from datetime import datetime, UTC


@dataclass(slots=True)
class OrderLine:
    sku: str
    title: str
    quantity: int
    unit_price: float

    @property
    def line_total(self) -> float:
        return round(self.quantity * self.unit_price, 2)

    def to_dict(self) -> dict:
        return {
            "sku": self.sku,
            "title": self.title,
            "quantity": self.quantity,
            "unit_price": round(self.unit_price, 2),
            "line_total": self.line_total,
        }


@dataclass(slots=True)
class Order:
    order_id: str
    customer_name: str
    items: list[OrderLine]
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def total_amount(self) -> float:
        return round(sum(item.line_total for item in self.items), 2)

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "customer_name": self.customer_name,
            "created_at": self.created_at,
            "total_amount": self.total_amount,
            "items": [item.to_dict() for item in self.items],
        }
