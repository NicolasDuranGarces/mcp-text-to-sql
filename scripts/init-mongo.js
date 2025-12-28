// =============================================================================
// MongoDB Test Database Initialization
// =============================================================================

// Switch to test database
db = db.getSiblingDB('mcp_test');

// Create collections and insert sample data
db.createCollection('customers');
db.createCollection('products');
db.createCollection('orders');
db.createCollection('logs');

// Insert sample customers
db.customers.insertMany([
    {
        name: 'John Doe',
        email: 'john@example.com',
        country: 'USA',
        tags: ['premium', 'active'],
        created_at: new Date()
    },
    {
        name: 'Jane Smith',
        email: 'jane@example.com',
        country: 'Canada',
        tags: ['new'],
        created_at: new Date()
    },
    {
        name: 'Carlos García',
        email: 'carlos@example.com',
        country: 'Mexico',
        tags: ['premium'],
        created_at: new Date()
    }
]);

// Insert sample products
db.products.insertMany([
    {
        name: 'Laptop Pro',
        category: 'Electronics',
        price: 1299.99,
        stock: 50,
        attributes: { brand: 'TechCorp', warranty: '2 years' },
        created_at: new Date()
    },
    {
        name: 'Wireless Mouse',
        category: 'Electronics',
        price: 29.99,
        stock: 200,
        attributes: { brand: 'TechCorp', color: 'black' },
        created_at: new Date()
    },
    {
        name: 'Python Book',
        category: 'Books',
        price: 39.99,
        stock: 75,
        attributes: { author: 'Expert Author', pages: 450 },
        created_at: new Date()
    }
]);

// Insert sample logs
db.logs.insertMany([
    {
        level: 'INFO',
        message: 'Application started',
        timestamp: new Date(),
        metadata: { version: '1.0.0' }
    },
    {
        level: 'ERROR',
        message: 'Connection timeout',
        timestamp: new Date(),
        metadata: { service: 'database', retry_count: 3 }
    },
    {
        level: 'WARNING',
        message: 'High memory usage',
        timestamp: new Date(),
        metadata: { memory_percent: 85 }
    }
]);

// Create indexes
db.customers.createIndex({ email: 1 }, { unique: true });
db.products.createIndex({ category: 1 });
db.logs.createIndex({ timestamp: -1 });
db.logs.createIndex({ level: 1 });

print('MongoDB test database initialized successfully');
