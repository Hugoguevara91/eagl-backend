import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.authorization import apply_scope_to_query, enforce_client_user_scope, require_scope_or_admin
from app.core.security import get_current_user, require_permission
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["CustomerAccounts"])


class CustomerAccountCreate(BaseModel):
    nome: str = Field(..., min_length=1)
    cnpj: str | None = None
    status: str = "ATIVO"


class CustomerAccountUpdate(BaseModel):
    nome: str | None = None
    cnpj: str | None = None
    status: str | None = None


class CustomerAccountResponse(BaseModel):
    id: str
    nome: str
    cnpj: str | None = None
    status: str
    created_at: str
    updated_at: str


def _ensure_msp_tenant(current_user: models.User, db: Session) -> models.Tenant:
    tenant = current_user.tenant
    if not tenant:
        tenant = db.query(models.Tenant).filter(models.Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nao encontrado")
    if tenant.tenant_type != "MSP":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recurso disponivel apenas para tenants MSP",
        )
    return tenant


def _to_response(account: models.CustomerAccount) -> CustomerAccountResponse:
    return CustomerAccountResponse(
        id=account.id,
        nome=account.name,
        cnpj=account.cnpj,
        status=account.status,
        created_at=account.created_at.isoformat(),
        updated_at=account.updated_at.isoformat(),
    )


@router.get("/customer-accounts")
def list_customer_accounts(
    current_user: models.User = Depends(require_permission("clients.view")),
    db: Session = Depends(get_db),
):
    _ensure_msp_tenant(current_user, db)
    scope = require_scope_or_admin(db, current_user)
    query = db.query(models.CustomerAccount).filter(
        models.CustomerAccount.tenant_id == current_user.tenant_id
    )
    query = apply_scope_to_query(query, scope, client_field=models.CustomerAccount.id)
    accounts = query.order_by(models.CustomerAccount.created_at.desc()).all()
    return {"items": [_to_response(account) for account in accounts]}


@router.post("/customer-accounts", status_code=status.HTTP_201_CREATED)
def create_customer_account(
    payload: CustomerAccountCreate,
    current_user: models.User = Depends(require_permission("clients.manage")),
    db: Session = Depends(get_db),
):
    _ensure_msp_tenant(current_user, db)
    account = models.CustomerAccount(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        name=payload.nome,
        cnpj=payload.cnpj,
        status=payload.status or "ATIVO",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return _to_response(account)


@router.get("/customer-accounts/{account_id}")
def get_customer_account(
    account_id: str,
    current_user: models.User = Depends(require_permission("clients.view")),
    db: Session = Depends(get_db),
):
    _ensure_msp_tenant(current_user, db)
    scope = require_scope_or_admin(db, current_user)
    query = db.query(models.CustomerAccount).filter(
        models.CustomerAccount.id == account_id,
        models.CustomerAccount.tenant_id == current_user.tenant_id,
    )
    query = apply_scope_to_query(query, scope, client_field=models.CustomerAccount.id)
    account = query.first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente nao encontrado")
    enforce_client_user_scope(current_user, account.id)
    return _to_response(account)


@router.patch("/customer-accounts/{account_id}")
def update_customer_account(
    account_id: str,
    payload: CustomerAccountUpdate,
    current_user: models.User = Depends(require_permission("clients.manage")),
    db: Session = Depends(get_db),
):
    _ensure_msp_tenant(current_user, db)
    account = (
        db.query(models.CustomerAccount)
        .filter(
            models.CustomerAccount.id == account_id,
            models.CustomerAccount.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente nao encontrado")
    enforce_client_user_scope(current_user, account.id)
    if payload.nome is not None:
        account.name = payload.nome
    if payload.cnpj is not None:
        account.cnpj = payload.cnpj
    if payload.status is not None:
        account.status = payload.status
    db.commit()
    db.refresh(account)
    return _to_response(account)


@router.delete("/customer-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer_account(
    account_id: str,
    current_user: models.User = Depends(require_permission("clients.manage")),
    db: Session = Depends(get_db),
):
    _ensure_msp_tenant(current_user, db)
    account = (
        db.query(models.CustomerAccount)
        .filter(
            models.CustomerAccount.id == account_id,
            models.CustomerAccount.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente nao encontrado")
    enforce_client_user_scope(current_user, account.id)
    db.delete(account)
    db.commit()
    return None
