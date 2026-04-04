from models.book import Book
from repositories.memory_store import InMemoryStore
from utils.validators import normalize_sku, require_positive_quantity


class InventoryService:
    def __init__(self, repository: InMemoryStore | None = None) -> None:
        self.repository = repository or InMemoryStore()

    def add_book(self, sku: str, title: str, author: str, price: float, quantity: int, reorder_level: int = 5) -> Book:
        sku = normalize_sku(sku)
        require_positive_quantity(quantity)
        if self.repository.get_book(sku):
            raise ValueError(f"Book with SKU {sku} already exists")
        book = Book(
            sku=sku,
            title=title.strip(),
            author=author.strip(),
            price=round(price, 2),
            quantity=quantity,
            reorder_level=reorder_level,
        )
        return self.repository.save_book(book)

    def list_books(self, low_stock_only: bool = False) -> list[Book]:
        books = self.repository.list_books()
        if low_stock_only:
            return [book for book in books if book.is_low_stock()]
        return books

    def get_book(self, sku: str) -> Book | None:
        return self.repository.get_book(normalize_sku(sku))

    def restock_book(self, sku: str, quantity: int) -> Book:
        require_positive_quantity(quantity)
        book = self.get_book(sku)
        if not book:
            raise ValueError(f"Book with SKU {sku} was not found")
        book.quantity += quantity
        return self.repository.save_book(book)

    def reserve_stock(self, sku: str, quantity: int) -> Book:
        require_positive_quantity(quantity)
        book = self.get_book(sku)
        if not book:
            raise ValueError(f"Book with SKU {sku} was not found")
        if book.quantity < quantity:
            raise ValueError(f"Insufficient stock for {book.title}")
        book.quantity -= quantity
        return self.repository.save_book(book)
