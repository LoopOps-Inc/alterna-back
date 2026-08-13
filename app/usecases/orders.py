import uuid
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any
from app.ports.database import IOrderRepository, IPortfolioRepository
from app.ports.custodian import ICustodianService
from app.domain.orders import Order, OrderPreview, OrderType, TimeInForce, OrderStatus, OrderSide
from app.domain.exceptions import (
    InsufficientFundsException,
    NonSuitableInstrumentException,
    DomainException
)
from app.core.security import KeyVaultSigner

class OrderUseCase:
    def __init__(
        self,
        order_repo: IOrderRepository,
        portfolio_repo: IPortfolioRepository,
        custodian_service: ICustodianService
    ):
        self.order_repo = order_repo
        self.portfolio_repo = portfolio_repo
        self.custodian_service = custodian_service

    async def generate_order_preview(
        self,
        account_id: str,
        instrument_id: str,
        ticker: str,
        side: str,
        quantity: float,
        order_type: str,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = "DAY"
    ) -> OrderPreview:
        """BE-040 & BE-042 & BE-049: Calculates financial Preview parameters, signs Token and persists Snapshot"""
        qty_dec = Decimal(str(quantity))
        
        # Mocking values for preview calculation
        estimated_price = Decimal("150.00") if limit_price is None else Decimal(str(limit_price))
        subtotal = qty_dec * estimated_price
        
        commission = subtotal * Decimal("0.0015")  # Alterna commission of 0.15%
        vat = commission * Decimal("0.16")  # 16% IVA
        estimated_withholding_tax = Decimal("0.00")
        
        fx_rate = Decimal("17.15")
        fx_markup = Decimal("0.05")  # Margen comercial explícito
        
        total_estimated_cost = subtotal + commission + vat

        # Suitability Evaluation logic BE-042
        # Let's say high volatility tickers like TSLA/NVDA are not suitable for low-profile users
        is_suitable = True
        disclosure_id = None
        disclosure_version = None
        
        if ticker in ["TSLA", "NVDA", "MOCK_RISKY"]:
            is_suitable = False
            disclosure_id = "disc-suitability-high-vol"
            disclosure_version = "v2"

        # Generate signed cryptographically-secure preview token BE-040
        expires_at = datetime.utcnow() + timedelta(minutes=2)
        preview_data = {
            "account_id": account_id,
            "instrument_id": instrument_id,
            "side": side,
            "quantity": float(qty_dec),
            "estimated_price": float(estimated_price),
            "commission": float(commission),
            "total_estimated_cost": float(total_estimated_cost),
            "expires_at": expires_at.isoformat()
        }
        preview_token = KeyVaultSigner.sign_payload(preview_data)

        # Create Domain OrderPreview entity
        preview_entity = OrderPreview(
            preview_token=preview_token,
            account_id=account_id,
            instrument_id=instrument_id,
            side=OrderSide(side),
            quantity=qty_dec,
            order_type=OrderType(order_type),
            limit_price=Decimal(str(limit_price)) if limit_price is not None else None,
            stop_price=Decimal(str(stop_price)) if stop_price is not None else None,
            time_in_force=TimeInForce(time_in_force),
            estimated_price=estimated_price,
            commission=commission,
            vat=vat,
            estimated_withholding_tax=estimated_withholding_tax,
            fx_rate=fx_rate,
            fx_markup=fx_markup,
            total_estimated_cost=total_estimated_cost,
            expires_at=expires_at,
            disclosure_id=disclosure_id,
            disclosure_version=disclosure_version,
            is_suitable=is_suitable
        )

        # Persist exact preview snapshot BE-049
        self.order_repo.save_order_preview(preview_entity)
        return preview_entity

    async def execute_order(
        self,
        preview_token: str,
        accepted_disclosure_version: Optional[str],
        idempotency_key: str,
        is_advised: bool = False
    ) -> Dict[str, Any]:
        """BE-041 & BE-045 & BE-046 & BE-048: Validates, guards idempotency, and submits strictly without retry"""
        
        # 1. Idempotency Check BE-046
        existing_order = self.order_repo.get_order_by_idempotency_key(idempotency_key)
        if existing_order:
            # Safe replay: return the original order immediately
            return {
                "order_id": existing_order.order_id,
                "status": existing_order.status.value,
                "msg": "Order replayed successfully from idempotency record."
            }

        # 2. Retrieve preview snapshot
        preview = self.order_repo.get_order_preview(preview_token)
        if not preview:
            raise DomainException("Invalid or missing order preview token.")

        if preview.expires_at < datetime.utcnow():
            raise DomainException("Order preview has expired (2 min limit BE-040).")

        # 3. Purchasing power / stock availability check BE-041
        cash = self.portfolio_repo.get_cash_balances(preview.account_id)
        if preview.side == OrderSide.BUY:
            if cash["operable"] < preview.total_estimated_cost:
                raise InsufficientFundsException(
                    f"Insufficient purchasing power. Required: {preview.total_estimated_cost}, Available: {cash['operable']}"
                )
        else:
            # Sell: check held shares quantity
            positions = self.portfolio_repo.get_positions_by_account(preview.account_id)
            pos_match = next((p for p in positions if p.instrument_id == preview.instrument_id), None)
            if not pos_match or pos_match.quantity < preview.quantity:
                raise InsufficientFundsException(
                    f"Insufficient share balance to execute sell. Required: {preview.quantity}, Held: {pos_match.quantity if pos_match else 0}"
                )

        # 4. Suitability warnings verification BE-045
        if not preview.is_suitable:
            if not accepted_disclosure_version or accepted_disclosure_version != preview.disclosure_version:
                raise NonSuitableInstrumentException(
                    message="Suitability acknowledgment required to purchase this volatile asset.",
                    disclosure_id=preview.disclosure_id or "disc-suitability",
                    version=preview.disclosure_version or "v1"
                )

        # 5. Build order payload
        order_id = str(uuid.uuid4())
        order_payload = {
            "order_id": order_id,
            "account_id": preview.account_id,
            "instrument_id": preview.instrument_id,
            "side": preview.side.value,
            "quantity": float(preview.quantity),
            "order_type": preview.order_type.value,
            "limit_price": float(preview.limit_price) if preview.limit_price else None,
            "stop_price": float(preview.stop_price) if preview.stop_price else None,
            "time_in_force": preview.time_in_force.value,
            "is_advised": is_advised
        }

        # Save order as RECEIVED first
        order_domain = Order(
            order_id=order_id,
            account_id=preview.account_id,
            instrument_id=preview.instrument_id,
            side=preview.side,
            quantity=preview.quantity,
            order_type=preview.order_type,
            limit_price=preview.limit_price,
            stop_price=preview.stop_price,
            time_in_force=preview.time_in_force,
            is_advised=is_advised,
            status=OrderStatus.RECEIVED,
            idempotency_key=idempotency_key,
            created_at=datetime.utcnow()
        )
        self.order_repo.save_order(order_domain)

        # 6. Submit strictly to custodian without retry BE-048
        try:
            custodian_response = await self.custodian_service.submit_order_to_market(
                order_payload,
                idempotency_key
            )
            self.order_repo.update_order_status(order_id, OrderStatus.SENT_TO_CUSTODIAN.value)
            return {
                "order_id": order_id,
                "status": OrderStatus.SENT_TO_CUSTODIAN.value,
                "msg": "Order submitted to custodian."
            }
        except Exception as e:
            # Timeout or custodian connection error occurred. DO NOT RETRY AUTOMATICALLY.
            # Mark order as PENDING reconciliation
            self.order_repo.update_order_status(order_id, OrderStatus.RECEIVED.value)
            raise DomainException(
                f"Custodian submission connection failure: {str(e)}. "
                "Order remains in pending state. Do not retry manually until status resolves."
            )
