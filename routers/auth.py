# main.py
from fastapi import FastAPI, Depends, HTTPException, status ,APIRouter
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, EmailStr, Field
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import re
import sqlite3
from typing import Optional, Union

router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
    responses={404: {"description": "Not found"}}
)

# Configuration
SECRET_KEY = "votre-cle-secrete-tres-forte-ici"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Base de données SQLite
SQLALCHEMY_DATABASE_URL = "sqlite:///./auth.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Configuration du chiffrement des mots de passe
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Configuration JWT
security = HTTPBearer()

# Modèles SQLAlchemy
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    phone = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# Créer les tables
Base.metadata.create_all(bind=engine)

# Modèles Pydantic
class UserRegister(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, regex=r"^\+?[1-9]\d{1,14}$")
    password: str = Field(..., min_length=8)
    
    def __init__(self, **data):
        super().__init__(**data)
        if not self.email and not self.phone:
            raise ValueError("Email ou numéro de téléphone requis")
        if self.email and self.phone:
            raise ValueError("Veuillez utiliser soit l'email soit le téléphone, pas les deux")

class UserLogin(BaseModel):
    identifier: str  # email ou phone
    password: str

class UserResponse(BaseModel):
    id: int
    email: Optional[str]
    phone: Optional[str]
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

# Utilitaires
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def is_valid_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_valid_phone(phone: str) -> bool:
    pattern = r'^\+?[1-9]\d{1,14}$'
    return re.match(pattern, phone) is not None

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def get_user_by_phone(db: Session, phone: str):
    return db.query(User).filter(User.phone == phone).first()

def get_user_by_identifier(db: Session, identifier: str):
    if is_valid_email(identifier):
        return get_user_by_email(db, identifier)
    elif is_valid_phone(identifier):
        return get_user_by_phone(db, identifier)
    return None

def authenticate_user(db: Session, identifier: str, password: str):
    user = get_user_by_identifier(db, identifier)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Impossible de valider les informations d'identification",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user

# Application FastAPI
# app = FastAPI(title="Système d'authentification", version="1.0.0")

@router.post("/register", response_model=Token)
def register_user(user: UserRegister, db: Session = Depends(get_db)):
    # Vérifier si l'utilisateur existe déjà
    if user.email:
        db_user = get_user_by_email(db, user.email)
        if db_user:
            raise HTTPException(
                status_code=400,
                detail="Un utilisateur avec cet email existe déjà"
            )
    
    if user.phone:
        db_user = get_user_by_phone(db, user.phone)
        if db_user:
            raise HTTPException(
                status_code=400,
                detail="Un utilisateur avec ce numéro de téléphone existe déjà"
            )
    
    # Créer le nouvel utilisateur
    hashed_password = get_password_hash(user.password)
    db_user = User(
        email=user.email,
        phone=user.phone,
        hashed_password=hashed_password
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Créer le token d'accès
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(db_user.id)}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": db_user
    }

@router.post("/login", response_model=Token)
def login_user(user_credentials: UserLogin, db: Session = Depends(get_db)):
    user = authenticate_user(db, user_credentials.identifier, user_credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email/téléphone ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Compte utilisateur désactivé"
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

@app.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@app.get("/")
def read_root():
    return {"message": "API d'authentification FastAPI avec SQLite"}

# Route protégée d'exemple
@app.get("/protected")
async def protected_route(current_user: User = Depends(get_current_user)):
    return {
        "message": "Ceci est une route protégée",
        "user_id": current_user.id,
        "email": current_user.email,
        "phone": current_user.phone
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# requirements.txt - Dépendances à installer avec pip install -r requirements.txt
"""
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
passlib[bcrypt]==1.7.4
python-jose[cryptography]==3.3.0
python-multipart==0.0.6
email-validator==2.1.0
"""

# Instructions pour démarrer :
"""
1. Installer les dépendances :
   pip install fastapi uvicorn sqlalchemy passlib[bcrypt] python-jose[cryptography] python-multipart email-validator

2. Lancer le serveur :
   python main.py
   ou
   uvicorn main:app --reload

3. Accéder à la documentation interactive :
   http://localhost:8000/docs

4. Exemples d'utilisation :

   Inscription avec email :
   POST /register
   {
     "email": "user@example.com",
     "password": "motdepasse123"
   }

   Inscription avec téléphone :
   POST /register
   {
     "phone": "+33123456789",
     "password": "motdepasse123"
   }

   Connexion :
   POST /login
   {
     "identifier": "user@example.com",  // ou "+33123456789"
     "password": "motdepasse123"
   }

   Accès au profil (avec token) :
   GET /me
   Headers: Authorization: Bearer YOUR_TOKEN_HERE
"""