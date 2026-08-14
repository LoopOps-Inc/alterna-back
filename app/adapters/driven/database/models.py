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


class DBOnboardingProgress(Base):
    __tablename__ = "onboarding_progress"
    
    id = Column(String, primary_key=True)  # onboarding transaction ID / session uuid
    username = Column(String, nullable=False)
    email = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    current_step = Column(String, default="START", nullable=False)
    
    # Step 1: Verification
    phone_verified = Column(Boolean, default=False, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    
    # Step 2: Personal Data & OCR
    full_name = Column(String, nullable=True)
    curp = Column(String, nullable=True)
    rfc = Column(String, nullable=True)
    birth_date = Column(String, nullable=True)
    birth_place = Column(String, nullable=True)
    nationality = Column(String, nullable=True)
    occupation = Column(String, nullable=True)
    id_type = Column(String, nullable=True) # INE or PASSPORT
    id_number = Column(String, nullable=True)
    id_image_quality = Column(Numeric(5, 2), nullable=True)
    
    # Step 3: Biometrics
    biometric_consent_given = Column(Boolean, default=False, nullable=False)
    biometric_similarity_score = Column(Numeric(5, 2), nullable=True)
    biometric_liveness_score = Column(Numeric(5, 2), nullable=True)
    biometric_attempts = Column(Integer, default=0, nullable=False)
    
    # Step 4: Address
    address_street = Column(String, nullable=True)
    address_city = Column(String, nullable=True)
    address_state = Column(String, nullable=True)
    address_zip = Column(String, nullable=True)
    address_proof_document = Column(String, nullable=True)
    
    # Step 5: Financial
    funds_source = Column(String, nullable=True)
    declared_wealth = Column(Numeric(18, 2), nullable=True)
    investment_purpose = Column(String, nullable=True)
    
    # Step 6: PEP & Screening
    is_pep = Column(Boolean, default=False, nullable=False)
    pep_details = Column(Text, nullable=True)
    screening_passed = Column(Boolean, default=False, nullable=False)
    screening_result = Column(Text, nullable=True)
    screening_list_version = Column(String, default="2026.08.13-V1", nullable=True)
    
    # Step 7: Investor Profile
    risk_profile = Column(String, default="CONSERVATIVE", nullable=False)
    investor_profile_score = Column(Integer, default=0, nullable=False)
    
    # Step 8: Consents & FATCA
    fatca_residency_us = Column(Boolean, default=False, nullable=False)
    fatca_tin = Column(String, nullable=True)
    consents_accepted = Column(Boolean, default=False, nullable=False)
    
    # Step 9: Digital Signature
    signed_contract_hash = Column(String, nullable=True)
    signed_at = Column(DateTime, nullable=True)
    
    # Metadata
    status = Column(String, default="IN_PROGRESS", nullable=False) # IN_PROGRESS, ESCALATED, COMPLETED, BLOCKED
    risk_classification = Column(String, default="LOW", nullable=False) # LOW, MEDIUM, HIGH
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
