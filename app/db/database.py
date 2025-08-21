from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from ..core.config import settings

# --- Local SQLite Database ---
LOCAL_DATABASE_URL = "sqlite:///./sql_app.db"
local_engine = create_engine(
    LOCAL_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=local_engine)

# --- Remote PostgreSQL Database (Optional) ---
remote_engine = None
SessionRemote = None

# Only create a remote engine if a valid URL is provided
if settings.REMOTE_DATABASE_URL and "user:password@host:port" not in settings.REMOTE_DATABASE_URL:
    remote_engine = create_engine(settings.REMOTE_DATABASE_URL)
    SessionRemote = sessionmaker(autocommit=False, autoflush=False, bind=remote_engine)


Base = declarative_base()

# Dependency to get local DB session for API requests
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Function to get a remote DB session for synchronization tasks
def get_remote_db():
    db = SessionRemote()
    try:
        yield db
    finally:
        db.close()
