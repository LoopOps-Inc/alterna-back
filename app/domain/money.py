from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field

class Beneficiary(BaseModel):
    id: str
    account_id: str
    name: str
    clabe: str = Field(..., max_length=18, min_length=18)
    bank_name: str
    is_third_party: bool = True
    created_at: datetime
    cooldown_until: datetime  # RF-071 Enforce withdrawal cooldown

class Transfer(BaseModel):
    transfer_id: str
    account_id: str
    beneficiary_id: str
    amount: Decimal
    currency: str = "MXN"
    idempotency_key: str
    created_at: datetime
    status: str = "PENDING"
