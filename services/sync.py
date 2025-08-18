import asyncio
import logging
import os
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from config import settings
from database import Database
from services.storage import StorageService
from services.sms import SMSService
from utils.logger import setup_logger

# Configuration du logger
setup_logger()
logger = logging.getLogger(__name__)

class SyncService:
    """
    Service de synchronisation des captures
    Gère la file d'attente des captures à synchroniser avec le stockage distant
    """
    
    def __init__(self):
        self.storage_service = StorageService()
        self.sms_service = SMSService()
        self.is_processing = False
        self.max_retries = getattr(settings, 'SYNC_MAX_RETRIES', 3)
        self.retry_delay = getattr(settings, 'SYNC_RETRY_DELAY', 300)  # 5 minutes par défaut
    
    async def add_to_queue(self, capture_id: str) -> bool:
        """
        Ajoute une capture à la file d'attente de synchronisation
        
        Args:
            capture_id: ID de la capture à synchroniser
            
        Returns:
            bool: True si l'ajout a réussi, False sinon
        """
        try:
            db = Database()
            
            # Vérifier si la capture existe déjà dans la file d'attente
            existing = await db.fetch_one(
                "SELECT id FROM sync_queue WHERE capture_id = :capture_id",
                {"capture_id": capture_id}
            )
            
            if not existing:
                # Ajouter à la file d'attente
                await db.execute(
                    """
                    INSERT INTO sync_queue (capture_id, status, created_at, updated_at)
                    VALUES (:capture_id, 'pending', :now, :now)
                    """,
                    {"capture_id": capture_id, "now": datetime.now()}
                )
                
                logger.info(f"Capture {capture_id} ajoutée à la file de synchronisation")
                
                # Démarrer le traitement si pas déjà en cours
                if not self.is_processing:
                    asyncio.create_task(self.process_queue())
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout à la file d'attente: {e}")
            return False
            
    async def process_queue(self):
        """
        Traite les captures en attente de synchronisation
        """
        if self.is_processing:
            return
            
        self.is_processing = True
        
        try:
            db = Database()
            
            while True:
                # Récupérer la prochaine capture à synchroniser
                queue_item = await db.fetch_one(
                    """
                    SELECT * FROM sync_queue 
                    WHERE status = 'pending' OR 
                          (status = 'failed' AND retry_count < :max_retries AND 
                           (last_attempt IS NULL OR last_attempt < :retry_time))
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    {
                        "max_retries": self.max_retries,
                        "retry_time": datetime.now() - timedelta(seconds=self.retry_delay)
                    }
                )
                
                if not queue_item:
                    break
                    
                capture_id = queue_item["capture_id"]
                
                try:
                    # Marquer comme en cours de traitement
                    await db.execute(
                        """
                        UPDATE sync_queue 
                        SET status = 'processing', 
                            last_attempt = :now,
                            updated_at = :now,
                            retry_count = COALESCE(retry_count, 0) + 1
                        WHERE id = :id
                        """,
                        {"id": queue_item["id"], "now": datetime.now()}
                    )
                    
                    # Récupérer les données de la capture
                    capture = await db.fetch_one(
                        """
                        SELECT c.*, u.phone 
                        FROM captures c
                        LEFT JOIN users u ON c.user_id = u.id
                        WHERE c.id = :id
                        """,
                        {"id": capture_id}
                    )
                    
                    if not capture:
                        raise Exception("Capture non trouvée")
                    
                    # Téléverser le fichier
                    if capture.get("photo_local_path") and not capture.get("photo_remote_url"):
                        remote_url = await self.storage_service.upload_file(
                            capture["photo_local_path"],
                            f"captures/{capture_id[:2]}/{capture_id}.jpg"
                        )
                        
                        if not remote_url:
                            raise Exception("Échec du téléversement du fichier")
                        
                        # Mettre à jour l'URL distante
                        await db.execute(
                            """
                            UPDATE captures 
                            SET photo_remote_url = :url, 
                                is_synced = 1,
                                synced_at = :now
                            WHERE id = :id
                            """,
                            {"id": capture_id, "url": remote_url, "now": datetime.now()}
                        )
                        
                        # Supprimer le fichier local
                        try:
                            if os.path.exists(capture["photo_local_path"]):
                                os.remove(capture["photo_local_path"])
                        except Exception as e:
                            logger.warning(f"Impossible de supprimer le fichier local {capture['photo_local_path']}: {e}")
                    
                    # Envoyer une notification SMS si nécessaire
                    if capture.get("phone"):
                        await self._send_notification(capture_id, capture["phone"])
                    
                    # Marquer comme terminé
                    await self._update_queue_status(queue_item["id"], "completed")
                    
                    logger.info(f"Capture {capture_id} synchronisée avec succès")
                    
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Erreur synchronisation capture {capture_id}: {error_msg}")
                    await self._update_queue_status(
                        queue_item["id"], 
                        "failed", 
                        error=error_msg
                    )
                    
                    # Attendre avant la prochaine tentative
                    await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"Erreur dans le traitement de la file d'attente: {e}")
        finally:
            self.is_processing = False
    
    async def _update_queue_status(
        self, 
        queue_id: int, 
        status: str, 
        error: Optional[str] = None
    ) -> None:
        """
        Met à jour le statut d'un élément de la file d'attente
        
        Args:
            queue_id: ID de l'élément dans la file d'attente
            status: Nouveau statut (pending, processing, completed, failed)
            error: Message d'erreur éventuel
        """
        try:
            db = Database()
            
            await db.execute(
                """
                UPDATE sync_queue 
                SET status = :status, 
                    error_message = :error,
                    updated_at = :now
                WHERE id = :id
                """,
                {
                    "id": queue_id,
                    "status": status,
                    "error": error,
                    "now": datetime.now()
                }
            )
            
        except Exception as e:
            logger.error(f"Erreur mise à jour statut file d'attente {queue_id}: {e}")
    
    async def _send_notification(self, capture_id: str, phone: str) -> bool:
        """
        Envoie une notification de téléchargement
        
        Args:
            capture_id: ID de la capture
            phone: Numéro de téléphone du destinataire
            
        Returns:
            bool: True si l'envoi a réussi, False sinon
        """
        try:
            db = Database()
            
            # Récupérer le token de téléchargement
            capture = await db.fetch_one(
                "SELECT download_token FROM captures WHERE id = :id",
                {"id": capture_id}
            )
            
            if not capture or not capture.get("download_token"):
                logger.warning(f"Token de téléchargement introuvable pour la capture {capture_id}")
                return False
            
            # Générer l'URL de téléchargement
            download_url = f"{settings.PUBLIC_BASE_URL}/download/{capture['download_token']}"
            
            # Récupérer le message depuis la configuration
            message_template = getattr(
                settings, 
                'SMS_DOWNLOAD_MESSAGE',
                'Votre selfie est prêt ! Téléchargez-le ici : {download_url}'
            )
            message = message_template.format(download_url=download_url)
            
            # Envoyer le SMS
            result = await self.sms_service.send_sms(phone, message)
            
            if result:
                logger.info(f"Notification SMS envoyée pour la capture {capture_id} à {phone}")
            else:
                logger.warning(f"Échec de l'envoi du SMS pour la capture {capture_id}")
            
            return bool(result)
            
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de la notification pour {capture_id}: {e}")
            return False