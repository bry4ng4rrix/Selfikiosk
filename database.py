from databases import Database
from sqlalchemy import (
    create_engine, MetaData, Table, Column, String, Integer, 
    Boolean, DateTime, Text, Float, Index, ForeignKey
)
from sqlalchemy.sql import func
from datetime import datetime
import aiosqlite
import logging

from config import settings
# from app_settings import app_settings
# settings = app_settings
logger = logging.getLogger(__name__)

# Configuration de la base de données
database = Database(settings.DATABASE_URL)
metadata = MetaData()

# ===== TABLES =====

# Table des captures
captures = Table(
    "captures",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("created_at", DateTime, default=func.now()),
    Column("phone", String(20), nullable=True),
    Column("email", String(255), nullable=True),
    Column("photo_local_path", String(500), nullable=True),
    Column("photo_remote_url", String(1000), nullable=True),
    Column("background_id", String(36), nullable=True),
    Column("is_synced", Boolean, default=False),
    Column("sync_attempts", Integer, default=0),
    Column("last_sync_attempt", DateTime, nullable=True),
    Column("synced_at", DateTime, nullable=True),
    Column("download_token", String(32), nullable=True),
    Column("download_expires_at", DateTime, nullable=True),
    Column("sms_sent", Boolean, default=False),
    Column("sms_sent_at", DateTime, nullable=True),
    Column("google_review_clicked", Boolean, default=False),
    Column("metadata", Text, nullable=True),  # JSON metadata
    Column("file_size", Integer, default=0),
    Column("last_error", Text, nullable=True),
    Index("idx_captures_created_at", "created_at"),
    Index("idx_captures_sync_status", "is_synced"),
    Index("idx_captures_phone", "phone"),
    Index("idx_captures_download_token", "download_token"),
)

# Table des fonds (backgrounds)
backgrounds = Table(
    "backgrounds",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(100), nullable=False),
    Column("file_path", String(500), nullable=False),
    Column("file_size", Integer, default=0),
    Column("is_active", Boolean, default=True),
    Column("display_order", Integer, default=0),
    Column("created_at", DateTime, default=func.now()),
    Column("updated_at", DateTime, default=func.now(), onupdate=func.now()),
    Index("idx_backgrounds_active", "is_active"),
    Index("idx_backgrounds_order", "display_order"),
)

# Table de configuration
config = Table(
    "config",
    metadata,
    Column("key", String(100), primary_key=True),
    Column("value", Text, nullable=True),
    Column("updated_at", DateTime, default=func.now(), onupdate=func.now()),
    Column("description", String(255), nullable=True),
)

