
# app/routers/products.py
# The product catalogue (with live stock levels)

from uuid import UUID

import psycopg

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import sql

from app.deps import Session, any_user, managers
from app.schemas import ProductCreate, ProductOut, ProductUpdate


router = APIRouter(prefix="/products", tags=["products"])


# Stock on hand = the sum of the ledger.
# LATERAL runs the sum once per product.

PRODUCT_SELECT = """
    SELECT
        p.id,
        p.sku,
        p.name,
        p.description,
        p.price,
        p.reorder_level,
        p.is_active,
        p.created_at,
        s.qty::int AS quantity
    FROM products p
    CROSS JOIN LATERAL (
        SELECT COALESCE(SUM(m.change), 0) AS qty
        FROM stock_movements m
        WHERE m.product_id = p.id
    ) s
"""


def fetch_product(conn, product_id: UUID):
    """Fetch a product with its current stock quantity."""

    return conn.execute(
        PRODUCT_SELECT + " WHERE p.id = %s",
        (product_id,),
    ).fetchone()


@router.get("", response_model=list[ProductOut])
def list_products(
    search: str | None = Query(default=None, max_length=100),
    low_stock: bool = False,
    include_inactive: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(any_user),
):
    """List products with optional search and stock filters."""

    # Fixed SQL fragments + separate parameter values.
    conditions = []
    params = []

    if not include_inactive:
        conditions.append("p.is_active")

    if search:
        conditions.append(
            "(p.name ILIKE %s OR p.sku ILIKE %s)"
        )
        params += [
            f"%{search}%",
            f"%{search}%",
        ]

    if low_stock:
        conditions.append("s.qty <= p.reorder_level")

    where = (
        " WHERE " + " AND ".join(conditions)
        if conditions
        else ""
    )

    query = (
        PRODUCT_SELECT
        + where
        + " ORDER BY p.name, p.id LIMIT %s OFFSET %s"
    )

    return session.conn.execute(
        query,
        params + [limit, offset],
    ).fetchall()


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: UUID,
    session: Session = Depends(any_user),
):
    """Get a single product by its ID."""

    product = fetch_product(
        session.conn,
        product_id,
    )

    # Also true for other tenants' products: RLS hides them.
    if product is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Product not found",
        )

    return product


@router.post("", response_model=ProductOut, status_code=201)
def create_product(
    data: ProductCreate,
    session: Session = Depends(managers),
):
    """Create a new product (manager or owner only)."""

    try:
        row = session.conn.execute(
            """
            INSERT INTO products (
                tenant_id,
                sku,
                name,
                description,
                price,
                reorder_level
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                session.tenant_id,
                data.sku,
                data.name,
                data.description,
                data.price,
                data.reorder_level,
            ),
        ).fetchone()

    except psycopg.errors.UniqueViolation:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "SKU already exists",
        )

    return fetch_product(
        session.conn,
        row["id"],
    )


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: UUID,
    data: ProductUpdate,
    session: Session = Depends(managers),
):
    """Update an existing product (manager or owner only)."""

    changes = data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Nothing to update",
        )

    # Column names come from our own model fields, never directly
    # from the client's text. sql.Identifier quotes them safely.
    assignments = sql.SQL(", ").join(
        sql.SQL("{} = %s").format(sql.Identifier(column))
        for column in changes
    )

    query = sql.SQL(
        "UPDATE products SET {} WHERE id = %s RETURNING id"
    ).format(assignments)

    row = session.conn.execute(
        query,
        [*changes.values(), product_id],
    ).fetchone()

    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Product not found",
        )

    return fetch_product(
        session.conn,
        product_id,
    )


@router.delete("/{product_id}", status_code=204)
def deactivate_product(
    product_id: UUID,
    session: Session = Depends(managers),
):
    """Soft delete: the product stays so its stock history stays valid."""

    row = session.conn.execute(
        """
        UPDATE products
        SET is_active = false
        WHERE id = %s
        RETURNING id
        """,
        (product_id,),
    ).fetchone()

    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Product not found",
        )
