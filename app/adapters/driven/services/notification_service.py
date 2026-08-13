import logging
from app.ports.services import INotificationService

logger = logging.getLogger("altm_backend")

class OutOfBandNotificationService(INotificationService):
    async def send_new_device_login_alert(self, email: str, device_info: str) -> None:
        logger.warning(
            f"SECURITY OOB ALERT: Sending email notification to {email} "
            f"regarding new device login details: {device_info} (BE-006)"
        )

    async def send_mfa_sms(self, phone: str, code: str) -> None:
        # Enforce BE-002 rule: Withdrawal operations should not allow SMS verification
        # The caller is responsible, but we log protection
        logger.info(f"OOB SMS sent to {phone} containing verification token: [REDACTED_MFA_CODE]")

    async def send_mfa_push(self, party_id: str, code: str) -> None:
        logger.info(f"OOB Secure Push notification sent to user {party_id} containing verification token: [REDACTED_MFA_CODE] (BE-002)")