# Table des utilisateurs admin
admin_users = Table(
    "admin_users",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("username", String(50), unique=True, nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("is_active", Boolean, default=True),
    Column("last_login", DateTime, nullable=True),
    Column("created_at", DateTime, default=func.now()),
    Index("idx_admin_username", "username"),
)

# Table des logs système
system_logs = Table(
    "system_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime, default=func.now()),
    Column("level", String(10), nullable=False),  # INFO, WARNING, ERROR
    Column("component", String(50), nullable=False),  # capture, sms, sync, etc.
    Column("message", Text, nullable=False),
    Column("details", Text, nullable=True),  # JSON details
    Column("correlation_id", String(36), nullable=True),
    Index("idx_logs_timestamp", "timestamp"),
    Index("idx_logs_level", "level"),
    Index("idx_logs_component", "component"),
)

# Table des statistiques quotidiennes
daily_stats = Table(
    "daily_stats",
    metadata,
    Column("date", DateTime, primary_key=True),
    Column("total_captures", Integer, default=0),
    Column("successful_captures", Integer, default=0),
    Column("sms_sent", Integer, default=0),
    Column("sync_successful", Integer, default=0),
    Column("sync_failed", Integer, default=0),
    Column("storage_used_mb", Float, default=0.0),
    Column("avg_processing_time_ms", Float, default=0.0),
    Column("updated_at", DateTime, default=func.now(), onupdate=func.now()),
)

# ===== FONCTIONS DE BASE DE DONNÉES =====

async def init_db():
    """Initialise la base de données et crée les tables"""
    try:
        # Connexion à la base de données
        await database.connect()
        
        # Création des tables avec SQLite
        engine = create_engine(
            settings.DATABASE_URL.replace("+aiosqlite", ""),
            connect_args={"check_same_thread": False}
        )
        
        metadata.create_all(engine)
        logger.info("✅ Tables créées avec succès")
        
        # Insertion de la configuration par défaut
        await insert_default_config()
        
        logger.info("✅ Base de données initialisée")
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'initialisation de la DB: {e}")
        raise

async def insert_default_config():
    """Insère la configuration par défaut"""
    default_config = {
        "welcome_message": settings.WELCOME_MESSAGE,
        "success_message": settings.SUCCESS_MESSAGE,
        "countdown_seconds": str(settings.COUNTDOWN_SECONDS),
    }
    
    for key, value in default_config.items():
        # Vérifier si la clé existe déjà
        existing = await database.fetch_one(
            "SELECT * FROM config WHERE key = :key", {"key": key}
        )
        
        if not existing:
            await database.execute(
                config.insert().values(
                    key=key,
                    value=value,
                    description=f"Configuration par défaut pour {key}"
                )
            )

async def get_db():
    """Dependency pour obtenir la connexion à la base de données"""
    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row

    return database

async def close_db():
    """Ferme la connexion à la base de données"""
    await database.disconnect()

# ===== CLASSE HELPER POUR LES REQUÊTES =====

class DatabaseHelper:
    """Classe helper pour les opérations de base de données"""
    
    def __init__(self):
        self.db = database
    
    async def get_config(self, key: str, default: str = None) -> str:
        """Récupère une valeur de configuration"""
        result = await self.db.fetch_one(
            "SELECT value FROM config WHERE key = :key", {"key": key}
        )
        return result["value"] if result else default
    
    async def set_config(self, key: str, value: str, description: str = None):
        """Met à jour une valeur de configuration"""
        existing = await self.db.fetch_one(
            "SELECT * FROM config WHERE key = :key", {"key": key}
        )
        
        if existing:
            await self.db.execute(
                "UPDATE config SET value = :value, updated_at = :now WHERE key = :key",
                {"key": key, "value": value, "now": datetime.now()}
            )
        else:
            await self.db.execute(
                config.insert().values(
                    key=key,
                    value=value,
                    description=description or f"Configuration {key}",
                    updated_at=datetime.now()
                )
            )
    
    async def log_event(self, level: str, component: str, message: str, 
                       details: str = None, correlation_id: str = None):
        """Enregistre un événement dans les logs système"""
        await self.db.execute(
            system_logs.insert().values(
                timestamp=datetime.now(),
                level=level.upper(),
                component=component,
                message=message,
                details=details,
                correlation_id=correlation_id
            )
        )
    
    async def update_daily_stats(self, date: datetime, **kwargs):
        """Met à jour les statistiques quotidiennes"""
        existing = await self.db.fetch_one(
            "SELECT * FROM daily_stats WHERE date = :date",
            {"date": date.date()}
        )
        
        if existing:
            # Mise à jour
            update_values = {k: v for k, v in kwargs.items() if v is not None}
            if update_values:
                query = "UPDATE daily_stats SET "
                query += ", ".join([f"{k} = :{k}" for k in update_values.keys()])
                query += ", updated_at = :now WHERE date = :date"
                
                await self.db.execute(query, {
                    **update_values,
                    "now": datetime.now(),
                    "date": date.date()
                })
        else:
            # Insertion
            await self.db.execute(
                daily_stats.insert().values(
                    date=date.date(),
                    updated_at=datetime.now(),
                    **{k: v for k, v in kwargs.items() if v is not None}
                )
            )
    
    async def cleanup_old_data(self, days: int = 30):
        """Nettoie les données anciennes"""
        cutoff_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_date = cutoff_date.replace(day=cutoff_date.day - days)
        
        # Supprimer les captures anciennes
        old_captures = await self.db.fetch_all(
            "SELECT * FROM captures WHERE created_at < :cutoff AND is_synced = 1",
            {"cutoff": cutoff_date}
        )
        
        deleted_count = 0
        for capture in old_captures:
            # Supprimer le fichier local si existe
            import os
            if capture["photo_local_path"] and os.path.exists(capture["photo_local_path"]):
                os.remove(capture["photo_local_path"])
            
            # Supprimer l'enregistrement
            await self.db.execute(
                "DELETE FROM captures WHERE id = :id",
                {"id": capture["id"]}
            )
            deleted_count += 1
        
        # Nettoyer les logs anciens
        await self.db.execute(
            "DELETE FROM system_logs WHERE timestamp < :cutoff",
            {"cutoff": cutoff_date}
        )
        
        logger.info(f"🧹 Nettoyage: {deleted_count} captures supprimées")
        return deleted_count
    
    async def create_admin_user(self, username: str, password: str) -> str:
        """Crée un nouvel utilisateur admin"""
        from passlib.context import CryptContext
        from uuid import uuid4
        
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        # Vérifier si l'utilisateur existe déjà
        existing = await self.db.fetch_one(
            "SELECT * FROM admin_users WHERE username = :username",
            {"username": username}
        )
        
        if existing:
            raise ValueError(f"L'utilisateur {username} existe déjà")
        
        # Créer le nouvel utilisateur
        user_id = str(uuid4())
        await self.db.execute(
            admin_users.insert().values(
                id=user_id,
                username=username,
                password_hash=pwd_context.hash(password),
                is_active=True
            )
        )
        
        logger.info(f"✅ Utilisateur admin créé: {username}")
        return user_id

# Instance globale
db_helper = DatabaseHelper()