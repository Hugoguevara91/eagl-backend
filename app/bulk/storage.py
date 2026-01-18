import hashlib
import os
import pathlib
import tempfile
from typing import BinaryIO, Tuple

from google.cloud import storage


class StorageError(Exception):
    pass


class StorageClient:
    def __init__(self) -> None:
        self.bucket_name = os.getenv("GCS_BUCKET")
        self.use_local = os.getenv("LOCAL_STORAGE", "0") == "1" or not self.bucket_name
        self.base_dir = pathlib.Path(os.getenv("LOCAL_STORAGE_DIR", "storage")).resolve()
        if self.use_local:
            self.base_dir.mkdir(parents=True, exist_ok=True)
        self._client = storage.Client() if self.bucket_name and not self.use_local else None

    def _ensure_bucket(self):
        if not self.bucket_name or not self._client:
            raise StorageError("GCS_BUCKET nao configurado.")
        return self._client.bucket(self.bucket_name)

    def upload_bytes(self, content: bytes, dest_path: str, content_type: str) -> str:
        if self.use_local:
            full_path = self.base_dir / dest_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(content)
            return full_path.as_uri()
        bucket = self._ensure_bucket()
        blob = bucket.blob(dest_path)
        blob.upload_from_string(content, content_type=content_type)
        return f"gs://{self.bucket_name}/{dest_path}"

    def upload_file(
        self,
        file_obj: BinaryIO,
        dest_path: str,
        content_type: str,
        max_bytes: int | None = None,
    ) -> Tuple[str, int, str]:
        hasher = hashlib.sha256()
        total = 0
        if self.use_local:
            full_path = self.base_dir / dest_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "wb") as handle:
                while True:
                    chunk = file_obj.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    total += len(chunk)
                    hasher.update(chunk)
                    if max_bytes and total > max_bytes:
                        raise StorageError("Arquivo excede o tamanho maximo permitido.")
            return full_path.as_uri(), total, hasher.hexdigest()

        bucket = self._ensure_bucket()
        blob = bucket.blob(dest_path)
        with blob.open("wb") as handle:
            while True:
                chunk = file_obj.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                total += len(chunk)
                hasher.update(chunk)
                if max_bytes and total > max_bytes:
                    raise StorageError("Arquivo excede o tamanho maximo permitido.")
        blob.content_type = content_type
        blob.patch()
        return f"gs://{self.bucket_name}/{dest_path}", total, hasher.hexdigest()

    def download_to_temp(self, file_url: str) -> str:
        if file_url.startswith("file://"):
            return file_url.replace("file:///", "")
        if file_url.startswith("gs://"):
            _, path = file_url.split("gs://", 1)
            bucket_name, blob_path = path.split("/", 1)
            client = self._client or storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(blob_path)[1])
            os.close(fd)
            blob.download_to_filename(tmp_path)
            return tmp_path
        raise StorageError("URL de arquivo nao suportada.")

    def generate_signed_url(self, file_url: str, expires_minutes: int = 30) -> str:
        if file_url.startswith("file://"):
            return file_url
        if file_url.startswith("gs://"):
            _, path = file_url.split("gs://", 1)
            bucket_name, blob_path = path.split("/", 1)
            client = self._client or storage.Client()
            blob = client.bucket(bucket_name).blob(blob_path)
            return blob.generate_signed_url(expiration=expires_minutes * 60, method="GET")
        raise StorageError("URL de arquivo nao suportada.")
