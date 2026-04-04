from dataclasses import dataclass


@dataclass(slots=True)
class Book:
    sku: str
    title: str
    author: str
    price: float
    quantity: int
    reorder_level: int

    def is_low_stock(self) -> bool:
        return self.quantity <= self.reorder_level

    def to_dict(self) -> dict:
        return {
            "sku": self.sku,
            "title": self.title,
            "author": self.author,
            "price": round(self.price, 2),
            "quantity": self.quantity,
            "reorder_level": self.reorder_level,
            "low_stock": self.is_low_stock(),
        }
