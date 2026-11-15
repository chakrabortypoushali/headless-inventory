# Inventory API
Headless, multi-tenant inventory REST API.
FastAPI + PostgreSQL (Row-Level Security) + JWT.
## Setup (Windows, PowerShell)
1. Install uv, Git and PostgreSQL 18.
2. `uv sync`
3. Create the databases `inventory` and `inventory_test` and the role `inventory_app`.
4. Apply the schema:
 `psql -U postgres -d inventory -f db/schema.sql` (and the same for inventory_test)
5. Copy `.env.example` to `.env` and fill in real secrets.
6. Run: `uv run fastapi dev app/main.py` then open http://127.0.0.1:8000/docs
7. Test: `uv run pytest`
## Security notes
- The API connects as a limited role, never as the postgres superuser.
- Every tenant table uses Row-Level Security keyed on `app.tenant_id`.
  
