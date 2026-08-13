from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from app.core.container import get_db
from app.adapters.driving.middlewares.ownership_decorator import (
    verify_account_ownership,
    verify_account_body_ownership
)
from app.adapters.driven.database.repositories import SQLAlchemyMoneyRepository, SQLAlchemyUserRepository
from app.usecases.money import MoneyUseCase

router = APIRouter(prefix="/money", tags=["Money"])

class RegisterBeneficiaryRequest(BaseModel):
    account_id: str
    name: str
    clabe: str = Field(..., max_length=18, min_length=18)
    is_third_party: bool = True

class WithdrawRequest(BaseModel):
    account_id: str
    beneficiary_id: str
    amount: float
    idempotency_key: str


@router.get("/clabe/info")
async def get_clabe_info(
    clabe: str = Query(..., min_length=18, max_length=18)
):
    """RF-072: Validates a 18-digit CLABE and resolves its bank code and correctness"""
    from app.usecases.money import validate_clabe_checksum, CLABE_BANKS
    if not validate_clabe_checksum(clabe):
        raise HTTPException(status_code=400, detail="Invalid CLABE checksum.")
    
    bank_code = clabe[:3]
    bank_name = CLABE_BANKS.get(bank_code, "UNKNOWN BANK")
    return {
        "valid": True,
        "clabe": clabe,
        "bank_code": bank_code,
        "bank_name": bank_name
    }


@router.post("/beneficiaries")
async def register_beneficiary(
    req: RegisterBeneficiaryRequest,
    db: Session = Depends(get_db),
    # Enforce BE-009 check: validates access to req.account_id from body
    validated_account_id: str = Depends(verify_account_body_ownership)
):
    """RF-071 & RF-072: Registers a new third party bank beneficiary under cooling-off periods"""
    money_repo = SQLAlchemyMoneyRepository(db)
    user_repo = SQLAlchemyUserRepository(db)
    
    usecase = MoneyUseCase(money_repo, user_repo)
    return await usecase.register_beneficiary(
        account_id=validated_account_id,
        name=req.name,
        clabe=req.clabe,
        is_third_party=req.is_third_party
    )


@router.get("/beneficiaries")
async def list_beneficiaries(
    account_id: str = Query(...),
    db: Session = Depends(get_db),
    # Enforce BE-009 check: validates access to account_id from query
    validated_account_id: str = Depends(verify_account_ownership)
):
    """RF-071: Lists registered beneficiaries and displays active security cooling-off locks"""
    money_repo = SQLAlchemyMoneyRepository(db)
    user_repo = SQLAlchemyUserRepository(db)
    
    usecase = MoneyUseCase(money_repo, user_repo)
    return await usecase.get_beneficiary_list(validated_account_id)


@router.post("/withdraw")
async def withdraw_money(
    req: WithdrawRequest,
    request: Request,
    db: Session = Depends(get_db),
    # Enforce BE-009 check: validates access to req.account_id from body
    validated_account_id: str = Depends(verify_account_body_ownership)
):
    """RF-071 & RF-073 & BE-010: Processes cash withdrawals with strict cooling-off checks and idempotency"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    money_repo = SQLAlchemyMoneyRepository(db)
    user_repo = SQLAlchemyUserRepository(db)
    
    usecase = MoneyUseCase(money_repo, user_repo)
    return await usecase.request_withdrawal(
        party_id=user_id,
        account_id=validated_account_id,
        beneficiary_id=req.beneficiary_id,
        amount=req.amount,
        idempotency_key=req.idempotency_key
    )
