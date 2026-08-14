import uuid
import hashlib
from datetime import datetime
from typing import Optional, Dict, List
from fastapi import APIRouter, Depends, Request, status, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from app.core.container import get_db, get_session_cache, get_notification_service
from app.adapters.driven.database.repositories import SQLAlchemyUserRepository
from app.usecases.auth import AuthUseCase
from app.domain.auth import User, DeviceFingerprint
from app.core.security import PasswordHasher, is_password_compromised
from app.adapters.driven.database.models import DBOnboardingProgress, DBUser, DBAccountAccess

router = APIRouter(prefix="/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    username: str
    password: str
    device_id: Optional[str] = None
    os_name: Optional[str] = None
    os_version: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_fingerprint: Optional[dict] = None

class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class StepUpPayloadRequest(BaseModel):
    transaction_payload: dict

class AccountAccessInfo(BaseModel):
    account_id: str
    role: str

class CurrentUserResponse(BaseModel):
    user_id: str
    username: str
    email: EmailStr
    is_active: bool
    account_id: Optional[str] = None
    accounts: list[AccountAccessInfo]

# --- HIGH FIDELITY ONBOARDING SCHEMAS ---

class OnboardingStartRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    phone: str

class OnboardingOTPVerifyRequest(BaseModel):
    onboarding_id: str
    email_otp: str
    phone_otp: str

class OnboardingPersonalDataRequest(BaseModel):
    onboarding_id: str
    full_name: str
    curp: str = Field(..., description="CURP validation")
    rfc: str = Field(..., description="RFC validation")
    birth_date: str
    birth_place: str
    nationality: str
    occupation: str

class OnboardingDocumentUploadRequest(BaseModel):
    onboarding_id: str
    id_type: str = Field(..., description="INE or PASSPORT")
    id_number: str
    id_image_base64: str = Field(..., description="Pass 'blurry' inside to trigger quality reject")

class OnboardingBiometricsRequest(BaseModel):
    onboarding_id: str
    biometric_consent_given: bool
    selfie_image_base64: str

class OnboardingAddressRequest(BaseModel):
    onboarding_id: str
    street: str
    city: str
    state: str
    zip_code: str
    proof_of_address_base64: str

class OnboardingFinancialRequest(BaseModel):
    onboarding_id: str
    funds_source: str
    declared_wealth: float
    investment_purpose: str

class OnboardingPEPAndScreeningRequest(BaseModel):
    onboarding_id: str
    is_pep: bool
    pep_details: Optional[str] = None

class OnboardingInvestorProfileRequest(BaseModel):
    onboarding_id: str
    objective: str
    horizon: str
    risk_tolerance: str
    knowledge_experience: str

class OnboardingFATCARequest(BaseModel):
    onboarding_id: str
    fatca_residency_us: bool
    fatca_tin: Optional[str] = None

class OnboardingConsentsRequest(BaseModel):
    onboarding_id: str
    intermediate_contract_consent: bool
    privacy_policy_consent: bool
    commissions_catalog_consent: bool
    terms_of_use_consent: bool
    biometric_treatment_consent: bool
    document_hash: str = Field(..., description="Must match the required official document hash")

class OnboardingSignRequest(BaseModel):
    onboarding_id: str
    signature_text: str


# --- EXISTING BASIC REGISTER ENDPOINT ---

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(req: RegisterRequest, db: Session = Depends(get_db)):
    """Sandbox endpoint to easily register testing users and encrypt password with Argon2id"""
    user_repo = SQLAlchemyUserRepository(db)
    existing = user_repo.get_by_username(req.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Enforce password strength/compromised check on registration to match security policies (ALTM-ARQ-004)
    if is_password_compromised(req.password):
        if len(req.password) < 8:
            raise HTTPException(
                status_code=400,
                detail="Password is too short. It must be at least 8 characters long."
            )
        raise HTTPException(
            status_code=400,
            detail="Password is weak or belongs to a known list of compromised passwords."
        )

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
    user_repo.create_account_access(user_id, "acc-12345", "OWNER")

    return {"message": "User registered successfully", "user_id": user_id, "sandbox_account_id": "acc-12345"}


# --- HIGH FIDELITY ONBOARDING FLOW IMPLEMENTATION ---

@router.post("/onboarding/start", status_code=status.HTTP_201_CREATED)
def onboarding_start(req: OnboardingStartRequest, db: Session = Depends(get_db)):
    """RF-110 & RF-111: Start onboarding flow, register credential and initiate OTP"""
    user_repo = SQLAlchemyUserRepository(db)
    existing = user_repo.get_by_username(req.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
        
    if is_password_compromised(req.password) or len(req.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long and not compromised."
        )

    onboarding_id = str(uuid.uuid4())
    password_hash = PasswordHasher.hash_password(req.password)
    
    # Create onboarding progress record
    progress = DBOnboardingProgress(
        id=onboarding_id,
        username=req.username,
        email=req.email,
        password_hash=password_hash,
        phone=req.phone,
        current_step="VERIFICATION",
        status="IN_PROGRESS"
    )
    db.add(progress)
    db.commit()

    # Simulated email & phone OTP dispatch (RF-110)
    return {
        "message": "Onboarding started. OTP sent to email and phone.",
        "onboarding_id": onboarding_id,
        "next_step": "OTP_VERIFICATION",
        "simulated_email_otp": "1234",
        "simulated_phone_otp": "5678"
    }


@router.post("/onboarding/verify-otp")
def onboarding_verify_otp(req: OnboardingOTPVerifyRequest, db: Session = Depends(get_db)):
    """RF-110: Verify both email and phone OTPs to proceed"""
    progress = db.query(DBOnboardingProgress).filter(DBOnboardingProgress.id == req.onboarding_id).first()
    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
        
    if req.email_otp != "1234" or req.phone_otp != "5678":
        raise HTTPException(status_code=400, detail="Invalid OTP code")
        
    progress.email_verified = True
    progress.phone_verified = True
    progress.current_step = "PERSONAL_DATA"
    db.commit()
    
    return {
        "message": "Email and phone verified successfully",
        "onboarding_id": req.onboarding_id,
        "next_step": "PERSONAL_DATA"
    }


@router.post("/onboarding/personal-data")
def onboarding_personal_data(req: OnboardingPersonalDataRequest, db: Session = Depends(get_db)):
    """RF-114: Capture and validate CURP/RFC details"""
    progress = db.query(DBOnboardingProgress).filter(DBOnboardingProgress.id == req.onboarding_id).first()
    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
        
    # Validate CURP/RFC format/existence against official sources (simulated)
    if len(req.curp) < 18:
        raise HTTPException(status_code=400, detail="Invalid CURP length")
    if len(req.rfc) < 12 or len(req.rfc) > 13:
        raise HTTPException(status_code=400, detail="Invalid RFC length")
        
    progress.full_name = req.full_name
    progress.curp = req.curp
    progress.rfc = req.rfc
    progress.birth_date = req.birth_date
    progress.birth_place = req.birth_place
    progress.nationality = req.nationality
    progress.occupation = req.occupation
    progress.current_step = "DOCUMENT_UPLOAD"
    db.commit()
    
    return {
        "message": "Personal data validated and stored successfully",
        "onboarding_id": req.onboarding_id,
        "next_step": "DOCUMENT_UPLOAD"
    }


@router.post("/onboarding/document-upload")
def onboarding_document_upload(req: OnboardingDocumentUploadRequest, db: Session = Depends(get_db)):
    """RF-112: Upload official ID with simulated quality checks and OCR"""
    progress = db.query(DBOnboardingProgress).filter(DBOnboardingProgress.id == req.onboarding_id).first()
    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
        
    # TC-112-01: Quality assessment
    if "blurry" in req.id_image_base64.lower() or "reflejo" in req.id_image_base64.lower():
        raise HTTPException(
            status_code=400,
            detail="La imagen está borrosa o tiene reflejos. Por favor, tómala de nuevo en un lugar bien iluminado."
        )
        
    progress.id_type = req.id_type
    progress.id_number = req.id_number
    progress.id_image_quality = 0.95
    progress.current_step = "BIOMETRICS"
    db.commit()
    
    return {
        "message": "Document uploaded and validated via OCR successfully",
        "onboarding_id": req.onboarding_id,
        "next_step": "BIOMETRICS"
    }


@router.post("/onboarding/biometrics")
def onboarding_biometrics(req: OnboardingBiometricsRequest, db: Session = Depends(get_db)):
    """RF-113 & TC-113-01 & TC-113-02: Liveness and biometric selfie check"""
    progress = db.query(DBOnboardingProgress).filter(DBOnboardingProgress.id == req.onboarding_id).first()
    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
        
    # TC-113-01: Consent check
    if not req.biometric_consent_given:
        raise HTTPException(
            status_code=400,
            detail="Biometric consent is mandatory to perform liveness checking and 1:1 match."
        )
        
    progress.biometric_consent_given = True
    progress.biometric_attempts += 1
    
    # TC-113-02: 3 strikes retry limits
    if "fail" in req.selfie_image_base64.lower():
        if progress.biometric_attempts >= 3:
            progress.status = "ESCALATED"
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="Biometric verification failed 3 times. Escalating to assisted videollamada route."
            )
        db.commit()
        raise HTTPException(status_code=400, detail=f"Biometric matching failed. Attempt {progress.biometric_attempts} of 3.")
        
    progress.biometric_similarity_score = 0.92
    progress.biometric_liveness_score = 0.98
    progress.current_step = "ADDRESS"
    db.commit()
    
    return {
        "message": "Biometrics selfie matched successfully with official ID",
        "onboarding_id": req.onboarding_id,
        "next_step": "ADDRESS"
    }


@router.post("/onboarding/address")
def onboarding_address(req: OnboardingAddressRequest, db: Session = Depends(get_db)):
    """RF-115: Address proof validation"""
    progress = db.query(DBOnboardingProgress).filter(DBOnboardingProgress.id == req.onboarding_id).first()
    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
        
    progress.address_street = req.street
    progress.address_city = req.city
    progress.address_state = req.state
    progress.address_zip = req.zip_code
    progress.address_proof_document = "proof_of_address.pdf"
    progress.current_step = "FINANCIAL"
    db.commit()
    
    return {
        "message": "Address details saved successfully",
        "onboarding_id": req.onboarding_id,
        "next_step": "FINANCIAL"
    }


@router.post("/onboarding/financial")
def onboarding_financial(req: OnboardingFinancialRequest, db: Session = Depends(get_db)):
    """RF-116: Financial profiling"""
    progress = db.query(DBOnboardingProgress).filter(DBOnboardingProgress.id == req.onboarding_id).first()
    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
        
    progress.funds_source = req.funds_source
    progress.declared_wealth = req.declared_wealth
    progress.investment_purpose = req.investment_purpose
    progress.current_step = "PEP_SCREENING"
    db.commit()
    
    return {
        "message": "Financial data saved successfully",
        "onboarding_id": req.onboarding_id,
        "next_step": "PEP_SCREENING"
    }


@router.post("/onboarding/pep-screening")
def onboarding_pep_screening(req: OnboardingPEPAndScreeningRequest, db: Session = Depends(get_db)):
    """RF-117 & RF-118 & TC-117-01 & TC-118-01 & TC-118-02: PEP evaluation & list screening"""
    progress = db.query(DBOnboardingProgress).filter(DBOnboardingProgress.id == req.onboarding_id).first()
    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
        
    # 1. PEP Check (TC-117-01)
    if req.is_pep:
        progress.is_pep = True
        progress.pep_details = req.pep_details or "Declared PEP"
        progress.status = "ESCALATED"
        progress.risk_classification = "HIGH"
        db.commit()
        # Escalates to manual queue, but let user continue step-by-step
        return {
            "message": "PEP status detected. Escalating to manual compliance review queue. Step continued.",
            "onboarding_id": req.onboarding_id,
            "next_step": "INVESTOR_PROFILE",
            "escalated": True
        }
        
    # 2. Automated list checks (TC-118-01 & TC-118-02)
    # Check if user is on the blacklist
    username_lower = progress.username.lower()
    if "blocked" in username_lower or "sanctioned" in username_lower or "terrorist" in username_lower:
        progress.status = "BLOCKED"
        progress.screening_passed = False
        progress.screening_result = "Matched with Mexican Blocked List (OFAC / CNBV)"
        progress.screening_list_version = "2026.08.13-V1"
        db.commit()
        
        # TC-118-01: Message must be strictly neutral and generic to avoid leaking the AML rule
        raise HTTPException(
            status_code=400,
            detail="Estamos revisando tu solicitud. Te contactaremos por correo electrónico en las próximas horas."
        )
        
    progress.is_pep = False
    progress.screening_passed = True
    progress.screening_result = "No matches found."
    progress.screening_list_version = "2026.08.13-V1"
    progress.current_step = "INVESTOR_PROFILE"
    db.commit()
    
    return {
        "message": "Screening passed successfully with list version: 2026.08.13-V1",
        "onboarding_id": req.onboarding_id,
        "next_step": "INVESTOR_PROFILE"
    }


@router.post("/onboarding/investor-profile")
def onboarding_investor_profile(req: OnboardingInvestorProfileRequest, db: Session = Depends(get_db)):
    """RF-119 & TC-119-01: Calculate risk profile score"""
    progress = db.query(DBOnboardingProgress).filter(DBOnboardingProgress.id == req.onboarding_id).first()
    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
        
    score = 0
    if "high" in req.risk_tolerance.lower():
        score += 15
        profile = "AGGRESSIVE"
        explanation = "You possess high tolerance to risk and seek long-term growth opportunities."
    elif "medium" in req.risk_tolerance.lower():
        score += 8
        profile = "MODERATE"
        explanation = "You seek balanced returns and have moderate resilience to market fluctuations."
    else:
        score += 3
        profile = "CONSERVATIVE"
        explanation = "You prefer stability and capital preservation over volatile returns."
        
    progress.investor_profile_score = score
    progress.risk_profile = profile
    progress.current_step = "FATCA_CONSENTS"
    db.commit()
    
    return {
        "message": "Investor profile calculated successfully",
        "onboarding_id": req.onboarding_id,
        "profile": profile,
        "explanation": explanation,
        "next_step": "FATCA_CONSENTS"
    }


@router.post("/onboarding/fatca-consents")
def onboarding_fatca_consents(req: OnboardingConsentsRequest, db: Session = Depends(get_db)):
    """RF-120 & RF-121 & TC-121-01 & TC-121-02 & TC-121-03: FATCA, individual consents, hash verification"""
    progress = db.query(DBOnboardingProgress).filter(DBOnboardingProgress.id == req.onboarding_id).first()
    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
        
    # Verify all individual consents are accepted (TC-121-01)
    if not (req.intermediate_contract_consent and 
            req.privacy_policy_consent and 
            req.commissions_catalog_consent and 
            req.terms_of_use_consent and 
            req.biometric_treatment_consent):
        raise HTTPException(
            status_code=400,
            detail="You must separate and explicitly accept all legal contracts and disclosures."
        )
        
    # Verify document hash integrity (TC-121-02)
    official_hash = "sha256-4da8-9861-f09477b7cb42"
    if req.document_hash != official_hash:
        raise HTTPException(
            status_code=400,
            detail="Integrity check failed. The document hash provided does not match the current official version."
        )
        
    progress.consents_accepted = True
    progress.current_step = "SIGN"
    db.commit()
    
    return {
        "message": "Individual consents validated with registered hash verification",
        "onboarding_id": req.onboarding_id,
        "next_step": "SIGN"
    }


@router.post("/onboarding/sign")
def onboarding_sign(req: OnboardingSignRequest, db: Session = Depends(get_db)):
    """RF-122: Complete the digital signature and persist the user into DB"""
    progress = db.query(DBOnboardingProgress).filter(DBOnboardingProgress.id == req.onboarding_id).first()
    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
        
    if not req.signature_text:
        raise HTTPException(status_code=400, detail="Signature is mandatory to sign the digital contract.")
        
    # Sign contract
    signed_hash = hashlib.sha256(f"{progress.username}:{datetime.utcnow().isoformat()}".encode()).hexdigest()
    progress.signed_contract_hash = signed_hash
    progress.signed_at = datetime.utcnow()
    progress.current_step = "COMPLETED"
    
    if progress.status != "ESCALATED":
        progress.status = "COMPLETED"
        
    # Create the user in official production database (RF-122 / RF-123)
    user_repo = SQLAlchemyUserRepository(db)
    
    # If the user exists in user DB, update or fail
    existing = user_repo.get_by_username(progress.username)
    if not existing:
        user_id = str(uuid.uuid4())
        domain_user = User(
            id=user_id,
            username=progress.username,
            email=progress.email,
            is_active=True,
            created_at=datetime.utcnow()
        )
        user_repo.save_user(domain_user, progress.password_hash)
        
        # Link default Sandbox testing account acc-12345 to owner
        user_repo.create_account_access(user_id, "acc-12345", "OWNER")
    else:
        user_id = existing.id

    db.commit()
    
    return {
        "message": "Contract digitally signed. Onboarding complete!",
        "onboarding_id": req.onboarding_id,
        "user_id": user_id,
        "status": progress.status,
        "signed_contract_hash": signed_hash,
        "timestamp": progress.signed_at.isoformat(),
        "sandbox_account_id": "acc-12345"
    }


@router.get("/onboarding/status/{onboarding_id}")
def onboarding_get_status(onboarding_id: str, db: Session = Depends(get_db)):
    """RF-125: Allow user to check the onboarding status and missing fields/steps in real-time"""
    progress = db.query(DBOnboardingProgress).filter(DBOnboardingProgress.id == onboarding_id).first()
    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
        
    steps_definition = {
        "VERIFICATION": "Verify email and phone OTPs",
        "PERSONAL_DATA": "CURP, RFC and identity declaration",
        "DOCUMENT_UPLOAD": "Official identity card upload (INE / Passport)",
        "BIOMETRICS": "Active/passive selfie liveness checks",
        "ADDRESS": "Proof of address details and verification",
        "FINANCIAL": "Origins of wealth declaration",
        "PEP_SCREENING": "Politically exposed person assessment",
        "INVESTOR_PROFILE": "Investor risk profiling questionnaire",
        "FATCA_CONSENTS": "FATCA details and individual checkbox consents",
        "SIGN": "Draw and submit digital signature and create user",
        "COMPLETED": "Completed onboarding"
    }
    
    return {
        "onboarding_id": onboarding_id,
        "username": progress.username,
        "email": progress.email,
        "current_step": progress.current_step,
        "step_description": steps_definition.get(progress.current_step, "Unknown"),
        "status": progress.status,
        "risk_classification": progress.risk_classification,
        "email_verified": progress.email_verified,
        "phone_verified": progress.phone_verified,
        "biometric_consent_given": progress.biometric_consent_given,
        "consents_accepted": progress.consents_accepted,
        "screening_passed": progress.screening_passed,
        "screening_list_version": progress.screening_list_version
    }


# --- THE REST OF BASIC ROUTERS ---

@router.get("/me", response_model=CurrentUserResponse)
def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Returns the authenticated party and the accounts they may access (BE-009)."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    user_repo = SQLAlchemyUserRepository(db)
    user = user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    accounts = user_repo.list_account_access(user_id)
    primary_account_id = accounts[0]["account_id"] if accounts else None
    return CurrentUserResponse(
        user_id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        account_id=primary_account_id,
        accounts=[AccountAccessInfo(**row) for row in accounts],
    )


@router.post("/login")
async def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user_repo = SQLAlchemyUserRepository(db)
    session_cache = get_session_cache()
    notifier = get_notification_service()
    
    usecase = AuthUseCase(user_repo, session_cache, notifier)
    
    # Extract nested device fingerprint details if present
    fingerprint_data = req.device_fingerprint or {}
    
    # Extract fallback values from HTTP request headers and client ip
    user_agent_header = request.headers.get("user-agent", "Unknown")
    client_ip = request.client.host if request.client else "127.0.0.1"
    
    device_id = fingerprint_data.get("device_id") or req.device_id
    if not device_id:
        # Stable fallback device_id per user/agent to prevent unnecessary alerts
        device_id = "dev-" + hashlib.md5(f"{req.username}:{user_agent_header}".encode()).hexdigest()[:12]
        
    os_name = fingerprint_data.get("os_name") or req.os_name or "WebBrowser"
    os_version = fingerprint_data.get("os_version") or req.os_version or "1.0"
    ip_address = fingerprint_data.get("ip_address") or req.ip_address or client_ip
    user_agent = fingerprint_data.get("user_agent") or req.user_agent or user_agent_header
    
    device = DeviceFingerprint(
        device_id=device_id,
        os_name=os_name,
        os_version=os_version,
        ip_address=ip_address,
        user_agent=user_agent,
        is_trusted=True  # For sandbox simplicity, assume initially trusted or verify
    )
    
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
