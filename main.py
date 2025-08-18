from typing import Annotated
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form ,Body , APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials , OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional, List
import logging
from datetime import datetime, timedelta
import base64
import uuid
import os
import json
from passlib.context import CryptContext
from jose import jwt, JWTError
from database import database 
from config import settings
from utils.logger import setup_logger



####router 

from routers.captures import router as captures_router

router = APIRouter(
    prefix  = "/apie",
    tags = ["public"]
)

router.include_router(captures_router)

####


# Configuration du logging
setup_logger()
logger = logging.getLogger(__name__)

# Sécurité
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# =============================================================================
# MODÈLES PYDANTIC
# =============================================================================

class CaptureRequest(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    photo_base64: str
    background_id: Optional[str] = None

class CaptureResponse(BaseModel):
    success: bool = True
    id: str
    message: str
    download_url: Optional[str] = None
    qr_code_url: Optional[str] = None
    mode: str = "online"
    timestamp: datetime

class SMSRequest(BaseModel):
    phone: str
    capture_id: str

class SMSResponse(BaseModel):
    success: bool = True
    message: str
    sms_id: Optional[str] = None
    timestamp: datetime

class Background(BaseModel):
    id: str
    name: str
    file_url: str
    file_size: int
    is_active: bool = True
    display_order: int = 0
    created_at: datetime

class BackgroundList(BaseModel):
    success: bool = True
    backgrounds: List[Background]
    total: int
    message: str = "Liste des fonds récupérée"

class LoginRequest(BaseModel):
    username: Annotated[str | None, Body()]
    password: Annotated[str | None, Body()]

class LoginResponse(BaseModel):
    success: bool = True
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    message: str = "Connexion réussie"

class ConfigResponse(BaseModel):
    success: bool = True
    config: dict
    message: str = "Configuration récupérée"

class StatsResponse(BaseModel):
    success: bool = True
    stats: dict
    timestamp: datetime
    message: str = "Statistiques récupérées"

class TestResponse(BaseModel):
    success: bool
    message: str
    details: Optional[dict] = None
    timestamp: datetime

# =============================================================================
# UTILITAIRES AUTH
# =============================================================================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Fonctions utilitaires

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt



def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Token invalide")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide")



async def get_current_user(username: str = Depends(verify_token)):
   
    try:
        # Récupérer l'utilisateur depuis la base de données
        db_user = await database.fetch_one(
            "SELECT * FROM admin_users WHERE username = :username AND is_active = 1",
            {"username": username}
        )
        
        if not db_user:
            raise HTTPException(
                status_code=401, 
                detail="Utilisateur non trouvé ou inactif"
            )
        
        # Convertir en dictionnaire pour faciliter l'usage
        current_user = {
            "id": db_user["id"],
            "username": db_user["username"],
            "is_active": db_user["is_active"],
            "last_login": db_user["last_login"],
            "created_at": db_user["created_at"]
        }
        
        return current_user
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'utilisateur: {e}")
        raise HTTPException(
            status_code=401, 
            detail="Erreur d'authentification"
        )

# =============================================================================
# APPLICATION FASTAPI
# =============================================================================

