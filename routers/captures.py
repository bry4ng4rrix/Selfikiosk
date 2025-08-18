from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query
from fastapi.responses import FileResponse
from datetime import datetime, timedelta
from typing import Optional
import os
import base64
import uuid
import logging
import asyncio

from database import get_db, Database, captures
from models import (
    CaptureCreate, CaptureResponse, CaptureStatus, CaptureList,
    SMSRequest, SMSResponse, StatusEnum, ModeEnum, PaginationParams
)
from config import settings
from services.storage import StorageService
from services.sms import SMSService 
from services.sync import SyncService
from utils.validation import validate_phone, validate_image
from utils.files import save_uploaded_file, generate_qr_code

router = APIRouter()
logger = logging.getLogger(__name__)

# Services
storage_service = StorageService()
sms_service = SMSService()
sync_service = SyncService()

@router.post("/capture", response_model=CaptureResponse)
async def create_capture(
    capture_data: CaptureCreate,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db)
):
 
    try:
        # Génération des IDs
        capture_id = str(uuid.uuid4())
        download_token = str(uuid.uuid4()).replace('-', '')[:16]
        
        # Validation de l'image base64
        try:
            image_data = base64.b64decode(capture_data.photo_base64)
            if not validate_image(image_data):
                raise HTTPException(status_code=400, detail="Format d'image invalide")
        except Exception as e:
            raise HTTPException(status_code=400, detail="Données image invalides")
        
        # Sauvegarde locale immédiate
        local_filename = f"{capture_id}.jpg"
        local_path = os.path.join(settings.UPLOAD_DIR, local_filename)
        
        with open(local_path, "wb") as f:
            f.write(image_data)
        
        file_size = len(image_data)
        
        # Détecter le mode (online/offline)
        is_online = await storage_service.test_connectivity()
        mode = ModeEnum.ONLINE if is_online else ModeEnum.OFFLINE
        
        # Sauvegarde en base de données
        await db.execute(
            captures.insert().values(
                id=capture_id,
                phone=capture_data.phone,
                email=capture_data.email,
                background_id=capture_data.background_id,
                photo_local_path=local_path,
                file_size=file_size,
                download_token=download_token,
                download_expires_at=datetime.now() + timedelta(days=7),
                is_synced=False,
                created_at=datetime.now()
            )
        )
        
        # Log de l'événement
        await db.log_event(
            level="INFO",
            component="capture",
            message=f"Nouvelle capture créée en mode {mode.value}",
            correlation_id=capture_id
        )
        
        # Traitement asynchrone selon le mode
        if is_online:
            # Mode online: upload immédiat
            background_tasks.add_task(
                process_capture_online,
                capture_id,
                capture_data.phone
            )
        else:
            # Mode offline: ajouter à la queue
            await sync_service.add_to_queue(capture_id)
        
        # URLs de réponse
        download_url = f"{settings.PUBLIC_BASE_URL}/api/download/{download_token}"
        qr_code_url = f"{settings.PUBLIC_BASE_URL}/api/qr/{download_token}"
        
        return CaptureResponse(
            id=capture_id,
            download_url=download_url,
            qr_code_url=qr_code_url,
            mode=mode,
            message="Capture créée avec succès"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la création de capture: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

async def process_capture_online(capture_id: str, phone: Optional[str]):
    """Traite une capture en mode online"""
    try:
        db = Database()
        
        # Récupérer les données de la capture
        capture = await db.fetch_one(
            "SELECT * FROM captures WHERE id = :id", {"id": capture_id}
        )
        
        if not capture:
            logger.error(f"Capture {capture_id} non trouvée")
            return
        
        # Upload vers le stockage distant
        remote_url = await storage_service.upload_file(
            capture["photo_local_path"],
            f"captures/{datetime.now():%Y%m%d}/{capture_id}.jpg"
        )
        
        if remote_url:
            # Marquer comme synchronisé
            await db.execute(
                "UPDATE captures SET photo_remote_url = :url, is_synced = 1, "
                "synced_at = :now WHERE id = :id",
                {
                    "url": remote_url,
                    "now": datetime.now(),
                    "id": capture_id
                }
            )
            
            # Supprimer le fichier local si synchronisé
            if os.path.exists(capture["photo_local_path"]):
                os.remove(capture["photo_local_path"])
            
            # Envoi SMS si numéro fourni
            if phone:
                await send_sms_notification(capture_id, phone)
            
            logger.info(f"Capture {capture_id} traitée avec succès")
        else:
            # Échec upload: ajouter à la queue pour retry
            await sync_service.add_to_queue(capture_id)
            
    except Exception as e:
        logger.error(f"Erreur traitement capture {capture_id}: {e}")
        # Ajouter à la queue pour retry
        await sync_service.add_to_queue(capture_id)

@router.post("/send-sms", response_model=SMSResponse)
async def send_sms(
    sms_request: SMSRequest,
    db: Database = Depends(get_db)
):
    """
    Envoie un SMS avec le lien de téléchargement
    """
    try:
        # Vérifier que la capture existe
        capture = await db.fetch_one(
            "SELECT * FROM captures WHERE id = :id",
            {"id": sms_request.capture_id}
        )
        
        if not capture:
            raise HTTPException(status_code=404, detail="Capture non trouvée")
        
        # Valider le numéro de téléphone
        phone = validate_phone(sms_request.phone)
        
        # Créer le lien de téléchargement
        download_url = f"{settings.PUBLIC_BASE_URL}/api/download/{capture['download_token']}"
        
        # Message SMS
        message = await db.get_config("sms_template", 
            f"Votre photo selfie est prête ! Téléchargez-la ici: {download_url}"
        )
        message = message.format(url=download_url)
        
        # Envoi SMS
        sms_id = await sms_service.send_sms(phone, message)
        
        if sms_id:
            # Mettre à jour la capture
            await db.execute(
                "UPDATE captures SET sms_sent = 1, sms_sent_at = :now WHERE id = :id",
                {"now": datetime.now(), "id": sms_request.capture_id}
            )
            
            # Log de l'événement
            await db.log_event(
                level="INFO",
                component="sms",
                message=f"SMS envoyé avec succès",
                correlation_id=sms_request.capture_id
            )
            
            return SMSResponse(
                sms_id=sms_id,
                phone=phone,
                message="SMS envoyé avec succès"
            )
        else:
            raise HTTPException(status_code=500, detail="Échec de l'envoi SMS")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur envoi SMS: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de l'envoi SMS")

async def send_sms_notification(capture_id: str, phone: str):
    """Fonction helper pour envoyer une notification SMS"""
    try:
        sms_request = SMSRequest(phone=phone, capture_id=capture_id)
        db = Database()
        
        # Utiliser la fonction send_sms existante
        # Note: Cette fonction sera appelée en arrière-plan
        await send_sms(sms_request, db)
        
    except Exception as e:
        logger.error(f"Erreur notification SMS pour {capture_id}: {e}")

@router.get("/download/{token}")
async def download_photo(token: str, db: Database = Depends(get_db)):
    """
    Télécharge une photo via son token
    """
    try:
        # Rechercher la capture par token
        capture = await db.fetch_one(
            "SELECT * FROM captures WHERE download_token = :token",
            {"token": token}
        )
        
        if not capture:
            raise HTTPException(status_code=404, detail="Photo non trouvée")
        
        # Vérifier l'expiration
        if capture["download_expires_at"] and capture["download_expires_at"] < datetime.now():
            raise HTTPException(status_code=410, detail="Lien de téléchargement expiré")
        
        # Déterminer le fichier à servir
        file_path = None
        
        # Essayer d'abord le fichier distant (si synchronisé)
        if capture["is_synced"] and capture["photo_remote_url"]:
            # Rediriger vers l'URL distante ou télécharger depuis le stockage distant
            file_path = await storage_service.get_file_path(capture["photo_remote_url"])
        
        # Sinon utiliser le fichier local
        if not file_path and capture["photo_local_path"] and os.path.exists(capture["photo_local_path"]):
            file_path = capture["photo_local_path"]
        
        if not file_path:
            raise HTTPException(status_code=404, detail="Fichier photo non disponible")
        
        # Log du téléchargement
        await db.log_event(
            level="INFO",
            component="download",
            message="Photo téléchargée",
            correlation_id=capture["id"]
        )
        
        return FileResponse(
            path=file_path,
            filename=f"selfie_{capture['id'][:8]}.jpg",
            media_type="image/jpeg"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur téléchargement photo {token}: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors du téléchargement")

@router.get("/qr/{token}")
async def get_qr_code(token: str, db: Database = Depends(get_db)):
    """
    Génère et retourne un QR code pour le téléchargement
    """
    try:
        # Vérifier que la capture existe
        capture = await db.fetch_one(
            "SELECT * FROM captures WHERE download_token = :token",
            {"token": token}
        )
        
        if not capture:
            raise HTTPException(status_code=404, detail="Photo non trouvée")
        
        # URL de téléchargement
        download_url = f"{settings.PUBLIC_BASE_URL}/api/download/{token}"
        
        # Générer le QR code
        qr_file_path = await generate_qr_code(download_url, token)
        
        return FileResponse(
            path=qr_file_path,
            filename=f"qr_{token}.png",
            media_type="image/png"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur génération QR code {token}: {e}")
        raise HTTPException(status_code=500, detail="Erreur génération QR code")

@router.get("/status/{capture_id}", response_model=CaptureStatus)
async def get_capture_status(capture_id: str, db: Database = Depends(get_db)):
    """
    Récupère le statut d'une capture
    """
    try:
        capture = await db.fetch_one(
            "SELECT * FROM captures WHERE id = :id", {"id": capture_id}
        )
        
        if not capture:
            raise HTTPException(status_code=404, detail="Capture non trouvée")
        
        # Déterminer le statut
        status = StatusEnum.COMPLETED if capture["is_synced"] else StatusEnum.PENDING
        if capture["sync_attempts"] > 0 and not capture["is_synced"]:
            status = StatusEnum.FAILED if capture["sync_attempts"] >= 5 else StatusEnum.PROCESSING
        
        # URL de téléchargement
        download_url = None
        if capture["download_token"]:
            download_url = f"{settings.PUBLIC_BASE_URL}/api/download/{capture['download_token']}"
        
        return CaptureStatus(
            id=capture["id"],
            status=status,
            created_at=capture["created_at"],
            synced_at=capture["synced_at"],
            download_url=download_url,
            attempts=capture["sync_attempts"],
            last_error=capture["last_error"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération statut {capture_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur récupération statut")

@router.get("/list", response_model=CaptureList)
async def list_captures(
    pagination: PaginationParams = Depends(),
    status: Optional[StatusEnum] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: Database = Depends(get_db)
):
    """
    Liste les captures avec pagination et filtres
    """
    try:
        # Construction de la requête avec filtres
        where_clauses = []
        params = {}
        
        if status:
            if status == StatusEnum.COMPLETED:
                where_clauses.append("is_synced = 1")
            elif status == StatusEnum.PENDING:
                where_clauses.append("is_synced = 0 AND sync_attempts = 0")
            elif status == StatusEnum.PROCESSING:
                where_clauses.append("is_synced = 0 AND sync_attempts > 0 AND sync_attempts < 5")
            elif status == StatusEnum.FAILED:
                where_clauses.append("sync_attempts >= 5")
        
        if date_from:
            where_clauses.append("created_at >= :date_from")
            params["date_from"] = date_from
        
        if date_to:
            where_clauses.append("created_at <= :date_to")
            params["date_to"] = date_to
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Requête de comptage
        count_query = f"SELECT COUNT(*) as count FROM captures WHERE {where_sql}"
        total_result = await db.fetch_one(count_query, params)
        total = total_result["count"] if total_result else 0
        
        # Requête principale avec pagination
        query = f"""
            SELECT * FROM captures 
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """
        
        params.update({
            "limit": pagination.per_page,
            "offset": pagination.offset
        })
        
        captures_data = await db.fetch_all(query, params)
        
        # Conversion en modèles de réponse
        capture_list = []
        for capture in captures_data:
            # Déterminer le statut
            status_value = StatusEnum.COMPLETED if capture["is_synced"] else StatusEnum.PENDING
            if capture["sync_attempts"] > 0 and not capture["is_synced"]:
                status_value = StatusEnum.FAILED if capture["sync_attempts"] >= 5 else StatusEnum.PROCESSING
            
            # URL de téléchargement
            download_url = None
            if capture["download_token"]:
                download_url = f"{settings.PUBLIC_BASE_URL}/api/download/{capture['download_token']}"
            
            capture_list.append(CaptureStatus(
                id=capture["id"],
                status=status_value,
                created_at=capture["created_at"],
                synced_at=capture["synced_at"],
                download_url=download_url,
                attempts=capture["sync_attempts"],
                last_error=capture["last_error"]
            ))
        
        return CaptureList(
            captures=capture_list,
            total=total,
            page=pagination.page,
            per_page=pagination.per_page,
            message=f"{len(capture_list)} captures trouvées"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur liste captures: {e}")
        raise HTTPException(status_code=500, detail="Erreur récupération liste")

@router.delete("/{capture_id}")
async def delete_capture(capture_id: str, db: Database = Depends(get_db)):
    """
    Supprime une capture et ses fichiers associés
    """
    try:
        # Récupérer la capture
        capture = await db.fetch_one(
            "SELECT * FROM captures WHERE id = :id", {"id": capture_id}
        )
        
        if not capture:
            raise HTTPException(status_code=404, detail="Capture non trouvée")
        
        # Supprimer le fichier local
        if capture["photo_local_path"] and os.path.exists(capture["photo_local_path"]):
            os.remove(capture["photo_local_path"])
        
        # Supprimer du stockage distant (si synchronisé)
        if capture["is_synced"] and capture["photo_remote_url"]:
            await storage_service.delete_file(capture["photo_remote_url"])
        
        # Supprimer de la base de données
        await db.execute(
            "DELETE FROM captures WHERE id = :id", {"id": capture_id}
        )
        
        # Log de l'événement
        await db.log_event(
            level="INFO",
            component="capture",
            message="Capture supprimée",
            correlation_id=capture_id
        )
        
        return {"success": True, "message": "Capture supprimée avec succès"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur suppression capture {capture_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la suppression")

@router.post("/retry-sync/{capture_id}")
async def retry_sync_capture(capture_id: str, db: Database = Depends(get_db)):
    """
    Relance la synchronisation d'une capture échouée
    """
    try:
        # Vérifier que la capture existe et n'est pas déjà synchronisée
        capture = await db.fetch_one(
            "SELECT * FROM captures WHERE id = :id", {"id": capture_id}
        )
        
        if not capture:
            raise HTTPException(status_code=404, detail="Capture non trouvée")
        
        if capture["is_synced"]:
            raise HTTPException(status_code=400, detail="Capture déjà synchronisée")
        
        # Remettre à zéro les tentatives et ajouter à la queue
        await db.execute(
            "UPDATE captures SET sync_attempts = 0, last_error = NULL WHERE id = :id",
            {"id": capture_id}
        )
        
        # Ajouter à la queue de synchronisation
        await sync_service.add_to_queue(capture_id)
        
        # Log de l'événement
        await db.log_event(
            level="INFO",
            component="sync",
            message="Retry synchronisation demandée",
            correlation_id=capture_id
        )
        
        return {
            "success": True,
            "message": "Synchronisation relancée",
            "capture_id": capture_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur retry sync {capture_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors du retry")