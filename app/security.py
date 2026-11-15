
# app/security.py
# Password hashing and JWT token management

from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.config import (
    ACCESS_TOKEN_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET,
)


# --------------------------------------------------
# Password Hashing
# --------------------------------------------------

# Recommended password hashing configuration.
# Uses Argon2id.

_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """
    Hash a plain-text password using Argon2id.

    Never store plain-text passwords in the database.
    """
    return _hasher.hash(password)


def verify_password(
    password: str,
    password_hash: str
) -> bool:
    """
    Verify a plain-text password against its stored hash.

    Returns True if the password matches, otherwise False.
    """
    return _hasher.verify(password, password_hash)


# --------------------------------------------------
# Dummy Password Hash
# --------------------------------------------------

# Used when the user does not exist.
#
# This helps ensure that an unknown user and a user
# with an incorrect password follow similar hashing
# workloads, reducing timing-based user enumeration.

DUMMY_HASH = _hasher.hash("not-a-real-password")


# --------------------------------------------------
# JWT Access Token Generation
# --------------------------------------------------

def create_access_token(user_id, tenant_id) -> str:
    """
    Generate a JWT access token.

    Token contains:
        sub = User ID
        tid = Tenant ID
        iat = Issued At
        exp = Expiration Time
    """

    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "iat": now,
        "exp": now + timedelta(
            minutes=ACCESS_TOKEN_MINUTES
        ),
    }

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )


# --------------------------------------------------
# JWT Token Validation
# --------------------------------------------------

def decode_token(token: str) -> dict | None:
    """
    Decode and validate a JWT access token.

    Returns:
        dict: Token claims if valid.
        None: If token is invalid or expired.
    """

    try:
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={
                "require": ["exp", "sub", "tid"]
            },
        )

    except jwt.PyJWTError:
        return None
