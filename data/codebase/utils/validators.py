def normalize_sku(raw_sku: str) -> str:
    sku = raw_sku.strip().upper()
    if len(sku) < 3:
        raise ValueError("SKU must be at least 3 characters long")
    return sku

def require_positive_quantity(quantity: int) -> None:
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero")

def validate_customer_name(name: str) -> None:
    if not name or len(name.strip()) == 0:
        raise ValueError("Customer name cannot be empty")
    if len(name) > 100:
        raise ValueError("Customer name cannot exceed 100 characters")

def validate_order_items(items: list[dict]) -> None:
    if not items:
        raise ValueError("Order must include at least one item")

    seen_skus = set()
    for item in items:
        if "sku" not in item or "quantity" not in item:
            raise ValueError("Each item must include sku and quantity")
        
        normalized_sku = normalize_sku(item["sku"])
        if normalized_sku in seen_skus:
            raise ValueError(f"Duplicate SKU '{item['sku']}' found in order items. SKUs must be unique (case-insensitive).")
        seen_skus.add(normalized_sku)
        
        require_positive_quantity(item["quantity"])