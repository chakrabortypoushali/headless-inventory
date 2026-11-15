
# app/routers/auth.py
# Sign up a company and log in

import psycopg

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import (
    ACCESS_TOKEN_MINUTES,
    ALLOW_SIGNUP,
    REGISTER_MAX_PER_HOUR,
)
from app.db import set_tenant
from app.deps import get_conn
from app.ratelimit import RateLimiter
from app.schemas import LoginIn, RegisterOut, TenantRegister, TokenOut
from app.security import (
    DUMMY_HASH,
    create_access_token,
    hash_password,
    verify_password,
)


router = APIRouter(prefix="/auth", tags=["auth"])

login_limiter = RateLimiter(
    max_events=5,
    window_seconds=15 * 60,
)

register_limiter = RateLimiter(
    max_events=REGISTER_MAX_PER_HOUR,
    window_seconds=3600,
)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=RegisterOut, status_code=201)
def register(
    data: TenantRegister,
    request: Request,
    conn=Depends(get_conn),
):
    """Create a new company (tenant) and its first user, the owner."""

    if not ALLOW_SIGNUP:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Sign-up is disabled",
        )

    ip = client_ip(request)

    if register_limiter.is_blocked(ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many sign-ups",
        )

    register_limiter.record(ip)

    password_hash = hash_password(data.owner_password)

    try:
        tenant = conn.execute(
            """
            INSERT INTO tenants (name, slug)
            VALUES (%s, %s)
            RETURNING id, name, slug
            """,
            (data.company_name, data.slug),
        ).fetchone()

        set_tenant(conn, tenant["id"])

        # Create the first user as the company owner.
        conn.execute(
            """
            INSERT INTO users (tenant_id, email, password_hash, role)
            VALUES (%s, %s, %s, 'owner')
            """,
            (
                tenant["id"],
                data.owner_email.lower(),
                password_hash,
            ),
        )

    except psycopg.errors.UniqueViolation:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That company ID is taken",
        )

    return tenant


@router.post("/login", response_model=TokenOut)
def login(
    data: LoginIn,
    request: Request,
    conn=Depends(get_conn),
):
    """Exchange company ID + email + password for a short-lived access token."""

    slug = data.tenant.strip().lower()
    email = data.email.lower()

    key = f"{client_ip(request)}|{slug}|{email}"

    if login_limiter.is_blocked(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed attempts. Try again in 15 minutes.",
            headers={"Retry-After": "900"},
        )

    tenant = conn.execute(
        "SELECT id, is_active FROM tenants WHERE slug = %s",
        (slug,),
    ).fetchone()

    user = None

    if tenant and tenant["is_active"]:
        set_tenant(conn, tenant["id"])

        user = conn.execute(
            """
            SELECT id, password_hash, is_active
            FROM users
            WHERE email = %s
            """,
            (email,),
        ).fetchone()

    # Always run a hash check, even for unknown users.
    # This provides approximately constant-time behavior.
    stored_hash = user["password_hash"] if user else DUMMY_HASH

    password_ok = verify_password(
        data.password,
        stored_hash,
    )

    if not (user and password_ok and user["is_active"]):
        login_limiter.record(key)

        # Use one generic message to avoid revealing which detail was wrong.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid company ID, email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    login_limiter.reset(key)

    token = create_access_token(
        user["id"],
        tenant["id"],
    )

    return TokenOut(
        access_token=token,
        expires_in=ACCESS_TOKEN_MINUTES * 60,
    )
