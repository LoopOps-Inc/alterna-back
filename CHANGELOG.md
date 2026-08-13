# Changelog

## [0.1.0] - 2023-10-27

### Added
- **Initial Backend Implementation for Alterna Mobile (ALTM)**
  - Implemented a secure, auditable, and scalable backend based on a Hexagonal Architecture using Python 3.11/3.12 and FastAPI.
  - Set up core application configuration, security primitives with Argon2id, and exception handlers.
  - Defined domain models for authentication, portfolio, orders, and money transfers.
  - Established ports (interfaces) for database, cache, custodian, and notification services.
  - Implemented driven adapters for PostgreSQL (via SQLAlchemy), Redis, and mock service clients.
  - Created core business logic in use cases for authentication, including secure login, refresh token rotation (RTR), and step-up authentication.

### Files Created
- `app/core/config.py`: Centralized application settings.
- `app/core/security.py`: Advanced cryptographic functions.
- `app/core/exception_handlers.py`: Global exception handling.
- `app/domain/auth.py`, `app/domain/portfolio.py`, `app/domain/orders.py`, `app/domain/money.py`: Domain entity models.
- `app/ports/database.py`, `app/ports/cache.py`, `app/ports/custodian.py`, `app/ports/services.py`: Abstract service contracts (Protocols).
- `app/adapters/driven/database/models.py`: SQLAlchemy ORM models.
- `app/adapters/driven/database/repositories.py`: SQLAlchemy repository implementations.
- `app/adapters/driven/cache/redis_service.py`: Redis cache implementation.
- `app/adapters/driving/routers/auth.py`: Authentication API endpoints.
- `app/usecases/auth.py`: Authentication business logic.
- `tests/test_backend.py`: Initial test suite for the backend implementation.
