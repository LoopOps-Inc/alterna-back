from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field

class TaxLot(BaseModel):
    id: str
    instrument_id: str
    purchase_date: datetime
    quantity: Decimal
    purchase_price: Decimal
    remaining_quantity: Decimal

class Position(BaseModel):
    instrument_id: str
    ticker: str
    name: str
    quantity: Decimal
    market_price: Decimal
    average_cost: Decimal
    market_value: Decimal
    unrealized_gain_loss: Decimal
    currency: str = "USD"
    # Allocation properties BE-026
    asset_class: str
    sector: str
    geography: str

class PerformanceSnapshot(BaseModel):
    account_id: str
    snapshot_date: datetime
    twr: Decimal = Field(..., description="Time-Weighted Return")
    mwr: Decimal = Field(..., description="Money-Weighted Return")

class PortfolioSummary(BaseModel):
    account_id: str
    positions: List[Position]
    total_market_value_usd: Decimal
    total_market_value_mxn: Decimal
    cash_operable: Decimal = Field(..., description="Operable cash BE-025")
    cash_retirable: Decimal = Field(..., description="Retirable cash BE-025")
    cash_committed: Decimal = Field(..., description="Committed in open orders BE-025")
    cash_in_transit: Decimal = Field(..., description="In settlement process BE-025")
    
    # Metadata required by BE-028
    data_as_of: datetime
    data_source: str = "Pershing LLC"
    is_realtime: bool
