# Selfie Kiosk API - Backend

API FastAPI complète pour application selfie kiosque autonome avec gestion offline et synchronisation cloud OVH.

## 🚀 Fonctionnalités Principales

- **Capture de selfies** avec gestion automatique online/offline
- **Stockage hybride** : local SQLite + cloud OVH Object Storage  
- **Envoi SMS** avec liens de téléchargement via API OVH
- **Gestion des fonds d'écran** personnalisés avec upload
- **Panel d'administration** sécurisé avec JWT
- **Synchronisation automatique** avec retry et queue Redis
- **Monitoring complet** avec health checks et métriques
- **Mode dégradé** : fonctionnement offline complet

## 🛠️ Stack Technique

- **Framework** : FastAPI 0.104+ avec Uvicorn
- **Base de données** : SQLite + aiosqlite (local) + PostgreSQL (distant)
- **Cache/Queue** : Redis pour gestion offline et synchronisation
- **Stockage** : OVH Object Storage (Swift API)
- **SMS** : API OVH SMS
- **Authentification** : JWT avec passlib/bcrypt
- **Images** : Pillow + OpenCV pour traitement
- **Validation** : Pydantic v2 + python-magic
- **Logs** : structlog avec rotation

## 📦 Installation

### Prérequis Système

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3.10 python3-pip redis-server sqlite3 
sudo apt install -y libmagic1 python3-opencv

# OU CentOS/RHEL
sudo yum install -y python3 python3-pip redis sqlite
sudo yum install -y file-libs opencv-python
```

### Installation Python

```bash
# Cloner le projet
git clone <repository-url>
cd selfie-kiosk-backend

# Créer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# OU venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -r requirements.txt
```

### Configuration

1. **Copier le fichier d'exemple de configuration** :
```bash
cp .env.example .env
```

2. **Éditer `.env` avec vos paramètres** :
```env
# Base de données
DATABASE_URL=sqlite+aiosqlite:///./selfie_kiosk.db

# Redis
REDIS_URL=redis://localhost:6379/0

# Sécurité
SECRET_KEY=your-super-secret-key-change-me
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme123!

# OVH API SMS
OVH_ENDPOINT=ovh-eu
OVH_APPLICATION_KEY=your-app-key
OVH_APPLICATION_SECRET=your-app-secret
OVH_CONSUMER_KEY=your-consumer-key
SMS_SERVICE_NAME=sms-XXXXXX-1

# OVH Object Storage
SWIFT_AUTH_URL=https://auth.cloud.ovh.net/v3
SWIFT_USERNAME=your-username
SWIFT_PASSWORD=your-password
SWIFT_TENANT_NAME=your-tenant
SWIFT_CONTAINER=selfie-photos

# Configuration application
UPLOAD_DIR=./uploads
PUBLIC_BASE_URL=http://localhost:8000
COUNTDOWN_SECONDS=3
WELCOME_MESSAGE=Bienvenue ! Prenez votre selfie !
SUCCESS_MESSAGE=Photo prise avec succès !

# Google Reviews (optionnel)
GOOGLE_REVIEW_URL=https://g.page/your-business/review
GOOGLE_REVIEW_ENABLED=false
```

### Initialisation

```bash
# Démarrer Redis
sudo systemctl start redis
sudo systemctl enable redis

# Initialiser la base de données
python -c "
import asyncio
from database import init_db
asyncio.run(init_db())
"

# Créer les dossiers nécessaires
mkdir -p uploads/backgrounds logs
```

## 🚀 Démarrage

### Mode Développement

```bash
# Démarrer l'API
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# OU avec le script Python
python main.py
```

### Mode Production

```bash
# Avec Gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 --timeout 60

# OU service systemd (recommandé)
sudo cp scripts/selfie-kiosk.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable selfie-kiosk
sudo systemctl start selfie-kiosk
```

### Configuration Nginx (Production)

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    client_max_body_size 20M;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    location /static {
        alias /path/to/selfie-kiosk/uploads;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

## 📚 API Documentation

### Endpoints Principaux

L'API complète est documentée automatiquement via OpenAPI/Swagger :
- **Documentation interactive** : http://localhost:8000/docs
- **Documentation ReDoc** : http://localhost:8000/redoc
- **Schéma OpenAPI** : http://localhost:8000/openapi.json

### Endpoints Publics (sans authentification)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/` | Informations générales de l'API |
| `GET` | `/health` | Status de santé complet du système |
| `GET` | `/health/ping` | Ping simple pour monitoring |
| `POST` | `/api/capture` | Créer une nouvelle capture |
| `POST` | `/api/send-sms` | Envoyer SMS avec lien téléchargement |
| `GET` | `/api/download/{token}` | Télécharger une photo |
| `GET` | `/api/qr/{token}` | QR Code pour téléchargement |
| `GET` | `/api/backgrounds` | Liste des fonds d'écran |
| `GET` | `/api/backgrounds/{id}/file` | Fichier fond d'écran |
| `GET` | `/api/status/{capture_id}` | Statut d'une capture |

