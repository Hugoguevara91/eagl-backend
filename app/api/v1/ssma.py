import uuid
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["SSMA"])


class OcorrenciaPayload(BaseModel):
    tipo: str
    gravidade: str
    contrato: str | None = None
    unidade: str | None = None
    descricao: str | None = None


class InspecaoPayload(BaseModel):
    contrato: str | None = None
    unidade: str | None = None
    resultado: str


class AcaoPayload(BaseModel):
    responsavel: str | None = None
    prazo: date | None = None
    descricao: str | None = None


@router.get("/ssma/ocorrencias")
def list_ocorrencias(
    current_user: models.User = Depends(require_permission("ssma.view")),
    db: Session = Depends(get_db),
):
    items = (
        db.query(models.SSMAOcorrencia)
        .filter(models.SSMAOcorrencia.tenant_id == current_user.tenant_id)
        .order_by(models.SSMAOcorrencia.created_at.desc())
        .all()
    )
    return {"items": items}


@router.post("/ssma/ocorrencias", status_code=status.HTTP_201_CREATED)
def create_ocorrencia(
    payload: OcorrenciaPayload,
    current_user: models.User = Depends(require_permission("ssma.manage")),
    db: Session = Depends(get_db),
):
    item = models.SSMAOcorrencia(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        tipo=payload.tipo,
        gravidade=payload.gravidade,
        contrato=payload.contrato,
        unidade=payload.unidade,
        descricao=payload.descricao,
        status="ABERTA",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/ssma/ocorrencias/{item_id}")
def get_ocorrencia(
    item_id: str,
    current_user: models.User = Depends(require_permission("ssma.view")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.SSMAOcorrencia)
        .filter(models.SSMAOcorrencia.id == item_id, models.SSMAOcorrencia.tenant_id == current_user.tenant_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Ocorrencia nao encontrada")
    return item


@router.put("/ssma/ocorrencias/{item_id}")
def update_ocorrencia(
    item_id: str,
    payload: OcorrenciaPayload,
    current_user: models.User = Depends(require_permission("ssma.manage")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.SSMAOcorrencia)
        .filter(models.SSMAOcorrencia.id == item_id, models.SSMAOcorrencia.tenant_id == current_user.tenant_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Ocorrencia nao encontrada")
    item.tipo = payload.tipo
    item.gravidade = payload.gravidade
    item.contrato = payload.contrato
    item.unidade = payload.unidade
    item.descricao = payload.descricao
    db.commit()
    db.refresh(item)
    return item


@router.get("/ssma/inspecoes")
def list_inspecoes(
    current_user: models.User = Depends(require_permission("ssma.view")),
    db: Session = Depends(get_db),
):
    items = (
        db.query(models.SSMAInspecao)
        .filter(models.SSMAInspecao.tenant_id == current_user.tenant_id)
        .order_by(models.SSMAInspecao.created_at.desc())
        .all()
    )
    return {"items": items}


@router.post("/ssma/inspecoes", status_code=status.HTTP_201_CREATED)
def create_inspecao(
    payload: InspecaoPayload,
    current_user: models.User = Depends(require_permission("ssma.manage")),
    db: Session = Depends(get_db),
):
    item = models.SSMAInspecao(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        contrato=payload.contrato,
        unidade=payload.unidade,
        resultado=payload.resultado,
        status="PENDENTE",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/ssma/acoes")
def list_acoes(
    current_user: models.User = Depends(require_permission("ssma.view")),
    db: Session = Depends(get_db),
):
    items = (
        db.query(models.SSMAAcao)
        .filter(models.SSMAAcao.tenant_id == current_user.tenant_id)
        .order_by(models.SSMAAcao.created_at.desc())
        .all()
    )
    return {"items": items}


@router.post("/ssma/acoes", status_code=status.HTTP_201_CREATED)
def create_acao(
    payload: AcaoPayload,
    current_user: models.User = Depends(require_permission("ssma.manage")),
    db: Session = Depends(get_db),
):
    item = models.SSMAAcao(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        responsavel=payload.responsavel,
        prazo=payload.prazo,
        descricao=payload.descricao,
        status="PENDENTE",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
