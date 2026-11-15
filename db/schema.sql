-- db/schema.sql (run as the postgres superuser, once per database)
-- Multi-tenant inventory schema: shared tables + tenant_id + Row-Level Security
CREATE TABLE tenants (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 name text NOT NULL,
 slug text NOT NULL UNIQUE
 CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$'),
 is_active boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE users (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 email text NOT NULL CHECK (email = lower(email)),
 password_hash text NOT NULL,
 role text NOT NULL CHECK (role IN ('owner', 'manager', 'staff')),
 is_active boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (tenant_id, email),
 UNIQUE (tenant_id, id)
);
CREATE TABLE products (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 sku text NOT NULL,
 name text NOT NULL,
 description text,
 price numeric(10, 2) NOT NULL CHECK (price >= 0),
 reorder_level integer NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
 is_active boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (tenant_id, sku),
 UNIQUE (tenant_id, id)
);
-- The stock ledger: stock on hand = SUM(change). Rows are never edited.
CREATE TABLE stock_movements (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 product_id uuid NOT NULL,
 change integer NOT NULL CHECK (change <> 0),
 reason text NOT NULL
 CHECK (reason IN ('purchase', 'sale', 'adjustment', 'return')),
 note text,
 created_by uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 -- composite foreign keys: a movement can only point at a product and a
 -- user that belong to the SAME tenant
 FOREIGN KEY (tenant_id, product_id) REFERENCES products (tenant_id, id),
 FOREIGN KEY (tenant_id, created_by) REFERENCES users (tenant_id, id)
);
CREATE INDEX idx_movements_product ON stock_movements (tenant_id, product_id);
CREATE INDEX idx_movements_created ON stock_movements (tenant_id, created_at DESC);
-- ---------------------------------------------------------------------------
-- Row-Level Security: every query is filtered by the tenant the API selected
-- ---------------------------------------------------------------------------
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_movements ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE products FORCE ROW LEVEL SECURITY;
ALTER TABLE stock_movements FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON users
 USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
 WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE POLICY tenant_isolation ON products
 USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
 WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE POLICY tenant_isolation ON stock_movements
 USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
 WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
-- ---------------------------------------------------------------------------
-- Least privilege: the API's database user gets only what it needs
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO inventory_app;
GRANT SELECT, INSERT ON tenants TO inventory_app;
GRANT SELECT, INSERT, UPDATE ON users TO inventory_app;
GRANT SELECT, INSERT, UPDATE ON products TO inventory_app;
GRANT SELECT, INSERT ON stock_movements TO inventory_app;