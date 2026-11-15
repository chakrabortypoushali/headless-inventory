
# app/schemas.py
# What the API accepts (In) and returns (Out)

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    model_validator,
)


# ==================================================
# COMMON TYPES AND VALIDATION PATTERNS
# ==================================================

Role = Literal["owner", "manager", "staff"]

Reason = Literal[
    "purchase",
    "sale",
    "adjustment",
    "return",
]

SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$"

SKU_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$"


# ==================================================
# BASE INPUT MODEL
# ==================================================

class StrictIn(BaseModel):
    """
    Base class for all input models.

    extra='forbid':
        Unknown fields are rejected with HTTP 422.

    This helps prevent mass assignment.

    Example:
        A client cannot send tenant_id or other
        unauthorized fields unless explicitly defined.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


# ==================================================
# AUTHENTICATION AND TENANT REGISTRATION
# ==================================================

class TenantRegister(StrictIn):
    company_name: str = Field(
        min_length=2,
        max_length=100,
    )

    slug: str = Field(
        pattern=SLUG_PATTERN,
        description="Company ID used to log in",
    )

    owner_email: EmailStr

    owner_password: str = Field(
        min_length=12,
        max_length=128,
    )


class RegisterOut(BaseModel):
    id: UUID
    name: str
    slug: str


class LoginIn(StrictIn):
    tenant: str = Field(
        min_length=1,
        max_length=40,
    )

    email: EmailStr

    password: str = Field(
        min_length=1,
        max_length=128,
    )


class TokenOut(BaseModel):
    access_token: str

    token_type: str = "bearer"

    expires_in: int  # Seconds


# ==================================================
# USER MANAGEMENT
# ==================================================

class UserCreate(StrictIn):
    email: EmailStr

    password: str = Field(
        min_length=12,
        max_length=128,
    )

    role: Role = "staff"


class UserUpdate(StrictIn):
    role: Role | None = None

    is_active: bool | None = None


class UserOut(BaseModel):
    id: UUID
    email: str
    role: Role
    is_active: bool
    created_at: datetime


# ==================================================
# PRODUCT MANAGEMENT
# ==================================================

class ProductCreate(StrictIn):
    sku: str = Field(
        pattern=SKU_PATTERN,
    )

    name: str = Field(
        min_length=1,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
    )

    price: Decimal = Field(
        ge=0,
        max_digits=10,
        decimal_places=2,
    )

    reorder_level: int = Field(
        default=0,
        ge=0,
        le=1_000_000,
    )


class ProductUpdate(StrictIn):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
    )

    price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=10,
        decimal_places=2,
    )

    reorder_level: int | None = Field(
        default=None,
        ge=0,
        le=1_000_000,
    )


class ProductOut(BaseModel):
    id: UUID
    sku: str
    name: str
    description: str | None
    price: Decimal
    reorder_level: int
    is_active: bool
    quantity: int
    created_at: datetime


# ==================================================
# STOCK MANAGEMENT
# ==================================================

class MovementCreate(StrictIn):
    product_id: UUID

    change: int = Field(
        ge=-1_000_000,
        le=1_000_000,
    )

    reason: Reason

    note: str | None = Field(
        default=None,
        max_length=500,
    )

    @model_validator(mode="after")
    def check_sign(self):
        """
        Validate stock movement direction.

        Purchase  -> Positive stock
        Return    -> Positive stock
        Sale      -> Negative stock
        Adjustment -> Positive or negative stock
        """

        if self.change == 0:
            raise ValueError(
                "change must not be zero"
            )

        if (
            self.reason in ("purchase", "return")
            and self.change < 0
        ):
            raise ValueError(
                f"a {self.reason} must add stock "
                "(positive change)"
            )

        if (
            self.reason == "sale"
            and self.change > 0
        ):
            raise ValueError(
                "a sale must remove stock "
                "(negative change)"
            )

        return self


class MovementOut(BaseModel):
    id: int
    product_id: UUID
    change: int
    reason: Reason
    note: str | None
    created_by: UUID
    created_at: datetime
    quantity_after: int | None = None
