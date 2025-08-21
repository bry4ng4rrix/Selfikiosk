from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Capture(BaseModel):
    id: str
    timestamp: datetime
    phone: Optional[str] = None
    email: Optional[str] = None
    photo_url: str
    background_id: Optional[str] = None
    synced: bool = False

class CaptureCreate(BaseModel):
    photo_base64: str
    phone: Optional[str] = None
    email: Optional[str] = None
    background_id: Optional[str] = None
