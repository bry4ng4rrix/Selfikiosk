import aiohttp
import asyncio
import logging
import os
from typing import Optional
from datetime import datetime, timedelta
import hashlib
import hmac
import base64
import json

from config import settings

logger = logging.getLogger(__name__)

class StorageService:
    """
    Service de stockage pour OVH Object Storage (Swift)
    Gère l'upload, le téléchargement et la suppression des fichiers
    """
    
    def __init__(self):
        self.auth_token = None
        self.storage_url = None
        self.token_expires = None
        self.session = None
    
    async def __aenter__(self):
        """Gestionnaire de contexte asynchrone"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Fermeture du gestionnaire de contexte"""
        if self.session:
            await self.session.close()
    
    async def authenticate(self) -> bool:
        """
        Authentification auprès de l'API OVH Object Storage
        """
        try:
            if not all([
                settings.SWIFT_AUTH_URL,
                settings.SWIFT_USERNAME,
                settings.SWIFT_PASSWORD,
                settings.SWIFT_TENANT_NAME
            ]):
                logger.warning("Configuration OVH Object Storage incomplète")
                return False
            
            # Vérifier si le token est encore valide
            if (self.auth_token and self.token_expires and 
                datetime.now() < self.token_expires - timedelta(minutes=5)):
                return True
            
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            auth_data = {
                "auth": {
                    "identity": {
                        "methods": ["password"],
                        "password": {
                            "user": {
                                "name": settings.SWIFT_USERNAME,
                                "domain": {"name": "default"}
                            },
                            "password": settings.SWIFT_PASSWORD
                        }
                    },
                    "scope": {
                        "project": {
                            "name": settings.SWIFT_TENANT_NAME,
                            "domain": {"name": "default"}
                        }
                    }
                }
            }
            
            async with self.session.post(
                f"{settings.SWIFT_AUTH_URL}/auth/tokens",
                json=auth_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status != 201:
                    logger.error(f"Échec authentification OVH: {response.status}")
                    return False
                
                # Récupérer le token
                self.auth_token = response.headers.get("X-Subject-Token")
                if not self.auth_token:
                    logger.error("Token d'authentification non reçu")
                    return False
                
                # Récupérer les informations du catalogue
                response_data = await response.json()
                catalog = response_data.get("token", {}).get("catalog", [])
                
                # Trouver le service Object Storage
                for service in catalog:
                    if service.get("type") == "object-store":
                        endpoints = service.get("endpoints", [])
                        for endpoint in endpoints:
                            if (endpoint.get("interface") == "public" and 
                                endpoint.get("region") == settings.SWIFT_REGION):
                                self.storage_url = endpoint.get("url")
                                break
                        break
                
                if not self.storage_url:
                    logger.error("URL de stockage non trouvée dans le catalogue")
                    return False
                
                # Calculer l'expiration du token (24h par défaut)
                self.token_expires = datetime.now() + timedelta(hours=23)
                
                logger.info("✅ Authentification OVH Object Storage réussie")
                return True
                
        except Exception as e:
            logger.error(f"Erreur authentification OVH: {e}")
            return False
    
    async def test_connectivity(self) -> bool:
        """
        Test de connectivité avec le service de stockage
        """
        try:
            if not await self.authenticate():
                return False
            
            # Test simple: récupérer les métadonnées du conteneur
            container_url = f"{self.storage_url}/{settings.SWIFT_CONTAINER}"
            
            async with self.session.head(
                container_url,
                headers={"X-Auth-Token": self.auth_token}
            ) as response:
                
                # 404 = conteneur n'existe pas mais service accessible
                # 200 = conteneur accessible
                return response.status in [200, 404]
                
        except Exception as e:
            logger.error(f"Test connectivité stockage échoué: {e}")
            return False
    
    async def create_container_if_not_exists(self) -> bool:
        """
        Crée le conteneur s'il n'existe pas
        """
        try:
            if not await self.authenticate():
                return False
            
            container_url = f"{self.storage_url}/{settings.SWIFT_CONTAINER}"
            
            async with self.session.put(
                container_url,
                headers={
                    "X-Auth-Token": self.auth_token,
                    "X-Container-Read": ".r:*",  # Lecture publique
                }
            ) as response:
                
                if response.status in [201, 202]:  # Created or Accepted
                    logger.info(f"✅ Conteneur '{settings.SWIFT_CONTAINER}' créé/configuré")
                    return True
                elif response.status == 204:  # No Content (déjà existe)
                    return True
                else:
                    logger.error(f"Échec création conteneur: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Erreur création conteneur: {e}")
            return False
    
    async def upload_file(self, local_file_path: str, remote_object_name: str) -> Optional[str]:
        """
        Upload un fichier vers le stockage distant
        
        Args:
            local_file_path: Chemin local du fichier
            remote_object_name: Nom de l'objet distant (ex: captures/20241201/uuid.jpg)
            
        Returns:
            URL publique du fichier ou None en cas d'erreur
        """
        try:
            if not os.path.exists(local_file_path):
                logger.error(f"Fichier local non trouvé: {local_file_path}")
                return None
            
            if not await self.authenticate():
                logger.error("Échec authentification pour upload")
                return None
            
            # Créer le conteneur si nécessaire
            if not await self.create_container_if_not_exists():
                logger.error("Impossible de créer/accéder au conteneur")
                return None
            
            # URL de l'objet
            object_url = f"{self.storage_url}/{settings.SWIFT_CONTAINER}/{remote_object_name}"
            
            # Lire le fichier
            with open(local_file_path, 'rb') as file:
                file_content = file.read()
            
            # Calculer l'ETag (MD5)
            etag = hashlib.md5(file_content).hexdigest()
            
            # Déterminer le Content-Type
            content_type = "image/jpeg"
            if remote_object_name.lower().endswith('.png'):
                content_type = "image/png"
            
            # Upload
            async with self.session.put(
                object_url,
                data=file_content,
                headers={
                    "X-Auth-Token": self.auth_token,
                    "Content-Type": content_type,
                    "ETag": etag
                }
            ) as response:
                
                if response.status in [201, 204]:  # Created or No Content
                    # URL publique
                    public_url = f"{self.storage_url}/{settings.SWIFT_CONTAINER}/{remote_object_name}"
                    
                    logger.info(f"✅ Fichier uploadé: {remote_object_name}")
                    return public_url
                else:
                    error_text = await response.text()
                    logger.error(f"Échec upload ({response.status}): {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Erreur upload fichier {local_file_path}: {e}")
            return None
    
    async def delete_file(self, remote_url: str) -> bool:
        """
        Supprime un fichier du stockage distant
        
        Args:
            remote_url: URL complète du fichier distant
            
        Returns:
            True si supprimé avec succès
        """
        try:
            if not await self.authenticate():
                return False
            
            # Extraire le nom de l'objet depuis l'URL
            if f"/{settings.SWIFT_CONTAINER}/" not in remote_url:
                logger.error(f"URL invalide: {remote_url}")
                return False
            
            object_name = remote_url.split(f"/{settings.SWIFT_CONTAINER}/")[1]
            object_url = f"{self.storage_url}/{settings.SWIFT_CONTAINER}/{object_name}"
            
            async with self.session.delete(
                object_url,
                headers={"X-Auth-Token": self.auth_token}
            ) as response:
                
                if response.status in [204, 404]:  # No Content or Not Found
                    logger.info(f"✅ Fichier supprimé: {object_name}")
                    return True
                else:
                    logger.error(f"Échec suppression ({response.status})")
                    return False
                    
        except Exception as e:
            logger.error(f"Erreur suppression fichier {remote_url}: {e}")
            return False
    
    async def get_file_info(self, remote_url: str) -> Optional[dict]:
        """
        Récupère les métadonnées d'un fichier distant
        
        Returns:
            Dict avec les informations du fichier ou None
        """
        try:
            if not await self.authenticate():
                return None
            
            if f"/{settings.SWIFT_CONTAINER}/" not in remote_url:
                return None
            
            object_name = remote_url.split(f"/{settings.SWIFT_CONTAINER}/")[1]
            object_url = f"{self.storage_url}/{settings.SWIFT_CONTAINER}/{object_name}"
            
            async with self.session.head(
                object_url,
                headers={"X-Auth-Token": self.auth_token}
            ) as response:
                
                if response.status == 200:
                    return {
                        "exists": True,
                        "size": int(response.headers.get("Content-Length", 0)),
                        "content_type": response.headers.get("Content-Type"),
                        "last_modified": response.headers.get("Last-Modified"),
                        "etag": response.headers.get("ETag")
                    }
                else:
                    return {"exists": False}
                    
        except Exception as e:
            logger.error(f"Erreur récupération info fichier: {e}")
            return None
    
    async def get_file_path(self, remote_url: str) -> Optional[str]:
        """
        Pour la compatibilité avec l'interface locale
        Retourne l'URL distante (pas de téléchargement local)
        """
        info = await self.get_file_info(remote_url)
        return remote_url if info and info.get("exists") else None
    
    async def list_container_objects(self, prefix: str = None, limit: int = 1000) -> list:
        """
        Liste les objets dans le conteneur
        
        Args:
            prefix: Préfixe pour filtrer les objets
            limit: Nombre maximum d'objets à retourner
            
        Returns:
            Liste des objets avec leurs métadonnées
        """
        try:
            if not await self.authenticate():
                return []
            
            container_url = f"{self.storage_url}/{settings.SWIFT_CONTAINER}"
            params = {"format": "json", "limit": limit}
            
            if prefix:
                params["prefix"] = prefix
            
            async with self.session.get(
                container_url,
                params=params,
                headers={"X-Auth-Token": self.auth_token}
            ) as response:
                
                if response.status == 200:
                    objects = await response.json()
                    return objects
                else:
                    logger.error(f"Échec listage objets: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Erreur listage objets: {e}")
            return []
    
    async def cleanup_old_files(self, days: int = 30) -> int:
        """
        Nettoie les fichiers anciens (utile pour maintenance)
        
        Returns:
            Nombre de fichiers supprimés
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            objects = await self.list_container_objects()
            
            deleted_count = 0
            for obj in objects:
                # Extraire la date depuis le nom de fichier si possible
                # Format: captures/YYYYMMDD/uuid.jpg
                obj_name = obj.get("name", "")
                if "/captures/" in obj_name:
                    try:
                        date_str = obj_name.split("/")[1]  # YYYYMMDD
                        obj_date = datetime.strptime(date_str, "%Y%m%d")
                        
                        if obj_date < cutoff_date:
                            object_url = f"{self.storage_url}/{settings.SWIFT_CONTAINER}/{obj_name}"
                            await self.session.delete(
                                object_url,
                                headers={"X-Auth-Token": self.auth_token}
                            )
                            deleted_count += 1
                            
                    except (IndexError, ValueError):
                        # Nom de fichier ne respecte pas le format attendu
                        continue
            
            logger.info(f"🧹 Nettoyage stockage: {deleted_count} fichiers supprimés")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Erreur nettoyage stockage: {e}")
            return 0

# Instance globale (à utiliser avec des gestionnaires de contexte)
async def get_storage_service():
    """Factory function pour obtenir le service de stockage"""
    return StorageService()