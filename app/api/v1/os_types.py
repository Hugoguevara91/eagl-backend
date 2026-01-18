import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.authorization import apply_scope_to_query, require_scope_or_admin
from app.core.security import require_permission
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["OS Types"])


class OSTypeCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None
    client_id: str | None = None
    is_active: bool = True


class OSTypeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    client_id: str | None = None
    is_active: bool | None = None


class OSTypeResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    client_id: str | None = None
    is_active: bool
    created_at: str
    updated_at: str


def _to_response(item: models.OSType) -> OSTypeResponse:
    return OSTypeResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        client_id=item.client_id,
        is_active=item.is_active,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


@router.get("/os-types")
def list_os_types(
    client_id: str | None = Query(default=None),
    current_user: models.User = Depends(require_permission("os.view")),
    db: Session = Depends(get_db),
):
    scope = require_scope_or_admin(db, current_user)
    query = db.query(models.OSType).filter(models.OSType.tenant_id == current_user.tenant_id)
    query = apply_scope_to_query(query, scope, client_field=models.OSType.client_id)
    if client_id:
        query = query.filter(models.OSType.client_id == client_id)
    items = query.order_by(models.OSType.created_at.desc()).all()
    return {"items": [_to_response(item) for item in items]}


@router.post("/os-types", status_code=status.HTTP_201_CREATED)
def create_os_type(
    payload: OSTypeCreate,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    scope = require_scope_or_admin(db, current_user)
    if scope["clients"] and payload.client_id and payload.client_id not in scope["clients"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cliente fora do escopo")
    item = models.OSType(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        client_id=payload.client_id,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"item": _to_response(item)}


@router.patch("/os-types/{os_type_id}")
def update_os_type(
    os_type_id: str,
    payload: OSTypeUpdate,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.OSType)
        .filter(models.OSType.id == os_type_id, models.OSType.tenant_id == current_user.tenant_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tipo de OS nao encontrado")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return {"item": _to_response(item)}


@router.delete("/os-types/{os_type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_os_type(
    os_type_id: str,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.OSType)
        .filter(models.OSType.id == os_type_id, models.OSType.tenant_id == current_user.tenant_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tipo de OS nao encontrado")
    db.delete(item)
    db.commit()
    return None
