from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ADMIN_API_KEY: str = "SUPER_SECRET_KEY"
    SECRET_KEY: str = "09f26e402586e2faa8da4c98a35f1b20d6b033c6097befa8be3486a829587fe2f"
    REMOTE_DATABASE_URL: str = "postgresql://garrix:strong@127.0.0.1:5432/garrix"
    REDIS_URL: str = "redis://localhost:6379/0"

    # OVH API Settings
    OVH_ENDPOINT: str = "ovh-eu"
    OVH_APP_KEY: str = "a0003bd03c5714b0"
    OVH_APP_SECRET: str = "39c7b1c1e182477d7b81b8d50daf00b6"
    OVH_CONSUMER_KEY: str = "1dc43ecde8a4bfdbce686fdfb354da4"
    SMS_SERVICE_NAME: str = "Selfikiosk"
    SMS_SENDER: str = "FoodAndBeer"

    class Config:
        env_file = ".env"

settings = Settings()
