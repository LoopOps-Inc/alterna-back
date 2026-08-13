from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr

class DeviceFingerprint(BaseModel):
    device_id: str = Field(..., description="Unique hardware UUID or browser fingerprint")
    os_name: str
    os_version: str
    ip_address: str
    user_agent: str
    is_trusted: bool = False

class TokenFamily(BaseModel):
    family_id: str
    party_id: str
    parent_token: Optional[str] = None
    active_token: str
    is_revoked: bool = False
    created_at: datetime
    expires_at: datetime

class StepUpToken(BaseModel):
    step_up_token: str
    party_id: str
    payload_hash: str = Field(..., description="SHA-256 hash of the exact transactional payload")
    expires_at: datetime
    is_used: bool = False

class User(BaseModel):
    id: str
    username: str
    email: EmailStr
    is_active: bool = True
    created_at: datetime
