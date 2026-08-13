import httpx
import logging
import asyncio
from typing import List, Dict, Any
from app.ports.custodian import ICustodianService
from app.core.config import settings

logger = logging.getLogger("altm_backend")

class PershingCustodianClient(ICustodianService):
    def __init__(self):
        self.base_url = settings.PERSHING_API_URL
        self.api_key = settings.PERSHING_API_KEY
        self.timeout = settings.PERSHING_TIMEOUT  # Strict 5 seconds BE-048

    async def fetch_realtime_positions(self, account_id: str) -> List[Dict[str, Any]]:
        # Mock mode when running in local development or test environment
        if "example.com" in self.base_url or not self.api_key:
            return [
                {
                    "instrument_id": "inst-aapl",
                    "ticker": "AAPL",
                    "name": "Apple Inc.",
                    "quantity": 100.0,
                    "market_price": 175.50,
                    "average_cost": 150.00,
                    "currency": "USD",
                    "asset_class": "EQUITY",
                    "sector": "TECHNOLOGY",
                    "geography": "US"
                },
                {
                    "instrument_id": "inst-msft",
                    "ticker": "MSFT",
                    "name": "Microsoft Corp.",
                    "quantity": 50.0,
                    "market_price": 415.00,
                    "average_cost": 380.00,
                    "currency": "USD",
                    "asset_class": "EQUITY",
                    "sector": "TECHNOLOGY",
                    "geography": "US"
                }
            ]

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/accounts/{account_id}/positions",
                    headers=headers,
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as e:
                logger.error(f"Custodian fetch positions timeout: {str(e)}")
                raise asyncio.TimeoutError("Custodian request timed out.")
            except Exception as e:
                logger.error(f"Custodian connection error: {str(e)}")
                raise

    async def submit_order_to_market(self, order_data: Dict[str, Any], idempotency_key: str) -> Dict[str, Any]:
        """Submit order to custodian API (5-second strict timeout, NO automatic retries BE-048)."""
        if "example.com" in self.base_url or not self.api_key:
            # Simulate a brief network delay (e.g. 100ms) and return success
            await asyncio.sleep(0.1)
            return {
                "order_id": order_data.get("order_id", "mock-ord-123"),
                "status": "SENT_TO_CUSTODIAN",
                "idempotency_key": idempotency_key,
                "timestamp": "2024-03-10T12:00:00Z"
            }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Idempotency-Key": idempotency_key,
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                # Strictly NO automatic retries on this HTTP client.
                response = await client.post(
                    f"{self.base_url}/orders",
                    json=order_data,
                    headers=headers,
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as e:
                logger.error(
                    f"Custodian submit order timeout for key {idempotency_key}. "
                    "NO auto-retry will be performed to prevent double transactions! (BE-048)"
                )
                raise asyncio.TimeoutError("Custodian order submission timed out. Reconciliation required.")
            except Exception as e:
                logger.error(f"Custodian order submission failed: {str(e)}")
                raise
