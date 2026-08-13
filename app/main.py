import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.adapters.driving.middlewares.auth_middleware import JWTAuthenticationMiddleware
from app.adapters.driving.routers import auth, portfolio, orders, money
from app.adapters.driving.webhooks import custodian_webhook

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("altm_backend")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Hexagonal Architecture backend aligned to Alterna Securities policies",
    version="1.0.0",
    docs_url="/docs",
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Allow CORS for mobile app (PWA)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
