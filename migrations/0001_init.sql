-- Inicialização das tabelas principais
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    email VARCHAR NOT NULL UNIQUE,
    role VARCHAR NOT NULL DEFAULT 'user',
    password VARCHAR NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW())
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS clients (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    document VARCHAR NULL,
    address TEXT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW())
);

CREATE INDEX IF NOT EXISTS idx_clients_document ON clients(document);

CREATE TABLE IF NOT EXISTS assets (
    id VARCHAR PRIMARY KEY,
    client_id VARCHAR NOT NULL REFERENCES clients(id),
    name VARCHAR NOT NULL,
    type VARCHAR NULL,
    location VARCHAR NULL,
    status VARCHAR NULL DEFAULT 'operating',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW())
);

CREATE INDEX IF NOT EXISTS idx_assets_client ON assets(client_id);

CREATE TABLE IF NOT EXISTS work_orders (
    id VARCHAR PRIMARY KEY,
    client_id VARCHAR NOT NULL REFERENCES clients(id),
    asset_id VARCHAR NULL REFERENCES assets(id),
    title VARCHAR NOT NULL,
    description TEXT NULL,
    status VARCHAR NOT NULL DEFAULT 'open',
    opened_at TIMESTAMP NOT NULL DEFAULT (NOW()),
    closed_at TIMESTAMP NULL,
    created_by VARCHAR NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW())
);

CREATE INDEX IF NOT EXISTS idx_work_orders_client ON work_orders(client_id);
CREATE INDEX IF NOT EXISTS idx_work_orders_status ON work_orders(status);
