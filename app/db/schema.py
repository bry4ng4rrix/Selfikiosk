from sqlalchemy import Boolean, Column, Integer, String, DateTime, JSON, TIMESTAMP
from sqlalchemy.sql import func
from .database import Base

class Capture(Base):
    __tablename__ = "captures"

    id = Column(String, primary_key=True, index=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    photo_local_path = Column(String, nullable=True)
    photo_remote_url = Column(String, nullable=True)
    background_id = Column(String, nullable=True)
    is_synced = Column(Boolean, default=False)
    sync_attempts = Column(Integer, default=0)
    capture_metadata = Column(JSON, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'created_at': self.created_at,
            'phone': self.phone,
            'email': self.email,
            'background_id': self.background_id,
            'photo_local_path': self.photo_local_path,
            'photo_remote_url': self.photo_remote_url,
            'is_synced': self.is_synced,
            'sync_attempts': self.sync_attempts,
            'capture_metadata': self.capture_metadata
        }

class Background(Base):
    __tablename__ = "backgrounds"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer)
    created_at = Column(TIMESTAMP, server_default=func.now())

class Config(Base):
    __tablename__ = "config"

    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    last_login = Column(TIMESTAMP, nullable=True)
