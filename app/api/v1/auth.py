from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.security import (
    build_user_context,
    create_access_token,
    get_password_hash,
    verify_password_with_upgrade,
)
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["Auth"])


class LoginRequest(BaseModel):
    usuario: str
    senha: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    role: str


def _authenticate(db: Session, username: str, password: str) -> models.User:
    normalized = username.strip().lower()
    query = db.query(models.User).join(models.Tenant, models.Tenant.id == models.User.tenant_id)
    query = query.filter(models.Tenant.status.in_(["active", "ATIVO", "TRIAL"]))
    query = query.filter(
        or_(
            func.lower(models.User.login) == normalized,
            func.lower(models.User.email) == normalized,
        )
    )
    users = query.order_by(models.User.created_at.desc()).all()
    if not users:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario ou senha invalidos"
        )
    user = users[0]
    ok, needs_upgrade = verify_password_with_upgrade(password, user.password_hash)
    if not user or not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario ou senha invalidos"
        )
    if needs_upgrade:
        user.password_hash = get_password_hash(password)
        db.add(user)
        db.commit()
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inativo")
    return user


@router.post("/auth/login", response_model=LoginResponse, summary="Login JSON (frontend)")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Uso tipico via frontend/script JSON:
    - POST /api/auth/login
    - body: {"usuario": "...", "senha": "..."}
    """
    user = _authenticate(db, payload.usuario, payload.senha)
    context = build_user_context(db, user)
    token = create_access_token(
        {
            "sub": user.id,
            "tenant_id": user.tenant_id,
            "role": user.role,
            "roles": context["roles"],
            "permissions_effective": context["permissions"],
            "scope": context["scope"],
        }
    )
    return {"access_token": token, "token_type": "bearer", "role": user.role}


@router.post(
    "/auth/token",
    response_model=LoginResponse,
    summary="Login para Swagger (OAuth2PasswordBearer)",
)
def login_swagger(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Uso via Swagger UI (botao Authorize):
    - tokenUrl aponta para este endpoint.
    - Campos esperados: username / password.
    """
    user = _authenticate(db, form_data.username, form_data.password)
    context = build_user_context(db, user)
    token = create_access_token(
        {
            "sub": user.id,
            "tenant_id": user.tenant_id,
            "role": user.role,
            "roles": context["roles"],
            "permissions_effective": context["permissions"],
            "scope": context["scope"],
        }
    )
    return {"access_token": token, "token_type": "bearer", "role": user.role}
