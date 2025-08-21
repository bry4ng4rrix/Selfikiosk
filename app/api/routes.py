from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Security
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Dict
from ..db import schema
from ..services.health import HealthCheckService
from ..models import capture as capture_models, sms as sms_models, config as config_models

from .dependencies import get_api_key, get_db
from ..services.sms import send_sms_task
from ..services.sync import sync_databases_task
import shutil
import uuid
import base64
from pathlib import Path

router = APIRouter()

# Directory for backgrounds
BACKGROUNDS_DIR = Path("static/backgrounds")
BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/health", tags=["Monitoring"])
async def health_check():
    """
    Comprehensive health check endpoint via router.
    Delegates to HealthCheckService in `app/services/health.py`.
    """
    return await HealthCheckService.perform_all_checks()


@router.get("/api/backgrounds", tags=["Public"])
async def get_backgrounds(db: Session = Depends(get_db)):
    backgrounds = db.query(schema.Background).filter(schema.Background.is_active == True).order_by(schema.Background.display_order).all()
    return backgrounds

@router.post("/admin/backgrounds", tags=["Admin"], dependencies=[Security(get_api_key)])
async def upload_background(
    name: str = Form(...),
    display_order: int = Form(0),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # Generate a unique filename
    file_extension = Path(file.filename).suffix
    file_id = str(uuid.uuid4())
    file_path = BACKGROUNDS_DIR / f"{file_id}{file_extension}"

    # Save the file
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()

    # Create DB entry
    db_background = schema.Background(
        id=file_id,
        name=name,
        file_path=str(file_path),
        display_order=display_order
    )
    db.add(db_background)
    db.commit()
    db.refresh(db_background)

    return db_background

@router.delete("/admin/backgrounds/{background_id}", tags=["Admin"], status_code=204, dependencies=[Security(get_api_key)])
async def delete_background(background_id: str, db: Session = Depends(get_db)):
    # Find the background
    db_background = db.query(schema.Background).filter(schema.Background.id == background_id).first()
    if not db_background:
        raise HTTPException(status_code=404, detail="Background not found")

    # Delete the file
    file_path = Path(db_background.file_path)
    if file_path.exists():
        file_path.unlink()

    # Delete from DB
    db.delete(db_background)
    db.commit()

    return

@router.post("/api/capture", tags=["Public"])
async def capture_selfie(
    capture_data: capture_models.CaptureCreate,
    db: Session = Depends(get_db)
):
    # Decode the base64 image
    try:
        image_data = base64.b64decode(capture_data.photo_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    # Generate a unique filename
    capture_id = str(uuid.uuid4())
    file_path = Path("static/captures") / f"{capture_id}.jpg"

    # Save the file
    with open(file_path, "wb") as f:
        f.write(image_data)

    # Create DB entry
    db_capture = schema.Capture(
        id=capture_id,
        phone=capture_data.phone,
        email=capture_data.email,
        background_id=capture_data.background_id,
        photo_local_path=str(file_path),
        photo_remote_url=f"/{file_path}" # Placeholder URL for now
    )
    db.add(db_capture)
    db.commit()
    db.refresh(db_capture)

    return db_capture

@router.post("/api/send-sms", tags=["Public"])
async def send_photo_sms(
    sms_request: sms_models.SmsRequest,
    db: Session = Depends(get_db)
):
    # Find the capture
    db_capture = db.query(schema.Capture).filter(schema.Capture.id == sms_request.capture_id).first()
    if not db_capture:
        raise HTTPException(status_code=404, detail="Capture not found")

    # Construct the message
    # In a real scenario, the base URL should come from config
    download_url = f"http://localhost:8000{db_capture.photo_remote_url}"
    message = f"Voici le lien pour télécharger votre photo : {download_url}"

    # Send the SMS task to the queue
    send_sms_task.send(phone=sms_request.phone, message=message)

    # Update the capture record with the phone number
    db_capture.phone = sms_request.phone
    db.commit()

    return {"status": "sms_queued"}

@router.get("/api/download/{capture_id}", tags=["Public"])
async def download_photo(capture_id: str, db: Session = Depends(get_db)):
    # Find the capture
    db_capture = db.query(schema.Capture).filter(schema.Capture.id == capture_id).first()
    if not db_capture or not db_capture.photo_local_path:
        raise HTTPException(status_code=404, detail="Photo not found")

    file_path = Path(db_capture.photo_local_path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Photo file not found on server")

    return FileResponse(file_path)

@router.get("/admin/config", tags=["Admin"], dependencies=[Security(get_api_key)])
async def get_config(db: Session = Depends(get_db)):
    config_items = db.query(schema.Config).all()
    return {c.key: c.value for c in config_items}

@router.put("/admin/config", tags=["Admin"], dependencies=[Security(get_api_key)])
async def update_config(config_data: Dict[str, str], db: Session = Depends(get_db)):
    for key, value in config_data.items():
        db_config = db.query(schema.Config).filter(schema.Config.key == key).first()
        if db_config:
            db_config.value = value
        else:
            db_config = schema.Config(key=key, value=value)
            db.add(db_config)
    db.commit()
    return {"status": "config_updated"}

@router.get("/admin/captures", tags=["Admin"])
async def list_captures(db: Session = Depends(get_db), skip: int = 0, limit: int = 100):
    captures = db.query(schema.Capture).offset(skip).limit(limit).all()
    return captures

@router.delete("/admin/captures/{capture_id}", tags=["Admin"], dependencies=[Security(get_api_key)])
async def delete_capture(capture_id: str, db: Session = Depends(get_db)):
    db_capture = db.query(schema.Capture).filter(schema.Capture.id == capture_id).first()
    if not db_capture:
        raise HTTPException(status_code=404, detail="Capture not found")

    # Delete the image file
    if db_capture.photo_local_path:
        file_path = Path(db_capture.photo_local_path)
        if file_path.is_file():
            file_path.unlink()

    # Delete the DB record
    db.delete(db_capture)
    db.commit()

    return {"status": "capture_deleted"}

@router.post("/admin/sync", tags=["Admin"])
async def trigger_sync():
    """
    Manually triggers a database synchronization task.
    """
    sync_databases_task.send()
    return {"status": "sync_task_queued"}
