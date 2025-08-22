from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from ..models.auth import AdminLogin, AdminCreate, AdminResponse, Token
from ..db import schema
from ..core.auth import verify_password, get_password_hash, create_access_token
from .dependencies import get_db, get_current_admin

router = APIRouter()

@router.post("/admin/login", response_model=Token, tags=["Admin Auth"])
async def admin_login(admin_data: AdminLogin, db: Session = Depends(get_db)):
 
    admin = db.query(schema.Admin).filter(schema.Admin.email == admin_data.email).first()
    
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account is inactive",
        )
    
    # Verify password
    if not verify_password(admin_data.password, admin.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    # Update last login
    admin.last_login = datetime.utcnow()
    db.commit()
    
    # Create access token
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": admin.email}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post("/admin/create", response_model=AdminResponse, tags=["Admin Auth"])
async def create_admin(admin_data: AdminCreate, db: Session = Depends(get_db)):
    """
    Create a new admin account.
    Note: In production, this should be protected or only available during initial setup.
    """
    # Check if admin with this email already exists
    existing_admin = db.query(schema.Admin).filter(schema.Admin.email == admin_data.email).first()
    if existing_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin with this email already exists",
        )
    
    # Create new admin
    hashed_password = get_password_hash(admin_data.password)
    new_admin = schema.Admin(
        email=admin_data.email,
        hashed_password=hashed_password,
        is_active=True
    )
    
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    
    return new_admin
