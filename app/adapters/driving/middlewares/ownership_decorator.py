import logging
import json
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.container import get_db
from app.adapters.driven.database.repositories import SQLAlchemyUserRepository
from app.domain.exceptions import ResourceNotFoundException

logger = logging.getLogger("altm_ownership_decorator")

def verify_account_ownership(
    account_id: str,
    request: Request,
    db: Session = Depends(get_db)
) -> str:
    """Enforces BE-009: Resource ownership validation. Returns 404 instead of 403 to obscure resource existence."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        logger.error("verify_account_ownership called without authenticated user_id in request state.")
        raise ResourceNotFoundException("Account resource not found")

    user_repo = SQLAlchemyUserRepository(db)
    has_access = user_repo.verify_account_access(user_id, account_id)
    if not has_access:
        logger.warning(
            f"ACCESS DENIED: User {user_id} attempted unauthorized access to account {account_id}. "
            f"Responding with 404 Not Found (BE-009)."
        )
        raise ResourceNotFoundException("Account resource not found")

    return account_id


async def verify_account_body_ownership(
    request: Request,
    db: Session = Depends(get_db)
) -> str:
    """Helper to extract and verify account_id from JSON request body. Enforces BE-009."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise ResourceNotFoundException("Account resource not found")

    # Read body
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body format")

    account_id = body.get("account_id")
    if not account_id:
        raise HTTPException(status_code=422, detail="Missing account_id in request body")

    user_repo = SQLAlchemyUserRepository(db)
    has_access = user_repo.verify_account_access(user_id, account_id)
    if not has_access:
        logger.warning(
            f"ACCESS DENIED: User {user_id} attempted unauthorized access to body account {account_id}. "
            f"Responding with 404 Not Found (BE-009)."
        )
        raise ResourceNotFoundException("Account resource not found")

    return account_id
