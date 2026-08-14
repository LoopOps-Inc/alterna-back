from typing import Generator
import logging
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError
from app.core.config import settings
from app.adapters.driven.database.models import Base
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

logger = logging.getLogger("altm_backend")

# Database engine initialization. 
# For lightweight testing, if sqlite is configured or database is empty, fall back to sqlite in-memory
if "sqlite" in settings.DATABASE_URL or "postgresql" not in settings.DATABASE_URL:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
else:
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Initializes the database and creates tables with a retry policy for connection/DNS lag."""
    # SQLite has no connection delay
    if "sqlite" in settings.DATABASE_URL or "postgresql" not in settings.DATABASE_URL:
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("SQLite database tables created successfully.")
        except Exception as e:
            logger.error(f"Error creating SQLite tables: {e}")
            raise e
        return

    # PostgreSQL retry mechanism
    max_retries = 5
    retry_delay = 3
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Connecting to database and creating tables (attempt {attempt}/{max_retries})...")
            Base.metadata.create_all(bind=engine)
            logger.info("PostgreSQL database tables created successfully.")
            return
        except OperationalError as e:
            if attempt == max_retries:
                logger.error("Failed to connect to database after maximum retries.")
                raise e
            logger.warning(
                f"Database connection attempt {attempt} failed: {e}. "
                f"Retrying in {retry_delay}s..."
            )
            time.sleep(retry_delay)


def get_db() -> Generator[Session, None, None]:
    """Provides a transactional database session context generator"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_user_repository(db: Session) -> SQLAlchemyUserRepository:
    return SQLAlchemyUserRepository(db)


def get_portfolio_repository(db: Session) -> SQLAlchemyPortfolioRepository:
    return SQLAlchemyPortfolioRepository(db)


def get_order_repository(db: Session) -> SQLAlchemyOrderRepository:
    return SQLAlchemyOrderRepository(db)


def get_money_repository(db: Session) -> SQLAlchemyMoneyRepository:
    return SQLAlchemyMoneyRepository(db)


def get_aml_repository(db: Session) -> SQLAlchemyAMLRepository:
    return SQLAlchemyAMLRepository(db)


def get_session_cache() -> RedisSessionCache:
    return RedisSessionCache()


def get_custodian_service() -> PershingCustodianClient:
    return PershingCustodianClient()


def get_notification_service() -> OutOfBandNotificationService:
    return OutOfBandNotificationService()
