
# app/db.py
# Connection pool and tenant context helper

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import DATABASE_URL


# --------------------------------------------------
# PostgreSQL Connection Pool
# --------------------------------------------------

# open=False:
# The pool will be opened and closed by the FastAPI
# application lifespan (see main.py).

pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=10,
    kwargs={
        "row_factory": dict_row
    },
    open=False,
)


# --------------------------------------------------
# Tenant Context Helper
# --------------------------------------------------

def set_tenant(
    conn: psycopg.Connection,
    tenant_id
) -> None:
    """
    Tell PostgreSQL which tenant this transaction belongs to.

    The third argument 'true' makes the setting LOCAL
    to the current transaction.

    It automatically disappears after COMMIT or ROLLBACK,
    preventing tenant context from leaking into the next
    request that reuses this pooled connection.
    """

    conn.execute(
        "SELECT set_config('app.tenant_id', %s, true)",
        (str(tenant_id),)
    )
