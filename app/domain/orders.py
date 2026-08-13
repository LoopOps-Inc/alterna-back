from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"

class TimeInForce(str, Enum):
    DAY = "DAY"
    GTC = "GTC"
    FOK = "FOK"

class OrderStatus(str, Enum):
    PENDING_PREVIEW = "PENDING_PREVIEW"
    RECEIVED = "RECEIVED"
    SENT_TO_CUSTODIAN = "SENT_TO_CUSTODIAN"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderPreview(BaseModel):
    preview_token: str
    account_id: str
    instrument_id: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    time_in_force: TimeInForce
    estimated_price: Decimal
    commission: Decimal
    vat: Decimal
    estimated_withholding_tax: Decimal
    fx_rate: Decimal
    fx_markup: Decimal
    total_estimated_cost: Decimal
    expires_at: datetime
    disclosure_id: Optional[str] = None
    disclosure_version: Optional[str] = None
    is_suitable: bool

class Order(BaseModel):
    order_id: str
    account_id: str
    instrument_id: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    time_in_force: TimeInForce
    is_advised: bool = False  # BE-044
    status: OrderStatus
    idempotency_key: str
    created_at: datetime
    filled_at: Optional[datetime] = None
    average_filled_price: Optional[Decimal] = None
