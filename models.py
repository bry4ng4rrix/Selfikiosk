from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid
import re

class StatusEnum(str, Enum):
    """Statuts possibles"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SYNCED = "synced"

class ModeEnum(str, Enum):
    """Modes de fonctionnement"""
    ONLINE = "online"
    OFFLINE = "offline"

# ===== MODÈLES DE BASE =====

class BaseResponse(BaseModel):
    """Réponse API de base"""
    success: bool = True
    message: str = "OK"
    timestamp: datetime = Field(default_factory=datetime.now)

class ErrorResponse(BaseResponse):
    """Réponse d'erreur"""
    success: bool = False
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

# ===== CAPTURES =====

class CaptureCreate(BaseModel):
    """Modèle pour créer une capture"""
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    background_id: Optional[str] = None
    photo_base64: str = Field(..., description="Photo encodée en base64")
    
    @validator('phone')
    def validate_phone(cls, v):
        if v and not re.match(r'^\+?[1-9]\d{1,14}$', v.replace(' ', '').replace('-', '')):
            raise ValueError('Format de téléphone invalide')
        return v

class CaptureResponse(BaseResponse):
    """Réponse après création de capture"""
    id: str
    download_url: Optional[str] = None
    qr_code_url: Optional[str] = None
    mode: ModeEnum

class CaptureStatus(BaseModel):
    """Statut d'une capture"""
    id: str
    status: StatusEnum
    created_at: datetime
    synced_at: Optional[datetime] = None
    download_url: Optional[str] = None
    attempts: int = 0
    last_error: Optional[str] = None

class CaptureList(BaseResponse):
    """Liste des captures"""
    captures: List[CaptureStatus]
    total: int
    page: int = 1
    per_page: int = 50

# ===== SMS =====

class SMSRequest(BaseModel):
    """Demande d'envoi SMS"""
    phone: str = Field(..., description="Numéro de téléphone")
    capture_id: str = Field(..., description="ID de la capture")
    
    @validator('phone')
    def validate_phone(cls, v):
        # Nettoyage du numéro
        cleaned = re.sub(r'[^\d+]', '', v)
        if not re.match(r'^\+?[1-9]\d{8,14}$', cleaned):
            raise ValueError('Format de téléphone invalide')
        return cleaned

class SMSResponse(BaseResponse):
    """Réponse envoi SMS"""
    sms_id: Optional[str] = None
    phone: str
    sent_at: datetime = Field(default_factory=datetime.now)

# ===== BACKGROUNDS =====

class BackgroundBase(BaseModel):
    """Modèle de base pour les fonds"""
    name: str = Field(..., max_length=100)
    is_active: bool = True
    display_order: int = 0

class BackgroundCreate(BackgroundBase):
    """Création d'un fond"""
    pass

class BackgroundUpdate(BaseModel):
    """Mise à jour d'un fond"""
    name: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    display_order: Optional[int] = None

class Background(BackgroundBase):
    """Modèle complet d'un fond"""
    id: str
    file_path: str
    file_url: str
    file_size: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class BackgroundList(BaseResponse):
    """Liste des fonds"""
    backgrounds: List[Background]
    total: int

# ===== CONFIGURATION =====

class ConfigUpdate(BaseModel):
    """Mise à jour de la configuration"""
    
    # Messages
    welcome_message: Optional[str] = None
    success_message: Optional[str] = None
    countdown_seconds: Optional[int] = Field(None, ge=1, le=10)
    
    # OVH SMS
    ovh_application_key: Optional[str] = None
    ovh_application_secret: Optional[str] = None
    ovh_consumer_key: Optional[str] = None
    sms_service_name: Optional[str] = None
    sms_sender: Optional[str] = Field(None, max_length=11)
    
    # OVH Storage
    swift_auth_url: Optional[str] = None
    swift_username: Optional[str] = None
    swift_password: Optional[str] = None
    swift_tenant_name: Optional[str] = None
    swift_container: Optional[str] = None
    
    # Google Reviews
    google_review_url: Optional[str] = None
    google_review_enabled: Optional[bool] = None
    
    # Nettoyage
    auto_delete_days: Optional[int] = Field(None, ge=1, le=365)
    auto_delete_enabled: Optional[bool] = None

class ConfigResponse(BaseResponse):
    """Configuration complète (sans secrets)"""
    welcome_message: str
    success_message: str
    countdown_seconds: int
    sms_sender: str
    google_review_enabled: bool
    google_review_url: Optional[str]
    auto_delete_days: int
    auto_delete_enabled: bool
    ovh_configured: bool
    storage_configured: bool

# ===== ADMIN =====

class LoginRequest(BaseModel):
    """Demande de connexion"""
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)

class LoginResponse(BaseResponse):
    """Réponse de connexion"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class UserInfo(BaseModel):
    """Informations utilisateur"""
    username: str
    is_admin: bool = True
    last_login: Optional[datetime] = None

# ===== STATISTIQUES =====

class Statistics(BaseResponse):
    """Statistiques générales"""
    total_captures: int
    today_captures: int
    week_captures: int
    month_captures: int
    successful_sms: int
    pending_sync: int
    storage_used_mb: float
    uptime_hours: float

class HealthStatus(BaseModel):
    """Statut de santé du système"""
    status: str  # "healthy", "degraded", "unhealthy"
    database: bool
    redis: bool
    storage: bool
    ovh_api: bool
    disk_space_gb: float
    memory_usage_percent: float
    uptime_seconds: int

# ===== EXPORT =====

class ExportRequest(BaseModel):
    """Demande d'export"""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    include_phone: bool = False  # Masquer les téléphones par défaut
    format: str = Field(default="excel", pattern="^(excel|csv)$")

class ExportResponse(BaseResponse):
    """Réponse d'export"""
    file_url: str
    filename: str
    expires_at: datetime
    total_records: int

# ===== TESTS DE CONNECTIVITÉ =====

class TestOVHRequest(BaseModel):
    """Test de connectivité OVH"""
    test_sms: bool = True
    test_storage: bool = True
    phone_number: Optional[str] = None  # Pour test SMS

class TestResult(BaseModel):
    """Résultat d'un test"""
    success: bool
    message: str
    response_time_ms: Optional[float] = None
    details: Optional[Dict[str, Any]] = None

class TestOVHResponse(BaseResponse):
    """Résultat des tests OVH"""
    sms_test: Optional[TestResult] = None
    storage_test: Optional[TestResult] = None

# ===== UTILITAIRES =====

def generate_id() -> str:
    """Génère un ID unique"""
    return str(uuid.uuid4())

def generate_download_token() -> str:
    """Génère un token de téléchargement"""
    return str(uuid.uuid4()).replace('-', '')[:16]

class PaginationParams(BaseModel):
    """Paramètres de pagination"""
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=50, ge=1, le=100)
    
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page