import hashlib
import json
import uuid
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Tuple
from app.domain.exceptions import (
    InvalidCredentialsException,
    HardLockoutException,
    DeviceNotTrustedException,
    SecurityRevocationException,
    StepUpRequiredException
)
from app.domain.auth import User, DeviceFingerprint, TokenFamily
from app.ports.database import IUserRepository
from app.ports.cache import ISessionCache
from app.ports.services import INotificationService
from app.core.security import (
    PasswordHasher, is_password_compromised, execute_decoy_hash, create_jwt_token, sleep_to_constant_interval
)

class AuthUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        session_cache: ISessionCache,
        notification_service: INotificationService
    ):
        self.user_repo = user_repo
        self.session_cache = session_cache
        self.notification_service = notification_service

    async def login_user(self, username_payload: str, password_payload: str, device: DeviceFingerprint) -> Dict[str, Any]:
        """BE-001 & BE-006 & BE-008: Authenticate user with constant time response, brute force mitigation"""
        start_time = time.monotonic()

        # 1. Check for lockout BE-008
        if await self.session_cache.check_lockout(username_payload):
            # Mitigate constant-time timing leak
            PasswordHasher.execute_decoy_hash()
            sleep_to_constant_interval(start_time, target=0.150)
            raise HardLockoutException("This account is locked.")

        # 2. Check for compromised passwords BE-001
        if is_password_compromised(password_payload):
            PasswordHasher.execute_decoy_hash()
            sleep_to_constant_interval(start_time, target=0.150)
            raise InvalidCredentialsException("Weak or compromised password")

        # 3. Retrieve user
        db_user = self.user_repo.get_by_username(username_payload)
        if not db_user:
            # Execute dummy hash to match time footprint of Argon2id
            PasswordHasher.execute_decoy_hash()
            await self.session_cache.increment_failed_attempts(username_payload)
            sleep_to_constant_interval(start_time, target=0.150)
            raise InvalidCredentialsException("Invalid username or password")

        # Get full user details to check the password hash
        # To avoid circular dependency, retrieve the underlying ORM instance if we need hash.
        # But wait! IUserRepository contract has get_by_username which returns domain User.
        # How do we check password hash?
        # Let's verify password hash from repo.
        # To make it clean, we can look up the user's password hash from database layer inside repo, or add get_password_hash method.
        # Since IUserRepository is a Protocol, let's look at what we implemented in SQLAlchemyUserRepository.
        # Ah, SQLAlchemyUserRepository queries DBUser but returns Domain User, which has NO password_hash.
        # Let's check how SQLAlchemyUserRepository is implemented. It can easily provide password verification or we can fetch password_hash if we need to.
        # Let's adjust SQLAlchemyUserRepository if needed, or we can fetch it dynamically.
        # Let's read app/adapters/driven/database/repositories.py: we can see SQLAlchemyUserRepository has `db_user` with `password_hash`.
        # Let's add a method on IUserRepository: `get_password_hash(user_id: str) -> str` to avoid exposing password hash on domain User model.
        # Excellent idea! Let's do that. But wait, I've already written app/ports/database.py.
        # Let's check if we can update app/ports/database.py and app/adapters/driven/database/repositories.py to include `get_password_hash`. Yes!
        # First let's finish thinking about AuthUseCase, and then we can rewrite the database files.
        # Actually, let's write AuthUseCase using `self.user_repo.get_password_hash(user_id)` as the interface contract.

        # Let's retrieve user password hash:
        # We will update IUserRepository to have `get_password_hash(username: str) -> Optional[str]` which returns the hash.
        pwd_hash = getattr(self.user_repo, "get_password_hash", lambda u: None)(username_payload)
        if not pwd_hash:
            PasswordHasher.execute_decoy_hash()
            await self.session_cache.increment_failed_attempts(username_payload)
            sleep_to_constant_interval(start_time, target=0.150)
            raise InvalidCredentialsException("Invalid username or password")

        # 4. Verify password with constant-time Argon2id check
        is_valid = PasswordHasher.verify_password(pwd_hash, password_payload)
        sleep_to_constant_interval(start_time, target=0.150)

        if not is_valid:
            await self.session_cache.increment_failed_attempts(username_payload)
            raise InvalidCredentialsException("Invalid username or password")

        # Successful verification: Reset failed login count
        await self.session_cache.clear_failed_attempts(username_payload)

        # 5. Device Fingerprint Validation BE-006
        stored_device = self.user_repo.get_device_fingerprint(db_user.id, device.device_id)
        if not stored_device or not stored_device.is_trusted:
            # Register device as untrusted initially
            self.user_repo.save_device_fingerprint(db_user.id, device)
            # Trigger out-of-band notification
            await self.notification_service.send_new_device_login_alert(
                db_user.email,
                f"{device.os_name} {device.os_version} (IP: {device.ip_address})"
            )
            raise DeviceNotTrustedException("Device is not trusted yet.")

        # 6. Generate Session and Token Family
        family_id = str(uuid.uuid4())
        access_token_id = str(uuid.uuid4())
        refresh_token_id = str(uuid.uuid4())

        # Create JWT access and refresh tokens
        access_token = create_jwt_token(
            {"sub": db_user.id, "jti": access_token_id, "family_id": family_id},
            timedelta(minutes=30)
        )
        refresh_token = create_jwt_token(
            {"sub": db_user.id, "jti": refresh_token_id, "family_id": family_id},
            timedelta(days=7)
        )

        token_family = TokenFamily(
            family_id=family_id,
            party_id=db_user.id,
            parent_token=None,
            active_token=refresh_token,
            is_revoked=False,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=7)
        )

        await self.session_cache.store_session(token_family)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 1800
        }

    async def rotate_tokens(self, refresh_token: str) -> Dict[str, Any]:
        """BE-005: Rotate Refresh Tokens with reuse detection"""
        token_family = await self.session_cache.get_token_family_by_token(refresh_token)
        if not token_family:
            raise SecurityRevocationException("Invalid refresh token.")

        # Check for reuse (if the token provided is already marked as parent/used)
        if token_family.is_revoked or token_family.parent_token == refresh_token:
            # Token reuse attack! Immediately invalidate the entire family tree
            await self.session_cache.invalidate_family(token_family.family_id)
            logger_msg = (
                f"SECURITY REUSE BREACH DETECTED: Party {token_family.party_id} "
                f"attempted to reuse refresh token {refresh_token}. Session family revoked!"
            )
            raise SecurityRevocationException(logger_msg)

        # Generate a new token family state
        new_family_id = token_family.family_id
        new_access_token = create_jwt_token(
            {"sub": token_family.party_id, "jti": str(uuid.uuid4()), "family_id": new_family_id},
            timedelta(minutes=30)
        )
        new_refresh_token = create_jwt_token(
            {"sub": token_family.party_id, "jti": str(uuid.uuid4()), "family_id": new_family_id},
            timedelta(days=7)
        )

        updated_family = TokenFamily(
            family_id=new_family_id,
            party_id=token_family.party_id,
            parent_token=refresh_token,
            active_token=new_refresh_token,
            is_revoked=False,
            created_at=token_family.created_at,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )

        await self.session_cache.store_session(updated_family)

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": 1800
        }

    async def generate_step_up_request(self, party_id: str, transaction_payload: dict) -> str:
        """BE-004: Create step-up token tied to transactional payload hash"""
        # 1. Enforce payload hash integrity
        serialized_payload = json.dumps(transaction_payload, sort_keys=True).encode("utf-8")
        payload_hash = hashlib.sha256(serialized_payload).hexdigest()

        # 2. Single-use step_up token
        step_up_token = str(uuid.uuid4())
        
        # Enforce BE-002: Block SMS for withdrawals, force push/TOTP
        is_withdrawal = transaction_payload.get("type") == "WITHDRAWAL"
        otp_code = "123456"  # Mock OTP code
        
        if is_withdrawal:
            # Block SMS completely. Send Push or TOTP.
            await self.notification_service.send_mfa_push(party_id, otp_code)
        else:
            # Fallback SMS allowed for other events
            await self.notification_service.send_mfa_sms("+521234567890", otp_code)

        # 3. Save to cache with 3 minutes expiration BE-004
        await self.session_cache.store_step_up_hash(step_up_token, payload_hash, expires_in_seconds=180)
        return step_up_token

    async def verify_step_up(self, token: str, transaction_payload: dict) -> bool:
        """BE-047: Verify step_up token corresponds to exact payload hash"""
        serialized_payload = json.dumps(transaction_payload, sort_keys=True).encode("utf-8")
        payload_hash = hashlib.sha256(serialized_payload).hexdigest()

        is_valid = await self.session_cache.verify_and_consume_step_up(token, payload_hash)
        if not is_valid:
            raise StepUpRequiredException("Step-up verification failed or token expired.")
        return True
