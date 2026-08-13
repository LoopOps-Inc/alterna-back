class DomainException(Exception):
    """Base domain exception"""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

class InsufficientFundsException(DomainException):
    """Raised when account lacks purchasing power or asset balance BE-041"""
    pass

class NonSuitableInstrumentException(DomainException):
    """Raised when instrument is not suitable for customer's profile BE-042"""
    def __init__(self, message: str, disclosure_id: str, version: str):
        super().__init__(message)
        self.disclosure_id = disclosure_id
        self.version = version

class LimitExceededException(DomainException):
    """Raised when concentration or withdraw limits are exceeded BE-043, RF-073"""
    pass

class AMLRuleViolationException(DomainException):
    """Raised when a PLD/FT rule is violated"""
    pass

class DeviceNotTrustedException(DomainException):
    """Raised when the client login originates from an untrusted fingerprint BE-006"""
    pass

class SecurityRevocationException(DomainException):
    """Raised when token reuse or security breach triggers family invalidation BE-005"""
    pass

class PreventiveLockoutException(DomainException):
    """Raised when withdrawal cooldown is active due to profile/credentials changes BE-010"""
    pass

class HardLockoutException(DomainException):
    """Raised when accounts are locked due to repeated brute-force attempts BE-008"""
    pass

class InvalidCredentialsException(DomainException):
    """Raised when username or password authentication fails with decoy security timing BE-001"""
    pass

class ReconciliationMismatchException(DomainException):
    """Raised when custodian daily reconciliation detects differences BE-021"""
    pass

class ResourceNotFoundException(DomainException):
    """Raised when resource does not exist (returns 404 to avoid enumeration BE-009)"""
    pass

class StepUpRequiredException(DomainException):
    """Raised when step up authentication/token is missing or invalid BE-047"""
    pass
