from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Column, String, Boolean, DateTime, Numeric, ForeignKey, Index, Text, Integer
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class DBUser(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    fingerprints = relationship("DBDeviceFingerprint", back_populates="user")
    accesses = relationship("DBAccountAccess", back_populates="user")


class DBDeviceFingerprint(Base):
    __tablename__ = "device_fingerprints"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    device_id = Column(String, nullable=False)
    os_name = Column(String, nullable=False)
    os_version = Column(String, nullable=False)
    ip_address = Column(String, nullable=False)
    user_agent = Column(String, nullable=False)
    is_trusted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("DBUser", back_populates="fingerprints")


class DBAccountAccess(Base):
    __tablename__ = "account_access"
    
    id = Column(String, primary_key=True)
    party_id = Column(String, ForeignKey("users.id"), nullable=False)
    account_id = Column(String, index=True, nullable=False)
    role = Column(String, nullable=False)  # OWNER, CO_OWNER, etc.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    user = relationship("DBUser", back_populates="accesses")

    __table_args__ = (
        Index("idx_account_party_active", "account_id", "party_id", "revoked_at"),
    )


class DBPosition(Base):
    __tablename__ = "positions"
    
    id = Column(String, primary_key=True)
    account_id = Column(String, index=True, nullable=False)
    instrument_id = Column(String, nullable=False)
    ticker = Column(String, nullable=False)
    name = Column(String, nullable=False)
    quantity = Column(Numeric(18, 6), nullable=False)
    market_price = Column(Numeric(18, 6), nullable=False)
    average_cost = Column(Numeric(18, 6), nullable=False)
    currency = Column(String, default="USD", nullable=False)
    asset_class = Column(String, nullable=False)
    sector = Column(String, nullable=False)
    geography = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class DBCashBalance(Base):
    __tablename__ = "cash_balances"
    
    account_id = Column(String, primary_key=True)
    operable = Column(Numeric(18, 4), default=0.0, nullable=False)
    retirable = Column(Numeric(18, 4), default=0.0, nullable=False)
    committed = Column(Numeric(18, 4), default=0.0, nullable=False)
    in_transit = Column(Numeric(18, 4), default=0.0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class DBOrderPreview(Base):
    __tablename__ = "order_previews"
    
    preview_token = Column(String, primary_key=True)
    account_id = Column(String, nullable=False)
    instrument_id = Column(String, nullable=False)
    side = Column(String, nullable=False)
    quantity = Column(Numeric(18, 6), nullable=False)
    order_type = Column(String, nullable=False)
    limit_price = Column(Numeric(18, 6), nullable=True)
    stop_price = Column(Numeric(18, 6), nullable=True)
    time_in_force = Column(String, nullable=False)
    estimated_price = Column(Numeric(18, 6), nullable=False)
    commission = Column(Numeric(18, 4), nullable=False)
    vat = Column(Numeric(18, 4), nullable=False)
    estimated_withholding_tax = Column(Numeric(18, 4), nullable=False)
    fx_rate = Column(Numeric(18, 6), nullable=False)
    fx_markup = Column(Numeric(18, 6), nullable=False)
    total_estimated_cost = Column(Numeric(18, 4), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    disclosure_id = Column(String, nullable=True)
    disclosure_version = Column(String, nullable=True)
    is_suitable = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class DBOrder(Base):
    __tablename__ = "orders"
    
    order_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False)
    instrument_id = Column(String, nullable=False)
    side = Column(String, nullable=False)
    quantity = Column(Numeric(18, 6), nullable=False)
    order_type = Column(String, nullable=False)
    limit_price = Column(Numeric(18, 6), nullable=True)
    stop_price = Column(Numeric(18, 6), nullable=True)
    time_in_force = Column(String, nullable=False)
    is_advised = Column(Boolean, default=False, nullable=False)
    status = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    filled_at = Column(DateTime, nullable=True)
    average_filled_price = Column(Numeric(18, 6), nullable=True)

    __table_args__ = (
        # BE-046: Physical database unique constraint to guarantee idempotency
        Index("idx_order_idempotency", "idempotency_key", unique=True),
    )


class DBBeneficiary(Base):
    __tablename__ = "beneficiaries"
    
    id = Column(String, primary_key=True)
    account_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    clabe = Column(String(18), nullable=False)
    bank_name = Column(String, nullable=False)
    is_third_party = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    cooldown_until = Column(DateTime, nullable=False)


class DBTransfer(Base):
    __tablename__ = "transfers"
    
    transfer_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False)
    beneficiary_id = Column(String, nullable=False)
    amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String, default="MXN", nullable=False)
    idempotency_key = Column(String, nullable=False)
    status = Column(String, default="PENDING", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        # BE-046: Physical database unique constraint to guarantee transfer idempotency
        Index("idx_transfer_idempotency", "idempotency_key", unique=True),
    )


class DBAMLAlert(Base):
    __tablename__ = "aml_alerts"
    
    id = Column(String, primary_key=True)
    party_id = Column(String, nullable=False, index=True)
    rule_code = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    payload_snapshot = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_resolved = Column(Boolean, default=False, nullable=False)


class DBProfileChangeLog(Base):
    __tablename__ = "profile_change_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False)
    change_type = Column(String, nullable=False)  # PASSWORD, PHONE, EMAIL
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class DBTaxLot(Base):
    __tablename__ = "tax_lots"
    
    id = Column(String, primary_key=True)
    account_id = Column(String, index=True, nullable=False)
    instrument_id = Column(String, index=True, nullable=False)
    purchase_date = Column(DateTime, nullable=False)
    quantity = Column(Numeric(18, 6), nullable=False)
    purchase_price = Column(Numeric(18, 6), nullable=False)
    remaining_quantity = Column(Numeric(18, 6), nullable=False)
