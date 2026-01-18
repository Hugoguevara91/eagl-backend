import logging
import os

from fastapi import APIRouter

from app.core import config
from app.services.geocode import reverse_geocode

router = APIRouter()
logger = logging.getLogger("eagl.doctor")


@router.get("/doctor/maps")
def doctor_maps():
    result = reverse_geocode(-23.5505, -46.6333)
    ok = result and result.get("status") == "OK"
    if not ok:
        logger.warning("doctor/maps failed")
    return {"status": "OK" if ok else "ERROR"}


@router.get("/doctor")
def doctor():
    settings = config.settings
    maps_ok = bool(os.getenv("GOOGLE_MAPS_API_KEY"))
    storage_bulk_ok = bool(os.getenv("GCS_BUCKET"))
    storage_os_ok = bool(os.getenv("GCS_BUCKET_OS_ASSETS"))
    firebase_ok = bool(os.getenv("FIREBASE_CREDENTIALS_JSON") or os.getenv("FIREBASE_CREDENTIALS_PATH"))
    pdf_ok = True
    try:
        import weasyprint  # noqa: F401
    except Exception:
        pdf_ok = False

    overall = all([maps_ok, storage_bulk_ok, storage_os_ok, firebase_ok, pdf_ok])
    return {
        "status": "OK" if overall else "WARN",
        "maps": "OK" if maps_ok else "ERROR",
        "storage_bulk": "OK" if storage_bulk_ok else "ERROR",
        "storage_os": "OK" if storage_os_ok else "ERROR",
        "pdf": "OK" if pdf_ok else "ERROR",
        "auth": "OK" if firebase_ok else "ERROR",
        "cors": "OK" if settings.BACKEND_CORS_ORIGINS else "ERROR",
    }