### Endpoints Admin (authentification JWT requise)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/admin/login` | Connexion admin |
| `GET` | `/admin/captures` | Liste complète des captures |
| `DELETE` | `/admin/captures/{id}` | Supprimer une capture |
| `POST` | `/admin/captures/{id}/retry` | Relancer la synchronisation |
| `POST` | `/admin/backgrounds` | Upload nouveau fond |
| `PUT` | `/admin/backgrounds/{id}` | Modifier fond |
| `DELETE` | `/admin/backgrounds/{id}` | Supprimer fond |
| `GET` | `/admin/config` | Configuration actuelle |
| `PUT` | `/admin/config` | Mettre à jour la configuration |
| `GET` | `/admin/stats` | Statistiques complètes |
| `POST` | `/admin/test/sms` | Test envoi SMS |
| `POST` | `/admin/test/storage` | Test connectivité stockage |
| `GET` | `/admin/export/excel` | Export Excel des données |

### Exemples d'utilisation

#### Créer une capture

```python
import requests
import base64

# Encoder l'image en base64
with open("photo.jpg", "rb") as f:
    photo_b64 = base64.b64encode(f.read()).decode()

# Créer la capture
response = requests.post("http://localhost:8000/api/capture", json={
    "phone": "+33123456789",
    "email": "user@example.com",
    "background_id": "fond-uuid",
    "photo_base64": photo_b64
})

result = response.json()
print(f"Capture créée: {result['id']}")
print(f"Lien téléchargement: {result['download_url']}")
```

#### Envoyer un SMS

```python
import requests

response = requests.post("http://localhost:8000/api/send-sms", json={
    "phone": "+33123456789",
    "capture_id": "capture-uuid"
})

result = response.json()
print(f"SMS envoyé: {result['sms_id']}")
```

#### Upload fond d'écran (Admin)

```python
import requests

# Se connecter
login = requests.post("http://localhost:8000/admin/login", json={
    "username": "admin",
    "password": "changeme123!"
})
token = login.json()["access_token"]

headers = {"Authorization": f"Bearer {token}"}

# Upload fond
with open("background.jpg", "rb") as f:
    files = {"file": f}
    data = {
        "name": "Fond plage",
        "is_active": True,
        "display_order": 1
    }
    response = requests.post(
        "http://localhost:8000/admin/backgrounds", 
        files=files, 
        data=data,
        headers=headers
    )

result = response.json()
print(f"Fond créé: {result['id']}")
```

## 🏗️ Architecture

### Structure du Projet

```
selfie-kiosk-backend/
├── main.py                 # Point d'entrée FastAPI
├── config.py              # Configuration et settings
├── database.py            # Configuration base de données
├── models.py              # Modèles Pydantic
├── requirements.txt       # Dépendances Python
├── .env.example          # Exemple configuration
├── README.md             # Documentation
├── routers/              # Endpoints API
│   ├── __init__.py
│   ├── health.py         # Health checks
│   ├── public.py         # API publique
│   ├── captures.py       # Gestion captures
│   ├── backgrounds.py    # Gestion fonds
│   ├── admin.py          # Panel admin
│   └── config.py         # Configuration
├── services/             # Services métier
│   ├── __init__.py
│   ├── storage.py        # Service stockage OVH
│   ├── sms.py           # Service SMS OVH
│   └── sync.py          # Service synchronisation
├── utils/               # Utilitaires
│   ├── __init__.py
│   ├── validation.py    # Fonctions validation
│   ├── files.py         # Gestion fichiers
│   └── logger.py        # Configuration logs
├── scripts/             # Scripts déploiement
│   ├── install.sh
│   ├── selfie-kiosk.service
│   └── backup.sh
└── logs/               # Logs application
    └── app.log
```

### Flux de Données

#### Mode Online
1. **Capture** → Validation → Sauvegarde locale → Upload cloud immédiat
2. **SMS** → Génération lien → Envoi via OVH API
3. **Téléchargement** → Depuis stockage cloud ou local

#### Mode Offline  
1. **Capture** → Validation → Sauvegarde locale → Ajout queue Redis
2. **SMS** → Différé (stocké en base)
3. **Synchronisation** → Retry automatique dès reconnexion
4. **Téléchargement** → Depuis stockage local

