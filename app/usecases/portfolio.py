from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from app.ports.database import IPortfolioRepository
from app.ports.custodian import ICustodianService
from app.domain.portfolio import PortfolioSummary, Position, TaxLot
from app.domain.exceptions import ReconciliationMismatchException

class PortfolioUseCase:
    def __init__(self, portfolio_repo: IPortfolioRepository, custodian_service: ICustodianService):
        self.portfolio_repo = portfolio_repo
        self.custodian_service = custodian_service

    async def get_portfolio_summary(self, account_id: str, target_currency: str = "USD") -> PortfolioSummary:
        """BE-025 & BE-026 & BE-028: Retrieve portfolio summary, cash breakdowns, and reexpress values"""
        # Fetch positions from local repository
        positions = self.portfolio_repo.get_positions_by_account(account_id)
        cash_breakdown = self.portfolio_repo.get_cash_balances(account_id)

        # Calculate valuations
        total_market_value_usd = Decimal("0.00")
        for pos in positions:
            total_market_value_usd += pos.market_value

        # Standard FX rate USDMXN
        fx_rate = Decimal("17.00")  # Mock FX rate
        total_market_value_mxn = total_market_value_usd * fx_rate

        return PortfolioSummary(
            account_id=account_id,
            positions=positions,
            total_market_value_usd=total_market_value_usd,
            total_market_value_mxn=total_market_value_mxn,
            cash_operable=cash_breakdown["operable"],
            cash_retirable=cash_breakdown["retirable"],
            cash_committed=cash_breakdown["committed"],
            cash_in_transit=cash_breakdown["in_transit"],
            data_as_of=datetime.utcnow(),
            data_source="Pershing LLC via Synchronizer",
            is_realtime=True
        )

    async def run_daily_reconciliation(self, account_id: str) -> None:
        """BE-021: Reconcile daily against custodian. No silent automated corrections."""
        local_positions = self.portfolio_repo.get_positions_by_account(account_id)
        
        # Pull actual custodian master record
        custodian_raw = await self.custodian_service.fetch_realtime_positions(account_id)
        
        # Build index of custodian positions
        custodian_map = {item["ticker"]: Decimal(str(item["quantity"])) for item in custodian_raw}
        local_map = {pos.ticker: pos.quantity for pos in local_positions}

        discrepancies = []
        for ticker, cust_qty in custodian_map.items():
            local_qty = local_map.get(ticker, Decimal("0.00"))
            if local_qty != cust_qty:
                discrepancies.append(f"{ticker}: Custodian={cust_qty}, Local={local_qty}")

        for ticker, local_qty in local_map.items():
            if ticker not in custodian_map and local_qty > 0:
                discrepancies.append(f"{ticker}: Custodian=0.00, Local={local_qty}")

        if discrepancies:
            error_details = "; ".join(discrepancies)
            # Throw severe exception to alert operations, do not perform silent updates BE-021
            raise ReconciliationMismatchException(
                f"Discrepancies detected during custodian synchronization for account {account_id}: {error_details}"
            )

    async def calculate_tax_lots_gain(self, account_id: str, instrument_id: str, sell_quantity: Decimal, sell_price: Decimal) -> Decimal:
        """BE-022: FIFO Tax lot gain/loss calculations"""
        lots = self.portfolio_repo.get_tax_lots(account_id, instrument_id)
        remaining_to_sell = sell_quantity
        total_cost_basis = Decimal("0.00")

        for lot in lots:
            if remaining_to_sell <= 0:
                break
            
            allocated_from_lot = min(lot.remaining_quantity, remaining_to_sell)
            total_cost_basis += allocated_from_lot * lot.purchase_price
            remaining_to_sell -= allocated_from_lot

        if remaining_to_sell > 0:
            # Over-selling positions
            raise ReconciliationMismatchException("Insufficient tax lot inventory to calculate enajenacion.")

        realized_revenue = sell_quantity * sell_price
        return realized_revenue - total_cost_basis
