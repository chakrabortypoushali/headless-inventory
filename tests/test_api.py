
# tests/test_api.py
# The security promises, written as executable tests

import psycopg
import pytest

from app.db import pool, set_tenant


# ---------- Authentication ----------

def test_register_and_login(company):
    """Verify that a registered company owner can access their profile."""

    me = company.client.get(
        "/users/me",
        headers=company.headers,
    )

    assert me.status_code == 200
    assert me.json()["role"] == "owner"


def test_wrong_password_and_unknown_user_look_identical(company):
    """Ensure login errors do not reveal whether a user exists."""

    c = company.client

    wrong = c.post(
        "/auth/login",
        json={
            "tenant": company.slug,
            "email": company.email,
            "password": "x" * 14,
        },
    )

    ghost = c.post(
        "/auth/login",
        json={
            "tenant": company.slug,
            "email": "nobody@example.com",
            "password": "x" * 14,
        },
    )

    assert wrong.status_code == ghost.status_code == 401
    assert wrong.json() == ghost.json()


def test_missing_and_tampered_tokens_are_rejected(company):
    """Verify that missing and modified JWT tokens are rejected."""

    c = company.client

    assert c.get("/products").status_code == 401

    token = company.headers["Authorization"]

    bad = {
        "Authorization": token[:-3]
        + ("abc" if token[-3:] != "abc" else "xyz")
    }

    assert c.get("/products", headers=bad).status_code == 401


def test_login_is_rate_limited(company):
    """Verify that repeated failed login attempts are rate-limited."""

    c = company.client

    codes = [
        c.post(
            "/auth/login",
            json={
                "tenant": company.slug,
                "email": company.email,
                "password": "wrong-pw",
            },
        ).status_code
        for _ in range(7)
    ]

    assert codes[:5] == [401] * 5
    assert codes[5] == 429


def test_deactivated_user_loses_access_immediately(company):
    """Verify that deactivated users immediately lose API access."""

    staff = company.add_user("staff")

    users = company.client.get(
        "/users",
        headers=company.headers,
    ).json()

    staff_id = next(
        u["id"] for u in users
        if u["role"] == "staff"
    )

    # Staff can initially access products.
    assert company.client.get(
        "/products",
        headers=staff,
    ).status_code == 200

    # Deactivate the staff account.
    r = company.client.patch(
        f"/users/{staff_id}",
        headers=company.headers,
        json={"is_active": False},
    )

    assert r.status_code == 200

    # The previously issued token must no longer work.
    assert company.client.get(
        "/products",
        headers=staff,
    ).status_code == 401


# ---------- Tenant Isolation ----------

def test_tenants_cannot_see_each_others_products(two_companies):
    """Verify that one tenant cannot access another tenant's products."""

    a, b = two_companies

    product = a.add_product("SECRET-A")
    c = a.client

    # Tenant B cannot list tenant A's products.
    assert c.get(
        "/products",
        headers=b.headers,
    ).json() == []

    # Tenant B cannot retrieve tenant A's product.
    assert c.get(
        f"/products/{product['id']}",
        headers=b.headers,
    ).status_code == 404

    # Tenant B cannot update tenant A's product.
    assert c.patch(
        f"/products/{product['id']}",
        headers=b.headers,
        json={"name": "hacked"},
    ).status_code == 404

    # Tenant B cannot deactivate tenant A's product.
    assert c.delete(
        f"/products/{product['id']}",
        headers=b.headers,
    ).status_code == 404

    # Tenant B cannot record stock against tenant A's product.
    r = c.post(
        "/stock/movements",
        headers=b.headers,
        json={
            "product_id": product["id"],
            "change": 5,
            "reason": "purchase",
        },
    )

    assert r.status_code == 404

    # Tenant A's product remains untouched.
    mine = c.get(
        f"/products/{product['id']}",
        headers=a.headers,
    ).json()

    assert mine["name"] == "Product SECRET-A"


def test_same_sku_allowed_in_different_tenants_but_not_twice_in_one(
    two_companies,
):
    """Verify that SKU uniqueness is enforced per tenant."""

    a, b = two_companies

    # The same SKU is allowed in separate companies.
    a.add_product("SAME")
    b.add_product("SAME")

    # Duplicate SKU within the same company is rejected.
    r = a.client.post(
        "/products",
        headers=a.headers,
        json={
            "sku": "SAME",
            "name": "dup",
            "price": "1.00",
        },
    )

    assert r.status_code == 409


