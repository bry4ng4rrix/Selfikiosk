
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



##Nginx:

nginx
location /uploads/ {
    alias /var/www/html/uploads/;
    autoindex off;
    add_header Cache-Control "public, max-age=86400";
}



##Apache:

apache
Alias /uploads/ "/var/www/html/uploads/"
<Directory "/var/www/html/uploads/">
    Options -Indexes
    Require all granted
</Directory>



##Endpoints
Public:
POST /api/capture: stocke base64 → /var/www/html/uploads/{id}.jpg
POST /api/capture-batch: batch (par défaut static/captures/)
GET /api/captures/status?ids=a,b,c: map id → {is_synced, exists}
POST /api/send-sms: envoie SMS OVH avec lien /uploads/{id}.jpg
GET /api/download/{capture_id}: renvoie le fichier local
Admin (auth requise):
GET /admin/config, PUT /admin/config
GET /admin/captures, DELETE /admin/captures/{id}
POST /admin/sync (queue sync)
POST /admin/cleanup (queue cleanup RGPD)
GET /admin/stats, GET /admin/export/excel
Monitoring: GET /health
RGPD (rétention/cleanup)
RETENTION_DAYS dans .env (défaut 30).
app/services/cleanup.py:
cleanup_old_captures: supprime DB + fichiers où created_at < seuil.
schedule_cleanup_task: planifie toutes les 24h.
Démarrage: planification initiale via startup_event + verrou Redis.
Santé/Diagnostics
/health agrège DB locale/distante, disque, OVH, Redis + statut global.
Logs: sync (app/services/sync.py), cleanup (app/services/cleanup.py).
Dépannage
Écriture /uploads: vérifier propriétaire/groupe/permissions.
Redis: service actif et REDIS_URL correct.
PostgreSQL distant: URL, réseau, firewall.
OVH: clés valides et droits sur /sms.
Dramatiq ne consomme pas: worker non lancé (dramatiq app.tasks).
Batch path: aligner /api/capture-batch sur /var/www/html/uploads si souhaité.
Développement
Hot-reload: uvicorn app.main:app --reload
Dépendances: requirements.txt
Schéma SQLAlchemy: app/db/schema.py
Besoin d’un guide systemd (API/worker) et d’une config Nginx complète (SSL, proxy, compression) ? Indique ta cible (Ubuntu/Debian/etc.) et je fournis les fichiers prêts à l’emploi. EOF



Compte rendu :

- Mise en place des tests sur l’API OVH.
- Tests de l’envoi de SMS via OVH.
- Configuration du VPS (Apache, Redis, PostgreSQL).
- Migration du code vers un stockage local.