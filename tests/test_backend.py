import pytest
import uuid
import time
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.adapters.driven.database.models import Base, DBUser
from app.adapters.driven.database.repositories import (
    SQLAlchemyUserRepository,
    SQLAlchemyPortfolioRepository,
    SQLAlchemyOrderRepository,
    SQLAlchemyMoneyRepository,
    SQLAlchemyAMLRepository
)
from app.adapters.driven.cache.redis_service import RedisSessionCache
from app.adapters.driven.custodian.pershing_client import PershingCustodianClient
from app.adapters.driven.services.notification_service import OutOfBandNotificationService
from app.usecases.auth import AuthUseCase
from app.usecases.portfolio import PortfolioUseCase
from app.usecases.orders import OrderUseCase
from app.usecases.money import MoneyUseCase, validate_clabe_checksum
from app.domain.auth import User, DeviceFingerprint, TokenFamily
from app.domain.orders import OrderType, TimeInForce
from app.domain.exceptions import (
    ResourceNotFoundException,
    InvalidCredentialsException,
    SecurityRevocationException,
    PreventiveLockoutException,
    NonSuitableInstrumentException,
    ReconciliationMismatchException
)
from app.core.security import PasswordHasher

# --- TEST SETUP ---

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def user_repo(db_session):
    return SQLAlchemyUserRepository(db_session)

@pytest.fixture
def session_cache():
    return RedisSessionCache()

@pytest.fixture
def notifier():
    return OutOfBandNotificationService()

@pytest.fixture
def auth_usecase(user_repo, session_cache, notifier):
    return AuthUseCase(user_repo, session_cache, notifier)

# --- TESTS ---

def test_clabe_validation():
    # Valid CLABE (example)
    valid_clabe = "002115111111111113"  # Standard checksum valid CLABE
    assert validate_clabe_checksum(valid_clabe) is True
    
    # Invalid CLABE
    invalid_clabe = "002115111111111111"
    assert validate_clabe_checksum(invalid_clabe) is False


def test_password_hashing_and_decoy():
    raw_pwd = "MySecretPassword123!"
    hashed = PasswordHasher.hash_password(raw_pwd)
    
    assert PasswordHasher.verify_password(hashed, raw_pwd) is True
    assert PasswordHasher.verify_password(hashed, "wrong_password") is False
    
    # Verify decoy executes cleanly
    start = time.monotonic()
    PasswordHasher.execute_decoy_hash()
    end = time.monotonic()
    assert (end - start) < 0.5  # dummy hash execution is fast but present


@pytest.mark.asyncio
async def test_auth_and_token_rotation_abuse(auth_usecase, user_repo, session_cache):
    # Register sandbox user
    user_id = str(uuid.uuid4())
    domain_user = User(
        id=user_id,
        username="test_trader",
        email="trader@test.com",
        is_active=True,
        created_at=datetime.utcnow()
    )
    hashed_pwd = PasswordHasher.hash_password("SuperSecureAlternativePass123!")
    user_repo.save_user(domain_user, hashed_pwd)

    device = DeviceFingerprint(
        device_id="dev-uuid-111",
        os_name="iOS",
        os_version="17.2",
        ip_address="192.168.1.50",
        user_agent="Safari iOS Mobile",
        is_trusted=True
    )
    user_repo.save_device_fingerprint(user_id, device)

    # Success Login
    tokens = await auth_usecase.login_user("test_trader", "SuperSecureAlternativePass123!", device)
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    
    # Rotate token once (valid)
    first_rotation = await auth_usecase.rotate_tokens(tokens["refresh_token"])
    assert "access_token" in first_rotation
    
    # Rotate token second time using same old refresh token (Abuse detection!)
    with pytest.raises(SecurityRevocationException):
        await auth_usecase.rotate_tokens(tokens["refresh_token"])


@pytest.mark.asyncio
async def test_account_ownership_mitigation(db_session, user_repo):
    # Setup user
    user_id = str(uuid.uuid4())
    user = User(id=user_id, username="victim_user", email="vic@test.com", is_active=True, created_at=datetime.utcnow())
    user_repo.save_user(user, "password_hash")
    
    # Verify verify_account_access is false for non-access accounts
    assert user_repo.verify_account_access(user_id, "account-secret-999") is False


@pytest.mark.asyncio
async def test_order_suitability_eval(db_session, user_repo):
    order_repo = SQLAlchemyOrderRepository(db_session)
    portfolio_repo = SQLAlchemyPortfolioRepository(db_session)
    custodian = PershingCustodianClient()
    
    usecase = OrderUseCase(order_repo, portfolio_repo, custodian)
    
    # Generate order preview on volatile TSLA stock
    preview = await usecase.generate_order_preview(
        account_id="acc-12345",
        instrument_id="inst-tsla",
        ticker="TSLA",
        side="BUY",
        quantity=10,
        order_type="MARKET"
    )
    
    # Should flag suitability alert
    assert preview.is_suitable is False
    assert preview.disclosure_id == "disc-suitability-high-vol"
    assert preview.disclosure_version == "v2"


@pytest.mark.asyncio
async def test_daily_reconciliation_discrepancy(db_session):
    portfolio_repo = SQLAlchemyPortfolioRepository(db_session)
    custodian = PershingCustodianClient()
    
    usecase = PortfolioUseCase(portfolio_repo, custodian)
    
    # Intentionally do not populate local DB positions -> triggers mismatch exception BE-021
    with pytest.raises(ReconciliationMismatchException):
        await usecase.run_daily_reconciliation("acc-123")
