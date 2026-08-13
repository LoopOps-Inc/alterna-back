from typing import Protocol, Optional, Dict, Any
from app.domain.auth import TokenFamily

class ISessionCache(Protocol):
    async def store_session(self, token_family: TokenFamily) -> None:
        """Store active token family in Redis."""
        ...

    async def get_token_family_by_token(self, token: str) -> Optional[TokenFamily]:
        """Fetch token family record using the token."""
        ...

    async def invalidate_family(self, family_id: str) -> None:
        """Revoke all sessions in the token family within 30s limit (BE-007)."""
        ...

    async def check_lockout(self, username: str) -> bool:
        """Checks if a user is locked out due to brute-force attempts."""
        ...

    async def increment_failed_attempts(self, username: str) -> int:
        """Record and return count of failed login attempts with exponential backoff calculation."""
        ...

    async def clear_failed_attempts(self, username: str) -> None:
        """Clears failed login attempt tracking."""
        ...

    async def store_step_up_hash(self, token: str, payload_hash: str, expires_in_seconds: int = 180) -> None:
        """Stores a step-up token mapped to a specific payload hash (BE-004, BE-047)."""
        ...

    async def verify_and_consume_step_up(self, token: str, payload_hash: str) -> bool:
        """Verifies if the step-up token is valid for the payload hash and consumes it (single-use)."""
        ...


class IPriceCache(Protocol):
    async def store_market_quote(self, ticker: str, price_data: Dict[str, Any], ttl_seconds: int = 60) -> None:
        """Store quotes in Redis with a short TTL."""
        ...

    async def get_market_quote(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get quote from Redis cache."""
        ...
