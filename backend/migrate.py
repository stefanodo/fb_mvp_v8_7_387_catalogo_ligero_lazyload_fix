#!/usr/bin/env python3
"""
Database migration for PostgreSQL deployment
Run this before deployment to set up PostgreSQL schema
"""
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.db_config import get_db_connection, IS_PRODUCTION


def migrate_to_postgresql():
    """Initialize PostgreSQL schema on Vercel"""
    
    if not IS_PRODUCTION:
        print("Not in production mode. Skipping PostgreSQL migration.")
        return
    
    print("Initializing PostgreSQL schema for Vercel...")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Create all tables for your application
        # This is a template - replace with your actual schema
        
        # Example tables (adjust to match your SQLite schema):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS centers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS warehouses (
                id SERIAL PRIMARY KEY,
                center_id INTEGER REFERENCES centers(id),
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                code VARCHAR(100) UNIQUE,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS productions (
                id SERIAL PRIMARY KEY,
                center_id INTEGER REFERENCES centers(id),
                warehouse_id INTEGER REFERENCES warehouses(id),
                status VARCHAR(50) DEFAULT 'DRAFT',
                note TEXT,
                production_group VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Add more tables as needed based on your schema
        
        conn.commit()
        print("✓ PostgreSQL schema initialized successfully")
        
    except Exception as e:
        print(f"✗ Error during migration: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_to_postgresql()
