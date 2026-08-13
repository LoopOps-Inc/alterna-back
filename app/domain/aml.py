from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel

class AMLAlert(BaseModel):
    id: str
    party_id: str
    rule_code: str  # AML-01, AML-02, etc.
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    description: str
    payload_snapshot: str  # JSON dump of context
    created_at: datetime
    is_resolved: bool = False
