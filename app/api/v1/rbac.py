import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["RBAC"])


class PermissionResponse(BaseModel):
    id: str
    code: str
    nome: str
    descricao: str | None = None


class RoleResponse(BaseModel):
    id: str
    nome: str
    descricao: str | None = None
    permissions: list[str]


class RoleCreate(BaseModel):
    nome: str = Field(..., min_length=2)
    descricao: str | None = None
    permissions: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    nome: str | None = None
    descricao: str | None = None
    permissions: list[str] | None = None


def _role_permissions(db: Session, role_id: str) -> list[str]:
    rows = (
        db.query(models.Permission.code)
        .join(models.RolePermission, models.RolePermission.permission_id == models.Permission.id)
        .filter(models.RolePermission.role_id == role_id)
        .all()
    )
    return [code for (code,) in rows]


@router.get("/permissions", response_model=list[PermissionResponse])
def list_permissions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_permission("permissions.view")),
):
    permissions = db.query(models.Permission).order_by(models.Permission.code.asc()).all()
    return [
        PermissionResponse(
            id=perm.id,
            code=perm.code,
            nome=perm.nome,
            descricao=perm.descricao,
        )
        for perm in permissions
    ]


@router.get("/roles", response_model=list[RoleResponse])
def list_roles(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_permission("roles.manage")),
):
    roles = (
        db.query(models.Role)
        .filter(models.Role.tenant_id == current_user.tenant_id)
        .order_by(models.Role.nome.asc())
        .all()
    )
    return [
        RoleResponse(
            id=role.id,
            nome=role.nome,
            descricao=role.descricao,
            permissions=_role_permissions(db, role.id),
        )
        for role in roles
    ]


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_permission("roles.manage")),
):
    exists = (
        db.query(models.Role)
        .filter(models.Role.tenant_id == current_user.tenant_id, models.Role.nome == payload.nome)
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="Role ja existe")
    role = models.Role(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        nome=payload.nome,
        descricao=payload.descricao,
        is_system_default=False,
    )
    db.add(role)
    db.flush()

    if payload.permissions:
        permissions = (
            db.query(models.Permission)
            .filter(models.Permission.code.in_(payload.permissions))
            .all()
        )
        for permission in permissions:
            db.add(models.RolePermission(role_id=role.id, permission_id=permission.id))
    db.commit()
    return RoleResponse(
        id=role.id,
        nome=role.nome,
        descricao=role.descricao,
        permissions=_role_permissions(db, role.id),
    )


@router.put("/roles/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: str,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_permission("roles.manage")),
):
    role = (
        db.query(models.Role)
        .filter(models.Role.id == role_id, models.Role.tenant_id == current_user.tenant_id)
        .first()
    )
    if not role:
        raise HTTPException(status_code=404, detail="Role nao encontrada")
    if role.is_system_default:
        raise HTTPException(status_code=403, detail="Role padrao nao pode ser editada")
    if payload.nome is not None:
        role.nome = payload.nome
    if payload.descricao is not None:
        role.descricao = payload.descricao

    if payload.permissions is not None:
        db.query(models.RolePermission).filter(models.RolePermission.role_id == role.id).delete()
        permissions = (
            db.query(models.Permission)
            .filter(models.Permission.code.in_(payload.permissions))
            .all()
        )
        for permission in permissions:
            db.add(models.RolePermission(role_id=role.id, permission_id=permission.id))
    db.commit()
    return RoleResponse(
        id=role.id,
        nome=role.nome,
        descricao=role.descricao,
        permissions=_role_permissions(db, role.id),
    )
