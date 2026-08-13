from typing import Protocol, Optional

class INotificationService(Protocol):
    async def send_new_device_login_alert(self, email: str, device_info: str) -> None:
        """Notifies user out-of-band of login from a new device (BE-006)."""
        ...

    async def send_mfa_sms(self, phone: str, code: str) -> None:
        """Sends an MFA code via SMS. Restrained/blocked for withdrawal authorization (BE-002)."""
        ...

    async def send_mfa_push(self, party_id: str, code: str) -> None:
        """Sends an MFA code via high-security Push Notification (BE-002)."""
        ...


class IStorageService(Protocol):
    async def upload_file(self, file_content: bytes, destination_path: str) -> str:
        """Uploads a report/file to a secure bucket and returns bucket path."""
        ...

    async def generate_presigned_url(self, bucket_path: str, expiration_seconds: int = 900) -> str:
        """Generates a temporary, single-use presigned URL (BE-027)."""
        ...


class IPDFGenerator(Protocol):
    async def generate_execution_invoice_pdf(self, order_data: dict) -> bytes:
        """Generates a tagged, accessible PDF execution invoice (BE-052)."""
        ...
