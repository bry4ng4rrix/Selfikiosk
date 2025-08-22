import asyncio
import shutil
import time
from typing import Dict, Any
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import redis
import psycopg2
from ..db.database import SessionLocal, local_engine
from ..core.config import settings

class HealthCheckService:
  
    
    @staticmethod
    async def check_database_connectivity() -> Dict[str, Any]:
        """Check local and remote database connectivity."""
        result = {
            "local_db": {"status": "unknown", "response_time_ms": None, "error": None},
            "remote_db": {"status": "unknown", "response_time_ms": None, "error": None}
        }
        
        # Check local database
        try:
            start_time = time.time()
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            db.close()
            response_time = (time.time() - start_time) * 1000
            result["local_db"] = {
                "status": "Bonne",
                "response_time_ms": round(response_time, 2),
                "error": None
            }
        except SQLAlchemyError as e:
            result["local_db"] = {
                "status": "Mauvaise",
                "response_time_ms": None,
                "error": str(e)
            }
        
        # Check remote database (PostgreSQL)
        try:
            start_time = time.time()
            conn = psycopg2.connect(settings.REMOTE_DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            response_time = (time.time() - start_time) * 1000
            result["remote_db"] = {
                "status": "Bonne",
                "response_time_ms": round(response_time, 2),
                "error": None
            }
        except Exception as e:
            result["remote_db"] = {
                "status": "Mauvaise",
                "response_time_ms": None,
                "error": str(e)
            }
        
        return result
    
    @staticmethod
    async def check_disk_space() -> Dict[str, Any]:
        """Check available disk space."""
        try:
            # Check disk space for current directory
            total, used, free = shutil.disk_usage(".")
            
            # Convert to GB
            total_gb = total / (1024**3)
            used_gb = used / (1024**3)
            free_gb = free / (1024**3)
            usage_percent = (used / total) * 100
            
            # Consider healthy if less than 90% used and at least 1GB free
            is_healthy = usage_percent < 90 and free_gb > 1
            
            return {
                "status": "Bonne" if is_healthy else "Attention",
                "total_gb": round(total_gb, 2),
                "used_gb": round(used_gb, 2),
                "free_gb": round(free_gb, 2),
                "usage_percent": round(usage_percent, 2),
                "error": None
            }
        except Exception as e:
            return {
                "status": "Mauvaise",
                "total_gb": None,
                "used_gb": None,
                "free_gb": None,
                "usage_percent": None,
                "error": str(e)
            }
    
    @staticmethod
    async def check_vps_connectivity() -> Dict[str, Any]:
        """Check VPS connectivity by testing remote database connection."""
        try:
            start_time = time.time()
            conn = psycopg2.connect(settings.REMOTE_DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            response_time = (time.time() - start_time) * 1000
            
            return {
                "status": "Bonne",
                "response_time_ms": round(response_time, 2),
                "postgres_version": version,
                "error": None
            }
        except Exception as e:
            return {
                "status": "Mauvaise",
                "response_time_ms": None,
                "postgres_version": None,
                "error": str(e)
            }
    
    @staticmethod
    async def check_redis_queue() -> Dict[str, Any]:
        """Check Redis queue functionality."""
        try:
            start_time = time.time()
            r = redis.from_url(settings.REDIS_URL)
            
            # Test basic operations
            test_key = "health_check_test"
            test_value = "test_value"
            
            # Set and get a test value
            r.set(test_key, test_value, ex=10)  # Expire in 10 seconds
            retrieved_value = r.get(test_key)
            r.delete(test_key)
            
            # Check if value was correctly stored and retrieved
            if retrieved_value and retrieved_value.decode() == test_value:
                response_time = (time.time() - start_time) * 1000
                
                # Get Redis info
                info = r.info()
                
                return {
                    "status": "Bonne",
                    "response_time_ms": round(response_time, 2),
                    "redis_version": info.get('redis_version', 'unknown'),
                    "connected_clients": info.get('connected_clients', 0),
                    "used_memory_human": info.get('used_memory_human', 'unknown'),
                    "error": None
                }
            else:
                return {
                    "status": "Mauvaise",
                    "response_time_ms": None,
                    "redis_version": None,
                    "connected_clients": None,
                    "used_memory_human": None,
                    "error": "Redis test operation failed"
                }
                
        except Exception as e:
            return {
                "status": "Mauvaise",
                "response_time_ms": None,
                "redis_version": None,
                "connected_clients": None,
                "used_memory_human": None,
                "error": str(e)
            }
    
    @classmethod
    async def perform_all_checks(cls) -> Dict[str, Any]:
        """Perform all health checks concurrently."""
        start_time = time.time()
        
        # Run all checks concurrently (removed OVH API check)
        database_check, disk_check, vps_check, redis_check = await asyncio.gather(
            cls.check_database_connectivity(),
            cls.check_disk_space(),
            cls.check_vps_connectivity(),
            cls.check_redis_queue(),
            return_exceptions=True
        )
        
        total_time = (time.time() - start_time) * 1000
        
        # Handle any exceptions from the checks
        checks = {
            "database": database_check if not isinstance(database_check, Exception) else {
                "status": "error", "error": str(database_check)
            },
            "disk": disk_check if not isinstance(disk_check, Exception) else {
                "status": "error", "error": str(disk_check)
            },
            "vps": vps_check if not isinstance(vps_check, Exception) else {
                "status": "error", "error": str(vps_check)
            },
            "redis": redis_check if not isinstance(redis_check, Exception) else {
                "status": "error", "error": str(redis_check)
            }
        }
        
        # Determine overall status
        all_statuses = []
        for check_name, check_result in checks.items():
            if isinstance(check_result, dict):
                if check_name == "database":
                    # For database, check both local and remote
                    all_statuses.extend([
                        check_result.get("local_db", {}).get("status", "unknown"),
                        check_result.get("remote_db", {}).get("status", "unknown")
                    ])
                else:
                    all_statuses.append(check_result.get("status", "unknown"))
        
        # Overall status logic
        if any(status == "Mauvaise" or status == "error" for status in all_statuses):
            overall_status = "Mauvaise"
        elif any(status == "warning" for status in all_statuses):
            overall_status = "warning"
        elif all(status == "Bonne" for status in all_statuses):
            overall_status = "Bonne"
        else:
            overall_status = "unknown"
        
        # Connectivity status (online/offline) derived from external services
        # Consider online if remote DB OR Redis are in "Bonne" state (removed OVH dependency)
        remote_db_status = checks.get("database", {}).get("remote_db", {}).get("status") if isinstance(checks.get("database"), dict) else None
        redis_status = checks.get("redis", {}).get("status") if isinstance(checks.get("redis"), dict) else None
        is_online = any(s == "Bonne" for s in [remote_db_status, redis_status])
        connectivity = {
            "online": bool(is_online),
            "status": "online" if is_online else "offline"
        }

        return {
            "status": overall_status,
            "timestamp": time.time(),
            "total_check_time_ms": round(total_time, 2),
            "checks": checks,
            "connectivity": connectivity
        }