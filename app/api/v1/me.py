from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import build_user_context, get_current_user, get_current_user_from_token
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["Usuario"])


@router.get("/me")
def get_me(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant = current_user.tenant
    if not tenant:
        tenant = db.query(models.Tenant).filter(models.Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant do usuario nao encontrado")

    allowed_contract_ids: list[str] | None = []
    if current_user.role == "TENANT_ADMIN":
        allowed_contract_ids = None
    else:
        if current_user.role in {"GERENTE", "COORDENADOR", "SUPERVISOR", "TECNICO"}:
            accesses = (
                db.query(models.UserContractAccess)
                .filter(
                    models.UserContractAccess.user_id == current_user.id,
                    models.UserContractAccess.tenant_id == current_user.tenant_id,
                )
                .all()
            )
            allowed_contract_ids = [access.contract_id for access in accesses]
        else:
            allowed_contract_ids = []

    scope = {
        "allowed_contract_ids": allowed_contract_ids if allowed_contract_ids is not None else None,
        "client_id": current_user.client_id,
    }
    context = build_user_context(db, current_user)

    return {
        "user": {
            "id": current_user.id,
            "name": current_user.name,
            "login": current_user.login,
            "role": current_user.role,
            "status": current_user.status,
            "roles": context["roles"],
            "permissions": context["permissions"],
        },
        "tenant": {
            "id": tenant.id,
            "name": tenant.name,
            "tenant_type": tenant.tenant_type,
        },
        "scope": {**scope, **context["scope"]},
    }


if settings.ENV == "development":

    @router.get(
        "/me/test",
        summary="Rota de teste simples via query param (apenas DEV)",
    )
    def get_me_test(
        token: str = Query(..., description="Token JWT gerado no /api/auth/login ou /api/auth/token"),
        db: Session = Depends(get_db),
    ):
        """
        Facilitador de testes (não usar em produção):
        - Navegador: http://127.0.0.1:8000/api/me/test?token=SEU_TOKEN
        - Script: requests.get('.../api/me/test', params={'token': token})
        - Swagger: usar o campo token acima sem o botão Authorize
        """
        current_user = get_current_user_from_token(token=token, db=db)
        return get_me(current_user=current_user, db=db)
