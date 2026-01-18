import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["Colaboradores"])


class ColaboradorPayload(BaseModel):
    nome: str
    funcao: str
    status: str = "ATIVO"
    coordenador_nome: str | None = None
    supervisor_nome: str | None = None
    contrato: str | None = None
    unidade: str | None = None
    especialidades: list[str] | None = None
    observacoes: str | None = None
    telefone: str | None = None
    email: str | None = None


class StatusPayload(BaseModel):
    status: str


@router.get("/colaboradores")
def list_colaboradores(
    current_user: models.User = Depends(require_permission("collaborators.view")),
    db: Session = Depends(get_db),
):
    items = (
        db.query(models.Colaborador)
        .filter(models.Colaborador.tenant_id == current_user.tenant_id)
        .order_by(models.Colaborador.nome.asc())
        .all()
    )
    return {"items": items}


@router.post("/colaboradores", status_code=status.HTTP_201_CREATED)
def create_colaborador(
    payload: ColaboradorPayload,
    current_user: models.User = Depends(require_permission("collaborators.manage")),
    db: Session = Depends(get_db),
):
    item = models.Colaborador(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        nome=payload.nome,
        funcao=payload.funcao,
        status=payload.status or "ATIVO",
        coordenador_nome=payload.coordenador_nome,
        supervisor_nome=payload.supervisor_nome,
        contrato=payload.contrato,
        unidade=payload.unidade,
        especialidades=payload.especialidades or [],
        observacoes=payload.observacoes,
        telefone=payload.telefone,
        email=payload.email,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/colaboradores/{colaborador_id}")
def get_colaborador(
    colaborador_id: str,
    current_user: models.User = Depends(require_permission("collaborators.view")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.Colaborador)
        .filter(
            models.Colaborador.id == colaborador_id,
            models.Colaborador.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Colaborador nao encontrado")
    return item


@router.put("/colaboradores/{colaborador_id}")
def update_colaborador(
    colaborador_id: str,
    payload: ColaboradorPayload,
    current_user: models.User = Depends(require_permission("collaborators.manage")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.Colaborador)
        .filter(
            models.Colaborador.id == colaborador_id,
            models.Colaborador.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Colaborador nao encontrado")
    item.nome = payload.nome
    item.funcao = payload.funcao
    item.status = payload.status or item.status
    item.coordenador_nome = payload.coordenador_nome
    item.supervisor_nome = payload.supervisor_nome
    item.contrato = payload.contrato
    item.unidade = payload.unidade
    item.especialidades = payload.especialidades or []
    item.observacoes = payload.observacoes
    item.telefone = payload.telefone
    item.email = payload.email
    db.commit()
    db.refresh(item)
    return item


@router.patch("/colaboradores/{colaborador_id}/status")
def update_colaborador_status(
    colaborador_id: str,
    payload: StatusPayload,
    current_user: models.User = Depends(require_permission("collaborators.manage")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.Colaborador)
        .filter(
            models.Colaborador.id == colaborador_id,
            models.Colaborador.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Colaborador nao encontrado")
    item.status = payload.status
    db.commit()
    db.refresh(item)
    return item
