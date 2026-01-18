import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.authorization import (
    apply_scope_to_query,
    enforce_client_user_scope,
    is_admin_user,
    require_scope_or_admin,
)
from app.core.security import get_current_user, require_permission
from app.db import models
from app.db.session import get_db
from app.services.geocoding import GeocodingError, geocode_address, is_address_complete

router = APIRouter(tags=["Clientes"])


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


class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1)
    client_code: str | None = None
    contract: str | None = None
    status: str = "active"
    document: str | None = None
    address: str | None = None


class ClientUpdate(BaseModel):
    name: str | None = None
    client_code: str | None = None
    contract: str | None = None
    status: str | None = None
    document: str | None = None
    address: str | None = None


class ClientResponse(BaseModel):
    id: str
    nome: str
    client_code: str | None = None
    contrato: str | None = None
    status: str | None = None
    documento: str | None = None
    endereco: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geocodedAt: datetime | None = None
    geocodeStatus: str | None = None
    ativosTotal: int | None = 0
    ativosCriticos: int | None = 0
    osEmAberto: int | None = 0
    statusOperacional: str | None = None


def to_response(c: models.Client) -> ClientResponse:
    return ClientResponse(
        id=c.id,
        nome=c.name,
        client_code=c.client_code,
        contrato=c.contract,
        status=c.status,
        documento=c.document,
        endereco=c.address,
        latitude=c.latitude,
        longitude=c.longitude,
        geocodedAt=c.geocoded_at,
        geocodeStatus=c.geocode_status,
        ativosTotal=0,
        ativosCriticos=0,
        osEmAberto=0,
        statusOperacional=None,
    )


def _apply_geocode(client: models.Client, address: str | None) -> None:
    if not address:
        client.latitude = None
        client.longitude = None
        client.geocoded_at = None
        client.geocode_status = None
        return
    if not is_address_complete(address):
        client.latitude = None
        client.longitude = None
        client.geocoded_at = datetime.utcnow()
        client.geocode_status = "INCOMPLETE_ADDRESS"
        return
    result = geocode_address(address)
    client.geocode_status = result.status
    client.geocoded_at = datetime.utcnow()
    if result.status == "OK":
        client.latitude = result.lat
        client.longitude = result.lng
    else:
        client.latitude = None
        client.longitude = None


@router.get("/clientes")
def list_clients(
    current_user: models.User = Depends(require_permission("clients.view")),
    db: Session = Depends(get_db),
):
    _ensure_msp_tenant(current_user, db)
    scope = require_scope_or_admin(db, current_user)
    query = db.query(models.Client).filter(models.Client.tenant_id == current_user.tenant_id)
    query = apply_scope_to_query(query, scope, client_field=models.Client.id)
    clients = query.order_by(models.Client.created_at.desc()).all()
    return {"clientes": [to_response(c) for c in clients]}


@router.post("/clientes", status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    current_user: models.User = Depends(require_permission("clients.manage")),
    db: Session = Depends(get_db),
):
    _ensure_msp_tenant(current_user, db)
    new_client = models.Client(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        name=payload.name,
        client_code=payload.client_code,
        contract=payload.contract,
        status=payload.status or "active",
        document=payload.document,
        address=payload.address,
    )
    try:
        _apply_geocode(new_client, payload.address)
    except GeocodingError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ocorreu um erro, tente novamente mais tarde.",
        )
    db.add(new_client)
    db.commit()
    db.refresh(new_client)
    return to_response(new_client)


@router.get("/clientes/{client_id}")
def get_client(
    client_id: str,
    current_user: models.User = Depends(require_permission("clients.view")),
    db: Session = Depends(get_db),
):
    _ensure_msp_tenant(current_user, db)
    scope = require_scope_or_admin(db, current_user)
    query = db.query(models.Client).filter(
        models.Client.id == client_id, models.Client.tenant_id == current_user.tenant_id
    )
    query = apply_scope_to_query(query, scope, client_field=models.Client.id)
    client = query.first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")
    enforce_client_user_scope(current_user, client.id)

    detail = {
        "cliente": to_response(client),
        "visaoGeral": {
            "ativos_total": 0,
            "ativos_criticos": 0,
            "os_aberto": 0,
            "os_atrasadas": 0,
            "ultima_manutencao": None,
            "proxima_preventiva": None,
        },
        "ativos": [],
        "manutencoes": [],
        "relatorios": [],
    }
    return detail


@router.delete("/clientes/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: str,
    current_user: models.User = Depends(require_permission("clients.manage")),
    db: Session = Depends(get_db),
):
    _ensure_msp_tenant(current_user, db)
    client = (
        db.query(models.Client)
        .filter(models.Client.id == client_id, models.Client.tenant_id == current_user.tenant_id)
        .first()
    )
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")
    enforce_client_user_scope(current_user, client.id)
    db.delete(client)
    db.commit()
    return None


@router.patch("/clientes/{client_id}")
def update_client(
    client_id: str,
    payload: ClientUpdate,
    current_user: models.User = Depends(require_permission("clients.manage")),
    db: Session = Depends(get_db),
):
    _ensure_msp_tenant(current_user, db)
    client = (
        db.query(models.Client)
        .filter(models.Client.id == client_id, models.Client.tenant_id == current_user.tenant_id)
        .first()
    )
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente nǜo encontrado")
    enforce_client_user_scope(current_user, client.id)

    def clean_text(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    if payload.name is not None:
        client.name = clean_text(payload.name) or client.name
    if payload.client_code is not None:
        client.client_code = clean_text(payload.client_code)
    if payload.contract is not None:
        client.contract = clean_text(payload.contract)
    if payload.status is not None:
        client.status = clean_text(payload.status) or client.status
    if payload.document is not None:
        client.document = clean_text(payload.document)
    address_changed = False
    if payload.address is not None:
        next_address = clean_text(payload.address)
        address_changed = next_address != client.address
        client.address = next_address

    try:
        if address_changed or client.latitude is None or client.longitude is None:
            _apply_geocode(client, client.address)
    except GeocodingError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ocorreu um erro, tente novamente mais tarde.",
        )

    db.commit()
    db.refresh(client)
    return to_response(client)


@router.post("/clientes/{client_id}/geocode")
def reprocess_geocode(
    client_id: str,
    current_user: models.User = Depends(require_permission("clients.manage")),
    db: Session = Depends(get_db),
):
    _ensure_msp_tenant(current_user, db)
    if not is_admin_user(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    client = (
        db.query(models.Client)
        .filter(models.Client.id == client_id, models.Client.tenant_id == current_user.tenant_id)
        .first()
    )
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente nǜo encontrado")
    try:
        _apply_geocode(client, client.address)
    except GeocodingError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ocorreu um erro, tente novamente mais tarde.",
        )
    db.commit()
    db.refresh(client)
    return to_response(client)


@router.post("/clientes/geocode/reprocess")
def reprocess_geocode_batch(
    limit: int = 50,
    current_user: models.User = Depends(require_permission("clients.manage")),
    db: Session = Depends(get_db),
):
    _ensure_msp_tenant(current_user, db)
    if not is_admin_user(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    limit = max(1, min(limit, 200))
    query = db.query(models.Client).filter(models.Client.tenant_id == current_user.tenant_id)
    query = query.filter((models.Client.latitude.is_(None)) | (models.Client.longitude.is_(None)))
    clients = query.order_by(models.Client.created_at.desc()).limit(limit).all()
    processed = 0
    for client in clients:
        try:
            _apply_geocode(client, client.address)
            processed += 1
        except GeocodingError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Ocorreu um erro, tente novamente mais tarde.",
            )
    db.commit()
    return {"processed": processed}
