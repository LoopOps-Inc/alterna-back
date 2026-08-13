from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.container import get_db, get_custodian_service
from app.adapters.driving.middlewares.ownership_decorator import verify_account_ownership
from app.adapters.driven.database.repositories import SQLAlchemyPortfolioRepository
from app.adapters.driven.services.s3_storage import S3StorageService
from app.usecases.portfolio import PortfolioUseCase

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])

@router.get("/summary")
async def get_summary(
    account_id: str = Query(..., description="Account ID to retrieve portfolio for"),
    currency: str = Query("USD", regex="^(USD|MXN)$"),
    db: Session = Depends(get_db),
    # Enforce BE-009: verify_account_ownership dependency will raise 404 if user has no legitimate access
    validated_account_id: str = Depends(verify_account_ownership)
):
    """BE-020 & BE-025 & BE-026 & BE-028: Returns positions allocation breakdowns and multimoneda balances"""
    portfolio_repo = SQLAlchemyPortfolioRepository(db)
    custodian = get_custodian_service()
    
    usecase = PortfolioUseCase(portfolio_repo, custodian)
    return await usecase.get_portfolio_summary(validated_account_id, currency)


@router.post("/reconcile")
async def trigger_reconciliation(
    account_id: str = Query(...),
    db: Session = Depends(get_db),
    validated_account_id: str = Depends(verify_account_ownership)
):
    """BE-021: Triggers daily automated reconciliation. Throws ReconciliationMismatchException on discrepancy."""
    portfolio_repo = SQLAlchemyPortfolioRepository(db)
    custodian = get_custodian_service()
    
    usecase = PortfolioUseCase(portfolio_repo, custodian)
    await usecase.run_daily_reconciliation(validated_account_id)
    return {"status": "SUCCESS", "message": "Reconciliation passed with no differences."}


@router.post("/export")
async def export_portfolio(
    account_id: str = Query(...),
    db: Session = Depends(get_db),
    validated_account_id: str = Depends(verify_account_ownership)
):
    """BE-027: Asynchronously generates CSV export of portfolio, deposits on bucket and returns presigned link"""
    portfolio_repo = SQLAlchemyPortfolioRepository(db)
    custodian = get_custodian_service()
    
    usecase = PortfolioUseCase(portfolio_repo, custodian)
    summary = await usecase.get_portfolio_summary(validated_account_id)
    
    # Simple CSV generation mock
    csv_rows = ["Ticker,Name,Quantity,MarketPrice,MarketValue"]
    for pos in summary.positions:
        csv_rows.append(f"{pos.ticker},{pos.name},{pos.quantity},{pos.market_price},{pos.market_value}")
    
    csv_bytes = "\n".join(csv_rows).encode("utf-8")
    
    storage = S3StorageService()
    path = f"exports/portfolio_{validated_account_id}_{int(summary.data_as_of.timestamp())}.csv"
    uploaded_uri = await storage.upload_file(csv_bytes, path)
    
    # Return 15 minutes valid presigned URL BE-027
    download_url = await storage.generate_presigned_url(path, expiration_seconds=900)
    
    return {
        "status": "COMPLETED",
        "download_url": download_url,
        "expires_in_seconds": 900
    }