### Base de Données

#### Tables Principales

```sql
-- Captures de selfies
CREATE TABLE captures (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP,
    phone TEXT,
    email TEXT,
    photo_local_path TEXT,
    photo_remote_url TEXT,
    background_id TEXT,
    is_synced BOOLEAN DEFAULT FALSE,
    sync_attempts INTEGER DEFAULT 0,
    download_token TEXT,
    sms_sent BOOLEAN DEFAULT FALSE,
    file_size INTEGER
);

-- Fonds d'écran
CREATE TABLE backgrounds (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP
);

-- Configuration
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP
);

-- Logs système
CREATE TABLE system_logs (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP,
    level TEXT,
    component TEXT,
    message TEXT,
    correlation_id TEXT
);
```

## 🔧 Configuration Avancée

### Variables d'Environnement Complètes

```env
# === BASE DE DONNÉES ===
DATABASE_URL=sqlite+aiosqlite:///./selfie_kiosk.db

# === REDIS ===
REDIS_URL=redis://localhost:6379/0
REDIS_QUEUE_NAME=selfie_sync_queue

# === SÉCURITÉ ===
SECRET_KEY=your-super-secret-key-256-bits
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# === ADMIN PAR DÉFAUT ===
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme123!

# === CORS ===
ALLOWED_ORIGINS=["*"]

# === STOCKAGE LOCAL ===
UPLOAD_DIR=./uploads
MAX_FILE_SIZE=10485760
ALLOWED_EXTENSIONS=["jpg","jpeg","png"]

# === OVH API CONFIGURATION ===
OVH_ENDPOINT=ovh-eu
OVH_APPLICATION_KEY=your-application-key
OVH_APPLICATION_SECRET=your-application-secret
OVH_CONSUMER_KEY=your-consumer-key

# === OVH SMS ===
SMS_SERVICE_NAME=sms-XXXXXX-1
SMS_SENDER=SelfieKiosk

# === OVH OBJECT STORAGE ===
SWIFT_AUTH_URL=https://auth.cloud.ovh.net/v3
SWIFT_USERNAME=user-XXXXXXXXX
SWIFT_PASSWORD=your-password
SWIFT_TENANT_NAME=XXXXXXXXXXXXXXXXX
SWIFT_REGION=GRA
SWIFT_CONTAINER=selfie-photos

# === URL PUBLIQUE ===
PUBLIC_BASE_URL=http://localhost:8000

# === CONFIGURATION APP ===
COUNTDOWN_SECONDS=3
WELCOME_MESSAGE=Bienvenue ! Prenez votre selfie !
SUCCESS_MESSAGE=Photo prise avec succès !

# === GOOGLE REVIEWS ===
GOOGLE_REVIEW_URL=https://g.page/your-business/review
GOOGLE_REVIEW_ENABLED=false

# === SYNCHRONISATION ===
SYNC_RETRY_ATTEMPTS=5
SYNC_RETRY_DELAY=60

# === NETTOYAGE AUTO ===
AUTO_DELETE_DAYS=30
AUTO_DELETE_ENABLED=true

# === LOGGING ===
LOG_LEVEL=INFO
LOG_FILE=./logs/app.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5

# === MONITORING ===
HEALTH_CHECK_INTERVAL=60
```

### Configuration OVH

#### 1. Créer les clés API OVH

1. Aller sur https://api.ovh.com/createToken/
2. Sélectionner vos droits :
   - `GET /sms/*` 
   - `POST /sms/*`
   - `GET /cloud/*`
   - `POST /cloud/*`
   - `PUT /cloud/*`
   - `DELETE /cloud/*`

3. Noter les clés générées dans `.env`

#### 2. Configurer Object Storage

```bash
# Créer un conteneur Object Storage
curl -X PUT \
  https://storage.gra.cloud.ovh.net/v1/AUTH_xxxxxx/selfie-photos \
  -H "X-Auth-Token: your-token" \
  -H "X-Container-Read: .r:*"
```

## 🚨 Monitoring et Maintenance

### Health Checks

```bash
# Check simple
curl http://localhost:8000/health/ping

# Check complet
curl http://localhost:8000/health

# Métriques système
curl http://localhost:8000/health/metrics
```

### Logs

```bash
# Logs en temps réel
tail -f logs/app.log

# Logs avec filtre par niveau
grep "ERROR" logs/app.log

# Logs par composant
grep "component.*sms" logs/app.log
```

### Nettoyage Automatique

Le système nettoie automatiquement :
- **Photos locales** après synchronisation
- **Données anciennes** selon `AUTO_DELETE_DAYS`
- **Logs rotatifs** selon `LOG_BACKUP_COUNT`

