from fastapi import Security, HTTPException, status, Depends
from fastapi.security import APIKeyHeader, HTTPBearer
from sqlalchemy.orm import Session
from ..core.config import settings
from ..core.auth import verify_token
from ..db import schema
from ..db.database import SessionLocal

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
security = HTTPBearer()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_api_key(api_key: str = Security(api_key_header)):
    if api_key == settings.ADMIN_API_KEY:
        return api_key
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )

async def get_current_admin(token: str = Depends(security), db: Session = Depends(get_db)):
    """Get current authenticated admin from JWT token."""
    email = verify_token(token.credentials)
    admin = db.query(schema.Admin).filter(schema.Admin.email == email).first()
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin not found",
        )
    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account is inactive",
        )
    return admin
