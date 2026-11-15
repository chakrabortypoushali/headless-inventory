
# app/routers/users.py
# Team management (owner only, except /users/me)

from uuid import UUID

import psycopg

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import Session, any_user, owners
from app.schemas import UserCreate, UserOut, UserUpdate
from app.security import hash_password


router = APIRouter(prefix="/users", tags=["users"])


# Fixed path BEFORE the dynamic /{user_id} path.
# See FastAPI guide, section 5.2.


@router.get("/me", response_model=UserOut)
def read_me(session: Session = Depends(any_user)):
    """Get the currently authenticated user's details."""

    return session.user


@router.get("", response_model=list[UserOut])
def list_users(session: Session = Depends(owners)):
    """List all users belonging to the current company."""

    return session.conn.execute(
        """
        SELECT id, email, role, is_active, created_at
        FROM users
        ORDER BY created_at
        """
    ).fetchall()


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    data: UserCreate,
    session: Session = Depends(owners),
):
    """Create a new team member (owner only)."""

    try:
        return session.conn.execute(
            """
            INSERT INTO users (
                tenant_id,
                email,
                password_hash,
                role
            )
            VALUES (%s, %s, %s, %s)
            RETURNING id, email, role, is_active, created_at
            """,
            (
                session.tenant_id,
                data.email.lower(),
                hash_password(data.password),
                data.role,
            ),
        ).fetchone()

    except psycopg.errors.UniqueViolation:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Email already in use",
        )


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: UUID,
    data: UserUpdate,
    session: Session = Depends(owners),
):
    """Update a team member's role or active status (owner only)."""

    if session.user["id"] == user_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "You cannot change your own role or deactivate yourself",
        )

    changes = data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Nothing to update",
        )

    row = session.conn.execute(
        """
        UPDATE users
        SET
            role = COALESCE(%s, role),
            is_active = COALESCE(%s, is_active)
        WHERE id = %s
        RETURNING id, email, role, is_active, created_at
        """,
        (
            changes.get("role"),
            changes.get("is_active"),
            user_id,
        ),
    ).fetchone()

    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "User not found",
        )

    return row
