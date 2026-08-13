from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.ports.database import (
    IUserRepository, IPortfolioRepository, IOrderRepository, IMoneyRepository, IAMLRepository
)
from app.domain.auth import User, DeviceFingerprint
from app.domain.portfolio import Position, TaxLot, PerformanceSnapshot
from app.domain.orders import Order, OrderPreview, OrderStatus, OrderSide, OrderType
from app.domain.money import Beneficiary, Transfer
from app.domain.aml import AMLAlert
from app.domain.exceptions import DomainException
from app.adapters.driven.database.models import (
    DBUser, DBDeviceFingerprint, DBAccountAccess, DBPosition, DBCashBalance,
    DBOrderPreview, DBOrder, DBBeneficiary, DBTransfer, DBAMLAlert, DBProfileChangeLog, DBTaxLot
)

class SQLAlchemyUserRepository(IUserRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: str) -> Optional[User]:
        db_user = self.db.query(DBUser).filter(DBUser.id == user_id).first()
        if not db_user:
            return None
        return User(id=db_user.id, username=db_user.username, email=db_user.email, is_active=db_user.is_active, created_at=db_user.created_at)

    def get_by_username(self, username: str) -> Optional[User]:
        db_user = self.db.query(DBUser).filter(DBUser.username == username).first()
        if not db_user:
            return None
        return User(id=db_user.id, username=db_user.username, email=db_user.email, is_active=db_user.is_active, created_at=db_user.created_at)

    def get_password_hash(self, username: str) -> Optional[str]:
        db_user = self.db.query(DBUser).filter(DBUser.username == username).first()
        if not db_user:
            return None
        return db_user.password_hash

    def save_user(self, user: User, password_hash: str) -> None:
        db_user = DBUser(
            id=user.id,
            username=user.username,
            email=user.email,
            password_hash=password_hash,
            is_active=user.is_active,
            created_at=user.created_at
        )
        self.db.add(db_user)
        self.db.commit()

    def get_device_fingerprint(self, user_id: str, device_id: str) -> Optional[DeviceFingerprint]:
        db_df = self.db.query(DBDeviceFingerprint).filter(
            DBDeviceFingerprint.user_id == user_id,
            DBDeviceFingerprint.device_id == device_id
        ).first()
        if not db_df:
            return None
        return DeviceFingerprint(
            device_id=db_df.device_id,
            os_name=db_df.os_name,
            os_version=db_df.os_version,
            ip_address=db_df.ip_address,
            user_agent=db_df.user_agent,
            is_trusted=db_df.is_trusted
        )

    def save_device_fingerprint(self, user_id: str, fingerprint: DeviceFingerprint) -> None:
        db_df = DBDeviceFingerprint(
            id=f"{user_id}_{fingerprint.device_id}",
            user_id=user_id,
            device_id=fingerprint.device_id,
            os_name=fingerprint.os_name,
            os_version=fingerprint.os_version,
            ip_address=fingerprint.ip_address,
            user_agent=fingerprint.user_agent,
            is_trusted=fingerprint.is_trusted,
            created_at=datetime.utcnow()
        )
        self.db.merge(db_df)
        self.db.commit()

    def get_recent_profile_changes_count(self, user_id: str, window_hours: int) -> int:
        cutoff = datetime.utcnow() - timedelta(hours=window_hours)
        return self.db.query(DBProfileChangeLog).filter(
            DBProfileChangeLog.user_id == user_id,
            DBProfileChangeLog.created_at >= cutoff
        ).count()

    def log_profile_change(self, user_id: str, change_type: str) -> None:
        log_entry = DBProfileChangeLog(
            user_id=user_id,
            change_type=change_type,
            created_at=datetime.utcnow()
        )
        self.db.add(log_entry)
        self.db.commit()

    def verify_account_access(self, party_id: str, account_id: str) -> bool:
        db_access = self.db.query(DBAccountAccess).filter(
            DBAccountAccess.party_id == party_id,
            DBAccountAccess.account_id == account_id,
            DBAccountAccess.revoked_at.is_(None)
        ).first()
        return db_access is not None

    def create_account_access(self, party_id: str, account_id: str, role: str) -> None:
        db_access = DBAccountAccess(
            id=f"{party_id}_{account_id}",
            party_id=party_id,
            account_id=account_id,
            role=role,
            created_at=datetime.utcnow()
        )
        self.db.merge(db_access)
        self.db.commit()


