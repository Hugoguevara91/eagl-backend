import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.security import get_password_hash, require_permission
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["Usuarios"])


class ScopePayload(BaseModel):
    scope_type: str
    scope_id: str


class PermissionOverridePayload(BaseModel):
    code: str
    mode: str = "grant"


class UserCreate(BaseModel):
    nome: str = Field(..., min_length=2)
    email: str
    login: str | None = None
    senha: str
    status: str = "active"
    roles: list[str] = Field(default_factory=list)
    permissions: list[PermissionOverridePayload] = Field(default_factory=list)
    scopes: list[ScopePayload] = Field(default_factory=list)


class UserUpdate(BaseModel):
    nome: str | None = None
    email: str | None = None
    login: str | None = None
    senha: str | None = None
    status: str | None = None
    roles: list[str] | None = None
    permissions: list[PermissionOverridePayload] | None = None
    scopes: list[ScopePayload] | None = None


def _serialize_user(db: Session, user: models.User) -> dict:
    roles = (
        db.query(models.Role)
        .join(models.UserRole, models.UserRole.role_id == models.Role.id)
        .filter(models.UserRole.user_id == user.id)
        .all()
    )
    permissions = (
        db.query(models.UserPermission, models.Permission.code)
        .join(models.Permission, models.Permission.id == models.UserPermission.permission_id)
        .filter(models.UserPermission.user_id == user.id)
        .all()
    )
    scopes = (
        db.query(models.UserScope)
        .filter(models.UserScope.user_id == user.id)
        .all()
    )
    return {
        "id": user.id,
        "nome": user.name,
        "email": user.email,
        "login": user.login,
        "status": user.status,
        "roles": [role.nome for role in roles],
        "permissions": [{"code": code, "mode": perm.mode} for perm, code in permissions],
        "scopes": [
            {"scope_type": scope.scope_type, "scope_id": scope.scope_id}
            for scope in scopes
        ],
        "created_at": user.created_at,
    }


def _audit(
    db: Session,
    request: Request,
    user_id: str | None,
    tenant_id: str,
    action: str,
    payload: dict,
) -> None:
    log = models.AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type="USER",
        resource_id=payload.get("user_id"),
        payload_resumo=payload,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(log)


@router.get("/users")
def list_users(
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_permission("users.manage")),
):
    query = db.query(models.User).filter(models.User.tenant_id == current_user.tenant_id)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            or_(
                models.User.name.ilike(like),
                models.User.login.ilike(like),
                models.User.email.ilike(like),
            )
        )
    total = query.count()
    items = (
        query.order_by(models.User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_serialize_user(db, user) for user in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_permission("users.manage")),
):
    login = payload.login or payload.email
    primary_role = payload.roles[0] if payload.roles else "TENANT_ADMIN"
    existing = (
        db.query(models.User)
        .filter(
            models.User.tenant_id == current_user.tenant_id,
            or_(models.User.login == login, models.User.email == payload.email),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Login ou email ja existe")
    user = models.User(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        name=payload.nome,
        login=login,
        email=payload.email,
        password_hash=get_password_hash(payload.senha),
        role="TENANT_ADMIN" if "TENANT_ADMIN" in payload.roles else primary_role,
        status=payload.status or "active",
    )
    db.add(user)
    db.flush()

    if payload.roles:
        roles = (
            db.query(models.Role)
            .filter(models.Role.tenant_id == current_user.tenant_id, models.Role.nome.in_(payload.roles))
            .all()
        )
        for role in roles:
            db.add(models.UserRole(user_id=user.id, role_id=role.id))

    for override in payload.permissions:
        permission = db.query(models.Permission).filter(models.Permission.code == override.code).first()
        if permission:
            db.add(
                models.UserPermission(
                    user_id=user.id,
                    permission_id=permission.id,
                    mode=override.mode,
                )
            )

    for scope in payload.scopes:
        db.add(
            models.UserScope(
                user_id=user.id,
                scope_type=scope.scope_type,
                scope_id=scope.scope_id,
            )
        )

    _audit(
        db,
        request,
        current_user.id,
        current_user.tenant_id,
        "USER_CREATE",
        {"user_id": user.id, "roles": payload.roles},
    )
    db.commit()
    db.refresh(user)
    return _serialize_user(db, user)


@router.put("/users/{user_id}")
def update_user(
    user_id: str,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_permission("users.manage")),
):
    user = (
        db.query(models.User)
        .filter(models.User.id == user_id, models.User.tenant_id == current_user.tenant_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    if payload.nome is not None:
        user.name = payload.nome
    if payload.email is not None:
        user.email = payload.email
    if payload.login is not None:
        user.login = payload.login
    if payload.senha:
        user.password_hash = get_password_hash(payload.senha)
    if payload.status is not None:
        user.status = payload.status

    if payload.roles is not None:
        db.query(models.UserRole).filter(models.UserRole.user_id == user.id).delete()
        if payload.roles:
            roles = (
                db.query(models.Role)
                .filter(models.Role.tenant_id == current_user.tenant_id, models.Role.nome.in_(payload.roles))
                .all()
            )
            for role in roles:
                db.add(models.UserRole(user_id=user.id, role_id=role.id))
            user.role = payload.roles[0]
        else:
            user.role = "TENANT_ADMIN"

    if payload.permissions is not None:
        db.query(models.UserPermission).filter(models.UserPermission.user_id == user.id).delete()
        for override in payload.permissions:
            permission = db.query(models.Permission).filter(models.Permission.code == override.code).first()
            if permission:
                db.add(
                    models.UserPermission(
                        user_id=user.id,
                        permission_id=permission.id,
                        mode=override.mode,
                    )
                )

    if payload.scopes is not None:
        db.query(models.UserScope).filter(models.UserScope.user_id == user.id).delete()
        for scope in payload.scopes:
            db.add(
                models.UserScope(
                    user_id=user.id,
                    scope_type=scope.scope_type,
                    scope_id=scope.scope_id,
                )
            )

    _audit(
        db,
        request,
        current_user.id,
        current_user.tenant_id,
        "USER_UPDATE",
        {"user_id": user.id},
    )
    db.commit()
    db.refresh(user)
    return _serialize_user(db, user)
