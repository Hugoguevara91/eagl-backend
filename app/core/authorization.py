from fastapi import HTTPException, status
from sqlalchemy.orm import Query, Session

from app.core.security import get_user_permissions, get_user_scope
from app.db import models


def is_admin_user(db: Session, user: models.User) -> bool:
    if user.role == "TENANT_ADMIN":
        return True
    permissions = get_user_permissions(db, user)
    return "users.manage" in permissions or "roles.manage" in permissions


def require_scope_or_admin(db: Session, user: models.User) -> dict[str, list[str]]:
    scope = get_user_scope(db, user)
    if is_admin_user(db, user):
        return scope
    if not scope["clients"] and not scope["sites"] and not scope["contracts"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu perfil nao possui escopo de dados configurado.",
        )
    return scope


def apply_scope_to_query(
    query: Query,
    scope: dict[str, list[str]],
    client_field=None,
    site_field=None,
    contract_field=None,
):
    if scope["clients"] and client_field is not None:
        query = query.filter(client_field.in_(scope["clients"]))
    if scope["sites"] and site_field is not None:
        query = query.filter(site_field.in_(scope["sites"]))
    if scope["contracts"] and contract_field is not None:
        query = query.filter(contract_field.in_(scope["contracts"]))
    return query


def enforce_client_user_scope(user: models.User, resource_client_id: str | None) -> None:
    if user.role == "CLIENTE":
        if not user.client_id or user.client_id != resource_client_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cliente nao autorizado para este recurso.",
            )
