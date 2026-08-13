from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from app.core.container import get_db, get_custodian_service, get_session_cache, get_notification_service
from app.adapters.driving.middlewares.ownership_decorator import verify_account_body_ownership
from app.adapters.driven.database.repositories import SQLAlchemyOrderRepository, SQLAlchemyPortfolioRepository, SQLAlchemyUserRepository
from app.usecases.orders import OrderUseCase
from app.usecases.auth import AuthUseCase

router = APIRouter(prefix="/orders", tags=["Orders"])

class PreviewRequest(BaseModel):
    account_id: str
    instrument_id: str
    ticker: str
    side: str = Field(..., description="BUY or SELL")
    quantity: float
    order_type: str = Field("MARKET", description="MARKET, LIMIT, STOP, STOP_LIMIT")
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = Field("DAY", description="DAY, GTC, FOK")

class ExecutionRequest(BaseModel):
    account_id: str
    preview_token: str
    step_up_token: str
    idempotency_key: str
    accepted_disclosure_version: Optional[str] = None
    is_advised: bool = False


@router.post("/preview")
async def create_preview(
    req: PreviewRequest,
    db: Session = Depends(get_db),
    # Enforce BE-009 check: validates access to req.account_id from body
    validated_account_id: str = Depends(verify_account_body_ownership)
):
    """BE-040 & BE-042: Generates financial quote preview, evaluates suitability and signs the preview token"""
    order_repo = SQLAlchemyOrderRepository(db)
    portfolio_repo = SQLAlchemyPortfolioRepository(db)
    custodian = get_custodian_service()
    
    usecase = OrderUseCase(order_repo, portfolio_repo, custodian)
    return await usecase.generate_order_preview(
        account_id=validated_account_id,
        instrument_id=req.instrument_id,
        ticker=req.ticker,
        side=req.side,
        quantity=req.quantity,
        order_type=req.order_type,
        limit_price=req.limit_price,
        stop_price=req.stop_price,
        time_in_force=req.time_in_force
    )


@router.post("/execute")
async def execute_order(
    req: ExecutionRequest,
    db: Session = Depends(get_db),
    # Enforce BE-009 check: validates access to req.account_id from body
    validated_account_id: str = Depends(verify_account_body_ownership)
):
    """BE-041 & BE-045 & BE-047 & BE-048: Submits order safely with idempotency checks and step-up verification"""
    order_repo = SQLAlchemyOrderRepository(db)
    portfolio_repo = SQLAlchemyPortfolioRepository(db)
    user_repo = SQLAlchemyUserRepository(db)
    custodian = get_custodian_service()
    session_cache = get_session_cache()
    notifier = get_notification_service()
    
    # 1. Step up token payload hash matching verification BE-047
    auth_usecase = AuthUseCase(user_repo, session_cache, notifier)
    
    # Reconstruct exact preview transaction payload used during preview step
    preview = order_repo.get_order_preview(req.preview_token)
    if not preview:
        raise HTTPException(status_code=400, detail="Invalid preview token.")
        
    transaction_payload = {
        "account_id": preview.account_id,
        "instrument_id": preview.instrument_id,
        "side": preview.side.value,
        "quantity": float(preview.quantity),
        "estimated_price": float(preview.estimated_price),
        "commission": float(preview.commission),
        "total_estimated_cost": float(preview.total_estimated_cost),
        "expires_at": preview.expires_at.isoformat()
    }
    
    # Consume step-up verification token
    await auth_usecase.verify_step_up(req.step_up_token, transaction_payload)

    # 2. Proceed with Order Execution UseCase
    orders_usecase = OrderUseCase(order_repo, portfolio_repo, custodian)
    return await orders_usecase.execute_order(
        preview_token=req.preview_token,
        accepted_disclosure_version=req.accepted_disclosure_version,
        idempotency_key=req.idempotency_key,
        is_advised=req.is_advised
    )
