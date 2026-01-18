from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.db import models

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard/summary")
def dashboard_summary(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant_id = current_user.tenant_id
    os_total = db.query(models.WorkOrder).filter(models.WorkOrder.tenant_id == tenant_id).count()
    os_atrasadas = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.tenant_id == tenant_id, models.WorkOrder.sla_breached.is_(True))
        .count()
    )
    clientes_total = db.query(models.Client).filter(models.Client.tenant_id == tenant_id).count()
    unidades_total = db.query(models.Site).filter(models.Site.tenant_id == tenant_id).count()
    colaboradores_total = db.query(models.Colaborador).filter(models.Colaborador.tenant_id == tenant_id).count()
    orcamentos_pendentes = (
        db.query(models.Orcamento)
        .filter(models.Orcamento.tenant_id == tenant_id, models.Orcamento.status == "PENDENTE")
        .count()
    )
    requisicoes_abertas = (
        db.query(models.SuprimentoRequisicao)
        .filter(models.SuprimentoRequisicao.tenant_id == tenant_id, models.SuprimentoRequisicao.status == "ABERTA")
        .count()
    )
    ssma_ocorrencias_mes = (
        db.query(models.SSMAOcorrencia)
        .filter(models.SSMAOcorrencia.tenant_id == tenant_id)
        .count()
    )
    return {
        "os_total": os_total,
        "os_atrasadas": os_atrasadas,
        "clientes_total": clientes_total,
        "unidades_total": unidades_total,
        "colaboradores_total": colaboradores_total,
        "orcamentos_pendentes": orcamentos_pendentes,
        "requisicoes_abertas": requisicoes_abertas,
        "ssma_ocorrencias_mes": ssma_ocorrencias_mes,
    }


@router.get("/dashboard/risk")
def dashboard_risk(current_user: models.User = Depends(get_current_user)):
    return {
        "ativos_criticos": [],
        "clientes_risco": [],
        "preventivas_vencidas": [],
    }


@router.get("/dashboard/execution")
def dashboard_execution(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant_id = current_user.tenant_id
    os_hoje = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.tenant_id == tenant_id)
        .count()
    )
    os_em_andamento = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.tenant_id == tenant_id, models.WorkOrder.status == "em_andamento")
        .count()
    )
    os_aguardando = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.tenant_id == tenant_id, models.WorkOrder.status == "aguardando")
        .count()
    )
    return {
        "os_hoje": os_hoje,
        "os_em_andamento": os_em_andamento,
        "os_aguardando": os_aguardando,
    }


@router.get("/dashboard/trends")
def dashboard_trends(current_user: models.User = Depends(get_current_user)):
    return {
        "points": [],
    }
