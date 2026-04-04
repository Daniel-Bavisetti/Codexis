from repositories.memory_store import InMemoryStore


class ReportingService:
    def __init__(self, inventory_repository: InMemoryStore, order_repository: InMemoryStore) -> None:
        self.inventory_repository = inventory_repository
        self.order_repository = order_repository

    def build_overview(self) -> dict:
        books = self.inventory_repository.list_books()
        orders = self.order_repository.list_orders()
        revenue = round(sum(order.total_amount for order in orders), 2)
        low_stock = [book.to_dict() for book in books if book.is_low_stock()]

        return {
            "catalog_size": len(books),
            "orders_count": len(orders),
            "total_revenue": revenue,
            "low_stock_books": low_stock,
            "top_titles": [book.title for book in books[:3]],
        }
