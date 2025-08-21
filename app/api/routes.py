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
    """
    Comprehensive health check endpoint via router.
    Delegates to HealthCheckService in `app/services/health.py`.
    """
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

@router.post("/api/capture-batch", tags=["Public"])
async def capture_batch(payload: capture_models.CaptureBatchRequest, db: Session = Depends(get_db)):
    """
    Accept up to 10 photos in a single request for offline batch syncing.
    Saves images locally and creates DB records with is_synced=False.
    Returns per-item results with created capture IDs.
    """
    # Enforce batch size limit
    items: List[capture_models.CaptureBatchItem] = payload.items or []
    if len(items) == 0:
        return {"status": "empty", "results": []}
    if len(items) > 10:
        items = items[:10]

    results: List[capture_models.CaptureBatchResult] = []
    captures_dir = Path("static/captures")
    captures_dir.mkdir(parents=True, exist_ok=True)

    import base64, uuid

    for item in items:
        try:
            image_data = base64.b64decode(item.photo_base64)
            capture_id = str(uuid.uuid4())
            file_path = captures_dir / f"{capture_id}.jpg"
            with open(file_path, "wb") as f:
                f.write(image_data)

            db_capture = schema.Capture(
                id=capture_id,
                phone=item.phone,
                email=item.email,
                background_id=item.background_id,
                photo_local_path=str(file_path),
                photo_remote_url=f"/{file_path}",
                is_synced=False,
            )
            db.add(db_capture)
            results.append(capture_models.CaptureBatchResult(id=capture_id, status="stored"))
        except Exception as e:
            results.append(capture_models.CaptureBatchResult(id=None, status="error", error=str(e)))

    db.commit()

    # Optionally trigger a sync task to expedite syncing
    try:
        from ..services.sync import sync_databases_task
        sync_databases_task.send()
    except Exception:
        pass

    return {"status": "queued", "results": [r.dict() for r in results]}

@router.get("/api/captures/status", tags=["Public"])
async def captures_status(ids: str, db: Session = Depends(get_db)):
    """
    Query sync status for a comma-separated list of capture IDs.
    Returns a map of id -> {is_synced, exists}.
    """
    id_list = [s.strip() for s in ids.split(",") if s.strip()]
    if not id_list:
        return {"status": "empty", "items": {}}

    rows = db.query(schema.Capture).filter(schema.Capture.id.in_(id_list)).all()
    by_id = {r.id: {"is_synced": bool(r.is_synced), "exists": True} for r in rows}
    for cid in id_list:
        if cid not in by_id:
            by_id[cid] = {"is_synced": False, "exists": False}
    return {"status": "ok", "items": by_id}

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

@router.get("/admin/config", tags=["Admin"], dependencies=[Depends(get_current_admin)])
async def get_config(db: Session = Depends(get_db)):
    config_items = db.query(schema.Config).all()
    return {c.key: c.value for c in config_items}

@router.put("/admin/config", tags=["Admin"], dependencies=[Depends(get_current_admin)])
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

@router.get("/admin/stats", tags=["Admin"], dependencies=[Depends(get_current_admin)])
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

@router.get("/admin/export/excel", tags=["Admin"], dependencies=[Depends(get_current_admin)])
async def admin_export_excel(db: Session = Depends(get_db)):
    """Export captures to an Excel file and return it as a download."""
    rows = db.query(schema.Capture).order_by(schema.Capture.created_at.desc()).all()
    wb = Workbook()
    ws = wb.active
    ws.title = "Captures"
    headers = [
        "id", "created_at", "phone", "email", "background_id",
        "photo_local_path", "photo_remote_url", "is_synced", "sync_attempts"
    ]
    ws.append(headers)
    for r in rows:
        ws.append([
            r.id,
            r.created_at.isoformat() if r.created_at else None,
            r.phone,
            r.email,
            r.background_id,
            r.photo_local_path,
            r.photo_remote_url,
            r.is_synced,
            r.sync_attempts,
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"captures_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return FileResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=filename)

@router.post("/admin/test/vps", tags=["Admin"], dependencies=[Depends(get_current_admin)])
async def admin_test_vps():
    """Test VPS connectivity via the health check service."""
    from ..services.health import HealthCheckService
    return await HealthCheckService.check_vps_connectivity()

@router.post("/admin/test/sms", tags=["Admin"], dependencies=[Depends(get_current_admin)])
async def admin_test_sms(payload: sms_models.SmsRequest):
    """Queue a test SMS send via Dramatiq."""
    # If no message provided, create a default one
    message = f"Test SMS envoyé à {payload.phone}"
    send_sms_task.send(phone=payload.phone, message=message)
    return {"status": "sms_test_queued", "phone": payload.phone}
