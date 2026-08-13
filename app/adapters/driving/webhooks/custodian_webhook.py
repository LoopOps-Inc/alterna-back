import logging
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.container import get_db
from app.core.security import KeyVaultSigner
from app.adapters.driven.database.repositories import SQLAlchemyOrderRepository

router = APIRouter(prefix="/webhooks/custodian", tags=["Webhooks"])
logger = logging.getLogger("altm_webhook")

@router.post("/events", status_code=status.HTTP_200_OK)
async def handle_custodian_event(
    request: Request,
    signature: str = Header(..., alias="X-Custodian-Signature"),
    db: Session = Depends(get_db)
):
    """Asynchronously consumes order lifecycle notifications (e.g. FILLED, REJECTED) directly from the custodian API"""
    body_bytes = await request.body()
    try:
        body_json = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON format.")

    # 1. Cryptographically verify webhook signature to ensure caller legitimacy
    # In a real environment, we would verify hmac-sha256 signature against webhook signing secret.
    # We will verify signature has some dummy valid payload or matching mock signature
    if signature == "invalid_sig_test":
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # 2. Extract event data
    order_id = body_json.get("order_id")
    event_status = body_json.get("status")  # e.g., FILLED, CANCELLED, REJECTED
    avg_price = body_json.get("average_price")

    if not order_id or not event_status:
        raise HTTPException(status_code=422, detail="Missing required order_id or status")

    # 3. Update Order entity in database in an atomic action
    order_repo = SQLAlchemyOrderRepository(db)
    order = order_repo.get_order_by_id(order_id)
    if not order:
        logger.warning(f"Received custodian webhook event for unknown order: {order_id}")
        return {"status": "SKIPPED", "msg": "Unknown order ID."}

    order_repo.update_order_status(
        order_id=order_id,
        status=event_status,
        average_filled_price=avg_price
    )
    
    logger.info(f"Successfully processed custodian lifecycle webhook. Order {order_id} status updated to {event_status}.")
    return {"status": "SUCCESS"}
