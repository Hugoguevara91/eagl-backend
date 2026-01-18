from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.console_auth import require_owner
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["Console"])


class ConsoleMeResponse(BaseModel):
    uid: str | None = None
    email: str | None = None
    role: str


class TenantResponse(BaseModel):
    id: str
    name: str
    tenant_type: str
    status: str
    created_at: str


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1)
    tenant_type: str = Field(..., min_length=1)
    status: str = Field("ACTIVE", min_length=1)


class TenantStatusUpdate(BaseModel):
    status: str = Field(..., min_length=1)


def _slugify(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("\\", "-")
        .replace("--", "-")
    )


def _normalize_status(value: str) -> str:
    val = value.strip().upper()
    if val in {"ACTIVE", "ATIVO"}:
        return "ATIVO"
    if val in {"SUSPENDED", "SUSPENSO", "SUSPENSA"}:
        return "SUSPENSO"
    if val in {"TRIAL"}:
        return "TRIAL"
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Status invalido")


def _normalize_tenant_type(value: str) -> str:
    val = value.strip().upper().replace(" ", "_")
    if val in {"MSP", "PRESTADOR"}:
        return "MSP"
    if val in {"ENTERPRISE", "ATIVOS_PROPRIOS"}:
        return "ENTERPRISE"
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo invalido")


def _to_tenant_response(tenant: models.Tenant) -> TenantResponse:
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        tenant_type=tenant.tenant_type,
        status=tenant.status,
        created_at=tenant.created_at.isoformat(),
    )


@router.get("/me", response_model=ConsoleMeResponse)
def get_me(owner=Depends(require_owner)):
    return ConsoleMeResponse(**owner)


@router.get("/tenants")
def list_tenants(
    _owner=Depends(require_owner),
    db: Session = Depends(get_db),
):
    tenants = db.query(models.Tenant).order_by(models.Tenant.created_at.desc()).all()
    return {"items": [_to_tenant_response(tenant).model_dump() for tenant in tenants]}


@router.post("/tenants", status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    _owner=Depends(require_owner),
    db: Session = Depends(get_db),
):
    tenant = models.Tenant(
        name=payload.name.strip(),
        slug=_slugify(payload.name),
        status=_normalize_status(payload.status),
        tenant_type=_normalize_tenant_type(payload.tenant_type),
        timezone="America/Sao_Paulo",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return {"tenant": _to_tenant_response(tenant).model_dump()}


@router.patch("/tenants/{tenant_id}/status")
def update_tenant_status(
    tenant_id: str,
    payload: TenantStatusUpdate,
    _owner=Depends(require_owner),
    db: Session = Depends(get_db),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nao encontrado")
    tenant.status = _normalize_status(payload.status)
    tenant.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(tenant)
    return {"tenant": _to_tenant_response(tenant).model_dump()}
