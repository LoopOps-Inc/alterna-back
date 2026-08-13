import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Alterna Mobile ALTM Backend"
    API_V1_STR: str = "/api/v1"
    
    # Security
    JWT_SECRET: str = "super_secure_unpredictable_development_secret_key_123!"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/altm_db"
    
    # Cache
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Custodian Pershing LLC
    PERSHING_API_URL: str = "https://api.pershing.example.com"
    PERSHING_API_KEY: str = "mock-pershing-key"
    PERSHING_TIMEOUT: int = 5  # Strict 5 seconds timeout BE-048
    
    # Withdrawal policies
    WITHDRAWAL_COOLDOWN_HOURS: int = 24  # BE-010 / RF-071
    
    # Email/SMS providers mock settings
    TWILIO_ACCOUNT_SID: Optional[str] = "ACmock"
    TWILIO_AUTH_TOKEN: Optional[str] = "mock_auth_token"
    TWILIO_FROM_NUMBER: Optional[str] = "+1234567890"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
