from pydantic import BaseModel
from typing import Optional, List
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

class CaptureBatchItem(BaseModel):
    photo_base64: str
    phone: Optional[str] = None
    email: Optional[str] = None
    background_id: Optional[str] = None

class CaptureBatchRequest(BaseModel):
    items: List[CaptureBatchItem]

class CaptureBatchResult(BaseModel):
    id: Optional[str] = None
    status: str
    error: Optional[str] = None
