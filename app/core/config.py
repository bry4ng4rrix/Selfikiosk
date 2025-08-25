from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ADMIN_API_KEY: str = "SUPER_SECRET_KEY"
    SECRET_KEY: str = "09f26e402586e2faa8da4c98a35f1b20d6b033c6097befa8be3486a829587fe2f"
    REMOTE_DATABASE_URL: str = "postgresql://selfikiosk:selfikiosk@127.0.0.1:5432/selfikiosk"
    REDIS_URL: str = "redis://localhost:6379/0"


    OVH_ENDPOINT: str = "ovh-eu"
    OVH_APP_KEY: str = "7dfab3c7464a4ed1"
    OVH_APP_SECRET: str = "4ef61fb048fced72744d4ee24a38dfa4"
    OVH_CONSUMER_KEY: str = "f5804baefabe063f090668e3d9436f3e"
    SMS_SERVICE_NAME: str = "sms-fr78991-1"
    SMS_SENDER: str = "FoodAndBeer"


    RETENTION_DAYS: int = 30

    class Config:
        env_file = ".env"

settings = Settings()
