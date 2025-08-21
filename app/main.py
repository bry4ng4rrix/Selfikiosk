from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .db import schema
from .db.database import local_engine, Base
from .api import routes, auth_routes
from .services.sync import schedule_sync_task
from .services.cleanup import schedule_cleanup_task
from . import tasks # This is important to initialize the broker
from .core.config import settings
import redis

schema.Base.metadata.create_all(bind=local_engine)


app = FastAPI(
    title="Selfie Kiosk API",
    description="API for the autonomous selfie kiosk.",
    version="1.0.0"
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(routes.router)
app.include_router(auth_routes.router)

@app.on_event("startup")
async def startup_event():
    """
    On application startup, send the first periodic sync task to the queue.
    Uses a Redis lock to prevent scheduling duplicates on reload.
    """
    try:
        r = redis.from_url(settings.REDIS_URL)
        # Set a lock key that expires in 10 minutes. If the key is set successfully (nx=True),
        # it means no other process has done it recently.
        if r.set("sync_scheduler_lock", "1", nx=True, ex=600):
            schedule_sync_task.send()
            print("Initial database sync scheduler task sent to the queue.")
        else:
            print("Sync scheduler lock already exists. Skipping.")
        # Schedule daily cleanup with a 12h lock to avoid duplicates
        if r.set("cleanup_scheduler_lock", "1", nx=True, ex=43_200):
            schedule_cleanup_task.send()
            print("Initial cleanup scheduler task sent to the queue.")
        else:
            print("Cleanup scheduler lock already exists. Skipping.")
    except redis.exceptions.ConnectionError as e:
        print(f"Could not connect to Redis to set scheduler lock: {e}")


