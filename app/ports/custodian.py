from typing import Protocol, List, Dict, Any, Optional
from app.domain.portfolio import Position

class ICustodianService(Protocol):
    async def fetch_realtime_positions(self, account_id: str) -> List[Dict[str, Any]]:
        """Fetch positions directly from custodian API. Should throw on error."""
        ...

    async def submit_order_to_market(self, order_data: Dict[str, Any], idempotency_key: str) -> Dict[str, Any]:
        """Submit order to custodian with a strict 5-second timeout and no auto-retries (BE-048)."""
        ...
