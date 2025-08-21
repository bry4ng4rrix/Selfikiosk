import dramatiq
from sqlalchemy.orm import Session
from ..db import schema
from ..db.database import get_db, get_remote_db

@dramatiq.actor(time_limit=300_000, max_retries=3)
def sync_databases_task():
    """
    Synchronizes data from the local SQLite database to the remote PostgreSQL database.
    """
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
        # Fetch unsynced captures from local DB
        unsynced_captures = db_local.query(schema.Capture).filter(schema.Capture.is_synced == False).all()
        if not unsynced_captures:
            print("Sync check: No new captures to sync.")
            return

        synced_count = 0
        for local_capture in unsynced_captures:
            db_remote.merge(local_capture) # merge() handles both insert and update
            local_capture.is_synced = True
            synced_count += 1

        db_remote.commit()
        db_local.commit()

        print(f"Sync successful: {synced_count} captures synchronized.")

    except Exception as e:
        db_remote.rollback()
        db_local.rollback()
        print(f"Sync error: {e}")
        raise # Re-raise to allow Dramatiq to handle retries
    finally:
        db_local.close()
        db_remote.close()

@dramatiq.actor(time_limit=60_000, max_retries=1)
def schedule_sync_task():
    """
    Periodically triggers the database synchronization task.
    """
    # Trigger the main sync task
    sync_databases_task.send()
    # Re-enqueue this scheduler to run again in 5 minutes (300,000 ms)
    schedule_sync_task.send_with_options(delay=300000)
    print("Scheduled next database sync in 5 minutes.")

