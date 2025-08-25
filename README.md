
# Selfie Kiosk Backend

API FastAPI pour une borne selfie autonome: réception/sauvegarde photos, envoi SMS (OVH), synchro vers base distante, et nettoyage RGPD.

## Sommaire
- Fonctionnalités
- Architecture
- Prérequis
- Installation
- Configuration (.env)
- Démarrage
- Workers Dramatiq
- Fichiers /uploads (Nginx/Apache)
- Endpoints
- RGPD (rétention/cleanup)
- Santé/Diagnostics
- Dépannage
- Développement

## Fonctionnalités
- __Captures__: réception d’images en base64, sauvegarde locale.
- __Envoi SMS__: lien de téléchargement via OVH SMS.
- __Synchronisation__: copie des captures vers base distante (PostgreSQL) via Dramatiq + Redis.
- __Nettoyage RGPD__: suppression automatique des captures > N jours (par défaut 30).
- __Admin__: fonds, stats, export Excel, triggers manuels (sync/cleanup).
- __Monitoring__: endpoint santé multi-services.

## Architecture
- FastAPI: [app/main.py](cci:7://file:///home/garrix/Dev/Work/newsselfibackend/app/main.py:0:0-0:0), routes [app/api/routes.py](cci:7://file:///home/garrix/Dev/Work/newsselfibackend/app/api/routes.py:0:0-0:0).
- DB locale SQLite: [selfie_kiosk.db](cci:7://file:///home/garrix/Dev/Work/newsselfibackend/selfie_kiosk.db:0:0-0:0).
- DB distante PostgreSQL (optionnelle).
- File de tâches: Redis + Dramatiq ([app/tasks.py](cci:7://file:///home/garrix/Dev/Work/newsselfibackend/app/tasks.py:0:0-0:0), [app/services/sync.py](cci:7://file:///home/garrix/Dev/Work/newsselfibackend/app/services/sync.py:0:0-0:0), [app/services/cleanup.py](cci:7://file:///home/garrix/Dev/Work/newsselfibackend/app/services/cleanup.py:0:0-0:0)).
- Stockage photos:
  - `POST /api/capture`: `/var/www/html/uploads/{id}.jpg`.
  - `POST /api/capture-batch`: par défaut [static/captures/](cci:7://file:///home/garrix/Dev/Work/newsselfibackend/static/captures:0:0-0:0) (peut être aligné sur `/uploads`).

## Prérequis
- Python 3.10+
- Redis en service (ex: `localhost:6379`)
- OVH API (si SMS)
- PostgreSQL (si synchro distante)
- Serveur web (Nginx/Apache) si exposition `/uploads`

## Installation
```bash
# Cloner le projet
git clone <repo> newsselfibackend
cd newsselfibackend

# Environnement virtuel
python3 -m venv venv
# Shell fish
source venv/bin/activate.fish

# Dépendances
pip install -r requirements.txt

configuration du .env

# Sécurité / Admin
ADMIN_API_KEY=remplacez_moi
SECRET_KEY=remplacez_moi

# Redis
REDIS_URL=redis://localhost:6379/0

# Base distante (optionnelle)
REMOTE_DATABASE_URL=postgresql://user:pass@host:5432/dbname

# OVH API (SMS)
OVH_ENDPOINT=ovh-eu
OVH_APP_KEY=xxxxxxxxxxxxxxxx
OVH_APP_SECRET=xxxxxxxxxxxxxxxx
OVH_CONSUMER_KEY=xxxxxxxxxxxxxxxx
SMS_SERVICE_NAME=sms-xxxxxx-1
SMS_SENDER=SelfieKiosk

# RGPD (jours de rétention)
RETENTION_DAYS=30





##Démarrage
source venv/bin/activate.fish
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload



##Droits d’écriture pour /var/www/html/uploads:
sudo mkdir -p /var/www/html/uploads
sudo chown -R $USER:www-data /var/www/html/uploads
sudo chmod -R 775 /var/www/html/uploads


