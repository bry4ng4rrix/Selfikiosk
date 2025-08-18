from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
import logging

from database import get_db, Database
from models import ConfigUpdate, ConfigResponse, BaseResponse
from utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

@router.get("/config", response_model=ConfigResponse)
async def get_current_config(db: Database = Depends(get_db)):
    """
    Récupère la configuration actuelle (sans les secrets)
    """
    try:
        # Récupérer toutes les configurations
        config_items = await db.fetch_all("SELECT key, value FROM config")
        config_dict = {item["key"]: item["value"] for item in config_items}
        
        # Convertir en réponse sécurisée
        return ConfigResponse(
            welcome_message=config_dict.get("welcome_message", "Bienvenue !"),
            success_message=config_dict.get("success_message", "Succès !"),
            countdown_seconds=int(config_dict.get("countdown_seconds", "3")),
            sms_sender=config_dict.get("sms_sender", "SelfieKiosk"),
            google_review_enabled=config_dict.get("google_review_enabled", "false").lower() == "true",
            google_review_url=config_dict.get("google_review_url"),
            auto_delete_days=int(config_dict.get("auto_delete_days", "30")),
            auto_delete_enabled=config_dict.get("auto_delete_enabled", "true").lower() == "true",
            ovh_configured=bool(config_dict.get("ovh_application_key")),
            storage_configured=bool(config_dict.get("swift_username")),
            message="Configuration récupérée"
        )
        
    except Exception as e:
        logger.log_error(e, {"context": "get_config"})
        raise HTTPException(
            status_code=500,
            detail="Erreur récupération configuration"
        )

@router.put("/config", response_model=BaseResponse)
async def update_config(
    config_update: ConfigUpdate,
    db: Database = Depends(get_db)
):
    """
    Met à jour la configuration
    """
    try:
        updated_fields = []
        
        # Traiter chaque champ modifié
        for field, value in config_update.dict(exclude_unset=True).items():
            if value is not None:
                await db.set_config(field, str(value))
                updated_fields.append(field)
        
        # Log de la modification
        logger.struct_logger.info(
            "Configuration updated",
            fields=updated_fields
        )
        
        return BaseResponse(
            message=f"Configuration mise à jour: {', '.join(updated_fields)}"
        )
        
    except Exception as e:
        logger.log_error(e, {"context": "update_config"})
        raise HTTPException(
            status_code=500,
            detail="Erreur mise à jour configuration"
        )