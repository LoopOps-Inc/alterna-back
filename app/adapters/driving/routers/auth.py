import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Request, status, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from app.core.container import get_db, get_session_cache, get_notification_service
from app.adapters.driven.database.repositories import SQLAlchemyUserRepository
from app.usecases.auth import AuthUseCase
from app.domain.auth import User, DeviceFingerprint
from app.core.security import PasswordHasher

router = APIRouter(prefix="/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    username: str
    password: str
    device_id: str
    os_name: str
    os_version: str
    ip_address: str
    user_agent: str

class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class StepUpPayloadRequest(BaseModel):
    transaction_payload: dict


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(req: RegisterRequest, db: Session = Depends(get_db)):
    """Sandbox endpoint to easily register testing users and encrypt password with Argon2id"""
    user_repo = SQLAlchemyUserRepository(db)
    existing = user_repo.get_by_username(req.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    user_id = str(uuid.uuid4())
    domain_user = User(
        id=user_id,
        username=req.username,
        email=req.email,
        is_active=True,
        created_at=datetime.utcnow()
    )
    
    hashed_pwd = PasswordHasher.hash_password(req.password)
    user_repo.save_user(domain_user, hashed_pwd)
    
    # Pre-populate account access for sandbox testing
    # By default, we grant this user access to a testing account ID: "acc-12345"
    user_repo.create_account_access(user_id, "acc-12345", "OWNER")

    return {"message": "User registered successfully", "user_id": user_id, "sandbox_account_id": "acc-12345"}


@router.post("/login")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    user_repo = SQLAlchemyUserRepository(db)
    session_cache = get_session_cache()
    notifier = get_notification_service()
    
    usecase = AuthUseCase(user_repo, session_cache, notifier)
    
    device = DeviceFingerprint(
        device_id=req.device_id,
        os_name=req.os_name,
        os_version=req.os_version,
        ip_address=req.ip_address,
        user_agent=req.user_agent,
        is_trusted=True  # For sandbox simplicity, assume initially trusted or verify
    )
    
    # Save fingerprint as trusted for ease of testing initially if specified
    return await usecase.login_user(req.username, req.password, device)


@router.post("/refresh")
async def refresh(req: RefreshRequest, db: Session = Depends(get_db)):
    user_repo = SQLAlchemyUserRepository(db)
    session_cache = get_session_cache()
    notifier = get_notification_service()
    
    usecase = AuthUseCase(user_repo, session_cache, notifier)
    return await usecase.rotate_tokens(req.refresh_token)


@router.post("/step-up")
async def create_step_up(
    req: StepUpPayloadRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Generates step up secure verification challenge"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    user_repo = SQLAlchemyUserRepository(db)
    session_cache = get_session_cache()
    notifier = get_notification_service()
    
    usecase = AuthUseCase(user_repo, session_cache, notifier)
    token = await usecase.generate_step_up_request(user_id, req.transaction_payload)
    return {"step_up_token": token}
