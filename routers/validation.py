import re
import base64
import magic
from PIL import Image
from typing import Optional
import io
import logging

logger = logging.getLogger(__name__)

def validate_phone(phone: str) -> str:
    """
    Valide et formate un numéro de téléphone
    
    Args:
        phone: Numéro de téléphone brut
        
    Returns:
        Numéro formaté
        
    Raises:
        ValueError: Si le numéro est invalide
    """
    if not phone:
        raise ValueError("Numéro de téléphone requis")
    
    # Nettoyer le numéro
    cleaned = re.sub(r'[^\d+]', '', phone)
    
    # Format français
    if cleaned.startswith('0'):
        cleaned = '+33' + cleaned[1:]
    elif not cleaned.startswith('+'):
        # Ajouter +33 par défaut si pas de préfixe international
        cleaned = '+33' + cleaned
    
    # Vérification basique du format international
    if not re.match(r'^\+[1-9]\d{8,14}$', cleaned):
        raise ValueError("Format de numéro de téléphone invalide")
    
    # Vérification spécifique France (+33)
    if cleaned.startswith('+33'):
        if not re.match(r'^\+33[1-9]\d{8}$', cleaned):
            raise ValueError("Format de numéro français invalide")
    
    return cleaned

def validate_email(email: str) -> str:
    """
    Valide un email
    
    Args:
        email: Adresse email
        
    Returns:
        Email normalisé
        
    Raises:
        ValueError: Si l'email est invalide
    """
    if not email:
        raise ValueError("Adresse email requise")
    
    # Pattern basique pour email
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(pattern, email.strip().lower()):
        raise ValueError("Format d'adresse email invalide")
    
    return email.strip().lower()

def validate_image(image_data: bytes) -> bool:
    """
    Valide qu'un contenu binaire est une image valide
    
    Args:
        image_data: Données binaires de l'image
        
    Returns:
        True si l'image est valide
    """
    try:
        # Vérifier la taille minimale
        if len(image_data) < 100:
            return False
        
        # Vérifier le type MIME avec python-magic
        try:
            mime_type = magic.from_buffer(image_data, mime=True)
            if mime_type not in ['image/jpeg', 'image/png', 'image/gif']:
                logger.warning(f"Type MIME non autorisé: {mime_type}")
                return False
        except:
            # Fallback si python-magic n'est pas disponible
            pass
        
        # Vérifier avec PIL
        with Image.open(io.BytesIO(image_data)) as img:
            # Vérifier les dimensions minimales
            if img.width < 100 or img.height < 100:
                logger.warning("Image trop petite")
                return False
            
            # Vérifier les dimensions maximales
            if img.width > 10000 or img.height > 10000:
                logger.warning("Image trop grande")
                return False
            
            # Vérifier le format
            if img.format not in ['JPEG', 'PNG']:
                logger.warning(f"Format non supporté: {img.format}")
                return False
            
            return True
            
    except Exception as e:
        logger.error(f"Erreur validation image: {e}")
        return False

def validate_image_file(file_content: bytes) -> bool:
    """
    Valide un fichier image uploadé
    
    Args:
        file_content: Contenu du fichier
        
    Returns:
        True si valide
    """
    return validate_image(file_content)

def validate_base64_image(base64_string: str) -> bool:
    """
    Valide une image encodée en base64
    
    Args:
        base64_string: Image en base64
        
    Returns:
        True si valide
    """
    try:
        # Supprimer le préfixe data:image si présent
        if base64_string.startswith('data:image'):
            base64_string = base64_string.split(',')[1]
        
        # Décoder
        image_data = base64.b64decode(base64_string)
        
        return validate_image(image_data)
        
    except Exception as e:
        logger.error(f"Erreur validation image base64: {e}")
        return False

