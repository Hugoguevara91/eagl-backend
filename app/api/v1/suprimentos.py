import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["Suprimentos"])


class RequisicaoItemPayload(BaseModel):
    material: str
    quantidade: int
    prioridade: str
    observacao: str | None = None


class RequisicaoPayload(BaseModel):
    os_id: str | None = None
    cliente: str | None = None
    contrato: str | None = None
    unidade: str | None = None
    solicitante: str | None = None
    itens: list[RequisicaoItemPayload] = []


class StatusPayload(BaseModel):
    status: str


@router.get("/suprimentos/requisicoes")
def list_requisicoes(
    current_user: models.User = Depends(require_permission("supplies.view")),
    db: Session = Depends(get_db),
):
    items = (
        db.query(models.SuprimentoRequisicao)
        .filter(models.SuprimentoRequisicao.tenant_id == current_user.tenant_id)
        .order_by(models.SuprimentoRequisicao.created_at.desc())
        .all()
    )
    return {"items": items}


@router.post("/suprimentos/requisicoes", status_code=status.HTTP_201_CREATED)
def create_requisicao(
    payload: RequisicaoPayload,
    current_user: models.User = Depends(require_permission("supplies.manage")),
    db: Session = Depends(get_db),
):
    req = models.SuprimentoRequisicao(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        os_id=payload.os_id,
        cliente=payload.cliente,
        contrato=payload.contrato,
        unidade=payload.unidade,
        solicitante=payload.solicitante,
        status="ABERTA",
    )
    db.add(req)
    db.flush()
    for item in payload.itens:
        db.add(
            models.SuprimentoItem(
                id=str(uuid.uuid4()),
                requisicao_id=req.id,
                material=item.material,
                quantidade=item.quantidade,
                prioridade=item.prioridade,
                observacao=item.observacao,
            )
        )
    db.commit()
    db.refresh(req)
    return req


@router.get("/suprimentos/requisicoes/{req_id}")
def get_requisicao(
    req_id: str,
    current_user: models.User = Depends(require_permission("supplies.view")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.SuprimentoRequisicao)
        .filter(models.SuprimentoRequisicao.id == req_id, models.SuprimentoRequisicao.tenant_id == current_user.tenant_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Requisicao nao encontrada")
    return item


@router.put("/suprimentos/requisicoes/{req_id}")
def update_requisicao(
    req_id: str,
    payload: RequisicaoPayload,
    current_user: models.User = Depends(require_permission("supplies.manage")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.SuprimentoRequisicao)
        .filter(models.SuprimentoRequisicao.id == req_id, models.SuprimentoRequisicao.tenant_id == current_user.tenant_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Requisicao nao encontrada")
    item.os_id = payload.os_id
    item.cliente = payload.cliente
    item.contrato = payload.contrato
    item.unidade = payload.unidade
    item.solicitante = payload.solicitante
    db.query(models.SuprimentoItem).filter(models.SuprimentoItem.requisicao_id == item.id).delete()
    for it in payload.itens:
        db.add(
            models.SuprimentoItem(
                id=str(uuid.uuid4()),
                requisicao_id=item.id,
                material=it.material,
                quantidade=it.quantidade,
                prioridade=it.prioridade,
                observacao=it.observacao,
            )
        )
    db.commit()
    db.refresh(item)
    return item


@router.patch("/suprimentos/requisicoes/{req_id}/status")
def update_requisicao_status(
    req_id: str,
    payload: StatusPayload,
    current_user: models.User = Depends(require_permission("supplies.manage")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.SuprimentoRequisicao)
        .filter(models.SuprimentoRequisicao.id == req_id, models.SuprimentoRequisicao.tenant_id == current_user.tenant_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Requisicao nao encontrada")
    item.status = payload.status
    db.commit()
    db.refresh(item)
    return item
