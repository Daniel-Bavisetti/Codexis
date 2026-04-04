from models.book import Book
from models.order import Order


class InMemoryStore:
    def __init__(self) -> None:
        self._books: dict[str, Book] = {}
        self._orders: list[Order] = []

    def list_books(self) -> list[Book]:
        return sorted(self._books.values(), key=lambda book: book.title.lower())

    def get_book(self, sku: str) -> Book | None:
        return self._books.get(sku)

    def save_book(self, book: Book) -> Book:
        self._books[book.sku] = book
        return book

    def list_orders(self) -> list[Order]:
        return list(self._orders)

    def get_order(self, order_id: int) -> Order | None:
        for order in self._orders:
            if order.order_id == order_id:
                return order
        return None

    def save_order(self, order: Order) -> Order:
        self._orders.append(order)
        return order