### Scripts de Maintenance

```bash
# Backup base de données
./scripts/backup.sh

# Nettoyage manuel
python -c "
import asyncio
from database import db_helper
asyncio.run(db_helper.cleanup_old_data(30))
"

# Test de tous les services
python -c "
import asyncio
from services.storage import StorageService
from services.sms import SMSService

async def test_all():
    storage = StorageService()
    sms = SMSService()
    
    print('Storage:', await storage.test_connectivity())
    print('SMS:', await sms.test_connection())

asyncio.run(test_all())
"
```

## 🔒 Sécurité

### Mesures Implémentées

- **JWT Authentication** pour l'admin
- **Validation stricte** des données d'entrée
- **Rate limiting** (100 req/min par IP)
- **CORS configuré** avec origines autorisées
- **Sanitization** des noms de fichiers
- **Validation MIME** des uploads
- **Secrets externalisés** via variables d'env

### Recommandations Production

```bash
# 1. Changer les secrets par défaut
openssl rand -hex 32  # Pour SECRET_KEY
pwgen -s 16 1         # Pour ADMIN_PASSWORD

# 2. Configurer le firewall
sudo ufw allow 8000/tcp
sudo ufw enable

# 3. Limiter les permissions fichiers
chmod 600 .env
chmod -R 755 uploads/
chown -R www-data:www-data uploads/

# 4. Configurer les sauvegardes automatiques
crontab -e
# Ajouter: 0 2 * * * /path/to/backup.sh
```

## 📊 Performance

### Optimisations Implémentées

- **Async/await** partout pour concurrence
- **Connection pooling** base de données
- **Cache Redis** pour files d'attente
- **Compression images** automatique
- **Lazy loading** des fonds d'écran
- **Pagination** des listes
- **Index optimisés** sur colonnes fréquentes

### Métriques Cibles

- **Temps de capture** : < 2 secondes
- **Upload cloud** : < 5 secondes
- **Envoi SMS** : < 3 secondes
- **Utilisation mémoire** : < 500 MB
- **Disponibilité** : > 99.5%

## 🧪 Tests

### Tests Manuels

```bash
# Test capture complète
curl -X POST http://localhost:8000/api/capture \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+33123456789",
    "photo_base64": "base64-image-data"
  }'

# Test SMS
curl -X POST http://localhost:8000/api/send-sms \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+33123456789",
    "capture_id": "uuid"
  }'
```

### Tests Automatisés (optionnel)

```bash
# Installer pytest
pip install pytest pytest-asyncio httpx

# Lancer les tests
pytest tests/ -v

# Tests avec couverture
pytest --cov=. tests/
```

## 🚀 Déploiement Production

### Docker (optionnel)

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Service Systemd

```ini
[Unit]
Description=Selfie Kiosk API
After=network.target redis.service

[Service]
Type=exec
User=www-data
Group=www-data
WorkingDirectory=/var/www/selfie-kiosk
Environment=PATH=/var/www/selfie-kiosk/venv/bin
ExecStart=/var/www/selfie-kiosk/venv/bin/gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## 💡 Dépannage

### Problèmes Courants

#### Base de données locked
```bash
# Vérifier les processus utilisant la DB
sudo lsof /path/to/selfie_kiosk.db
# Redémarrer le service
sudo systemctl restart selfie-kiosk
```

#### OVH API erreur 403
```bash
# Vérifier les droits des clés API
# Régénérer consumer_key si nécessaire
```

#### Redis connexion refusée
```bash
sudo systemctl status redis
sudo systemctl start redis
```

#### Espace disque plein
```bash
# Nettoyer uploads anciens
find uploads/ -name "*.jpg" -mtime +7 -delete
# Ou lancer le nettoyage automatique
```

### Logs de Debug

```python
# Activer debug dans config.py
LOG_LEVEL=DEBUG

# Ou temporairement
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📞 Support

Pour toute question ou problème :

1. **Vérifier** cette documentation
2. **Consulter** les logs : `logs/app.log`
3. **Tester** la connectivité : `/health`
4. **Vérifier** la configuration : `/admin/config`

## 📝 Changelog

### v1.0.0 (2024-01-15)
- ✅ Implémentation complète API FastAPI
- ✅ Gestion offline avec Redis
- ✅ Intégrations OVH (SMS + Storage)
- ✅ Panel admin avec JWT
- ✅ Documentation complète
- ✅ Health checks et monitoring
- ✅ Tests et validation

---

**Développé avec ❤️ pour des kiosques selfie performants et autonomes**