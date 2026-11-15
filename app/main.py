
# app/main.py
# Assemble the application

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS, IS_PRODUCTION
from app.db import pool
from app.routers import auth, products, stock, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database connection pool lifecycle."""

    pool.open()
    yield
    pool.close()


app = FastAPI(
    title="Inventory API",
    version="1.0.0",
    description="Headless, multi-tenant inventory REST API",
    lifespan=lifespan,

    # Hide interactive documentation and schema in production.
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)


# Configure CORS only for the websites listed in CORS_ORIGINS.
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add security-related HTTP response headers."""

    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"

    if IS_PRODUCTION:
        # A pure JSON API needs no scripts, frames, or styles.
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )

        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000"
        )

    return response


# Register application routers.
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(products.router)
app.include_router(stock.router)


# Health check endpoint.
@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}
