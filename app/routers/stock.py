
# app/routers/stock.py
# The stock ledger: record and list movements

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import Session, any_user
from app.schemas import MovementCreate, MovementOut


router = APIRouter(prefix="/stock", tags=["stock"])


@router.post("/movements", response_model=MovementOut, status_code=201)
def record_movement(
    data: MovementCreate,
    session: Session = Depends(any_user),
):
    """Record a stock movement and prevent negative stock levels."""

    conn = session.conn

    # Lock the product row so two simultaneous sales
    # cannot both pass the stock availability check.
    product = conn.execute(
        """
        SELECT id, is_active
        FROM products
        WHERE id = %s
        FOR UPDATE
        """,
        (data.product_id,),
    ).fetchone()

    if product is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Product not found",
        )

    if not product["is_active"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Product is deactivated",
        )

    # Calculate the current stock quantity from the stock ledger.
    current = conn.execute(
        """
        SELECT COALESCE(SUM(change), 0)::int AS qty
        FROM stock_movements
        WHERE product_id = %s
        """,
        (data.product_id,),
    ).fetchone()["qty"]

    # Prevent stock from becoming negative.
    if current + data.change < 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            (
                f"Insufficient stock: {current} on hand, "
                f"change is {data.change}"
            ),
        )

    # Insert the new stock movement.
    movement = conn.execute(
        """
        INSERT INTO stock_movements (
            tenant_id,
            product_id,
            change,
            reason,
            note,
            created_by
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING
            id,
            product_id,
            change,
            reason,
            note,
            created_by,
            created_at
        """,
        (
            session.tenant_id,
            data.product_id,
            data.change,
            data.reason,
            data.note,
            session.user["id"],
        ),
    ).fetchone()

    # Include the resulting stock quantity in the response.
    movement["quantity_after"] = current + data.change

    return movement


@router.get("/movements", response_model=list[MovementOut])
def list_movements(
    product_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(any_user),
):
    """List stock movements with optional product filtering."""

    return session.conn.execute(
        """
        SELECT
            id,
            product_id,
            change,
            reason,
            note,
            created_by,
            created_at
        FROM stock_movements
        WHERE (
            %s::uuid IS NULL
            OR product_id = %s::uuid
        )
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (
            product_id,
            product_id,
            limit,
            offset,
        ),
    ).fetchall()
