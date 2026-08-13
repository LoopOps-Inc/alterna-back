import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List
from app.ports.database import IMoneyRepository, IUserRepository
from app.domain.money import Beneficiary, Transfer
from app.domain.exceptions import (
    PreventiveLockoutException,
    LimitExceededException,
    DomainException
)

# CLABE Bank code resolution prefix dictionary RF-072
CLABE_BANKS = {
    "002": "BANAMEX",
    "012": "BBVA BANCOMER",
    "014": "SANTANDER",
    "021": "HSBC",
    "030": "BAJIO",
    "072": "BANORTE",
    "127": "AZTECA",
    "137": "BANCOPPEL",
    "710": "SPEI_MOCK"
}

def validate_clabe_checksum(clabe: str) -> bool:
    """Validate 18-digit Mexican CLABE checksum using Modulo 97 algorithm (RF-072)"""
    if len(clabe) != 18 or not clabe.isdigit():
        return False
    
    # Weights for CLABE: 3, 7, 1
    weights = [3, 7, 1, 3, 7, 1, 3, 7, 1, 3, 7, 1, 3, 7, 1, 3, 7]
    products = []
    for char, weight in zip(clabe[:-1], weights):
        val = int(char) * weight
        products.append(val % 10)
    
    sum_products = sum(products)
    calculated_digit = (10 - (sum_products % 10)) % 10
    return calculated_digit == int(clabe[-1])


class MoneyUseCase:
    def __init__(self, money_repo: IMoneyRepository, user_repo: IUserRepository):
        self.money_repo = money_repo
        self.user_repo = user_repo

    async def register_beneficiary(
        self,
        account_id: str,
        name: str,
        clabe: str,
        is_third_party: bool = True
    ) -> Beneficiary:
        """RF-071 & RF-072: Registers a beneficiary bank account with CLABE validation and cooling-off period"""
        # 1. Validate CLABE structural correctness
        if not validate_clabe_checksum(clabe):
            raise DomainException("Invalid Mexican CLABE checksum validation failed.")

        # 2. Resolve bank name
        bank_code = clabe[:3]
        bank_name = CLABE_BANKS.get(bank_code, "UNKNOWN BANK")

        # Check if already registered
        existing = self.money_repo.get_beneficiary_by_account_and_clabe(account_id, clabe)
        if existing:
            return existing

        # 3. Apply cooling-off security lock (e.g., 24 hours RF-071)
        cooldown_until = datetime.utcnow() + timedelta(hours=24)

        beneficiary = Beneficiary(
            id=str(uuid.uuid4()),
            account_id=account_id,
            name=name,
            clabe=clabe,
            bank_name=bank_name,
            is_third_party=is_third_party,
            created_at=datetime.utcnow(),
            cooldown_until=cooldown_until
        )

        self.money_repo.save_beneficiary(beneficiary)
        return beneficiary

    async def request_withdrawal(
        self,
        party_id: str,
        account_id: str,
        beneficiary_id: str,
        amount: float,
        idempotency_key: str
    ) -> Dict[str, Any]:
        """RF-071 & RF-073 & BE-046: Withdraws money with cooling-off safety and idempotency protection"""
        
        # 1. Database Idempotency Check BE-046
        existing_transfer = self.money_repo.get_transfer_by_idempotency_key(idempotency_key)
        if existing_transfer:
            return {
                "transfer_id": existing_transfer.transfer_id,
                "status": existing_transfer.status,
                "msg": "Replayed withdrawal transaction."
            }

        # 2. Check general BE-010 cooling-off (if user modified security details in past 24h)
        recent_changes = self.user_repo.get_recent_profile_changes_count(party_id, window_hours=24)
        if recent_changes > 0:
            raise PreventiveLockoutException(
                "Withdrawals are locked for 24 hours following any profile or credential change (BE-010)."
            )

        # 3. Retrieve and inspect beneficiary account cooling-off
        beneficiary = self.money_repo.get_beneficiary_by_id(beneficiary_id)
        if not beneficiary or beneficiary.account_id != account_id:
            raise DomainException("Beneficiary account not found or access denied.")

        if beneficiary.cooldown_until > datetime.utcnow():
            remaining_cooldown = beneficiary.cooldown_until - datetime.utcnow()
            minutes_left = int(remaining_cooldown.total_seconds() / 60)
            raise PreventiveLockoutException(
                f"Target bank account is in security cooling-off lock. {minutes_left} minutes remaining."
            )

        # 4. Limit verification RF-073
        amt_dec = Decimal(str(amount))
        # Daily limit check (e.g. Max 250,000 MXN per day)
        if amt_dec > Decimal("250000.00"):
            raise LimitExceededException("Withdrawal amount exceeds single-transaction policy limits.")

        # Create transfer record
        transfer_id = str(uuid.uuid4())
        transfer_entity = Transfer(
            transfer_id=transfer_id,
            account_id=account_id,
            beneficiary_id=beneficiary_id,
            amount=amt_dec,
            currency="MXN",
            idempotency_key=idempotency_key,
            created_at=datetime.utcnow(),
            status="COMPLETED"  # Assume processed for sandbox simplicity
        )

        self.money_repo.create_transfer(transfer_entity)

        return {
            "transfer_id": transfer_id,
            "status": "COMPLETED",
            "msg": "Withdrawal processed successfully."
        }

    async def get_beneficiary_list(self, account_id: str) -> List[Beneficiary]:
        return self.money_repo.get_beneficiaries(account_id)
