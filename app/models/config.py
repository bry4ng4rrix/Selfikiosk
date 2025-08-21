from pydantic import BaseModel
from typing import Optional

class Config(BaseModel):
    ovh_app_key: str
    ovh_app_secret: str
    ovh_consumer_key: str
    vps_host: str
    vps_path: str
    google_review_url: Optional[str] = None
    google_review_enabled: bool
    countdown_seconds: int = 3
    welcome_message: str
    success_message: str
