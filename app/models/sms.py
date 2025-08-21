from pydantic import BaseModel

class SmsRequest(BaseModel):
    capture_id: str
    phone: str