class SQLAlchemyPortfolioRepository(IPortfolioRepository):
    def __init__(self, db: Session):
        self.db = db

    def save_positions(self, account_id: str, positions: List[Position]) -> None:
        self.db.query(DBPosition).filter(DBPosition.account_id == account_id).delete()
        for pos in positions:
            db_pos = DBPosition(
                id=f"{account_id}_{pos.instrument_id}",
                account_id=account_id,
                instrument_id=pos.instrument_id,
                ticker=pos.ticker,
                name=pos.name,
                quantity=pos.quantity,
                market_price=pos.market_price,
                average_cost=pos.average_cost,
                currency=pos.currency,
                asset_class=pos.asset_class,
                sector=pos.sector,
                geography=pos.geography,
                updated_at=datetime.utcnow()
            )
            self.db.add(db_pos)
        self.db.commit()

    def get_positions_by_account(self, account_id: str) -> List[Position]:
        db_positions = self.db.query(DBPosition).filter(DBPosition.account_id == account_id).all()
        return [
            Position(
                instrument_id=p.instrument_id,
                ticker=p.ticker,
                name=p.name,
                quantity=Decimal(str(p.quantity)),
                market_price=Decimal(str(p.market_price)),
                average_cost=Decimal(str(p.average_cost)),
                market_value=Decimal(str(p.quantity * p.market_price)),
                unrealized_gain_loss=Decimal(str((p.market_price - p.average_cost) * p.quantity)),
                currency=p.currency,
                asset_class=p.asset_class,
                sector=p.sector,
                geography=p.geography
            )
            for p in db_positions
        ]

    def save_performance_snapshot(self, snapshot: PerformanceSnapshot) -> None:
        pass

    def get_tax_lots(self, account_id: str, instrument_id: str) -> List[TaxLot]:
        db_lots = self.db.query(DBTaxLot).filter(
            DBTaxLot.account_id == account_id,
            DBTaxLot.instrument_id == instrument_id,
            DBTaxLot.remaining_quantity > 0
        ).order_by(DBTaxLot.purchase_date.asc()).all()
        return [
            TaxLot(
                id=lot.id,
                instrument_id=lot.instrument_id,
                purchase_date=lot.purchase_date,
                quantity=Decimal(str(lot.quantity)),
                purchase_price=Decimal(str(lot.purchase_price)),
                remaining_quantity=Decimal(str(lot.remaining_quantity))
            )
            for lot in db_lots
        ]

    def get_cash_balances(self, account_id: str) -> Dict[str, Any]:
        bal = self.db.query(DBCashBalance).filter(DBCashBalance.account_id == account_id).first()
        if not bal:
            bal = DBCashBalance(
                account_id=account_id,
                operable=Decimal("100000.00"),
                retirable=Decimal("100000.00"),
                committed=Decimal("0.00"),
                in_transit=Decimal("0.00"),
                updated_at=datetime.utcnow()
            )
            self.db.add(bal)
            self.db.commit()
        return {
            "operable": Decimal(str(bal.operable)),
            "retirable": Decimal(str(bal.retirable)),
            "committed": Decimal(str(bal.committed)),
            "in_transit": Decimal(str(bal.in_transit))
        }


