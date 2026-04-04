from services.inventory_service import InventoryService


def seed_store(inventory_service: InventoryService) -> None:
    books = [
        ("bk-100", "Practical FastAPI", "Dana Holt", 34.99, 12, 4),
        ("bk-101", "Designing Data Workflows", "Mina Brooks", 42.50, 8, 3),
        ("bk-102", "Testing Python Services", "Aaron Pike", 29.00, 3, 3),
        ("bk-103", "Clean APIs in Practice", "Lena Ford", 37.75, 6, 2),
    ]

    for sku, title, author, price, quantity, reorder_level in books:
        inventory_service.add_book(
            sku=sku,
            title=title,
            author=author,
            price=price,
            quantity=quantity,
            reorder_level=reorder_level,
        )
