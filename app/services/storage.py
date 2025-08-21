import os
from typing import Optional, Dict
import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from ..core.config import settings


def is_s3_configured() -> bool:
    return bool(settings.S3_ENDPOINT_URL and settings.S3_BUCKET_NAME and settings.S3_ACCESS_KEY and settings.S3_SECRET_KEY)


def get_s3_client():
    session = boto3.session.Session()
    return session.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=getattr(settings, "S3_REGION", None) or None,
        config=BotoConfig(s3={"addressing_style": "path"})
    )


def upload_file_to_s3(local_path: str, object_key: str, content_type: Optional[str] = None) -> Dict[str, str]:
    """
    Upload a file to OVH PCS (S3-compatible). Returns dict with object_key and optional presigned_url.
    """
    if not is_s3_configured():
        raise RuntimeError("S3 storage is not configured")

    s3 = get_s3_client()
    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type
    try:
        s3.upload_file(local_path, settings.S3_BUCKET_NAME, object_key, ExtraArgs=extra_args or None)
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"S3 upload failed: {e}")

    return {
        "object_key": object_key,
        "s3_pointer": f"s3://{settings.S3_BUCKET_NAME}/{object_key}",
    }


def generate_presigned_url(s3_pointer: str, expires_seconds: int = 604800) -> Optional[str]:
    """
    Generate a presigned GET URL for a given s3://bucket/key pointer.
    """
    if not is_s3_configured():
        return None
    if not s3_pointer.startswith("s3://"):
        return None
    _, rest = s3_pointer.split("s3://", 1)
    bucket, key = rest.split("/", 1)
    s3 = get_s3_client()
    try:
        url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
        return url
    except (BotoCoreError, ClientError) as e:
        return None
