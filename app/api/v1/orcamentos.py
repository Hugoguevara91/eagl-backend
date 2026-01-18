import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["Orcamentos"])


class OrcamentoItemPayload(BaseModel):
    descricao: str
    quantidade: int
    valor_unitario: int


class OrcamentoPayload(BaseModel):
    cliente: str | None = None
    contrato: str | None = None
    unidade: str | None = None
    os_id: str | None = None
    itens: list[OrcamentoItemPayload] = []


class StatusPayload(BaseModel):
    status: str


@router.get("/orcamentos")
def list_orcamentos(
    current_user: models.User = Depends(require_permission("budgets.view")),
    db: Session = Depends(get_db),
):
    items = (
        db.query(models.Orcamento)
        .filter(models.Orcamento.tenant_id == current_user.tenant_id)
        .order_by(models.Orcamento.created_at.desc())
        .all()
    )
    return {"items": items}


@router.post("/orcamentos", status_code=status.HTTP_201_CREATED)
def create_orcamento(
    payload: OrcamentoPayload,
    current_user: models.User = Depends(require_permission("budgets.manage")),
    db: Session = Depends(get_db),
):
    total = sum(item.quantidade * item.valor_unitario for item in payload.itens)
    orcamento = models.Orcamento(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        cliente=payload.cliente,
        contrato=payload.contrato,
        unidade=payload.unidade,
        os_id=payload.os_id,
        status="PENDENTE",
        total=total,
    )
    db.add(orcamento)
    db.flush()

    for item in payload.itens:
        db.add(
            models.OrcamentoItem(
                id=str(uuid.uuid4()),
                orcamento_id=orcamento.id,
                descricao=item.descricao,
                quantidade=item.quantidade,
                valor_unitario=item.valor_unitario,
            )
        )
    db.commit()
    db.refresh(orcamento)
    return orcamento


@router.get("/orcamentos/{orcamento_id}")
def get_orcamento(
    orcamento_id: str,
    current_user: models.User = Depends(require_permission("budgets.view")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.Orcamento)
        .filter(models.Orcamento.id == orcamento_id, models.Orcamento.tenant_id == current_user.tenant_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Orcamento nao encontrado")
    return item


@router.put("/orcamentos/{orcamento_id}")
def update_orcamento(
    orcamento_id: str,
    payload: OrcamentoPayload,
    current_user: models.User = Depends(require_permission("budgets.manage")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.Orcamento)
        .filter(models.Orcamento.id == orcamento_id, models.Orcamento.tenant_id == current_user.tenant_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Orcamento nao encontrado")
    item.cliente = payload.cliente
    item.contrato = payload.contrato
    item.unidade = payload.unidade
    item.os_id = payload.os_id
    item.total = sum(it.quantidade * it.valor_unitario for it in payload.itens)
    db.query(models.OrcamentoItem).filter(models.OrcamentoItem.orcamento_id == item.id).delete()
    for it in payload.itens:
        db.add(
            models.OrcamentoItem(
                id=str(uuid.uuid4()),
                orcamento_id=item.id,
                descricao=it.descricao,
                quantidade=it.quantidade,
                valor_unitario=it.valor_unitario,
            )
        )
    db.commit()
    db.refresh(item)
    return item


@router.patch("/orcamentos/{orcamento_id}/status")
def update_orcamento_status(
    orcamento_id: str,
    payload: StatusPayload,
    current_user: models.User = Depends(require_permission("budgets.manage")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.Orcamento)
        .filter(models.Orcamento.id == orcamento_id, models.Orcamento.tenant_id == current_user.tenant_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Orcamento nao encontrado")
    item.status = payload.status
    db.commit()
    db.refresh(item)
    return item
