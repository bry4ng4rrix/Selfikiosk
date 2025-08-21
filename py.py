from app.db.database import remote_engine
from app.db import schema
if remote_engine is None:
    raise SystemExit("remote_engine is None: vérifiez REMOTE_DATABASE_URL.")
schema.Base.metadata.create_all(bind=remote_engine)
print("Tables créées (si non existantes) sur la base distante.")