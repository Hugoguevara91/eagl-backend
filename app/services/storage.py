import os
from datetime import timedelta
from functools import lru_cache
from typing import Optional

from google.cloud import storage


@lru_cache(maxsize=1)
def get_storage_client() -> storage.Client:
    return storage.Client()


def get_bucket_name() -> str:
    bucket = os.getenv("GCS_BUCKET_OS_ASSETS")
    if not bucket:
        raise RuntimeError("GCS_BUCKET_OS_ASSETS is not configured")
    return bucket


def upload_bytes(
    data: bytes,
    object_name: str,
    content_type: Optional[str] = None,
) -> str:
    client = get_storage_client()
    bucket = client.bucket(get_bucket_name())
    blob = bucket.blob(object_name)
    blob.upload_from_string(data, content_type=content_type)
    return object_name


def upload_file(
    file_obj,
    object_name: str,
    content_type: Optional[str] = None,
) -> str:
    client = get_storage_client()
    bucket = client.bucket(get_bucket_name())
    blob = bucket.blob(object_name)
    blob.upload_from_file(file_obj, content_type=content_type)
    return object_name


def delete_object(object_name: str) -> None:
    client = get_storage_client()
    bucket = client.bucket(get_bucket_name())
    blob = bucket.blob(object_name)
    blob.delete()


def generate_signed_url(object_name: str, expires_minutes: int = 30) -> str:
    client = get_storage_client()
    bucket = client.bucket(get_bucket_name())
    blob = bucket.blob(object_name)
    return blob.generate_signed_url(expiration=timedelta(minutes=expires_minutes), method="GET")
