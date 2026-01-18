import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.authorization import apply_scope_to_query, enforce_client_user_scope, require_scope_or_admin
from app.core.security import require_permission
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["Assets"])


class AssetCreate(BaseModel):
    name: str = Field(..., min_length=1)
    tag: str = Field(..., min_length=1)
    status: str | None = None
    asset_type: str | None = None
    site_id: str | None = None


class AssetUpdate(BaseModel):
    name: str | None = None
    tag: str | None = None
    status: str | None = None
    asset_type: str | None = None
    site_id: str | None = None


class AssetResponse(BaseModel):
    id: str
    client_id: str | None = None
    site_id: str | None = None
    name: str
    tag: str
    status: str | None = None
    asset_type: str | None = None
    created_at: str
    updated_at: str


def _to_response(asset: models.Asset) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        client_id=asset.client_id,
        site_id=asset.site_id,
        name=asset.name,
        tag=asset.tag,
        status=asset.status,
        asset_type=asset.asset_type,
        created_at=asset.created_at.isoformat(),
        updated_at=asset.updated_at.isoformat(),
    )


def _get_client_or_404(client_id: str, current_user: models.User, db: Session) -> models.Client:
    scope = require_scope_or_admin(db, current_user)
    query = db.query(models.Client).filter(
        models.Client.id == client_id, models.Client.tenant_id == current_user.tenant_id
    )
    query = apply_scope_to_query(query, scope, client_field=models.Client.id)
    client = query.first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente nao encontrado")
    enforce_client_user_scope(current_user, client.id)
    return client


@router.get("/clients/{client_id}/assets")
def list_assets(
    client_id: str,
    current_user: models.User = Depends(require_permission("assets.view")),
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, current_user, db)
    assets = (
        db.query(models.Asset)
        .filter(
            models.Asset.tenant_id == current_user.tenant_id,
            models.Asset.client_id == client_id,
        )
        .order_by(models.Asset.created_at.desc())
        .all()
    )
    return {"assets": [_to_response(asset) for asset in assets]}


@router.post("/clients/{client_id}/assets", status_code=status.HTTP_201_CREATED)
def create_asset(
    client_id: str,
    payload: AssetCreate,
    current_user: models.User = Depends(require_permission("assets.manage")),
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, current_user, db)
    asset = models.Asset(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        client_id=client_id,
        site_id=payload.site_id,
        tag=payload.tag,
        name=payload.name,
        asset_type=payload.asset_type,
        status=payload.status or "operational",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return {"asset": _to_response(asset)}


@router.get("/clients/{client_id}/assets/{asset_id}")
def get_asset(
    client_id: str,
    asset_id: str,
    current_user: models.User = Depends(require_permission("assets.view")),
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, current_user, db)
    asset = (
        db.query(models.Asset)
        .filter(
            models.Asset.id == asset_id,
            models.Asset.client_id == client_id,
            models.Asset.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ativo nao encontrado")
    return {"asset": _to_response(asset)}


@router.patch("/clients/{client_id}/assets/{asset_id}")
def update_asset(
    client_id: str,
    asset_id: str,
    payload: AssetUpdate,
    current_user: models.User = Depends(require_permission("assets.manage")),
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, current_user, db)
    asset = (
        db.query(models.Asset)
        .filter(
            models.Asset.id == asset_id,
            models.Asset.client_id == client_id,
            models.Asset.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ativo nao encontrado")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(asset, field, value)
    db.commit()
    db.refresh(asset)
    return {"asset": _to_response(asset)}


@router.delete("/clients/{client_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    client_id: str,
    asset_id: str,
    current_user: models.User = Depends(require_permission("assets.manage")),
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, current_user, db)
    asset = (
        db.query(models.Asset)
        .filter(
            models.Asset.id == asset_id,
            models.Asset.client_id == client_id,
            models.Asset.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ativo nao encontrado")
    db.delete(asset)
    db.commit()
    return None
