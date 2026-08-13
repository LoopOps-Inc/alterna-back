import hmac
import hashlib
import json
import time
from typing import Dict, Any, Union
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher as ArgonPH
from argon2.exceptions import VerifyMismatchError
from app.core.config import settings

# Initialize Argon2id with OWASP recommended parameters
# m=65536 (64MiB), t=3, p=4
argon2_hasher = ArgonPH(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16
)

# Common/Compromised Passwords Corpus Check (Simple set for local verification BE-001)
COMPROMISED_PASSWORDS = {
    "123456", "password", "123456789", "12345678", "12345", "qwerty",
    "password123", "admin", "admin123", "alterna2024", "alterna123"
}

class PasswordHasher:
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using Argon2id"""
        return argon2_hasher.hash(password)

    @staticmethod
    def verify_password(hash_str: str, password: str) -> bool:
        """Verify password using Argon2id. Always executes decoy/hash if verification is bypassed."""
        try:
            return argon2_hasher.verify(hash_str, password)
        except VerifyMismatchError:
            return False
        except Exception:
            return False

    @staticmethod
    def execute_decoy_hash() -> None:
        """Executes a dummy Argon2id hash verify to maintain constant time profile for non-existent users BE-001"""
        # A typical dummy hash that fails verify
        dummy_hash = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$R016S3l0WElMUG9YVnRvR0g1RjYxQT09"
        try:
            argon2_hasher.verify(dummy_hash, "decoy_password_to_force_mismatch")
        except Exception:
            pass


class KeyVaultSigner:
    @staticmethod
    def sign_payload(payload: Dict[str, Any]) -> str:
        """Generates an HMAC-SHA256 signature for a dictionary of values (BE-004, BE-040)"""
        serialized = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            settings.JWT_SECRET.encode('utf-8'),
            serialized.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    @staticmethod
    def verify_payload_signature(payload: Dict[str, Any], signature: str) -> bool:
        """Verifies HMAC-SHA256 signature for a payload"""
        try:
            calculated = KeyVaultSigner.sign_payload(payload)
            return hmac.compare_digest(calculated, signature)
        except Exception:
            return False


def is_password_compromised(password: str) -> bool:
    """Check if password belongs to a corpus of compromised passwords BE-001"""
    # Normalize and check
    normalized = password.strip().lower()
    if normalized in COMPROMISED_PASSWORDS:
        return True
    # Additionally reject super short passwords as a minimum baseline
    if len(password) < 8:
        return True
    return False


def create_jwt_token(data: dict, expires_delta: timedelta) -> str:
    """Create a cryptographically signed stateless JWT token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_jwt_token(token: str) -> Union[Dict[str, Any], None]:
    """Decode and verify stateless JWT token"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


def sleep_to_constant_interval(start_time: float, target: float = 0.150) -> None:
    """Ensures action execution time matches constant interval to mitigate enumeration BE-001"""
    elapsed = time.monotonic() - start_time
    if elapsed < target:
        time.sleep(target - elapsed)
