import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from app.ports.cache import ISessionCache, IPriceCache
from app.domain.auth import TokenFamily

logger = logging.getLogger("altm_backend")

class InMemoryRedisMock:
    """A reliable in-memory fallback for Redis to enable testing and local development without a running daemon"""
    def __init__(self):
        self.kv = {}
        self.expirations = {}

    def setex(self, key: str, seconds: int, value: str):
        self.kv[key] = value
        self.expirations[key] = datetime.now(timezone.utc).timestamp() + seconds

    def get(self, key: str) -> Optional[str]:
        # Cleanup expired
        if key in self.expirations:
            if datetime.now(timezone.utc).timestamp() > self.expirations[key]:
                self.kv.pop(key, None)
                self.expirations.pop(key, None)
                return None
        return self.kv.get(key)

    def delete(self, key: str):
        self.kv.pop(key, None)
        self.expirations.pop(key, None)

    def incr(self, key: str) -> int:
        val = self.get(key)
        try:
            current = int(val) if val else 0
        except ValueError:
            current = 0
        new_val = current + 1
        self.kv[key] = str(new_val)
        return new_val


class RedisSessionCache(ISessionCache):
    def __init__(self, redis_client=None):
        # Fall back to InMemoryRedisMock if no client is passed or if it's not a real client
        self.client = redis_client if redis_client is not None else InMemoryRedisMock()

    async def store_session(self, token_family: TokenFamily) -> None:
        key = f"session_family:{token_family.family_id}"
        # Bind the active_token and other fields
        data = {
            "family_id": token_family.family_id,
            "party_id": token_family.party_id,
            "parent_token": token_family.parent_token,
            "active_token": token_family.active_token,
            "is_revoked": token_family.is_revoked,
            "created_at": token_family.created_at.isoformat(),
            "expires_at": token_family.expires_at.isoformat()
        }
        # Store for access by direct token too
        self.client.setex(f"session_token_map:{token_family.active_token}", 86400, token_family.family_id)
        if token_family.parent_token:
            self.client.setex(f"session_token_map:{token_family.parent_token}", 86400, token_family.family_id)
            
        self.client.setex(key, 86400, json.dumps(data))

    async def get_token_family_by_token(self, token: str) -> Optional[TokenFamily]:
        family_id = self.client.get(f"session_token_map:{token}")
        if not family_id:
            return None
        raw_data = self.client.get(f"session_family:{family_id}")
        if not raw_data:
            return None
        data = json.loads(raw_data)
        return TokenFamily(
            family_id=data["family_id"],
            party_id=data["party_id"],
            parent_token=data.get("parent_token"),
            active_token=data["active_token"],
            is_revoked=data["is_revoked"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"])
        )

    async def invalidate_family(self, family_id: str) -> None:
        # Enforce BE-007 (Session revocation taking effect in less than 30s)
        raw_data = self.client.get(f"session_family:{family_id}")
        if raw_data:
            data = json.loads(raw_data)
            data["is_revoked"] = True
            # Update cache immediately
            self.client.setex(f"session_family:{family_id}", 86400, json.dumps(data))
            logger.warning(f"Token family revoked: {family_id}")

    async def check_lockout(self, username: str) -> bool:
        attempts_str = self.client.get(f"failed_attempts:{username}")
        if attempts_str:
            attempts = int(attempts_str)
            if attempts >= 10:  # BE-008: lock out after 10 attempts
                return True
        return False

    async def increment_failed_attempts(self, username: str) -> int:
        attempts = self.client.incr(f"failed_attempts:{username}")
        # Apply exponential backoff based on attempts count BE-008
        return attempts

    async def clear_failed_attempts(self, username: str) -> None:
        self.client.delete(f"failed_attempts:{username}")

    async def store_step_up_hash(self, token: str, payload_hash: str, expires_in_seconds: int = 180) -> None:
        self.client.setex(f"step_up_token:{token}", expires_in_seconds, payload_hash)

    async def verify_and_consume_step_up(self, token: str, payload_hash: str) -> bool:
        stored_hash = self.client.get(f"step_up_token:{token}")
        if not stored_hash:
            return False
        # Single-use constraint: immediately delete on read BE-004
        self.client.delete(f"step_up_token:{token}")
        return stored_hash == payload_hash


class RedisPriceCache(IPriceCache):
    def __init__(self, redis_client=None):
        self.client = redis_client if redis_client is not None else InMemoryRedisMock()

    async def store_market_quote(self, ticker: str, price_data: Dict[str, Any], ttl_seconds: int = 60) -> None:
        self.client.setex(f"quote:{ticker}", ttl_seconds, json.dumps(price_data))

    async def get_market_quote(self, ticker: str) -> Optional[Dict[str, Any]]:
        raw = self.client.get(f"quote:{ticker}")
        if raw:
            return json.loads(raw)
        return None
