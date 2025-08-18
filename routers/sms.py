import ovh
import asyncio
import logging
from typing import Optional
import re
from datetime import datetime

from app_settings import app_settings

logger = logging.getLogger(__name__)

class SMSService:
    """
    Service d'envoi de SMS via l'API OVH
    """
    
    def __init__(self):
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialise le client OVH"""
        try:
            if not all([
                settings.OVH_APPLICATION_KEY,
                settings.OVH_APPLICATION_SECRET,
                settings.OVH_CONSUMER_KEY
            ]):
                logger.warning("Configuration OVH SMS incomplète")
                return
            
            self.client = ovh.Client(
                endpoint=settings.OVH_ENDPOINT,
                application_key=settings.OVH_APPLICATION_KEY,
                application_secret=settings.OVH_APPLICATION_SECRET,
                consumer_key=settings.OVH_CONSUMER_KEY
            )
            
            logger.info("✅ Client OVH SMS initialisé")
            
        except Exception as e:
            logger.error(f"Erreur initialisation client OVH: {e}")
    
    def _format_phone_number(self, phone: str) -> str:
        """
        Formate un numéro de téléphone pour l'API OVH
        
        Args:
            phone: Numéro de téléphone brut
            
        Returns:
            Numéro formaté (format international)
        """
        # Nettoyer le numéro
        cleaned = re.sub(r'[^\d+]', '', phone)
        
        # Si commence par 0, remplacer par +33 (France)
        if cleaned.startswith('0'):
            cleaned = '+33' + cleaned[1:]
        
        # Si ne commence pas par +, ajouter +33
        elif not cleaned.startswith('+'):
            cleaned = '+33' + cleaned
        
        return cleaned
    
    def _validate_phone_number(self, phone: str) -> bool:
        """
        Valide un numéro de téléphone
        
        Args:
            phone: Numéro à valider
            
        Returns:
            True si valide
        """
        formatted = self._format_phone_number(phone)
        
        # Vérification basique du format international
        pattern = r'^\+[1-9]\d{8,14}$'
        return bool(re.match(pattern, formatted))
    
    async def test_connection(self) -> bool:
        """
        Test de connectivité avec l'API OVH SMS
        
        Returns:
            True si la connexion fonctionne
        """
        try:
            if not self.client or not settings.SMS_SERVICE_NAME:
                return False
            
            # Test asynchrone en utilisant un executor
            loop = asyncio.get_event_loop()
            
            # Récupérer les informations du service SMS
            result = await loop.run_in_executor(
                None,
                lambda: self.client.get(f'/sms/{settings.SMS_SERVICE_NAME}')
            )
            
            if result and 'name' in result:
                logger.info("✅ Test connexion OVH SMS réussi")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Test connexion OVH SMS échoué: {e}")
            return False
    
    async def get_sms_services(self) -> list:
        """
        Récupère la liste des services SMS disponibles
        
        Returns:
            Liste des services SMS
        """
        try:
            if not self.client:
                return []
            
            loop = asyncio.get_event_loop()
            services = await loop.run_in_executor(
                None,
                lambda: self.client.get('/sms/')
            )
            
            return services or []
            
        except Exception as e:
            logger.error(f"Erreur récupération services SMS: {e}")
            return []
    
    async def get_sms_credits(self) -> Optional[float]:
        """
        Récupère le solde de crédits SMS
        
        Returns:
            Nombre de crédits disponibles ou None
        """
        try:
            if not self.client or not settings.SMS_SERVICE_NAME:
                return None
            
            loop = asyncio.get_event_loop()
            service_info = await loop.run_in_executor(
                None,
                lambda: self.client.get(f'/sms/{settings.SMS_SERVICE_NAME}')
            )
            
            return float(service_info.get('creditsLeft', 0))
            
        except Exception as e:
            logger.error(f"Erreur récupération crédits SMS: {e}")
            return None
    
    async def send_sms(self, phone: str, message: str, sender: str = None) -> Optional[str]:
        """
        Envoie un SMS
        
        Args:
            phone: Numéro de téléphone destinataire
            message: Message à envoyer
            sender: Expéditeur (optionnel, utilise la config par défaut)
            
        Returns:
            ID du SMS envoyé ou None en cas d'erreur
        """
        try:
            if not self.client or not settings.SMS_SERVICE_NAME:
                logger.error("Client OVH ou service SMS non configuré")
                return None
            
            # Valider et formater le numéro
            if not self._validate_phone_number(phone):
                logger.error(f"Numéro de téléphone invalide: {phone}")
                return None
            
            formatted_phone = self._format_phone_number(phone)
            sender = sender or settings.SMS_SENDER
            
            # Limiter la longueur du message (160 caractères pour SMS standard)
            if len(message) > 160:
                message = message[:157] + "..."
                logger.warning("Message SMS tronqué à 160 caractères")
            
            # Données pour l'API OVH
            sms_data = {
                'message': message,
                'receivers': [formatted_phone],
                'sender': sender,
                'charset': 'UTF-8',
                'coding': '7bit',
                'priority': 'high',
                'validityPeriod': 2880  # 48 heures
            }
            
            # Envoi asynchrone
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.client.post(
                    f'/sms/{settings.SMS_SERVICE_NAME}/jobs',
                    **sms_data
                )
            )
            
            if result and 'ids' in result and result['ids']:
                sms_id = str(result['ids'][0])
                logger.info(f"✅ SMS envoyé avec succès: {sms_id} -> {formatted_phone}")
                return sms_id
            else:
                logger.error("Aucun ID de SMS retourné par l'API")
                return None
                
        except ovh.exceptions.APIError as e:
            logger.error(f"Erreur API OVH SMS: {e}")
            return None
        except Exception as e:
            logger.error(f"Erreur envoi SMS: {e}")
            return None
    
    async def get_sms_status(self, sms_id: str) -> Optional[dict]:
        """
        Récupère le statut d'un SMS envoyé
        
        Args:
            sms_id: ID du SMS
            
        Returns:
            Informations sur le statut du SMS
        """
        try:
            if not self.client or not settings.SMS_SERVICE_NAME:
                return None
            
            loop = asyncio.get_event_loop()
            status = await loop.run_in_executor(
                None,
                lambda: self.client.get(
                    f'/sms/{settings.SMS_SERVICE_NAME}/jobs/{sms_id}'
                )
            )
            
            return status
            
        except Exception as e:
            logger.error(f"Erreur récupération statut SMS {sms_id}: {e}")
            return None
    
    async def send_test_sms(self, phone: str) -> dict:
        """
        Envoie un SMS de test
        
        Args:
            phone: Numéro de téléphone pour le test
            
        Returns:
            Dict avec le résultat du test
        """
        try:
            test_message = f"Test Selfie Kiosk - {datetime.now().strftime('%H:%M:%S')}"
            
            sms_id = await self.send_sms(phone, test_message)
            
            if sms_id:
                # Attendre un peu puis vérifier le statut
                await asyncio.sleep(2)
                status = await self.get_sms_status(sms_id)
                
                return {
                    'success': True,
                    'sms_id': sms_id,
                    'status': status,
                    'message': 'SMS de test envoyé avec succès'
                }
            else:
                return {
                    'success': False,
                    'message': 'Échec envoi SMS de test'
                }
                
        except Exception as e:
            logger.error(f"Erreur test SMS: {e}")
            return {
                'success': False,
                'message': f'Erreur test SMS: {str(e)}'
            }
    
    def format_download_message(self, download_url: str, 
                              custom_message: str = None) -> str:
        """
        Formate le message SMS avec le lien de téléchargement
        
        Args:
            download_url: URL de téléchargement
            custom_message: Message personnalisé (optionnel)
            
        Returns:
            Message SMS formaté
        """
        if custom_message:
            # Remplacer {url} dans le message personnalisé
            if '{url}' in custom_message:
                return custom_message.format(url=download_url)
            else:
                return f"{custom_message} {download_url}"
        else:
            # Message par défaut
            return f"Votre photo selfie est prête ! Téléchargez-la ici : {download_url}"
    
    async def send_download_notification(self, phone: str, download_url: str,
                                       custom_message: str = None) -> Optional[str]:
        """
        Envoie une notification de téléchargement
        
        Args:
            phone: Numéro de téléphone
            download_url: URL de téléchargement
            custom_message: Message personnalisé
            
        Returns:
            ID du SMS ou None
        """
        message = self.format_download_message(download_url, custom_message)
        return await self.send_sms(phone, message)
    
    async def get_delivery_receipts(self, sms_id: str) -> list:
        """
        Récupère les accusés de réception pour un SMS
        
        Args:
            sms_id: ID du SMS
            
        Returns:
            Liste des accusés de réception
        """
        try:
            if not self.client or not settings.SMS_SERVICE_NAME:
                return []
            
            loop = asyncio.get_event_loop()
            receipts = await loop.run_in_executor(
                None,
                lambda: self.client.get(
                    f'/sms/{settings.SMS_SERVICE_NAME}/jobs/{sms_id}/receivers'
                )
            )
            
            return receipts or []
            
        except Exception as e:
            logger.error(f"Erreur récupération accusés réception: {e}")
            return []

# Instance globale du service
sms_service = SMSService()

# Fonctions helper pour compatibility
async def send_sms_notification(phone: str, download_url: str) -> bool:
    """
    Helper function pour envoyer une notification SMS
    
    Returns:
        True si envoyé avec succès
    """
    sms_id = await sms_service.send_download_notification(phone, download_url)
    return sms_id is not None