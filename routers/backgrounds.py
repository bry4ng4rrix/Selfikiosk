from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, Form
from fastapi.responses import FileResponse
from typing import List, Optional
import os
import uuid
import logging
from PIL import Image
import shutil

from database import get_db, Database, backgrounds
from models import Background, BackgroundCreate, BackgroundUpdate, BackgroundList
from app_settings import app_settings
from utils.validation import validate_image_file
from utils.files import optimize_image

router = APIRouter()
logger = logging.getLogger(__name__)

# Dossier pour stocker les fonds
BACKGROUNDS_DIR = os.path.join(settings.UPLOAD_DIR, "backgrounds")
os.makedirs(BACKGROUNDS_DIR, exist_ok=True)

@router.get("/backgrounds", response_model=BackgroundList)
async def list_backgrounds(
    active_only: bool = True,
    db: Database = Depends(get_db)
):
    """
    Récupère la liste des fonds d'écran
    """
    try:
        # Construction de la requête
        query = "SELECT * FROM backgrounds"
        params = {}
        
        if active_only:
            query += " WHERE is_active = 1"
        
        query += " ORDER BY display_order ASC, name ASC"
        
        backgrounds_data = await db.fetch_all(query, params)
        
        # Conversion en modèles de réponse
        background_list = []
        for bg_data in backgrounds_data:
            # Générer l'URL publique
            file_url = f"{settings.PUBLIC_BASE_URL}/api/backgrounds/{bg_data['id']}/file"
            
            background_list.append(Background(
                id=bg_data["id"],
                name=bg_data["name"],
                file_path=bg_data["file_path"],
                file_url=file_url,
                file_size=bg_data["file_size"],
                is_active=bg_data["is_active"],
                display_order=bg_data["display_order"],
                created_at=bg_data["created_at"]
            ))
        
        return BackgroundList(
            backgrounds=background_list,
            total=len(background_list),
            message=f"{len(background_list)} fonds trouvés"
        )
        
    except Exception as e:
        logger.error(f"Erreur récupération fonds: {e}")
        raise HTTPException(status_code=500, detail="Erreur récupération fonds")

@router.post("/backgrounds", response_model=Background)
async def create_background(
    name: str = Form(...),
    display_order: int = Form(0),
    is_active: bool = Form(True),
    file: UploadFile = File(...),
    db: Database = Depends(get_db)
):
    """
    Créer un nouveau fond d'écran
    """
    try:
        # Validation du fichier
        if not file.filename:
            raise HTTPException(status_code=400, detail="Nom de fichier requis")
        
        # Vérifier l'extension
        allowed_extensions = ['.jpg', '.jpeg', '.png']
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"Extension non autorisée. Utilisez: {', '.join(allowed_extensions)}"
            )
        
        # Lire et valider le contenu
        content = await file.read()
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Fichier trop volumineux. Maximum: {settings.MAX_FILE_SIZE / (1024*1024):.1f}MB"
            )
        
        if not validate_image_file(content):
            raise HTTPException(status_code=400, detail="Format d'image invalide")
        
        # Génération des identifiants
        background_id = str(uuid.uuid4())
        filename = f"{background_id}{file_ext}"
        file_path = os.path.join(BACKGROUNDS_DIR, filename)
        
        # Sauvegarde et optimisation de l'image
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        # Optimiser l'image (redimensionner si trop grande, compression)
        optimized_path = await optimize_image(file_path, max_width=1920, max_height=1080, quality=90)
        if optimized_path != file_path:
            os.replace(optimized_path, file_path)
        
        # Récupérer la taille finale
        final_size = os.path.getsize(file_path)
        
        # Enregistrement en base de données
        await db.execute(
            backgrounds.insert().values(
                id=background_id,
                name=name,
                file_path=file_path,
                file_size=final_size,
                is_active=is_active,
                display_order=display_order
            )
        )
        
        # Log de l'événement
        await db.log_event(
            level="INFO",
            component="backgrounds",
            message=f"Nouveau fond créé: {name}",
            correlation_id=background_id
        )
        
        # URL publique
        file_url = f"{settings.PUBLIC_BASE_URL}/api/backgrounds/{background_id}/file"
        
        return Background(
            id=background_id,
            name=name,
            file_path=file_path,
            file_url=file_url,
            file_size=final_size,
            is_active=is_active,
            display_order=display_order,
            created_at=datetime.now()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur création fond: {e}")
        # Nettoyer le fichier en cas d'erreur
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail="Erreur création fond")

