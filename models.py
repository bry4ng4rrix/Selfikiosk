



class Capture(BaseModel):
    id: str
    timestamp: datetime
    phone: Optional[str]
    email: Optional[str]
    photo_url: str
    background_id: Optional[str]
    synced: bool = False

class Config(BaseModel):
    ovh_app_key: str
    ovh_app_secret: str
    ovh_consumer_key: str
    vps_host: str
    vps_path: str
    google_review_url: Optional[str]
    google_review_enabled: bool
    countdown_seconds: int = 3
    welcome_message: str
    success_message: str