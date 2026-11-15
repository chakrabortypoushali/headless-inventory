
# app/config.py
# All application settings come from environment variables (.env file)

import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


def _require(name: str) -> str:
    """Get a required environment variable."""
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Missing setting {name}. Check your .env file."
        )

    return value


# Database configuration
DATABASE_URL = _require("DATABASE_URL")


# JWT authentication configuration
JWT_SECRET = _require("JWT_SECRET")

if len(JWT_SECRET) < 32:
    raise RuntimeError(
        "JWT_SECRET must be at least 32 characters long."
    )

JWT_ALGORITHM = "HS256"

ACCESS_TOKEN_MINUTES = int(
    os.getenv("ACCESS_TOKEN_MINUTES", "30")
)


# Application environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

IS_PRODUCTION = ENVIRONMENT == "production"


# CORS configuration
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]


# Registration configuration
ALLOW_SIGNUP = (
    os.getenv("ALLOW_SIGNUP", "true").lower() == "true"
)

REGISTER_MAX_PER_HOUR = int(
    os.getenv("REGISTER_MAX_PER_HOUR", "5")
)
