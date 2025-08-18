import re
import base64
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from typing import Optional, Tuple, Union, Dict, Any
from datetime import datetime, date
from email_validator import validate_email, EmailNotValidError
from pydantic import BaseModel, validator, ValidationError
from fastapi import HTTPException, status
from config import settings

# Configuration du logger
import logging
from utils.logger import setup_logger

setup_logger()
logger = logging.getLogger(__name__)

class ValidationError(ValueError):
    """Exception personnalisée pour les erreurs de validation"""
    def __init__(self, message: str, field: str = None, code: str = None):
        self.message = message
        self.field = field
        self.code = code or "validation_error"
        super().__init__(message)

class PhoneNumberError(ValidationError):
    """Erreur de validation de numéro de téléphone"""
    def __init__(self, message: str = "Numéro de téléphone invalide"):
        super().__init__(message, field="phone", code="invalid_phone")

class EmailError(ValidationError):
    """Erreur de validation d'email"""
    def __init__(self, message: str = "Adresse email invalide"):
        super().__init__(message, field="email", code="invalid_email")

class ImageError(ValidationError):
    """Erreur de validation d'image"""
    def __init__(self, message: str = "Image invalide"):
        super().__init__(message, field="image", code="invalid_image")

def validate_phone_number(phone: str, country_code: str = "FR") -> str:
    """
    Valide et formate un numéro de téléphone
    
    Args:
        phone: Numéro de téléphone à valider
        country_code: Code pays (FR par défaut)
        
    Returns:
        str: Numéro de téléphone formaté
        
    Raises:
        PhoneNumberError: Si le numéro est invalide
    """
    if not phone:
        raise PhoneNumberError("Le numéro de téléphone est requis")
    
    # Nettoyage du numéro
    phone = re.sub(r"[^0-9+]", "", phone.strip())
    
    # Vérification de la longueur minimale (au moins 10 chiffres pour un numéro français)
    if len(re.sub(r"[^0-9]", "", phone)) < 10:
        raise PhoneNumberError("Le numéro de téléphone est trop court")
    
    # Formatage standard (pour la France)
    if country_code.upper() == "FR":
        # Si le numéro commence par 0, on le remplace par +33
        if phone.startswith('0'):
            phone = '+33' + phone[1:]
        # Si le numéro commence par 33, on ajoute le +
        elif phone.startswith('33'):
            phone = '+' + phone
        # Si le numéro commence par un + mais pas par +33, on le laisse tel quel
        elif not phone.startswith('+33'):
            phone = '+33' + phone[-9:]  # On garde les 9 derniers chiffres
    
    return phone

# Alias pour la compatibilité avec le code existant
validate_phone = validate_phone_number

def validate_email_address(email: str) -> str:
    """
    Valide une adresse email
    
    Args:
        email: Adresse email à valider
        
    Returns:
        str: Email normalisé
        
    Raises:
        EmailError: Si l'email est invalide
    """
    if not email:
        raise EmailError("L'adresse email est requise")
    
    try:
        # Valider et normaliser l'email
        valid = validate_email(email)
        return valid.email
    except EmailNotValidError as e:
        raise EmailError(str(e))
        

def validate_image(
    file_content: bytes, 
    max_size: int = 10 * 1024 * 1024,  # 10MB par défaut
    allowed_types: tuple = ('jpeg', 'png', 'gif')
) -> Tuple[str, str]:
    """
    Valide un fichier image
    
    Args:
        file_content: Contenu binaire du fichier
        max_size: Taille maximale en octets
        allowed_types: Types MIME autorisés
        
    Returns:
        Tuple[str, str]: (type_mime, extension)
        
    Raises:
        ImageError: Si l'image est invalide
    """
    if not file_content:
        raise ImageError("Aucune donnée d'image fournie")
    
    # Vérifier la taille
    if len(file_content) > max_size:
        raise ImageError(f"L'image est trop volumineuse (max: {max_size/1024/1024}MB)")
    
    # Détecter le type de l'image avec Pillow
    try:
        with Image.open(BytesIO(file_content)) as img:
            image_type = img.format.lower()
            if image_type == 'jpeg':  # Normaliser jpeg en jpg
                image_type = 'jpg'
            
            if not image_type or image_type not in allowed_types:
                raise ImageError(
                    f"Type d'image non supporté. Types autorisés: {', '.join(allowed_types)}"
                )
            
            return image_type, image_type
    except UnidentifiedImageError:
        raise ImageError("Impossible d'identifier le type d'image")

