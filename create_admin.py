#!/usr/bin/env python3
"""
Utility script to create the first admin user.
Run this script to create an admin account for the selfie kiosk system.
"""

import sys
import os
from getpass import getpass

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.db.database import SessionLocal
from app.db import schema
from app.core.auth import get_password_hash

def create_admin():
    """Create a new admin user interactively."""
    print("=== Selfie Kiosk Admin Creation ===")
    
    # Get admin details
    email = input("Enter admin email: ").strip()
    if not email:
        print("Email is required!")
        return
    
    password = getpass("Enter admin password: ")
    if not password:
        print("Password is required!")
        return
    
    confirm_password = getpass("Confirm admin password: ")
    if password != confirm_password:
        print("Passwords do not match!")
        return
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Check if admin already exists
        existing_admin = db.query(schema.Admin).filter(schema.Admin.email == email).first()
        if existing_admin:
            print(f"Admin with email '{email}' already exists!")
            return
        
        # Create new admin
        hashed_password = get_password_hash(password)
        new_admin = schema.Admin(
            email=email,
            hashed_password=hashed_password,
            is_active=True
        )
        
        db.add(new_admin)
        db.commit()
        db.refresh(new_admin)
        
        print(f"✅ Admin user created successfully!")
        print(f"Email: {email}")
        print(f"ID: {new_admin.id}")
        print(f"Created at: {new_admin.created_at}")
        
    except Exception as e:
        print(f"❌ Error creating admin: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_admin()