class SQLAlchemyOrderRepository(IOrderRepository):
    def __init__(self, db: Session):
        self.db = db

    def save_order_preview(self, preview: OrderPreview) -> None:
        db_preview = DBOrderPreview(
            preview_token=preview.preview_token,
            account_id=preview.account_id,
            instrument_id=preview.instrument_id,
            side=preview.side.value,
            quantity=preview.quantity,
            order_type=preview.order_type.value,
            limit_price=preview.limit_price,
            stop_price=preview.stop_price,
            time_in_force=preview.time_in_force.value,
            estimated_price=preview.estimated_price,
            commission=preview.commission,
            vat=preview.vat,
            estimated_withholding_tax=preview.estimated_withholding_tax,
            fx_rate=preview.fx_rate,
            fx_markup=preview.fx_markup,
            total_estimated_cost=preview.total_estimated_cost,
            expires_at=preview.expires_at,
            disclosure_id=preview.disclosure_id,
            disclosure_version=preview.disclosure_version,
            is_suitable=preview.is_suitable,
            created_at=datetime.utcnow()
        )
        self.db.add(db_preview)
        self.db.commit()

    def get_order_preview(self, preview_token: str) -> Optional[OrderPreview]:
        db_p = self.db.query(DBOrderPreview).filter(DBOrderPreview.preview_token == preview_token).first()
        if not db_p:
            return None
        return OrderPreview(
            preview_token=db_p.preview_token,
            account_id=db_p.account_id,
            instrument_id=db_p.instrument_id,
            side=OrderSide(db_p.side),
            quantity=Decimal(str(db_p.quantity)),
            order_type=OrderType(db_p.order_type),
            limit_price=Decimal(str(db_p.limit_price)) if db_p.limit_price is not None else None,
            stop_price=Decimal(str(db_p.stop_price)) if db_p.stop_price is not None else None,
            time_in_force=db_p.time_in_force,
            estimated_price=Decimal(str(db_p.estimated_price)),
            commission=Decimal(str(db_p.commission)),
            vat=Decimal(str(db_p.vat)),
            estimated_withholding_tax=Decimal(str(db_p.estimated_withholding_tax)),
            fx_rate=Decimal(str(db_p.fx_rate)),
            fx_markup=Decimal(str(db_p.fx_markup)),
            total_estimated_cost=Decimal(str(db_p.total_estimated_cost)),
            expires_at=db_p.expires_at,
            disclosure_id=db_p.disclosure_id,
            disclosure_version=db_p.disclosure_version,
            is_suitable=db_p.is_suitable
        )

    def save_order(self, order: Order) -> None:
        db_order = DBOrder(
            order_id=order.order_id,
            account_id=order.account_id,
            instrument_id=order.instrument_id,
            side=order.side.value,
            quantity=order.quantity,
            order_type=order.order_type.value,
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            time_in_force=order.time_in_force.value,
            is_advised=order.is_advised,
            status=order.status.value,
            idempotency_key=order.idempotency_key,
            created_at=order.created_at,
            filled_at=order.filled_at,
            average_filled_price=order.average_filled_price
        )
        try:
            self.db.add(db_order)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise DomainException("Order with this idempotency key already exists.")

    def get_order_by_id(self, order_id: str) -> Optional[Order]:
        o = self.db.query(DBOrder).filter(DBOrder.order_id == order_id).first()
        if not o:
            return None
        return Order(
            order_id=o.order_id,
            account_id=o.account_id,
            instrument_id=o.instrument_id,
            side=OrderSide(o.side),
            quantity=Decimal(str(o.quantity)),
            order_type=OrderType(o.order_type),
            limit_price=Decimal(str(o.limit_price)) if o.limit_price is not None else None,
            stop_price=Decimal(str(o.stop_price)) if o.stop_price is not None else None,
            time_in_force=o.time_in_force,
            is_advised=o.is_advised,
            status=OrderStatus(o.status),
            idempotency_key=o.idempotency_key,
            created_at=o.created_at,
            filled_at=o.filled_at,
            average_filled_price=Decimal(str(o.average_filled_price)) if o.average_filled_price is not None else None
        )

    def get_order_by_idempotency_key(self, idempotency_key: str) -> Optional[Order]:
        o = self.db.query(DBOrder).filter(DBOrder.idempotency_key == idempotency_key).first()
        if not o:
            return None
        return Order(
            order_id=o.order_id,
            account_id=o.account_id,
            instrument_id=o.instrument_id,
            side=OrderSide(o.side),
            quantity=Decimal(str(o.quantity)),
            order_type=OrderType(o.order_type),
            limit_price=Decimal(str(o.limit_price)) if o.limit_price is not None else None,
            stop_price=Decimal(str(o.stop_price)) if o.stop_price is not None else None,
            time_in_force=o.time_in_force,
            is_advised=o.is_advised,
            status=OrderStatus(o.status),
            idempotency_key=o.idempotency_key,
            created_at=o.created_at,
            filled_at=o.filled_at,
            average_filled_price=Decimal(str(o.average_filled_price)) if o.average_filled_price is not None else None
        )

    def update_order_status(self, order_id: str, status: str, filled_at: Optional[datetime] = None, average_filled_price: Optional[float] = None) -> None:
        db_o = self.db.query(DBOrder).filter(DBOrder.order_id == order_id).first()
        if db_o:
            db_o.status = status
            if filled_at:
                db_o.filled_at = filled_at
            if average_filled_price is not None:
                db_o.average_filled_price = average_filled_price
            self.db.commit()


