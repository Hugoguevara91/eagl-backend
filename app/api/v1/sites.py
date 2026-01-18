import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.authorization import apply_scope_to_query, enforce_client_user_scope, require_scope_or_admin
from app.core.security import get_current_user, require_permission
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["Sites"])


class SiteCreate(BaseModel):
    nome: str = Field(..., min_length=1)
    code: str | None = None
    status: str = "ATIVO"
    endereco: str | None = None
    customer_account_id: str | None = None


class SiteUpdate(BaseModel):
    nome: str | None = None
    code: str | None = None
    status: str | None = None
    endereco: str | None = None
    customer_account_id: str | None = None


class SiteResponse(BaseModel):
    id: str
    nome: str
    code: str | None = None
    status: str
    endereco: str | None = None
    customer_account_id: str | None = None
    created_at: str
    updated_at: str


def _get_tenant(current_user: models.User, db: Session) -> models.Tenant:
    tenant = current_user.tenant
    if not tenant:
        tenant = db.query(models.Tenant).filter(models.Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nao encontrado")
    return tenant


def _validate_customer_account(
    tenant: models.Tenant,
    customer_account_id: str | None,
    db: Session,
) -> str | None:
    if tenant.tenant_type == "MSP":
        if not customer_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cliente final obrigatorio para tenants MSP",
            )
        account = (
            db.query(models.CustomerAccount)
            .filter(
                models.CustomerAccount.id == customer_account_id,
                models.CustomerAccount.tenant_id == tenant.id,
            )
            .first()
        )
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente final nao encontrado")
        return account.id

    if customer_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cliente final nao permitido para tenants Enterprise",
        )
    return None


def _to_response(site: models.Site) -> SiteResponse:
    return SiteResponse(
        id=site.id,
        nome=site.name,
        code=site.code,
        status=site.status,
        endereco=site.address,
        customer_account_id=site.customer_account_id,
        created_at=site.created_at.isoformat(),
        updated_at=site.updated_at.isoformat(),
    )


@router.get("/sites")
def list_sites(
    customer_account_id: str | None = Query(default=None),
    current_user: models.User = Depends(require_permission("assets.view")),
    db: Session = Depends(get_db),
):
    tenant = _get_tenant(current_user, db)
    scope = require_scope_or_admin(db, current_user)
    query = db.query(models.Site).filter(models.Site.tenant_id == current_user.tenant_id)
    query = apply_scope_to_query(query, scope, site_field=models.Site.id, client_field=models.Site.customer_account_id)
    if tenant.tenant_type == "MSP" and customer_account_id:
        query = query.filter(models.Site.customer_account_id == customer_account_id)
    sites = query.order_by(models.Site.created_at.desc()).all()
    return {"items": [_to_response(site) for site in sites]}


@router.post("/sites", status_code=status.HTTP_201_CREATED)
def create_site(
    payload: SiteCreate,
    current_user: models.User = Depends(require_permission("assets.manage")),
    db: Session = Depends(get_db),
):
    tenant = _get_tenant(current_user, db)
    customer_account_id = _validate_customer_account(tenant, payload.customer_account_id, db)
    site = models.Site(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        customer_account_id=customer_account_id,
        code=payload.code,
        name=payload.nome,
        status=payload.status or "ATIVO",
        address=payload.endereco,
    )
    db.add(site)
    db.commit()
    db.refresh(site)
    return _to_response(site)


@router.get("/sites/{site_id}")
def get_site(
    site_id: str,
    current_user: models.User = Depends(require_permission("assets.view")),
    db: Session = Depends(get_db),
):
    _get_tenant(current_user, db)
    scope = require_scope_or_admin(db, current_user)
    query = db.query(models.Site).filter(
        models.Site.id == site_id, models.Site.tenant_id == current_user.tenant_id
    )
    query = apply_scope_to_query(query, scope, site_field=models.Site.id, client_field=models.Site.customer_account_id)
    site = query.first()
    if not site:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site nao encontrado")
    if site.customer_account_id:
        enforce_client_user_scope(current_user, site.customer_account_id)
    return _to_response(site)


@router.patch("/sites/{site_id}")
def update_site(
    site_id: str,
    payload: SiteUpdate,
    current_user: models.User = Depends(require_permission("assets.manage")),
    db: Session = Depends(get_db),
):
    tenant = _get_tenant(current_user, db)
    scope = require_scope_or_admin(db, current_user)
    query = db.query(models.Site).filter(
        models.Site.id == site_id, models.Site.tenant_id == current_user.tenant_id
    )
    query = apply_scope_to_query(query, scope, site_field=models.Site.id, client_field=models.Site.customer_account_id)
    site = query.first()
    if not site:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site nao encontrado")
    if site.customer_account_id:
        enforce_client_user_scope(current_user, site.customer_account_id)
    if payload.nome is not None:
        site.name = payload.nome
    if payload.code is not None:
        site.code = payload.code
    if payload.status is not None:
        site.status = payload.status
    if payload.endereco is not None:
        site.address = payload.endereco
    if "customer_account_id" in payload.__fields_set__:
        customer_account_id = _validate_customer_account(tenant, payload.customer_account_id, db)
        site.customer_account_id = customer_account_id
    db.commit()
    db.refresh(site)
    return _to_response(site)


@router.delete("/sites/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_site(
    site_id: str,
    current_user: models.User = Depends(require_permission("assets.manage")),
    db: Session = Depends(get_db),
):
    _get_tenant(current_user, db)
    scope = require_scope_or_admin(db, current_user)
    query = db.query(models.Site).filter(
        models.Site.id == site_id, models.Site.tenant_id == current_user.tenant_id
    )
    query = apply_scope_to_query(query, scope, site_field=models.Site.id, client_field=models.Site.customer_account_id)
    site = query.first()
    if not site:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site nao encontrado")
    if site.customer_account_id:
        enforce_client_user_scope(current_user, site.customer_account_id)
    db.delete(site)
    db.commit()
    return None
