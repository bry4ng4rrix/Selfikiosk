import dramatiq
from sqlalchemy.orm import Session
from ..db import schema
from ..db.database import get_db, get_remote_db

@dramatiq.actor(time_limit=300_000, max_retries=0)
def sync_databases_task(attempt: int = 0, batch_size: int = 10):
  
    local_db_gen = get_db()
    remote_db_gen = get_remote_db()

    try:
        db_local: Session = next(local_db_gen)
        db_remote: Session = next(remote_db_gen)
    except StopIteration:
        return {"error": "Could not connect to one of the databases."}
    except TypeError: # This will happen if remote_db_gen is None
        print("Sync skipped: Remote database not configured.")
        return

    try:
        # Fetch up to `batch_size` unsynced captures from local DB
        unsynced_captures = (
            db_local.query(schema.Capture)
            .filter(schema.Capture.is_synced == False)
            .limit(batch_size)
            .all()
        )
        if not unsynced_captures:
            print("Sync check: No new captures to sync.")
            return

        synced_count = 0
        for local_capture in unsynced_captures:
            db_remote.merge(local_capture)  # merge() handles both insert and update
            local_capture.is_synced = True
            synced_count += 1

        db_remote.commit()
        db_local.commit()

        print(f"Sync successful: {synced_count} captures synchronized.")

        # If more items remain, schedule next batch soon
        remaining = (
            db_local.query(schema.Capture)
            .filter(schema.Capture.is_synced == False)
            .count()
        )
        if remaining > 0:
            # small delay to allow system to breathe
            sync_databases_task.send_with_options(args=(0, batch_size), delay=2_000)
    except Exception as e:
        try:
            db_remote.rollback()
        except Exception:
            pass
        try:
            db_local.rollback()
        except Exception:
            pass
        print(f"Sync error: {e}")
        # Manual exponential backoff
        next_attempt = attempt + 1
        delay = min(60_000, 2_000 * (2 ** attempt))  # 2s, 4s, 8s, ... capped at 60s
        sync_databases_task.send_with_options(args=(next_attempt, batch_size), delay=delay)
    finally:
        try:
            db_local.close()
        except Exception:
            pass
        try:
            db_remote.close()
        except Exception:
            pass

@dramatiq.actor(time_limit=60_000, max_retries=0)
def schedule_sync_task():
    """
    Periodically triggers the database synchronization task.
    """
    # Trigger the main sync task
    sync_databases_task.send()
    # Re-enqueue this scheduler to run again in 30 seconds (30,000 ms)
    schedule_sync_task.send_with_options(delay=30_000)
    print("Scheduled next database sync in 30 seconds.")

