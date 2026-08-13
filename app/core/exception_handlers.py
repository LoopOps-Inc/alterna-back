import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from app.domain.exceptions import (
    DomainException,
    InsufficientFundsException,
    NonSuitableInstrumentException,
    LimitExceededException,
    AMLRuleViolationException,
    DeviceNotTrustedException,
    SecurityRevocationException,
    PreventiveLockoutException,
    HardLockoutException,
    InvalidCredentialsException,
    ReconciliationMismatchException,
    ResourceNotFoundException,
    StepUpRequiredException
)

logger = logging.getLogger("altm_backend")

def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ResourceNotFoundException)
    async def resource_not_found_handler(request: Request, exc: ResourceNotFoundException):
        # Enforce BE-009: return 404 to obscure resource existence
        logger.warning(f"ResourceNotFound: {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message}
        )

    @app.exception_handler(InvalidCredentialsException)
    async def invalid_credentials_handler(request: Request, exc: InvalidCredentialsException):
        logger.info("Failed login attempt with invalid credentials.")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid username or password"}
        )

    @app.exception_handler(HardLockoutException)
    async def hard_lockout_handler(request: Request, exc: HardLockoutException):
        logger.warning("Account hard locked due to too many failed attempts.")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Account locked due to multiple failed login attempts. Contact support."}
        )

    @app.exception_handler(DeviceNotTrustedException)
    async def device_not_trusted_handler(request: Request, exc: DeviceNotTrustedException):
        logger.info("Login from untrusted device. Out of band validation initiated.")
        return JSONResponse(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            content={"detail": "New device detected. Out of band verification required.", "code": "NEW_DEVICE"}
        )

    @app.exception_handler(SecurityRevocationException)
    async def security_revocation_handler(request: Request, exc: SecurityRevocationException):
        logger.error(f"SECURITY ALERT: {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Session revoked due to security token invalidation."}
        )

    @app.exception_handler(PreventiveLockoutException)
    async def preventive_lockout_handler(request: Request, exc: PreventiveLockoutException):
        logger.warning(f"Preventive lockout triggered: {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.message}
        )

    @app.exception_handler(InsufficientFundsException)
    async def insufficient_funds_handler(request: Request, exc: InsufficientFundsException):
        logger.info(f"Transaction rejected due to insufficient funds: {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.message, "code": "INSUFFICIENT_FUNDS"}
        )

    @app.exception_handler(NonSuitableInstrumentException)
    async def non_suitable_instrument_handler(request: Request, exc: NonSuitableInstrumentException):
        logger.info(f"Suitability warning: {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": exc.message,
                "code": "SUITABILITY_WARNING",
                "disclosure_id": exc.disclosure_id,
                "disclosure_version": exc.version
            }
        )

    @app.exception_handler(StepUpRequiredException)
    async def step_up_required_handler(request: Request, exc: StepUpRequiredException):
        logger.info(f"Step up validation failed or required: {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.message, "code": "STEP_UP_REQUIRED"}
        )

    @app.exception_handler(LimitExceededException)
    async def limit_exceeded_handler(request: Request, exc: LimitExceededException):
        logger.warning(f"Limit check failed: {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.message, "code": "LIMIT_EXCEEDED"}
        )

    @app.exception_handler(AMLRuleViolationException)
    async def aml_rule_violation_handler(request: Request, exc: AMLRuleViolationException):
        logger.error(f"AML Alert Triggered: {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "Transaction under AML/compliance review.", "code": "AML_REVIEW"}
        )

    @app.exception_handler(ReconciliationMismatchException)
    async def reconciliation_mismatch_handler(request: Request, exc: ReconciliationMismatchException):
        logger.critical(f"CRITICAL SYSTEM ALARM: Daily reconciliation failed: {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "System synchronization error. Operations halted for safety."}
        )

    @app.exception_handler(DomainException)
    async def domain_exception_handler(request: Request, exc: DomainException):
        logger.error(f"Domain error occurred: {exc.message}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.message}
        )
