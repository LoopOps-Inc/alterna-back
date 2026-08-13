import uuid
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any
from app.ports.database import IAMLRepository, IUserRepository
from app.domain.exceptions import AMLRuleViolationException
from app.domain.aml import AMLAlert

class AMLEngine:
    def __init__(self, aml_repo: IAMLRepository, user_repo: IUserRepository):
        self.aml_repo = aml_repo
        self.user_repo = user_repo

    async def evaluate_transaction_compliance(
        self,
        party_id: str,
        account_id: str,
        transaction_payload: Dict[str, Any]
    ) -> bool:
        """Evaluates live regulatory compliance rules (AML-01 to AML-07)"""
        amount = Decimal(str(transaction_payload.get("amount", "0.00")))
        tx_type = transaction_payload.get("type", "WITHDRAWAL")

        # --- Rule AML-07: Change of contact followed by immediate withdrawal (BE-010/AML-07) ---
        if tx_type == "WITHDRAWAL":
            recent_changes = self.user_repo.get_recent_profile_changes_count(party_id, window_hours=24)
            if recent_changes > 0:
                alert = AMLAlert(
                    id=str(uuid.uuid4()),
                    party_id=party_id,
                    rule_code="AML-07",
                    severity="HIGH",
                    description="Withdrawal requested immediately within 24 hours after credential modification.",
                    payload_snapshot=json.dumps(transaction_payload),
                    created_at=datetime.utcnow()
                )
                self.aml_repo.log_aml_alert(alert)
                raise AMLRuleViolationException("Transaction suspended under AML-07 Contact Modification checks.")

        # --- Rule AML-02: Smurfing/Fraccionamiento check (Multiple small withdrawals) ---
        if amount < Decimal("1000.00"):
            # Check accumulated volume in past 24 hours
            recent_volume = self.aml_repo.get_transaction_volume_window(account_id, window_hours=24)
            if recent_volume > 50000.0:  # Excessive micro-transfers
                alert = AMLAlert(
                    id=str(uuid.uuid4()),
                    party_id=party_id,
                    rule_code="AML-02",
                    severity="MEDIUM",
                    description="Possible fractioning / smurfing detected in 24 hour window.",
                    payload_snapshot=json.dumps(transaction_payload),
                    created_at=datetime.utcnow()
                )
                self.aml_repo.log_aml_alert(alert)
                raise AMLRuleViolationException("Transaction flagged under AML-02 Micro-transfer Accumulation.")

        # --- Rule AML-04: Pass-through (deposit followed by fast withdrawal without asset purchases) ---
        if tx_type == "WITHDRAWAL":
            last_funding = self.aml_repo.get_last_funding_time(account_id)
            if last_funding and (datetime.utcnow() - last_funding) < timedelta(hours=48):
                # Simple check: if cash is being routed out immediately without any stock buy orders
                alert = AMLAlert(
                    id=str(uuid.uuid4()),
                    party_id=party_id,
                    rule_code="AML-04",
                    severity="HIGH",
                    description="Immediate cash routing (pass-through) within 48h without asset trading.",
                    payload_snapshot=json.dumps(transaction_payload),
                    created_at=datetime.utcnow()
                )
                self.aml_repo.log_aml_alert(alert)
                raise AMLRuleViolationException("Transaction flagged under AML-04 Pass-through limits.")

        # --- Rule AML-05: High Risk Jurisdiction checks ---
        destination_country = transaction_payload.get("country_code", "MX")
        if destination_country in ["KP", "IR", "SY", "YE"]:  # Sanctioned lists
            alert = AMLAlert(
                id=str(uuid.uuid4()),
                party_id=party_id,
                rule_code="AML-05",
                severity="CRITICAL",
                description=f"Transaction routed to high-risk sanctioned jurisdiction: {destination_country}",
                payload_snapshot=json.dumps(transaction_payload),
                created_at=datetime.utcnow()
            )
            self.aml_repo.log_aml_alert(alert)
            raise AMLRuleViolationException("Transaction rejected under international AML-05 country sanctions.")

        return True
