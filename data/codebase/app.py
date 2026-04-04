from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from services.inventory_service import InventoryService
from services.order_service import OrderService
from services.reporting_service import ReportingService
from utils.seed import seed_store


app = FastAPI(title="BookBarn API", version="1.0.0")

inventory_service = InventoryService()
order_service = OrderService(inventory_service.repository)
reporting_service = ReportingService(inventory_service.repository, order_service.repository)


class RestockRequest(BaseModel):
    sku: str = Field(..., min_length=3)
    quantity: int = Field(..., gt=0)


class OrderItemRequest(BaseModel):
    sku: str = Field(..., min_length=3)
    quantity: int = Field(..., gt=0)


class CreateOrderRequest(BaseModel):
    customer_name: str = Field(..., min_length=2)
    items: list[OrderItemRequest]


@app.on_event("startup")
def startup() -> None:
    if not inventory_service.list_books():
        seed_store(inventory_service)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "BookBarn API"}


@app.get("/books")
def list_books(low_stock_only: bool = False) -> list[dict]:
    return [book.to_dict() for book in inventory_service.list_books(low_stock_only=low_stock_only)]


@app.get("/books/{sku}")
def get_book(sku: str) -> dict:
    book = inventory_service.get_book(sku)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book.to_dict()


@app.post("/books/{sku}/restock")
def restock_book(sku: str, request: RestockRequest) -> dict:
    if sku != request.sku:
        raise HTTPException(status_code=400, detail="Path SKU does not match payload SKU")
    try:
        updated = inventory_service.restock_book(request.sku, request.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return updated.to_dict()


@app.post("/orders")
def create_order(request: CreateOrderRequest) -> dict:
    try:
        order = order_service.create_order(
            customer_name=request.customer_name,
            items=[item.model_dump() for item in request.items],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return order.to_dict()


@app.get("/orders")
def list_orders() -> list[dict]:
    return [order.to_dict() for order in order_service.list_orders()]


@app.get("/reports/overview")
def get_overview() -> dict:
    return reporting_service.build_overview()