@router.get("/backgrounds/{background_id}/file")
async def get_background_file(background_id: str, db: Database = Depends(get_db)):
    """
    Récupère le fichier image d'un fond
    """
    try:
        # Rechercher le fond
        background = await db.fetch_one(
            "SELECT * FROM backgrounds WHERE id = :id", {"id": background_id}
        )
        
        if not background:
            raise HTTPException(status_code=404, detail="Fond non trouvé")
        
        if not os.path.exists(background["file_path"]):
            raise HTTPException(status_code=404, detail="Fichier image non trouvé")
        
        # Déterminer le type MIME
        file_ext = os.path.splitext(background["file_path"])[1].lower()
        media_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png'
        }
        media_type = media_types.get(file_ext, 'image/jpeg')
        
        return FileResponse(
            path=background["file_path"],
            filename=f"{background['name']}{file_ext}",
            media_type=media_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération fichier fond {background_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur récupération fichier")

@router.get("/backgrounds/{background_id}", response_model=Background)
async def get_background(background_id: str, db: Database = Depends(get_db)):
    """
    Récupère les informations d'un fond spécifique
    """
    try:
        background = await db.fetch_one(
            "SELECT * FROM backgrounds WHERE id = :id", {"id": background_id}
        )
        
        if not background:
            raise HTTPException(status_code=404, detail="Fond non trouvé")
        
        file_url = f"{settings.PUBLIC_BASE_URL}/api/backgrounds/{background_id}/file"
        
        return Background(
            id=background["id"],
            name=background["name"],
            file_path=background["file_path"],
            file_url=file_url,
            file_size=background["file_size"],
            is_active=background["is_active"],
            display_order=background["display_order"],
            created_at=background["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération fond {background_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur récupération fond")

@router.put("/backgrounds/{background_id}", response_model=Background)
async def update_background(
    background_id: str,
    background_update: BackgroundUpdate,
    db: Database = Depends(get_db)
):
    """
    Met à jour les informations d'un fond
    """
    try:
        # Vérifier que le fond existe
        existing = await db.fetch_one(
            "SELECT * FROM backgrounds WHERE id = :id", {"id": background_id}
        )
        
        if not existing:
            raise HTTPException(status_code=404, detail="Fond non trouvé")
        
        # Préparer les données de mise à jour
        update_data = {}
        for field, value in background_update.dict(exclude_unset=True).items():
            if value is not None:
                update_data[field] = value
        
        if not update_data:
            raise HTTPException(status_code=400, detail="Aucune donnée à mettre à jour")
        
        # Mise à jour en base
        set_clauses = [f"{field} = :{field}" for field in update_data.keys()]
        query = f"UPDATE backgrounds SET {', '.join(set_clauses)} WHERE id = :id"
        
        await db.execute(query, {**update_data, "id": background_id})
        
        # Log de l'événement
        await db.log_event(
            level="INFO",
            component="backgrounds",
            message=f"Fond mis à jour: {existing['name']}",
            details=str(update_data),
            correlation_id=background_id
        )
        
        # Récupérer les données mises à jour
        updated = await db.fetch_one(
            "SELECT * FROM backgrounds WHERE id = :id", {"id": background_id}
        )
        
        file_url = f"{settings.PUBLIC_BASE_URL}/api/backgrounds/{background_id}/file"
        
        return Background(
            id=updated["id"],
            name=updated["name"],
            file_path=updated["file_path"],
            file_url=file_url,
            file_size=updated["file_size"],
            is_active=updated["is_active"],
            display_order=updated["display_order"],
            created_at=updated["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur mise à jour fond {background_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur mise à jour fond")

@router.delete("/backgrounds/{background_id}")
async def delete_background(background_id: str, db: Database = Depends(get_db)):
    """
    Supprime un fond et son fichier
    """
    try:
        # Récupérer le fond
        background = await db.fetch_one(
            "SELECT * FROM backgrounds WHERE id = :id", {"id": background_id}
        )
        
        if not background:
            raise HTTPException(status_code=404, detail="Fond non trouvé")
        
        # Vérifier qu'il n'est pas utilisé dans des captures récentes
        recent_usage = await db.fetch_one(
            """
            SELECT COUNT(*) as count FROM captures 
            WHERE background_id = :bg_id AND created_at > datetime('now', '-7 days')
            """,
            {"bg_id": background_id}
        )
        
        if recent_usage and recent_usage["count"] > 0:
            raise HTTPException(
                status_code=400,
                detail="Impossible de supprimer: fond utilisé dans des captures récentes"
            )
        
        # Supprimer le fichier
        if os.path.exists(background["file_path"]):
            os.remove(background["file_path"])
        
        # Supprimer de la base de données
        await db.execute(
            "DELETE FROM backgrounds WHERE id = :id", {"id": background_id}
        )
        
        # Log de l'événement
        await db.log_event(
            level="INFO",
            component="backgrounds",
            message=f"Fond supprimé: {background['name']}",
            correlation_id=background_id
        )
        
        return {
            "success": True,
            "message": "Fond supprimé avec succès",
            "background_id": background_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur suppression fond {background_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur suppression fond")

@router.post("/backgrounds/reorder")
async def reorder_backgrounds(
    background_orders: List[dict],  # [{"id": "uuid", "display_order": int}]
    db: Database = Depends(get_db)
):
    """
    Réorganise l'ordre d'affichage des fonds
    """
    try:
        # Valider les données
        for item in background_orders:
            if "id" not in item or "display_order" not in item:
                raise HTTPException(
                    status_code=400,
                    detail="Chaque élément doit contenir 'id' et 'display_order'"
                )
        
        # Mettre à jour chaque fond
        updated_count = 0
        for item in background_orders:
            result = await db.execute(
                "UPDATE backgrounds SET display_order = :order WHERE id = :id",
                {"order": item["display_order"], "id": item["id"]}
            )
            if result:
                updated_count += 1
        
        # Log de l'événement
        await db.log_event(
            level="INFO",
            component="backgrounds",
            message=f"Ordre des fonds mis à jour: {updated_count} éléments"
        )
        
        return {
            "success": True,
            "message": f"{updated_count} fonds réorganisés",
            "updated_count": updated_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur réorganisation fonds: {e}")
        raise HTTPException(status_code=500, detail="Erreur réorganisation")

@router.get("/backgrounds/preview/{background_id}")
async def get_background_preview(
    background_id: str,
    width: int = 300,
    height: int = 200,
    db: Database = Depends(get_db)
):
    """
    Génère une miniature/preview d'un fond
    """
    try:
        # Récupérer le fond
        background = await db.fetch_one(
            "SELECT * FROM backgrounds WHERE id = :id", {"id": background_id}
        )
        
        if not background:
            raise HTTPException(status_code=404, detail="Fond non trouvé")
        
        if not os.path.exists(background["file_path"]):
            raise HTTPException(status_code=404, detail="Fichier image non trouvé")
        
        # Générer le chemin de la miniature
        preview_dir = os.path.join(BACKGROUNDS_DIR, "previews")
        os.makedirs(preview_dir, exist_ok=True)
        
        preview_filename = f"{background_id}_{width}x{height}.jpg"
        preview_path = os.path.join(preview_dir, preview_filename)
        
        # Créer la miniature si elle n'existe pas
        if not os.path.exists(preview_path):
            with Image.open(background["file_path"]) as img:
                # Conserver les proportions
                img.thumbnail((width, height), Image.Resampling.LANCZOS)
                
                # Créer une image de fond avec les dimensions exactes
                preview_img = Image.new('RGB', (width, height), color='white')
                
                # Centrer l'image redimensionnée
                x = (width - img.width) // 2
                y = (height - img.height) // 2
                preview_img.paste(img, (x, y))
                
                # Sauvegarder
                preview_img.save(preview_path, 'JPEG', quality=80)
        
        return FileResponse(
            path=preview_path,
            filename=preview_filename,
            media_type="image/jpeg"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur génération preview {background_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur génération preview")