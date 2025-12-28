-- =============================================================================
-- PostgreSQL Test Database Initialization
-- =============================================================================

-- Create sample tables for testing
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    country VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(100),
    price DECIMAL(10, 2) NOT NULL,
    stock INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    total_amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL
);

-- Insert sample data
INSERT INTO customers (name, email, country) VALUES
    ('John Doe', 'john@example.com', 'USA'),
    ('Jane Smith', 'jane@example.com', 'Canada'),
    ('Carlos García', 'carlos@example.com', 'Mexico'),
    ('Marie Dupont', 'marie@example.com', 'France')
ON CONFLICT (email) DO NOTHING;

INSERT INTO products (name, category, price, stock) VALUES
    ('Laptop Pro', 'Electronics', 1299.99, 50),
    ('Wireless Mouse', 'Electronics', 29.99, 200),
    ('Office Chair', 'Furniture', 249.99, 30),
    ('Desk Lamp', 'Furniture', 49.99, 100),
    ('Python Book', 'Books', 39.99, 75)
ON CONFLICT DO NOTHING;
