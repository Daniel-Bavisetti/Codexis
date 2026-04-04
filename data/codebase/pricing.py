import math

def calculate_discounted_price(original_price: float, discount_percentage: float) -> float:
    """
    Calculates the price after applying a percentage discount.

    Args:
        original_price: The original price of the item. Must be non-negative.
        discount_percentage: The percentage discount to apply (e.g., 10 for 10% off).
                             Must be between 0 and 100.

    Returns:
        The price after applying the discount.

    Raises:
        ValueError: If original_price is negative or discount_percentage is out of range.
    """
    if original_price < 0:
        raise ValueError("Original price cannot be negative.")
    if not (0 <= discount_percentage <= 100):
        raise ValueError("Discount percentage must be between 0 and 100.")

    discount_factor = 1 - (discount_percentage / 100)
    discounted_price = original_price * discount_factor
    return round(discounted_price, 2)