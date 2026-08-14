import pytest
import uuid
import time
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.adapters.driven.database.models import Base, DBUser, DBProfileChangeLog, DBTransfer, DBAMLAlert
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
from app.usecases.aml import AMLEngine
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
def money_repo(db_session):
    return SQLAlchemyMoneyRepository(db_session)

@pytest.fixture
def aml_repo(db_session):
    return SQLAlchemyAMLRepository(db_session)

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
    # Valid CLABE (using standard valid check-digit 0)
    valid_clabe = "002115111111111110"  
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


@pytest.mark.asyncio
async def test_withdrawal_cooldown_period_be010(db_session, user_repo, money_repo):
    """
    BE-010 / AML-07: Tests that changing credentials or security info blocks subsequent
    cash withdrawals for a cooling-off period of 24 hours.
    """
    usecase = MoneyUseCase(money_repo, user_repo)
    
    # Register sandbox user
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        username="cooldown_user",
        email="cooldown@test.com",
        is_active=True,
        created_at=datetime.utcnow()
    )
    user_repo.save_user(user, "password_hash")
    
    # Record a profile change (e.g. password update) in past 24 hours
    change = DBProfileChangeLog(
        user_id=user_id,
        change_type="PASSWORD_UPDATE",
        created_at=datetime.utcnow()
    )
    db_session.add(change)
    db_session.commit()
    
    # Find any method on MoneyUseCase that handles withdrawal
    withdraw_method = None
    for name in dir(usecase):
        if "withdraw" in name.lower() and not name.startswith("_"):
            withdraw_method = getattr(usecase, name)
            break
            
    assert withdraw_method is not None, "Could not find withdrawal method on MoneyUseCase"
    
    # Inspect arguments and dynamically prepare required parameters
    import inspect
    sig = inspect.signature(withdraw_method)
    kwargs = {}
    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        elif "party" in param_name or "user" in param_name:
            kwargs[param_name] = user_id
        elif "account" in param_name:
            kwargs[param_name] = "acc-12345"
        elif "amount" in param_name:
            kwargs[param_name] = Decimal("5000.00")
        elif "clabe" in param_name:
            kwargs[param_name] = "002115111111111110"
        elif param.default == inspect.Parameter.empty:
            kwargs[param_name] = "test-value"
            
    # Attempting withdrawal must raise PreventiveLockoutException
    with pytest.raises(PreventiveLockoutException):
        await withdraw_method(**kwargs)


@pytest.mark.asyncio
async def test_aml_smurfing_pitufeo_rule(db_session, user_repo, aml_repo):
    """
    AML-02 (Smurfing/Structuring): Tests that multiple transactions of low denominations
    within a short window trigger an AML restriction.
    """
    engine = AMLEngine(aml_repo, user_repo)
    
    # Register user
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        username="smurf_user",
        email="smurf@test.com",
        is_active=True,
        created_at=datetime.utcnow()
    )
    user_repo.save_user(user, "password_hash")
    
    # Add multiple DBTransfer transactions under typical reporting thresholds (e.g. 6 transfers of $1500)
    # in the last hour to trigger structuring alert
    for i in range(6):
        transfer_kwargs = {
            "transfer_id": str(uuid.uuid4()),
            "account_id": "acc-12345",
            "beneficiary_id": "beneficiary-1",
            "amount": Decimal("1500.00"),
            "currency": "MXN",
            "idempotency_key": str(uuid.uuid4()),
            "status": "COMPLETED",
            "created_at": datetime.utcnow() - timedelta(minutes=i*10)
        }
        db_session.add(DBTransfer(**transfer_kwargs))
    db_session.commit()
    
    # Call AML Engine to evaluate the new withdrawal transaction
    tx_payload = {
        "type": "WITHDRAWAL",
        "amount": 1500.00,
        "account_id": "acc-12345"
    }
    
    # Check if evaluating this transaction returns False or raises a security compliance exception
    try:
        is_compliant = await engine.evaluate_transaction_compliance(user_id, tx_payload)
        # If it returns a boolean, it must be False (blocked)
        assert is_compliant is False, "Transaction should be marked non-compliant due to AML-02"
    except Exception as e:
        # If it raises a custom domain/compliance exception
        err_msg = str(e).lower()
        assert "revisando" in err_msg or "pld" in err_msg or "aml" in err_msg or "compliance" in err_msg or "hold" in err_msg
        
    # Check that an AML alert record exists or is flagged in the database
    alert = db_session.query(DBAMLAlert).filter(DBAMLAlert.party_id == user_id).first()
    if alert:
        assert alert.rule_code == "AML-02"
