
# app/deps.py
# The "bouncer": authentication, tenant context, roles

from collections.abc import Iterator
from dataclasses import dataclass

import psycopg

from fastapi import Depends, HTTPException, status

from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from app.db import pool, set_tenant
from app.security import decode_token


# ==================================================
# HTTP BEARER AUTHENTICATION
# ==================================================

# auto_error=False:
# We handle missing or invalid credentials ourselves.
# Also enables the Authorize button in Swagger UI (/docs).

bearer_scheme = HTTPBearer(auto_error=False)


# ==================================================
# UNAUTHORIZED RESPONSE
# ==================================================

def unauthorized() -> HTTPException:
    """
    Return HTTP 401 Unauthorized.

    Used when authentication credentials are missing,
    invalid, expired, or associated with an inactive user.
    """

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ==================================================
# DATABASE CONNECTION
# ==================================================

def get_conn() -> Iterator[psycopg.Connection]:
    """
    Provide a plain database connection.

    No tenant is selected.

    Used only for operations such as:
        - Tenant registration
        - User login
    """

    with pool.connection() as conn:
        yield conn


# ==================================================
# AUTHENTICATED SESSION
# ==================================================

@dataclass
class Session:
    """
    Represents an authenticated user's database session.

    conn:
        Database connection already configured for
        the authenticated tenant.

    user:
        Fresh user information fetched from PostgreSQL,
        not copied from JWT claims.
    """

    conn: psycopg.Connection

    user: dict

    @property
    def tenant_id(self):
        """
        Return the authenticated user's tenant ID.
        """

        return self.user["tenant_id"]


# ==================================================
# TENANT-AWARE AUTHENTICATION
# ==================================================

def tenant_session(
    creds: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> Iterator[Session]:
    """
    Authenticate the request and establish tenant context.

    Steps:
        1. Check whether a Bearer token exists.
        2. Decode and validate the JWT.
        3. Set PostgreSQL tenant context.
        4. Fetch the user from the database.
        5. Verify user and tenant are active.
        6. Yield an authenticated Session.
    """

    # Step 1: Check credentials
    if creds is None:
        raise unauthorized()

    # Step 2: Decode JWT
    claims = decode_token(creds.credentials)

    if claims is None:
        raise unauthorized()

    # Step 3: Borrow database connection
    with pool.connection() as conn:

        try:
            # Set tenant context for this transaction
            set_tenant(conn, claims["tid"])

            # Step 4: Fetch fresh user information
            row = conn.execute(
                """
                SELECT
                    u.id,
                    u.tenant_id,
                    u.email,
                    u.role,
                    u.is_active,
                    u.created_at,
                    t.is_active AS tenant_active

                FROM users u

                JOIN tenants t
                    ON t.id = u.tenant_id

                WHERE u.id = %s
                """,
                (claims["sub"],),
            ).fetchone()

        except psycopg.errors.DataError:
            # Invalid UUID or other malformed database value
            raise unauthorized()

        # Step 5: Check user and tenant status
        if (
            row is None
            or not row["is_active"]
            or not row["tenant_active"]
        ):
            raise unauthorized()

        # Step 6: Provide authenticated session
        yield Session(
            conn=conn,
            user=row,
        )


# ==================================================
# ROLE-BASED ACCESS CONTROL (RBAC)
# ==================================================

def require_role(*allowed: str):
    """
    Build a FastAPI dependency that allows
    only the specified roles.

    Example:
        require_role("owner", "manager")
    """

    def checker(
        session: Session = Depends(tenant_session),
    ) -> Session:

        if session.user["role"] not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

        return session

    return checker


# ==================================================
# COMMON ROLE DEPENDENCIES
# ==================================================

# All authenticated users
any_user = require_role(
    "owner",
    "manager",
    "staff",
)

# Owners and managers
managers = require_role(
    "owner",
    "manager",
)

# Only owners
owners = require_role(
    "owner",
)
