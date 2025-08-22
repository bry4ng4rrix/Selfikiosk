from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Security
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import Dict
from ..db import schema
from ..services.health import HealthCheckService
from ..models import capture as capture_models, sms as sms_models, config as config_models

from .dependencies import get_current_admin, get_db
from ..services.sms import send_sms_task, send_sms_now
import ovh
from ..services.sync import sync_databases_task
import shutil
import uuid
import base64
from pathlib import Path
from datetime import datetime, timedelta
import io
from openpyxl import Workbook
from typing import List


router = APIRouter()





# Directory for backgrounds
BACKGROUNDS_DIR = Path("static/backgrounds")
BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/health", tags=["Monitoring"])
async def health_check():
   
    return await HealthCheckService.perform_all_checks()


@router.get("/api/backgrounds", tags=["Public"])
async def get_backgrounds(db: Session = Depends(get_db)):
    backgrounds = db.query(schema.Background).filter(schema.Background.is_active == True).order_by(schema.Background.display_order).all()
    return backgrounds

@router.post("/admin/backgrounds", tags=["Admin"], dependencies=[Depends(get_current_admin)])
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

@router.delete("/admin/backgrounds/{background_id}", tags=["Admin"], status_code=204, dependencies=[Depends(get_current_admin)])
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

    # Generate a unique filename and absolute upload path
    capture_id = str(uuid.uuid4())
    uploads_dir = Path("/var/www/html/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / f"{capture_id}.jpg"

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
        # Assuming web server exposes /uploads from /var/www/html/uploads
        photo_remote_url=f"/uploads/{capture_id}.jpg"
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
   
    download_url = f"http://localhost:8000{db_capture.photo_remote_url}"
    message = f"Voici le lien pour télécharger votre photo : {download_url}"

    # Send the SMS synchronously to confirm delivery request
    try:
        result = send_sms_now(phone=sms_request.phone, message=message)
        sent = True
    except ovh.exceptions.APIError as e:
        # Keep a record of the phone even if sending failed
        db_capture.phone = sms_request.phone
        db.commit()
        raise HTTPException(status_code=502, detail=f"OVH SMS error: {e}")

    # Update the capture record with the phone number
    db_capture.phone = sms_request.phone
    db.commit()

    return {"status": "sent", "job": result}

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

def _get_env_masked() -> Dict[str, str]:
    """Helper: return current application settings loaded from .env (masked)."""
    from ..core.config import settings

    def _mask(val: str) -> str:
        if not val:
            return val
        if len(val) <= 6:
            return "*" * len(val)
        return f"{val[:3]}****{val[-2:]}"

    data = settings.model_dump()
    sensitive_keys = {
        "ADMIN_API_KEY",
        "SECRET_KEY",
        "OVH_APP_SECRET",
        "OVH_CONSUMER_KEY",
        "REMOTE_DATABASE_URL",
    }
    masked: Dict[str, str] = {}
    for k, v in data.items():
        if isinstance(v, str) and (k in sensitive_keys or any(s in k.upper() for s in ["SECRET", "PASSWORD", "TOKEN", "KEY"])):
            masked[k] = _mask(v)
        else:
            masked[k] = v
    return masked

@router.get("/admin/config", tags=["Admin"], dependencies=[Depends(get_current_admin)])
async def get_config():
    """Expose the configuration from .env/settings (UNMASKED, admin-only)."""
    from ..core.config import settings
    return settings.model_dump()


@router.post("/admin/config/sync", tags=["Admin"], dependencies=[Depends(get_current_admin)])
async def sync_env_to_db(db: Session = Depends(get_db)):
    """Synchronize current .env/settings values into the database `config` table (upsert)."""
    from ..core.config import settings
    data = settings.model_dump()
    # Upsert each key/value as strings
    for key, value in data.items():
        val_str = str(value) if value is not None else ""
        db_row = db.query(schema.Config).filter(schema.Config.key == key).first()
        if db_row:
            db_row.value = val_str
        else:
            db_row = schema.Config(key=key, value=val_str)
            db.add(db_row)
    db.commit()
    return {"status": "synced", "count": len(data)}

@router.put("/admin/config", tags=["Admin"], dependencies=[Depends(get_current_admin)])
async def update_config(config_data: Dict[str, object], db: Session = Depends(get_db)):
   
    from ..core.config import settings

    # Upsert provided keys, skipping masked placeholders
    for key, value in (config_data or {}).items():
        # Skip masked placeholders like "abc****yz"
        if isinstance(value, str) and "****" in value:
            continue
        val_str = str(value) if value is not None else ""
        db_config = db.query(schema.Config).filter(schema.Config.key == key).first()
        if db_config:
            db_config.value = val_str
        else:
            db_config = schema.Config(key=key, value=val_str)
            db.add(db_config)
    db.commit()

    # Build response: merge DB values over settings defaults, then mask
    defaults = settings.model_dump()
    db_items = {c.key: c.value for c in db.query(schema.Config).all()}

    merged: Dict[str, object] = {}
    for k, default_val in defaults.items():
        v = db_items.get(k, default_val)
        # Try to coerce to default type for cleaner response (e.g., int)
        if isinstance(default_val, int) and isinstance(v, str):
            try:
                v = int(v)
            except ValueError:
                pass
        merged[k] = v

    # Apply masking to sensitive values
    masked = _get_env_masked()
    # But keep non-sensitive from merged (preserve types for those)
    sensitive_markers = ["SECRET", "PASSWORD", "TOKEN", "KEY"]
    sensitive_explicit = {"ADMIN_API_KEY", "SECRET_KEY", "OVH_APP_SECRET", "OVH_CONSUMER_KEY", "REMOTE_DATABASE_URL"}

    response: Dict[str, object] = {}
    for k, v in merged.items():
        if (isinstance(v, str) and (k in sensitive_explicit or any(s in k.upper() for s in sensitive_markers))):
            response[k] = masked.get(k, v)
        else:
            response[k] = v

    return {"status": "config_updated", "config": response}

@router.get("/admin/captures", tags=["Admin"])
async def list_captures(db: Session = Depends(get_db), skip: int = 0, limit: int = 100, current_admin: schema.Admin = Depends(get_current_admin)):
    captures = db.query(schema.Capture).offset(skip).limit(limit).all()
    return captures

@router.delete("/admin/captures/{capture_id}", tags=["Admin"], dependencies=[Depends(get_current_admin)])
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

@router.post("/admin/sync", tags=["Admin"], dependencies=[Depends(get_current_admin)])
async def trigger_sync():
    """
    Manually triggers a database synchronization task.
    """
    sync_databases_task.send()
    return {"status": "sync_task_queued"}

@router.get("/admin/stats", tags=["Admin"])
async def admin_stats(db: Session = Depends(get_db)):
    """Basic statistics for admin dashboard."""
    total_captures = db.query(schema.Capture).count()
    unsynced = db.query(schema.Capture).filter(schema.Capture.is_synced == False).count()
    backgrounds = db.query(schema.Background).count()
    admins = db.query(schema.Admin).count()
    since = datetime.utcnow() - timedelta(days=1)
    recent_24h = db.query(schema.Capture).filter(schema.Capture.created_at >= since).count()
    return {
        "total_captures": total_captures,
        "unsynced_captures": unsynced,
        "backgrounds": backgrounds,
        "admins": admins,
        "captures_last_24h": recent_24h,
    }


@router.post("/admin/cleanup", tags=["Admin"], dependencies=[Depends(get_current_admin)])
async def trigger_cleanup():
    """Manually trigger cleanup of old captures (RGPD)."""
    try:
        from ..services.cleanup import cleanup_old_captures
        cleanup_old_captures.send()
        return {"status": "cleanup_task_queued"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not queue cleanup: {e}")

@router.post("/admin/test/vps", tags=["Admin"], dependencies=[Depends(get_current_admin)])
async def admin_test_vps():
    """Test VPS connectivity via the health check service."""
    from ..services.health import HealthCheckService
    return await HealthCheckService.check_vps_connectivity()

@router.post("/admin/test/sms", tags=["Admin"], dependencies=[Depends(get_current_admin)])
async def admin_test_sms(payload: sms_models.SmsRequest, db: Session = Depends(get_db)):
    """Send SMS synchronously like /api/send-sms (admin test)."""
    from ..services.sms import send_sms_now

    # Find the capture
    db_capture = db.query(schema.Capture).filter(schema.Capture.id == payload.capture_id).first()
    if not db_capture:
        raise HTTPException(status_code=404, detail="Capture not found")

    download_url = f"http://localhost:8000{db_capture.photo_remote_url}"
    message = f"Voici le lien pour télécharger votre photo : {download_url}"

    try:
        result = send_sms_now(phone=payload.phone, message=message)
    except ovh.exceptions.APIError as e:
        db_capture.phone = payload.phone
        db.commit()
        raise HTTPException(status_code=502, detail=f"OVH SMS error: {e}")

    db_capture.phone = payload.phone
    db.commit()
    return {"status": "sent", "job": result}