def sanitize_filename(filename: str) -> str:
    """
    Nettoie un nom de fichier pour éviter les problèmes de sécurité
    
    Args:
        filename: Nom de fichier original
        
    Returns:
        Nom de fichier sécurisé
    """
    # Garder seulement les caractères alphanumériques, points, tirets et underscores
    sanitized = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    
    # Éviter les noms de fichiers cachés
    if sanitized.startswith('.'):
        sanitized = 'file' + sanitized
    
    # Limiter la longueur
    if len(sanitized) > 100:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:95] + ext
    
    return sanitized

def validate_uuid(uuid_string: str) -> bool:
    """
    Valide un UUID
    
    Args:
        uuid_string: UUID à valider
        
    Returns:
        True si UUID valide
    """
    pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    return bool(re.match(pattern, uuid_string.lower()))

def validate_url(url: str) -> bool:
    """
    Valide une URL
    
    Args:
        url: URL à valider
        
    Returns:
        True si URL valide
    """
    pattern = r'^https?:\/\/(?:[-\w.])+(?:[:\d]+)?(?:\/(?:[\w._~!$&\'()*+,;=:@]|%[\da-fA-F]{2})*)*(?:\?(?:[\w._~!$&\'()*+,;=:@\/?]|%[\da-fA-F]{2})*)?(?:#(?:[\w._~!$&\'()*+,;=:@\/?]|%[\da-fA-F]{2})*)?$'
    return bool(re.match(pattern, url))

def validate_config_value(key: str, value: str) -> tuple[bool, str]:
    """
    Valide une valeur de configuration selon sa clé
    
    Args:
        key: Clé de configuration
        value: Valeur à valider
        
    Returns:
        Tuple (is_valid, error_message)
    """
    if not value:
        return False, "Valeur requise"
    
    # Validations spécifiques par clé
    if key in ['welcome_message', 'success_message']:
        if len(value) > 200:
            return False, "Message trop long (max 200 caractères)"
        return True, ""
    
    elif key == 'countdown_seconds':
        try:
            seconds = int(value)
            if not 1 <= seconds <= 10:
                return False, "Délai doit être entre 1 et 10 secondes"
            return True, ""
        except ValueError:
            return False, "Valeur numérique requise"
    
    elif key == 'sms_sender':
        if not re.match(r'^[a-zA-Z0-9\s]{1,11}$', value):
            return False, "Expéditeur SMS invalide (11 caractères max, alphanumériques)"
        return True, ""
    
    elif key in ['google_review_url', 'swift_auth_url']:
        if not validate_url(value):
            return False, "URL invalide"
        return True, ""
    
    elif key == 'auto_delete_days':
        try:
            days = int(value)
            if not 1 <= days <= 365:
                return False, "Délai doit être entre 1 et 365 jours"
            return True, ""
        except ValueError:
            return False, "Valeur numérique requise"
    
    elif key in ['ovh_application_key', 'ovh_application_secret', 'ovh_consumer_key']:
        if len(value) < 10:
            return False, "Clé OVH trop courte"
        return True, ""
    
    else:
        # Validation générale
        if len(value) > 500:
            return False, "Valeur trop longue"
        return True, ""

def validate_background_name(name: str) -> bool:
    """
    Valide un nom de fond d'écran
    
    Args:
        name: Nom du fond
        
    Returns:
        True si valide
    """
    if not name or not name.strip():
        return False
    
    if len(name.strip()) > 100:
        return False
    
    # Éviter les caractères spéciaux problématiques
    if re.search(r'[<>:"/\\|?*]', name):
        return False
    
    return True

def get_file_extension(filename: str) -> Optional[str]:
    
    try:
        return os.path.splitext(filename)[1].lower()
    except:
        return None

def is_allowed_image_extension(filename: str) -> bool:
    
    ext = get_file_extension(filename)
    allowed_extensions = ['.jpg', '.jpeg', '.png']
    return ext in allowed_extensions

class ValidationError(Exception):
    """Exception personnalisée pour les erreurs de validation"""
    pass