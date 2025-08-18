import logging
import os
from datetime import datetime

def setup_logger():
    """Configure le système de logging de base"""
    
    # Créer le dossier de logs
    os.makedirs("logs", exist_ok=True)
    
    # Configuration du logger principal
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler('./logs/app.log'),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("✅ Logging configuré")

def get_logger(name: str):
    """Retourne un logger basique"""
    return logging.getLogger(name)