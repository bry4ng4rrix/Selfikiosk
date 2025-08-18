from fastapi import APIRouter, Depends
from datetime import datetime
import psutil
import os
import redis
import logging
import asyncio
import time

from database import get_db, Database
from models import HealthStatus, BaseResponse
from app_settings import app_settings
from services.storage import StorageService
from services.sms import SMSService

router = APIRouter()
logger = logging.getLogger(__name__)

# Variables globales pour le monitoring
startup_time = datetime.now()

@router.get("/", response_model=HealthStatus)
async def health_check(db: Database = Depends(get_db)):
    """
    Point de terminaison de santé complet du système
    Vérifie tous les composants critiques
    """
    checks = {}
    overall_status = "healthy"
    
    # Test base de données
    try:
        await db.fetch_one("SELECT 1")
        checks["database"] = True
    except Exception as e:
        checks["database"] = False
        overall_status = "unhealthy"
        logger.error(f"Database health check failed: {e}")
    
    # Test Redis
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.ping()
        checks["redis"] = True
        r.close()
    except Exception as e:
        checks["redis"] = False
        overall_status = "degraded" if overall_status == "healthy" else "unhealthy"
        logger.error(f"Redis health check failed: {e}")
    
    # Test stockage local
    try:
        disk_usage = psutil.disk_usage(settings.UPLOAD_DIR)
        free_gb = disk_usage.free / (1024**3)
        checks["storage"] = free_gb > 1.0  # Au moins 1GB libre
        if not checks["storage"]:
            overall_status = "degraded" if overall_status == "healthy" else overall_status
    except Exception as e:
        checks["storage"] = False
        free_gb = 0
        overall_status = "unhealthy"
        logger.error(f"Storage health check failed: {e}")
    
    # Test API OVH (si configurée)
    ovh_status = False
    try:
        if settings.OVH_APPLICATION_KEY:
            sms_service = SMSService()
            ovh_status = await sms_service.test_connection()
        else:
            ovh_status = True  # Pas configuré = OK
    except Exception as e:
        logger.error(f"OVH health check failed: {e}")
    
    checks["ovh_api"] = ovh_status
    if not ovh_status and settings.OVH_APPLICATION_KEY:
        overall_status = "degraded" if overall_status == "healthy" else overall_status
    
    # Métriques système
    memory_info = psutil.virtual_memory()
    uptime_seconds = (datetime.now() - startup_time).total_seconds()
    
    return HealthStatus(
        status=overall_status,
        database=checks["database"],
        redis=checks["redis"],
        storage=checks["storage"],
        ovh_api=checks["ovh_api"],
        disk_space_gb=free_gb,
        memory_usage_percent=memory_info.percent,
        uptime_seconds=int(uptime_seconds)
    )

@router.get("/ping", response_model=dict)
async def ping():
    """Point de terminaison simple pour vérifier que l'API répond"""
    return {
        "status": "ok",
        "timestamp": datetime.now(),
        "uptime_seconds": int((datetime.now() - startup_time).total_seconds())
    }

@router.get("/readiness", response_model=dict)
async def readiness_check(db: Database = Depends(get_db)):
    """
    Check de préparation - vérifie si l'application est prête à recevoir du trafic
    Utilisé par les orchestrateurs comme Kubernetes
    """
    try:
        # Test base de données
        await db.fetch_one("SELECT 1")
        
        # Test dossier uploads
        if not os.path.exists(settings.UPLOAD_DIR):
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        
        # Test écriture
        test_file = os.path.join(settings.UPLOAD_DIR, ".health_check")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        
        return {
            "status": "ready",
            "timestamp": datetime.now(),
            "message": "Application ready to serve traffic"
        }
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {
            "status": "not_ready",
            "timestamp": datetime.now(),
            "message": str(e)
        }

@router.get("/liveness", response_model=dict)
async def liveness_check():
    """
    Check de vivacité - vérifie si l'application fonctionne
    Utilisé par les orchestrateurs pour redémarrer l'application si nécessaire
    """
    try:
        # Test simple de réponse
        current_time = datetime.now()
        
        # Test que l'application n'est pas bloquée (timeout de 1 seconde)
        start_time = time.time()
        await asyncio.sleep(0.001)  # Test async
        response_time = (time.time() - start_time) * 1000
        
        if response_time > 1000:  # Plus de 1 seconde
            raise Exception("Application appears to be blocked")
        
        return {
            "status": "alive",
            "timestamp": current_time,
            "response_time_ms": response_time
        }
        
    except Exception as e:
        logger.error(f"Liveness check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now(),
            "message": str(e)
        }

@router.get("/metrics", response_model=dict)
async def system_metrics():
    """Métriques système détaillées pour monitoring"""
    try:
        # Métriques CPU et mémoire
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_info = psutil.virtual_memory()
        
        # Métriques disque
        disk_usage = psutil.disk_usage(settings.UPLOAD_DIR)
        
        # Métriques réseau (optionnel)
        try:
            network_io = psutil.net_io_counters()
            network_stats = {
                "bytes_sent": network_io.bytes_sent,
                "bytes_recv": network_io.bytes_recv,
                "packets_sent": network_io.packets_sent,
                "packets_recv": network_io.packets_recv
            }
        except:
            network_stats = None
        
        # Uptime
        uptime_seconds = (datetime.now() - startup_time).total_seconds()
        
        metrics = {
            "timestamp": datetime.now(),
            "uptime_seconds": int(uptime_seconds),
            "cpu": {
                "usage_percent": cpu_percent,
                "count": psutil.cpu_count()
            },
            "memory": {
                "total_gb": round(memory_info.total / (1024**3), 2),
                "available_gb": round(memory_info.available / (1024**3), 2),
                "used_gb": round(memory_info.used / (1024**3), 2),
                "usage_percent": memory_info.percent
            },
            "disk": {
                "total_gb": round(disk_usage.total / (1024**3), 2),
                "free_gb": round(disk_usage.free / (1024**3), 2),
                "used_gb": round(disk_usage.used / (1024**3), 2),
                "usage_percent": round((disk_usage.used / disk_usage.total) * 100, 2)
            }
        }
        
        if network_stats:
            metrics["network"] = network_stats
        
        return metrics
        
    except Exception as e:
        logger.error(f"Metrics collection failed: {e}")
        return {
            "error": str(e),
            "timestamp": datetime.now()
        }

@router.get("/version", response_model=dict)
async def version_info():
    """Informations sur la version de l'application"""
    return {
        "name": "Selfie Kiosk API",
        "version": "1.0.0",
        "build_date": "2024",
        "python_version": "3.10+",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "startup_time": startup_time
    }