
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
import os

class Settings(BaseSettings):
    """Configuration de l'application"""
    
    # Environnement
    ENVIRONMENT: str = Field(default="development")
    
    # Base de données
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./selfie_kiosk.db")
    
    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_QUEUE_NAME: str = Field(default="selfie_sync_queue")
    
    # Sécurité
    SECRET_KEY: str = Field(default="your-secret-key-change-in-production")
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440)  # 24 heures
    
    # Admin par défaut
    ADMIN_USERNAME: str = Field(default="admin")
    ADMIN_PASSWORD: str = Field(default="changeme123!")
    
    # CORS
    ALLOWED_ORIGINS: List[str] = Field(default=["*"])
    
    # Stockage local
    UPLOAD_DIR: str = Field(default="./uploads")
    MAX_FILE_SIZE: int = Field(default=10 * 1024 * 1024)  # 10MB
    ALLOWED_EXTENSIONS: List[str] = Field(default=["jpg", "jpeg", "png"])
    
    # URL publique
    PUBLIC_BASE_URL: str = Field(default="http://localhost:8000/")
    
    # Configuration par défaut de l'application
    COUNTDOWN_SECONDS: int = Field(default=3)
    WELCOME_MESSAGE: str = Field(default="Bienvenue ! Prenez votre selfie !")
    SUCCESS_MESSAGE: str = Field(default="Photo prise avec succès !")
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FILE: str = Field(default="./logs/app.log")
    LOG_MAX_BYTES: int = Field(default=10_485_760)  # 10MB
    LOG_BACKUP_COUNT: int = Field(default=5)
    
    # OVH Configuration (optionnel)
    OVH_ENDPOINT: str = Field(default="ovh-eu")
    OVH_APPLICATION_KEY: Optional[str] = Field(default=None)
    OVH_APPLICATION_SECRET: Optional[str] = Field(default=None)
    OVH_CONSUMER_KEY: Optional[str] = Field(default=None)
    SMS_SERVICE_NAME: Optional[str] = Field(default=None)
    SMS_SENDER: str = Field(default="SelfieKiosk")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "allow"  # Autoriser les champs supplémentaires
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Créer les dossiers nécessaires
        os.makedirs(self.UPLOAD_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(self.LOG_FILE), exist_ok=True)

# Instance globale des settings - ATTENTION: ne pas créer de référence circulaire
settings = Settings()