app = FastAPI(
    title="Selfie Kiosk API",
    description="API complète pour application selfie kiosque autonome",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configuration CORS

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# ENDPOINTS PUBLICS
# =============================================================================

@app.get("/")
async def root():
    return {
        "name": "Selfie Kiosk API",
        "version": "1.0.0",
        "status": "running",
        "environment": settings.ENVIRONMENT,
        "endpoints": {
            "public": {
                "capture": "POST /api/capture",
                "backgrounds": "GET /api/backgrounds",
                "send_sms": "POST /api/send-sms",
                "download": "GET /api/download/{id}"
            },
            "admin": {
                "login": "POST /admin/login",
                "config": "GET/PUT /admin/config",
                "backgrounds": "POST /admin/backgrounds",
                "backgrounds": "/DELETE /admin/backgrounds/{id}",
                "stats": "GET /admin/stats",
                "export": "GET /admin/export/excel",
                "tests": "POST /admin/test/*"
            }
        },
        "docs": "/docs",
        "timestamp": datetime.now()
    }

@app.get("/health")
async def health_check():
    """Check de santé"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "config_loaded": True,
        "upload_dir": settings.UPLOAD_DIR
    }

@app.post("/api/capture", response_model=CaptureResponse, tags=["Public"])
async def create_capture(capture_data: CaptureRequest):
    try:
        capture_id = str(uuid.uuid4())
        logger.info(f"📸 Nouvelle capture: {capture_id}")
        if not capture_data.photo_base64:
            raise HTTPException(status_code=400, detail="Photo base64 requise")
        try:
            photo_data = capture_data.photo_base64
            if photo_data.startswith('data:image'):
                photo_data = photo_data.split(',')[1]

            decoded_data = base64.b64decode(photo_data)
            if len(decoded_data) < 100:
                raise HTTPException(status_code=400, detail="Image trop petite")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Format base64 invalide: {str(e)}")

        # Sauvegarder
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        file_path = os.path.join(settings.UPLOAD_DIR, f"{capture_id}.jpg")
        with open(file_path, "wb") as f:
            f.write(decoded_data)

        logger.info(f"✅ Fichier sauvé: {file_path} ({len(decoded_data)} bytes)")

        download_url = f"{settings.PUBLIC_BASE_URL}/api/download/{capture_id}"
        qr_code_url = f"{settings.PUBLIC_BASE_URL}/api/qr/{capture_id}"

        return CaptureResponse(
            id=capture_id,
            message="Capture créée avec succès !",
            download_url=download_url,
            qr_code_url=qr_code_url,
            timestamp=datetime.now()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur capture: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne")

@app.get("/api/backgrounds", response_model=BackgroundList, tags=["Public"])
async def list_backgrounds():
    """
    GET /api/backgrounds - Liste des fonds d'écran
    """
    try:
        backgrounds_dir = os.path.join(settings.UPLOAD_DIR, "backgrounds")
        backgrounds = []

        if os.path.exists(backgrounds_dir):
            for filename in os.listdir(backgrounds_dir):
                if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    file_path = os.path.join(backgrounds_dir, filename)
                    stat = os.stat(file_path)

                    backgrounds.append(Background(
                        id=filename.split('.')[0],
                        name=filename,
                        file_url=f"{settings.PUBLIC_BASE_URL}/api/backgrounds/{filename.split('.')[0]}/file",
                        file_size=stat.st_size,
                        is_active=True,
                        display_order=0,
                        created_at=datetime.fromtimestamp(stat.st_ctime)
                    ))

        return BackgroundList(
            backgrounds=backgrounds,
            total=len(backgrounds)
        )

    except Exception as e:
        logger.error(f"❌ Erreur liste backgrounds: {e}")
        raise HTTPException(status_code=500, detail="Erreur récupération fonds")


"""
eto mila verifications 

"""

@app.post("/api/send-sms", response_model=SMSResponse, tags=["Public"])
async def send_sms(sms_request: SMSRequest):
    """
    POST /api/send-sms - Envoyer SMS avec lien téléchargement
    """
    try:
        logger.info(f"📱 Envoi SMS vers {sms_request.phone[:4]}**** pour capture {sms_request.capture_id}")

        # Vérifier que la capture existe
        file_path = os.path.join(settings.UPLOAD_DIR, f"{sms_request.capture_id}.jpg")
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Capture non trouvée")

        # Simuler envoi SMS (en production: intégrer API OVH)
        download_url = f"{settings.PUBLIC_BASE_URL}/api/download/{sms_request.capture_id}"
        sms_message = f"Votre photo selfie est prête ! Téléchargez-la ici: {download_url}"

        # TODO: Intégrer vraie API SMS
        fake_sms_id = f"sms_{uuid.uuid4().hex[:8]}"

        logger.info(f"✅ SMS simulé envoyé: {fake_sms_id}")

        return SMSResponse(
            message="SMS envoyé avec succès",
            sms_id=fake_sms_id,
            timestamp=datetime.now()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur SMS: {e}")
        raise HTTPException(status_code=500, detail="Erreur envoi SMS")

@app.get("/api/download/{capture_id}", tags=["Public"])
async def download_photo(capture_id: str):
    """
    GET /api/download/{id} - Télécharger une photo
    """
    try:
        file_path = os.path.join(settings.UPLOAD_DIR, f"{capture_id}.jpg")

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Photo non trouvée")

        logger.info(f"📥 Téléchargement: {capture_id}")

        return FileResponse(
            path=file_path,
            filename=f"selfie_{capture_id[:8]}.jpg",
            media_type="image/jpeg"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur téléchargement: {e}")
        raise HTTPException(status_code=500, detail="Erreur téléchargement")

















# =============================================================================
# ENDPOINTS ADMIN (AUTHENTIFIÉS)
# =============================================================================

###################################################


#####################################
@app.post("/admin/login", response_model=LoginResponse, tags=["Admin"])
async def admin_login(login_request: LoginRequest):
    try:
        # Récupérer l'utilisateur depuis la base de données
        db_user = await database.fetch_one(
            "SELECT * FROM admin_users WHERE username = :username AND is_active = 1",
            {"username": login_request.username}
        )
        
        if not db_user:
            logger.warning(f"Tentative de connexion échouée: {login_request.username}")
            raise HTTPException(status_code=401, detail="Identifiants incorrects")
        
        # Vérifier le mot de passe
        if not verify_password(login_request.password, db_user["password_hash"]):
            logger.warning(f"Mot de passe incorrect pour: {login_request.username}")
            raise HTTPException(status_code=401, detail="Mot de pass incorrects")
        
        # Mettre à jour la dernière connexion
        await database.execute(
            "UPDATE admin_users SET last_login = :now WHERE id = :user_id",
            {"now": datetime.now(), "user_id": db_user["id"]}
        )
        
        # Créer token
        access_token = create_access_token(data={"sub": login_request.username})
        logger.info(f"✅ Connexion admin réussie: {login_request.username}")
        
        return LoginResponse(
            access_token=access_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur login: {e}")
        raise HTTPException(status_code=500, detail="Erreur connexion")

@app.get("/admin/config", response_model=ConfigResponse, tags=["Admin"])
async def get_config(current_user: str = Depends(get_current_user)):
    try:
        config = {
            "welcome_message": settings.WELCOME_MESSAGE,
            "success_message": settings.SUCCESS_MESSAGE,
            "countdown_seconds": settings.COUNTDOWN_SECONDS,
            "admin_username": settings.ADMIN_USERNAME,
            "upload_dir": settings.UPLOAD_DIR,
            "environment": settings.ENVIRONMENT,
            "public_base_url": settings.PUBLIC_BASE_URL
        }

        return ConfigResponse(config=config)

    except Exception as e:
        logger.error(f"❌ Erreur config: {e}")
        raise HTTPException(status_code=500, detail="Erreur récupération config")

@app.put("/admin/config", tags=["Admin"])
async def update_config(
    config_update: dict,
    current_user: str = Depends(get_current_user)
):
 
    try:
        logger.info(f"🔧 Mise à jour config par {current_user}")

        # En production: sauvegarder en base de données
        # Ici on simule juste la validation

        allowed_fields = [
            "welcome_message", "success_message", "countdown_seconds"
        ]

        updated_fields = []
        for key, value in config_update.items():
            if key in allowed_fields:
                updated_fields.append(key)
                # TODO: Mettre à jour les settings réels

        logger.info(f"✅ Config mise à jour: {updated_fields}")

        return {
            "success": True,
            "message": f"Configuration mise à jour: {', '.join(updated_fields)}",
            "updated_fields": updated_fields
        }

    except Exception as e:
        logger.error(f"❌ Erreur mise à jour config: {e}")
        raise HTTPException(status_code=500, detail="Erreur mise à jour")

@app.post("/admin/backgrounds", tags=["Admin"])
async def upload_background(
    name: str = Form(...),
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user)
):
    """
    POST /admin/backgrounds - Upload nouveau fond
    """
    try:
        if not file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            raise HTTPException(status_code=400, detail="Format non supporté")

        # Créer dossier backgrounds
        backgrounds_dir = os.path.join(settings.UPLOAD_DIR, "backgrounds")
        os.makedirs(backgrounds_dir, exist_ok=True)

        # Générer nom unique
        background_id = str(uuid.uuid4())
        file_ext = os.path.splitext(file.filename)[1]
        filename = f"{background_id}{file_ext}"
        file_path = os.path.join(backgrounds_dir, filename)

        # Sauvegarder
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"✅ Nouveau fond uploadé: {name} ({len(content)} bytes)")

        return {
            "success": True,
            "message": "Fond d'écran uploadé avec succès",
            "background_id": background_id,
            "filename": filename,
            "size_bytes": len(content),
            "file_url": f"{settings.PUBLIC_BASE_URL}/api/backgrounds/{background_id}/file"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur upload background: {e}")
        raise HTTPException(status_code=500, detail="Erreur upload")

@app.delete("/admin/backgrounds/{background_id}", tags=["Admin"])
async def delete_background(
    background_id: str,
    current_user: str = Depends(get_current_user)
):
    """
    DELETE /admin/backgrounds/{id} - Supprimer un fond
    """
    try:
        backgrounds_dir = os.path.join(settings.UPLOAD_DIR, "backgrounds")

        # Chercher le fichier
        deleted = False
        for filename in os.listdir(backgrounds_dir):
            if filename.startswith(background_id):
                file_path = os.path.join(backgrounds_dir, filename)
                os.remove(file_path)
                deleted = True
                logger.info(f"🗑️  Fond supprimé: {filename}")
                break

        if not deleted:
            raise HTTPException(status_code=404, detail="Fond non trouvé")

        return {
            "success": True,
            "message": "Fond d'écran supprimé avec succès",
            "background_id": background_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur suppression background: {e}")
        raise HTTPException(status_code=500, detail="Erreur suppression")

@app.get("/admin/stats", response_model=StatsResponse, tags=["Admin"])
async def get_stats(current_user: str = Depends(get_current_user)):
    """
    GET /admin/stats - Statistiques système
    """
    try:
        upload_dir = settings.UPLOAD_DIR

        # Compter les captures
        capture_count = 0
        total_size = 0

        if os.path.exists(upload_dir):
            for filename in os.listdir(upload_dir):
                if filename.endswith('.jpg'):
                    capture_count += 1
                    file_path = os.path.join(upload_dir, filename)
                    total_size += os.path.getsize(file_path)

        # Compter les backgrounds
        backgrounds_dir = os.path.join(upload_dir, "backgrounds")
        background_count = 0
        if os.path.exists(backgrounds_dir):
            background_count = len([f for f in os.listdir(backgrounds_dir)
                                 if f.lower().endswith(('.jpg', '.jpeg', '.png'))])

        stats = {
            "total_captures": capture_count,
            "total_backgrounds": background_count,
            "storage_used_mb": round(total_size / (1024 * 1024), 2),
            "upload_directory": upload_dir,
            "environment": settings.ENVIRONMENT,
            "uptime_info": "Service running"
        }

        return StatsResponse(
            stats=stats,
            timestamp=datetime.now()
        )

    except Exception as e:
        logger.error(f"❌ Erreur stats: {e}")
        raise HTTPException(status_code=500, detail="Erreur récupération stats")


"""
export exel mila jerena 
"""



@app.get("/admin/export/excel", tags=["Admin"])
async def export_data(current_user: str = Depends(get_current_user)):
    """
    GET /admin/export/excel - Export données Excel
    """
    try:
        # Simuler export Excel
        export_data = {
            "export_type": "excel",
            "generated_at": datetime.now(),
            "total_records": 0,
            "note": "Fonctionnalité d'export à implémenter avec openpyxl"
        }

        logger.info(f"📊 Export demandé par {current_user}")

        return {
            "success": True,
            "message": "Export généré (simulation)",
            "data": export_data
        }

    except Exception as e:
        logger.error(f"❌ Erreur export: {e}")
        raise HTTPException(status_code=500, detail="Erreur export")



"""
text vps mila jerena 

"""
@app.post("/admin/test/vps", response_model=TestResponse, tags=["Admin"])
async def test_vps_connection(current_user: str = Depends(get_current_user)):
    """
    POST /admin/test/vps - Test connexion VPS
    """
    try:
        # Simuler test VPS
        logger.info(f"🔍 Test VPS demandé par {current_user}")

        # TODO: Implémenter vraie connexion VPS
        test_result = {
            "vps_host": "simulation",
            "connection_status": "success",
            "response_time_ms": 150,
            "storage_available": True
        }

        return TestResponse(
            success=True,
            message="Test VPS réussi (simulation)",
            details=test_result,
            timestamp=datetime.now()
        )

    except Exception as e:
        logger.error(f"❌ Erreur test VPS: {e}")
        raise HTTPException(status_code=500, detail="Erreur test VPS")

@app.post("/admin/test/sms", response_model=TestResponse, tags=["Admin"])
async def test_sms_service(
    phone: str = Form(...),
    current_user: str = Depends(get_current_user)
):
    """
    POST /admin/test/sms - Test service SMS
    """
    try:
        logger.info(f"📱 Test SMS vers {phone[:4]}**** demandé par {current_user}")

        # TODO: Implémenter vraie API SMS
        test_result = {
            "phone_number": f"{phone[:4]}****",
            "sms_service": "simulation",
            "status": "sent",
            "sms_id": f"test_{uuid.uuid4().hex[:8]}"
        }

        return TestResponse(
            success=True,
            message="Test SMS réussi (simulation)",
            details=test_result,
            timestamp=datetime.now()
        )

    except Exception as e:
        logger.error(f"❌ Erreur test SMS: {e}")
        raise HTTPException(status_code=500, detail="Erreur test SMS")

# =============================================================================
# ENDPOINTS UTILITAIRES
# =============================================================================

@app.get("/api/test/sample-image", tags=["Utilities"])
async def get_sample_image():
    """Image de test pour les démonstrations"""
    try:
        from PIL import Image, ImageDraw
        import io

        img = Image.new('RGB', (300, 200), color='lightblue')
        draw = ImageDraw.Draw(img)
        draw.rectangle([20, 20, 280, 180], fill='lightgreen', outline='darkgreen', width=2)
        draw.ellipse([50, 50, 250, 150], fill='yellow', outline='orange', width=3)

        try:
            draw.text((100, 90), "SELFIE TEST", fill='red')
        except:
            pass

        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=80)
        img_base64 = base64.b64encode(buffer.getvalue()).decode()

        return {
            "success": True,
            "sample_base64": img_base64,
            "size_bytes": len(buffer.getvalue()),
            "usage": "Utilisez cette image pour tester /api/capture"
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "fallback_base64": "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwA/wA=="
        }

@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """Gestionnaire d'erreurs général"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": str(exc),
            "type": type(exc).__name__
        }
    )

if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Démarrage Selfie Kiosk API - Version Complète")
    logger.info(f"📖 Documentation: http://localhost:8000/docs")
    logger.info(f"👤 Admin: {settings.ADMIN_USERNAME} / {settings.ADMIN_PASSWORD}")
    uvicorn.run(
        "complete_main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
