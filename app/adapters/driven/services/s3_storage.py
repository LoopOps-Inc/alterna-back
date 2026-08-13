import logging
from app.ports.services import IStorageService

logger = logging.getLogger("altm_backend")

class S3StorageService(IStorageService):
    def __init__(self):
        self.bucket_name = "altm-reports-bucket"

    async def upload_file(self, file_content: bytes, destination_path: str) -> str:
        logger.info(f"Uploading file to secure bucket {self.bucket_name} at path {destination_path}")
        # Return mock file uri
        return f"s3://{self.bucket_name}/{destination_path}"

    async def generate_presigned_url(self, bucket_path: str, expiration_seconds: int = 900) -> str:
        logger.info(f"Generating presigned URL for {bucket_path} with expiry {expiration_seconds} seconds")
        # Return signed-like mock URL
        return f"https://secure-download.alternasecurities.com/download?file={bucket_path}&token=presigned_token_xyz"
