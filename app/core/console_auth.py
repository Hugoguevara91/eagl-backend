import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from firebase_admin import auth
from sqlalchemy.orm import Session

from app.core.firebase import get_firebase_app
from app.db import models
from app.db.session import get_db


def _extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente")
    return auth_header.split(" ", 1)[1].strip()


def _ensure_console_origin(request: Request) -> None:
    allowed = os.getenv("CONSOLE_CORS_ORIGINS")
    allowed_origins = (
        [origin.strip() for origin in allowed.split(",") if origin.strip()]
        if allowed
        else ["https://console.eagl.com.br", "http://localhost:5173"]
    )
    origin = request.headers.get("origin")
    if origin and origin not in allowed_origins:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origem nao permitida")


def _find_owner(db: Session, uid: Optional[str], email: Optional[str]) -> Optional[models.Owner]:
    if uid:
        owner = db.query(models.Owner).filter(models.Owner.uid == uid).first()
        if owner:
            return owner
    if email:
        lowered = email.strip().lower()
        return db.query(models.Owner).filter(models.Owner.email == lowered).first()
    return None


def require_owner(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    _ensure_console_origin(request)
    token = _extract_bearer_token(request)
    try:
        get_firebase_app()
        decoded = auth.verify_id_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido")

    uid = decoded.get("uid")
    email = decoded.get("email")
    owner = _find_owner(db, uid, email)
    if not owner or owner.status.upper() != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissao")
    return {"uid": uid, "email": email, "role": "OWNER"}
