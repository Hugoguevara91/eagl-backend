from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.authorization import apply_scope_to_query, require_scope_or_admin
from app.core.security import require_permission
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["Mapa"])


class MapContractItem(BaseModel):
    id: str
    nome: str
    contrato: str | None = None
    status: str | None = None
    endereco: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    clienteId: str | None = None


@router.get("/map/contracts", response_model=list[MapContractItem])
def list_map_contracts(
    q: str | None = None,
    status: str | None = None,
    current_user: models.User = Depends(require_permission("clients.view")),
    db: Session = Depends(get_db),
):
    scope = require_scope_or_admin(db, current_user)
    query = db.query(models.Client).filter(models.Client.tenant_id == current_user.tenant_id)
    query = apply_scope_to_query(query, scope, client_field=models.Client.id)

    if status and status != "all":
        query = query.filter(models.Client.status == status)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            models.Client.name.ilike(like)
            | models.Client.contract.ilike(like)
            | models.Client.address.ilike(like)
        )

    clients = query.order_by(models.Client.created_at.desc()).all()
    return [
        MapContractItem(
            id=client.id,
            nome=client.name,
            contrato=client.contract,
            status=client.status,
            endereco=client.address,
            latitude=client.latitude,
            longitude=client.longitude,
            clienteId=client.id,
        )
        for client in clients
    ]
