import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import dramatiq
from sqlalchemy.orm import Session

from ..db import schema
from ..db.database import get_db
from ..core.config import settings


def _delete_file_safely(path_str: Optional[str]) -> bool:
    if not path_str:
        return False
    try:
        p = Path(path_str)
        if p.is_file():
            p.unlink()
            return True
    except Exception:
        pass
    return False


@dramatiq.actor(time_limit=300_000, max_retries=0)
def cleanup_old_captures():

    retention_days = getattr(settings, "RETENTION_DAYS", 30) or 30
    threshold = datetime.utcnow() - timedelta(days=int(retention_days))

    db_gen = get_db()
    try:
        db: Session = next(db_gen)
    except StopIteration:
        return {"error": "Could not open DB session"}

    removed_count = 0
    removed_files = 0
    try:

        batch_size = 200
        while True:
            items = (
                db.query(schema.Capture)
                .filter(schema.Capture.created_at < threshold)
                .limit(batch_size)
                .all()
            )
            if not items:
                break
            for cap in items:
                if _delete_file_safely(cap.photo_local_path):
                    removed_files += 1
                db.delete(cap)
                removed_count += 1
            db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"Cleanup error: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        try:
            db.close()
        except Exception:
            pass

    print(f"Cleanup done. Removed {removed_count} captures, {removed_files} files older than {retention_days} days.")
    return {"status": "ok", "removed": removed_count, "files": removed_files}


@dramatiq.actor(time_limit=60_000, max_retries=0)
def schedule_cleanup_task():
    """
    Schedule periodic cleanup (every 24 hours).
    """
    cleanup_old_captures.send()

    schedule_cleanup_task.send_with_options(delay=86_400_000)
    print("Scheduled next cleanup in 24 hours.")