def validate_base64_image(
    base64_string: str, 
    max_size: int = 10 * 1024 * 1024,  # 10MB par défaut
    allowed_types: tuple = ('jpeg', 'png', 'gif')
) -> Tuple[bytes, str, str]:
    """
    Valide une image encodée en base64
    
    Args:
        base64_string: Chaîne base64 de l'image
        max_size: Taille maximale en octets
        allowed_types: Types MIME autorisés
        
    Returns:
        Tuple[bytes, str, str]: (données binaires, type_mime, extension)
        
    Raises:
        ImageError: Si l'image est invalide
    """
    if not base64_string:
        raise ImageError("Aucune donnée d'image fournie")
    
    try:
        # Vérifier si c'est bien du base64 et décoder
        if ";base64," in base64_string:
            header, data = base64_string.split(";base64,")
            image_type = header.split('/')[-1]
        else:
            data = base64_string
            image_type = None
        
        file_content = base64.b64decode(data)
        
        # Vérifier la taille
        if len(file_content) > max_size:
            raise ImageError(f"L'image est trop volumineuse (max: {max_size/1024/1024}MB)")
        
        # Si le type n'était pas dans l'en-tête, le détecter avec Pillow
        if not image_type:
            try:
                with Image.open(BytesIO(file_content)) as img:
                    image_type = img.format.lower()
                    if image_type == 'jpeg':  # Normaliser jpeg en jpg
                        image_type = 'jpg'
            except UnidentifiedImageError:
                raise ImageError("Impossible d'identifier le type d'image")
        
        if not image_type or image_type not in allowed_types:
            raise ImageError(
                f"Type d'image non supporté. Types autorisés: {', '.join(allowed_types)}"
            )
        
        return file_content, image_type, image_type
        
    except Exception as e:
        logger.error(f"Erreur de validation d'image base64: {e}")
        if isinstance(e, ImageError):
            raise e
        raise ImageError("Format d'image invalide")

def validate_date_string(date_str: str, date_format: str = "%Y-%m-%d") -> date:
    """
    Valide une chaîne de date
    
    Args:
        date_str: Date sous forme de chaîne
        date_format: Format de date attendu (par défaut: YYYY-MM-DD)
        
    Returns:
        date: Objet date
        
    Raises:
        ValidationError: Si la date est invalide
    """
    try:
        return datetime.strptime(date_str, date_format).date()
    except (ValueError, TypeError) as e:
        raise ValidationError(
            f"Format de date invalide. Format attendu: {date_format}",
            field="date",
            code="invalid_date"
        )

def validate_enum(value: Any, enum_class: type, field_name: str = None) -> Any:
    """
    Valide qu'une valeur appartient à une énumération
    
    Args:
        value: Valeur à valider
        enum_class: Classe de l'énumération
        field_name: Nom du champ pour le message d'erreur
        
    Returns:
        La valeur validée
        
    Raises:
        ValidationError: Si la valeur n'est pas dans l'énumération
    """
    field_name = field_name or "champ"
    try:
        return enum_class(value)
    except ValueError:
        valid_values = [e.value for e in enum_class]
        raise ValidationError(
            f"Valeur invalide pour {field_name}. Valeurs autorisées: {', '.join(map(str, valid_values))}",
            field=field_name,
            code="invalid_enum_value"
        )

# Modèle Pydantic pour la validation des requêtes
class BaseRequestModel(BaseModel):
    """Modèle de base pour la validation des requêtes"""
    
    class Config:
        extra = 'forbid'  # Rejette les champs supplémentaires
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat()
        }

def validate_request(data: Dict[str, Any], model: type[BaseModel]) -> BaseModel:
    """
    Valide les données de requête avec un modèle Pydantic
    
    Args:
        data: Données à valider
        model: Classe du modèle Pydantic à utiliser pour la validation
        
    Returns:
        Instance du modèle validé
        
    Raises:
        HTTPException: Si la validation échoue
    """
    try:
        return model(**data)
    except ValidationError as e:
        errors = []
        for error in e.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            errors.append({
                "field": field,
                "message": error["msg"],
                "code": error.get("type", "validation_error")
            })
        
        logger.warning(f"Validation error: {errors}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": "Erreur de validation",
                "errors": errors
            }
        )

# Exemple d'utilisation des validateurs
def validate_capture_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Exemple de fonction de validation pour une capture
    
    Args:
        data: Données de la capture à valider
        
    Returns:
        Dict[str, Any]: Données validées
    """
    validated = {}
    
    # Valider le numéro de téléphone si fourni
    if 'phone' in data:
        try:
            validated['phone'] = validate_phone_number(data['phone'])
        except ValidationError as e:
            raise  # Remonte l'erreur avec les détails
    
    # Valider l'email si fourni
    if 'email' in data:
        try:
            validated['email'] = validate_email_address(data['email'])
        except ValidationError as e:
            raise
    
    # Valider l'image si fournie
    if 'image' in data:
        try:
            file_content, image_type, extension = validate_base64_image(data['image'])
            validated['image_data'] = file_content
            validated['image_type'] = image_type
        except ValidationError as e:
            raise
    
    # Ajouter les autres champs non validés
    for key, value in data.items():
        if key not in validated and key != 'image':  # On a déjà traité l'image
            validated[key] = value
    
    return validated