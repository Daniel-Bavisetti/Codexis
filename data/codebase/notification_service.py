import logging
from typing import List

from services.inventory_service import InventoryService
from models.book import Book

logger = logging.getLogger(__name__)
# Configure logger to output to console for demonstration purposes
# In a production environment, this would likely be configured via a global logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class NotificationService:
    """
    Service responsible for checking inventory levels and generating low-stock alerts.
    """
    def __init__(self, inventory_service: InventoryService) -> None:
        """
        Initializes the NotificationService with an InventoryService instance.

        Args:
            inventory_service: An instance of InventoryService to access book inventory data.
        """
        self.inventory_service = inventory_service

    def check_and_send_low_stock_alerts(self) -> List[dict]:
        """
        Checks the inventory for any books that are currently in low stock
        and "sends" alerts by logging a warning message for each.

        Returns:
            A list of dictionaries, where each dictionary represents a low-stock book
            that triggered an alert.
        """
        low_stock_books_data: List[dict] = []
        all_books = self.inventory_service.list_books()

        for book in all_books:
            if book.is_low_stock():
                alert_message = (
                    f"LOW STOCK ALERT: Book '{book.title}' (SKU: {book.sku}) "
                    f"has only {book.quantity} units left. Reorder level is {book.reorder_level}."
                )
                logger.warning(alert_message)
                low_stock_books_data.append(book.to_dict())

        return low_stock_books_data

    def get_low_stock_books(self) -> List[dict]:
        """
        Retrieves a list of all books that are currently in low stock without sending alerts.

        Returns:
            A list of dictionaries, where each dictionary represents a low-stock book.
        """
        low_stock_books_data: List[dict] = []
        all_books = self.inventory_service.list_books()

        for book in all_books:
            if book.is_low_stock():
                low_stock_books_data.append(book.to_dict())

        return low_stock_books_data