def test_database_itself_enforces_isolation(two_companies):
    """Even a buggy query with no WHERE clause cannot cross tenants (RLS)."""

    a, b = two_companies

    a.add_product("RLS-A")
    b.add_product("RLS-B")

    with pool.connection() as conn:

        # No tenant selected -> zero rows.
        assert conn.execute(
            "SELECT count(*) AS n FROM products"
        ).fetchone()["n"] == 0

        # Select tenant A.
        set_tenant(conn, a.tenant_id)

        rows = conn.execute(
            "SELECT sku FROM products"
        ).fetchall()

        assert [r["sku"] for r in rows] == ["RLS-A"]

        # Writing a row for ANOTHER tenant is refused.
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                """
                INSERT INTO products (tenant_id, sku, name, price)
                VALUES (%s, 'EVIL', 'evil', 1)
                """,
                (b.tenant_id,),
            )


# ---------- Roles ----------

def test_role_permissions(company):
    """Verify that staff, managers, and owners have different permissions."""

    staff = company.add_user("staff")
    manager = company.add_user("manager")

    c = company.client

    body = {
        "sku": "R-1",
        "name": "Role test",
        "price": "5.00",
    }

    # Staff cannot create products.
    assert c.post(
        "/products",
        headers=staff,
        json=body,
    ).status_code == 403

    # Staff cannot list users.
    assert c.get(
        "/users",
        headers=staff,
    ).status_code == 403

    # Managers cannot list users.
    assert c.get(
        "/users",
        headers=manager,
    ).status_code == 403

    # Managers can create products.
    assert c.post(
        "/products",
        headers=manager,
        json=body,
    ).status_code == 201

    # Staff can view products.
    assert c.get(
        "/products",
        headers=staff,
    ).status_code == 200


# ---------- Stock Ledger ----------

def test_stock_cannot_go_negative(company):
    """Verify that stock movements cannot create negative inventory."""

    p = company.add_product("STOCK-1")

    c = company.client
    h = company.headers

    def move(change, reason):
        return c.post(
            "/stock/movements",
            headers=h,
            json={
                "product_id": p["id"],
                "change": change,
                "reason": reason,
            },
        )

    # Purchase 5 units.
    assert move(5, "purchase").json()["quantity_after"] == 5

    # Attempt to sell more than available.
    assert move(-10, "sale").status_code == 409

    # Sell 3 units successfully.
    assert move(-3, "sale").json()["quantity_after"] == 2

    # Verify the final product quantity.
    assert c.get(
        f"/products/{p['id']}",
        headers=h,
    ).json()["quantity"] == 2

    # A sale must always have a negative change.
    assert move(5, "sale").status_code == 422


def test_low_stock_filter(company):
    """Verify that the low-stock filter returns only matching products."""

    low = company.add_product(
        "LOW-1",
        reorder_level=10,
    )

    fine = company.add_product(
        "OK-1",
        reorder_level=2,
    )

    # Add stock to both products.
    for product, qty in (
        (low, 4),
        (fine, 5),
    ):
        company.client.post(
            "/stock/movements",
            headers=company.headers,
            json={
                "product_id": product["id"],
                "change": qty,
                "reason": "purchase",
            },
        )

    r = company.client.get(
        "/products?low_stock=true",
        headers=company.headers,
    )

    assert [p["sku"] for p in r.json()] == ["LOW-1"]


# ---------- Input Hardening ----------

def test_unknown_fields_are_rejected(company):
    """Verify that clients cannot submit unexpected product fields."""

    r = company.client.post(
        "/products",
        headers=company.headers,
        json={
            "sku": "X-1",
            "name": "x",
            "price": "1.00",
            "tenant_id": "anything",
        },
    )

    assert r.status_code == 422


def test_sql_injection_text_is_just_text(company):
    """Verify that SQL injection attempts are treated as ordinary text."""

    company.add_product("INJ-1")

    r = company.client.get(
        "/products",
        headers=company.headers,
        params={
            "search": "'; DROP TABLE products; --"
        },
    )

    assert r.status_code == 200
    assert r.json() == []

    # Verify that the products table still exists and contains its product.
    products = company.client.get(
        "/products",
        headers=company.headers,
    ).json()

    assert len(products) == 1


def test_weak_password_rejected(client):
    """Verify that registration rejects weak passwords."""

    r = client.post(
        "/auth/register",
        json={
            "company_name": "Weak Co",
            "slug": "weakco-test",
            "owner_email": "a@example.com",
            "owner_password": "short",
        },
    )

    assert r.status_code == 422
