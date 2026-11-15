
# tests/conftest.py
# Point the app at the TEST database before it is imported.

import os
import uuid

import pytest

from dotenv import load_dotenv


# Load environment variables from the .env file.
load_dotenv()

# Configure the test database before importing the application.
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

# Tests create many companies, so increase the registration limit.
os.environ["REGISTER_MAX_PER_HOUR"] = "1000"


from fastapi.testclient import TestClient

from app.main import app


PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session")
def client():
    """Create a test client for the entire test session."""

    with TestClient(app) as test_client:
        # Runs the application lifespan (opens the database pool).
        yield test_client


class Company:
    """A freshly registered company with its owner already logged in."""

    def __init__(self, client):
        self.client = client

        self.slug = "t" + uuid.uuid4().hex[:10]
        self.email = f"owner@{self.slug}.example.com"

        # Register a new company and its first owner.
        response = client.post(
            "/auth/register",
            json={
                "company_name": f"Company {self.slug}",
                "slug": self.slug,
                "owner_email": self.email,
                "owner_password": PASSWORD,
            },
        )

        assert response.status_code == 201, response.text

        self.tenant_id = response.json()["id"]

        # Log in automatically as the company owner.
        self.headers = self.login(self.email)

    def login(self, email, password=PASSWORD):
        """Log in a company user and return authentication headers."""

        response = self.client.post(
            "/auth/login",
            json={
                "tenant": self.slug,
                "email": email,
                "password": password,
            },
        )

        assert response.status_code == 200, response.text

        return {
            "Authorization": f"Bearer {response.json()['access_token']}"
        }

    def add_user(self, role):
        """Create a new company user and return their login headers."""

        email = (
            f"{role}-{uuid.uuid4().hex[:6]}@"
            f"{self.slug}.example.com"
        )

        response = self.client.post(
            "/users",
            headers=self.headers,
            json={
                "email": email,
                "password": PASSWORD,
                "role": role,
            },
        )

        assert response.status_code == 201, response.text

        return self.login(email)

    def add_product(self, sku="SKU-1", price="9.99", **extra):
        """Create a product and return its API response."""

        body = {
            "sku": sku,
            "name": f"Product {sku}",
            "price": price,
            **extra,
        }

        response = self.client.post(
            "/products",
            headers=self.headers,
            json=body,
        )

        assert response.status_code == 201, response.text

        return response.json()


@pytest.fixture()
def company(client):
    """Provide a freshly registered company for a test."""

    return Company(client)


@pytest.fixture()
def two_companies(client):
    """Provide two separate companies for tenant isolation tests."""

    return Company(client), Company(client)