class SQLAlchemyMoneyRepository(IMoneyRepository):
    def __init__(self, db: Session):
        self.db = db

    def save_beneficiary(self, beneficiary: Beneficiary) -> None:
        db_b = DBBeneficiary(
            id=beneficiary.id,
            account_id=beneficiary.account_id,
            name=beneficiary.name,
            clabe=beneficiary.clabe,
            bank_name=beneficiary.bank_name,
            is_third_party=beneficiary.is_third_party,
            created_at=beneficiary.created_at,
            cooldown_until=beneficiary.cooldown_until
        )
        self.db.merge(db_b)
        self.db.commit()

    def get_beneficiary_by_account_and_clabe(self, account_id: str, clabe: str) -> Optional[Beneficiary]:
        db_b = self.db.query(DBBeneficiary).filter(
            DBBeneficiary.account_id == account_id,
            DBBeneficiary.clabe == clabe
        ).first()
        if not db_b:
            return None
        return Beneficiary(
            id=db_b.id,
            account_id=db_b.account_id,
            name=db_b.name,
            clabe=db_b.clabe,
            bank_name=db_b.bank_name,
            is_third_party=db_b.is_third_party,
            created_at=db_b.created_at,
            cooldown_until=db_b.cooldown_until
        )

    def get_beneficiary_by_id(self, beneficiary_id: str) -> Optional[Beneficiary]:
        db_b = self.db.query(DBBeneficiary).filter(DBBeneficiary.id == beneficiary_id).first()
        if not db_b:
            return None
        return Beneficiary(
            id=db_b.id,
            account_id=db_b.account_id,
            name=db_b.name,
            clabe=db_b.clabe,
            bank_name=db_b.bank_name,
            is_third_party=db_b.is_third_party,
            created_at=db_b.created_at,
            cooldown_until=db_b.cooldown_until
        )

    def get_beneficiaries(self, account_id: str) -> List[Beneficiary]:
        db_bens = self.db.query(DBBeneficiary).filter(DBBeneficiary.account_id == account_id).all()
        return [
            Beneficiary(
                id=b.id,
                account_id=b.account_id,
                name=b.name,
                clabe=b.clabe,
                bank_name=b.bank_name,
                is_third_party=b.is_third_party,
                created_at=b.created_at,
                cooldown_until=b.cooldown_until
            )
            for b in db_bens
        ]

    def create_transfer(self, transfer: Transfer) -> None:
        db_t = DBTransfer(
            transfer_id=transfer.transfer_id,
            account_id=transfer.account_id,
            beneficiary_id=transfer.beneficiary_id,
            amount=transfer.amount,
            currency=transfer.currency,
            idempotency_key=transfer.idempotency_key,
            status=transfer.status,
            created_at=transfer.created_at
        )
        try:
            self.db.add(db_t)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise DomainException("Transfer with this idempotency key already exists.")

    def get_transfer_by_idempotency_key(self, idempotency_key: str) -> Optional[Transfer]:
        t = self.db.query(DBTransfer).filter(DBTransfer.idempotency_key == idempotency_key).first()
        if not t:
            return None
        return Transfer(
            transfer_id=t.transfer_id,
            account_id=t.account_id,
            beneficiary_id=t.beneficiary_id,
            amount=Decimal(str(t.amount)),
            currency=t.currency,
            idempotency_key=t.idempotency_key,
            created_at=t.created_at,
            status=t.status
        )


class SQLAlchemyAMLRepository(IAMLRepository):
    def __init__(self, db: Session):
        self.db = db

    def log_aml_alert(self, alert: AMLAlert) -> None:
        db_a = DBAMLAlert(
            id=alert.id,
            party_id=alert.party_id,
            rule_code=alert.rule_code,
            severity=alert.severity,
            description=alert.description,
            payload_snapshot=alert.payload_snapshot,
            created_at=alert.created_at,
            is_resolved=alert.is_resolved
        )
        self.db.add(db_a)
        self.db.commit()

    def get_transaction_volume_window(self, account_id: str, window_hours: int) -> float:
        cutoff = datetime.utcnow() - timedelta(hours=window_hours)
        transfers_total = self.db.query(DBTransfer).filter(
            DBTransfer.account_id == account_id,
            DBTransfer.created_at >= cutoff
        ).all()
        return sum(float(t.amount) for t in transfers_total)

    def get_last_funding_time(self, account_id: str) -> Optional[datetime]:
        last_t = self.db.query(DBTransfer).filter(
            DBTransfer.account_id == account_id,
            DBTransfer.status == "COMPLETED"
        ).order_by(DBTransfer.created_at.desc()).first()
        return last_t.created_at if last_t else None
