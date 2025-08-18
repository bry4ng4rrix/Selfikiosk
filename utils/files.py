import os
import uuid
import hashlib
import qrcode
from io import BytesIO
from typing import Tuple, Optional, BinaryIO
from pathlib import Path
from datetime import datetime
from config import settings
import logging
from utils.logger import setup_logger

# Configuration du logger
setup_logger()
logger = logging.getLogger(__name__)

def ensure_directory_exists(directory: str) -> None:
    """
    Crée le répertoire s'il n'existe pas
    
    Args:
        directory: Chemin du répertoire à créer
    """
    try:
        os.makedirs(directory, exist_ok=True)
    except Exception as e:
        logger.error(f"Erreur lors de la création du répertoire {directory}: {e}")
        raise

def generate_unique_filename(original_filename: str, prefix: str = '') -> str:
    """
    Génère un nom de fichier unique avec un préfixe optionnel
    
    Args:
        original_filename: Nom de fichier original
        prefix: Préfixe optionnel pour le fichier
        
    Returns:
        str: Nom de fichier unique
    """
    # Extraire l'extension du fichier
    ext = Path(original_filename).suffix.lower()
    
    # Générer un identifiant unique
    unique_id = uuid.uuid4().hex
    
    # Créer le nouveau nom de fichier
    if prefix:
        filename = f"{prefix}_{unique_id}{ext}"
    else:
        filename = f"{unique_id}{ext}"
    
    return filename

def save_uploaded_file(
    file_content: bytes, 
    upload_dir: str, 
    original_filename: str, 
    prefix: str = ''
) -> Tuple[str, str]:
    """
    Sauvegarde un fichier téléversé sur le disque
    
    Args:
        file_content: Contenu binaire du fichier
        upload_dir: Répertoire de destination
        original_filename: Nom de fichier original
        prefix: Préfixe optionnel pour le fichier
        
    Returns:
        Tuple[str, str]: (chemin relatif, chemin absolu)
        
    Raises:
        IOError: En cas d'erreur d'écriture
    """
    try:
        # S'assurer que le répertoire existe
        ensure_directory_exists(upload_dir)
        
        # Générer un nom de fichier unique
        filename = generate_unique_filename(original_filename, prefix)
        
        # Déterminer les chemins
        relative_path = os.path.join(upload_dir, filename)
        absolute_path = os.path.abspath(relative_path)
        
        # Écrire le fichier
        with open(absolute_path, 'wb') as f:
            f.write(file_content)
            
        logger.info(f"Fichier sauvegardé: {absolute_path}")
        
        return relative_path, absolute_path
        
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde du fichier {original_filename}: {e}")
        raise IOError(f"Impossible de sauvegarder le fichier: {e}")

def generate_qr_code(
    data: str, 
    output_dir: str = None, 
    filename: str = None,
    size: int = 10,
    border: int = 4,
    fill_color: str = 'black',
    back_color: str = 'white'
) -> Tuple[bytes, str]:
    """
    Génère un code QR à partir des données fournies
    
    Args:
        data: Données à encoder dans le QR code
        output_dir: Répertoire de sortie (si None, ne sauvegarde pas le fichier)
        filename: Nom du fichier de sortie (sans extension)
        size: Taille du QR code (1-40, 1 étant le plus petit)
        border: Taille de la bordure (en modules)
        fill_color: Couleur de remplissage (nom ou code hexa)
        back_color: Couleur d'arrière-plan (nom ou code hexa)
        
    Returns:
        Tuple[bytes, str]: (données binaires du QR code, chemin du fichier si enregistré)
    """
    try:
        # Créer le QR code
        qr = qrcode.QRCode(
            version=size,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=border,
        )
        
        # Ajouter les données
        qr.add_data(data)
        qr.make(fit=True)
        
        # Créer l'image
        img = qr.make_image(fill_color=fill_color, back_color=back_color)
        
        # Convertir en bytes
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        qr_bytes = buffer.getvalue()
        
        # Sauvegarder le fichier si un répertoire de sortie est spécifié
        filepath = None
        if output_dir:
            ensure_directory_exists(output_dir)
            
            # Générer un nom de fichier si non fourni
            if not filename:
                # Créer un hachage des données pour le nom de fichier
                hash_obj = hashlib.md5(data.encode())
                filename = f"qr_{hash_obj.hexdigest()}.png"
            elif not filename.lower().endswith('.png'):
                filename += '.png'
                
            filepath = os.path.join(output_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(qr_bytes)
                
            logger.info(f"QR code généré et sauvegardé: {filepath}")
        
        return qr_bytes, filepath
        
    except Exception as e:
        logger.error(f"Erreur lors de la génération du QR code: {e}")
        raise ValueError(f"Erreur lors de la génération du QR code: {e}")

def get_file_checksum(filepath: str, algorithm: str = 'md5') -> str:
    """
    Calcule la somme de contrôle d'un fichier
    
    Args:
        filepath: Chemin vers le fichier
        algorithm: Algorithme de hachage (md5, sha1, sha256, etc.)
        
    Returns:
        str: Somme de contrôle hexadécimale
    """
    hash_obj = hashlib.new(algorithm)
    
    try:
        with open(filepath, 'rb') as f:
            # Lire le fichier par blocs pour économiser la mémoire
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
                
        return hash_obj.hexdigest()
        
    except Exception as e:
        logger.error(f"Erreur lors du calcul de la somme de contrôle de {filepath}: {e}")
        raise IOError(f"Impossible de calculer la somme de contrôle: {e}")

def delete_file(filepath: str) -> bool:
    """
    Supprime un fichier s'il existe
    
    Args:
        filepath: Chemin vers le fichier à supprimer
        
    Returns:
        bool: True si le fichier a été supprimé, False s'il n'existait pas
    """
    try:
        if os.path.isfile(filepath):
            os.remove(filepath)
            logger.info(f"Fichier supprimé: {filepath}")
            return True
        return False
    except Exception as e:
        logger.error(f"Erreur lors de la suppression du fichier {filepath}: {e}")
        return False
