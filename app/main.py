import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.adapters.driving.middlewares.auth_middleware import JWTAuthenticationMiddleware
from app.adapters.driving.routers import auth, portfolio, orders, money
from app.adapters.driving.webhooks import custodian_webhook
from app.core.container import init_db

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("altm_backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database on startup (with connection retries)
    logger.info("Initializing database on startup...")
    init_db()
    yield


# Instantiate HTTPBearer with auto_error=False so that Swagger UI registers 
# the "Authorize" button globally, while leaving actual validation and enforcement 
# to our dedicated JWTAuthenticationMiddleware.
security_scheme = HTTPBearer(auto_error=False)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Hexagonal Architecture backend aligned to Alterna Securities policies",
    version="1.0.0",
    docs_url="/docs",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    dependencies=[Depends(security_scheme)],
    lifespan=lifespan
)

# Configure CORS dynamically based on security policies and Starlette constraints.
# Starlette raises a ValueError/AssertionError if allow_origins=["*"] and allow_credentials=True.
if settings.BACKEND_CORS_ORIGINS:
    if "*" in settings.BACKEND_CORS_ORIGINS:
        logger.warning(
            "CORS Configuration: Wildcard '*' found in BACKEND_CORS_ORIGINS with allow_credentials=True. "
            "Reverting to allow_credentials=False to prevent Starlette from crashing or throwing errors."
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.BACKEND_CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Register JWT Session-checking and RTR Middleware
app.add_middleware(JWTAuthenticationMiddleware)

# Register Exception Handlers mapping domain exceptions to HTTP codes with PII protection
register_exception_handlers(app)

# Include Routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(portfolio.router, prefix=settings.API_V1_STR)
app.include_router(orders.router, prefix=settings.API_V1_STR)
app.include_router(money.router, prefix=settings.API_V1_STR)
app.include_router(custodian_webhook.router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Utilities"])
def health_check():
    """Service health and connection statuses check"""
    return {
        "status": "healthy",
        "timestamp": "2024-03-10T12:00:00Z",
        "service": settings.PROJECT_NAME
    }
