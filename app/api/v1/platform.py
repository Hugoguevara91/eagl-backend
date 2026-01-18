import uuid
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.security import (
    PLATFORM_ROLES,
    create_access_token,
    get_current_platform_user,
    get_password_hash,
    require_platform_roles,
    verify_password_with_upgrade,
)
from app.db import models
from app.db.session import get_db
from app.services.entitlements import EntitlementsService

router = APIRouter(prefix="/platform", tags=["Platform"])

ENTITLEMENT_CATALOG = {
    "module_ai": "Acesso ao modulo de IA",
    "module_workflows": "Acesso a workflows avancados",
    "assets_limit": "Limite de ativos",
    "users_limit": "Limite de usuarios",
    "ai_credits_month": "Creditos de IA por mes",
    "storage_mb": "Armazenamento em MB",
    "kill_switch_module_ai": "Kill switch do modulo IA",
}
PRODUCT_STATUSES = {"BETA", "GA", "RESTRICTED", "DEPRECATED"}
PRODUCT_RULE_TYPES = {"ENABLE_BOOL", "SET_INT", "MIN_INT", "SET_STRING"}


def _model_to_dict(model: Any) -> dict:
    if model is None:
        return {}
    payload = {}
    for column in model.__table__.columns:
        value = getattr(model, column.name)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        payload[column.name] = value
    return payload


def _now() -> datetime:
    return datetime.utcnow()


def _build_governance_decisions(db: Session) -> list[dict]:
    decisions: list[dict] = []
    now = _now()

    trials = (
        db.query(models.Subscription, models.Tenant)
        .join(models.Tenant, models.Tenant.id == models.Subscription.tenant_id)
        .filter(
            models.Subscription.status == "TRIAL",
            models.Subscription.trial_ends_at.isnot(None),
        )
        .all()
    )
    for subscription, tenant in trials:
        if subscription.trial_ends_at and subscription.trial_ends_at <= now + timedelta(days=7):
            decisions.append(
                {
                    "type": "TRIAL_ENDING",
                    "tenant_id": tenant.id,
                    "tenant_nome": tenant.name,
                    "due_at": subscription.trial_ends_at,
                    "message": "Trial proximo do fim",
                }
            )

    overdue = (
        db.query(models.Invoice, models.Tenant)
        .join(models.Tenant, models.Tenant.id == models.Invoice.tenant_id)
        .filter(
            or_(
                models.Invoice.status == "VENCIDO",
                (models.Invoice.status == "PENDENTE") & (models.Invoice.due_date < now.date()),
            )
        )
        .all()
    )
    for invoice, tenant in overdue:
        decisions.append(
            {
                "type": "INVOICE_OVERDUE",
                "tenant_id": tenant.id,
                "tenant_nome": tenant.name,
                "due_at": invoice.due_date,
                "message": "Fatura vencida",
                "invoice_id": invoice.id,
            }
        )

    usage_entries = (
        db.query(models.UsageMeter, models.Tenant)
        .join(models.Tenant, models.Tenant.id == models.UsageMeter.tenant_id)
        .order_by(models.UsageMeter.updated_at.desc())
        .all()
    )
    seen_tenants: set[str] = set()
    for usage, tenant in usage_entries:
        if tenant.id in seen_tenants:
            continue
        seen_tenants.add(tenant.id)
        entitlements = EntitlementsService.get_effective_entitlements(db, tenant.id)
        limits = {ent["key"]: ent["value"] for ent in entitlements if ent.get("value") is not None}
        checks = [
            ("users_limit", usage.users_count, "Usuarios perto do limite"),
            ("assets_limit", usage.assets_count, "Ativos perto do limite"),
            ("storage_mb", usage.storage_mb, "Armazenamento perto do limite"),
            ("ai_credits_month", usage.ai_credits_used, "Creditos de IA perto do limite"),
        ]
        for key, value, message in checks:
            limit = limits.get(key)
            if isinstance(limit, int) and limit > 0:
                if value / limit >= 0.8:
                    decisions.append(
                        {
                            "type": "LIMIT_NEAR",
                            "tenant_id": tenant.id,
                            "tenant_nome": tenant.name,
                            "metric": key,
                            "usage": value,
                            "limit": limit,
                            "message": message,
                        }
                    )

    return decisions


def _audit_event(
    db: Session,
    actor_id: str,
    action: str,
    severity: str = "INFO",
    tenant_id: Optional[str] = None,
    payload: Optional[dict] = None,
    request: Optional[Request] = None,
) -> models.AuditEvent:
    event = models.AuditEvent(
        actor_platform_user_id=actor_id,
        tenant_id=tenant_id,
        action=action,
        severity=severity,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
        payload_json=payload or {},
    )
    db.add(event)
    return event


def _serialize_platform_user(user: models.PlatformUser) -> dict:
    return {
        "id": user.id,
        "nome": user.nome,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "mfa_enabled": user.mfa_enabled,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def _serialize_tenant(tenant: models.Tenant) -> dict:
    return {
        "id": tenant.id,
        "nome": tenant.name,
        "slug": tenant.slug,
        "cnpj": tenant.cnpj,
        "status": tenant.status,
        "tenant_type": tenant.tenant_type,
        "timezone": tenant.timezone,
        "contato_email": tenant.contato_email,
        "razao_social": tenant.razao_social,
        "contato_nome": tenant.contato_nome,
        "contato_telefone": tenant.contato_telefone,
        "segmento": tenant.segmento,
        "porte_empresa": tenant.porte_empresa,
        "site_url": tenant.site_url,
        "billing_email": tenant.billing_email,
        "billing_metodo": tenant.billing_metodo,
        "billing_ciclo": tenant.billing_ciclo,
        "billing_dia_vencimento": tenant.billing_dia_vencimento,
        "billing_proximo_vencimento": tenant.billing_proximo_vencimento,
        "billing_observacoes": tenant.billing_observacoes,
        "created_at": tenant.created_at,
        "updated_at": tenant.updated_at,
    }


def _serialize_plan(plan: models.Plan) -> dict:
    return {
        "id": plan.id,
        "nome": plan.nome,
        "descricao": plan.descricao,
        "preco_mensal_centavos": plan.preco_mensal_centavos,
        "preco_anual_centavos": plan.preco_anual_centavos,
        "is_active": plan.is_active,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
    }


def _serialize_subscription(subscription: models.Subscription) -> dict:
    return {
        "id": subscription.id,
        "tenant_id": subscription.tenant_id,
        "plan_id": subscription.plan_id,
        "status": subscription.status,
        "trial_ends_at": subscription.trial_ends_at,
        "current_period_start": subscription.current_period_start,
        "current_period_end": subscription.current_period_end,
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "created_at": subscription.created_at,
        "updated_at": subscription.updated_at,
    }


def _serialize_invoice(invoice: models.Invoice) -> dict:
    return {
        "id": invoice.id,
        "tenant_id": invoice.tenant_id,
        "subscription_id": invoice.subscription_id,
        "amount_centavos": invoice.amount_centavos,
        "due_date": invoice.due_date,
        "status": invoice.status,
        "paid_at": invoice.paid_at,
        "created_at": invoice.created_at,
    }


def _serialize_product(product: models.Product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "code": product.code,
        "status": product.status,
        "description": product.description,
        "created_at": product.created_at,
        "updated_at": product.updated_at,
    }


def _serialize_tenant_user(user: models.User) -> dict:
    return {
        "id": user.id,
        "tenant_id": user.tenant_id,
        "nome": user.name,
        "login": user.login,
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "created_at": user.created_at,
    }


def _serialize_tenant_contact(contact: models.TenantContact) -> dict:
    return {
        "id": contact.id,
        "tenant_id": contact.tenant_id,
        "nome": contact.nome,
        "email": contact.email,
        "telefone": contact.telefone,
        "created_at": contact.created_at,
    }


def _validate_entitlement_key(key: str) -> None:
    if key not in ENTITLEMENT_CATALOG:
        raise HTTPException(status_code=400, detail="Entitlement nao suportado")


def _extract_entitlement_value(payload: "EntitlementValue") -> tuple[str, Any, dict]:
    value_type = payload.value_type
    if value_type not in {"BOOL", "INT", "STRING"}:
        raise HTTPException(status_code=400, detail="value_type invalido")
    if value_type == "BOOL":
        if payload.value_bool is None:
            raise HTTPException(status_code=400, detail="value_bool obrigatorio para BOOL")
        return value_type, payload.value_bool, {"value_bool": payload.value_bool}
    if value_type == "INT":
        if payload.value_int is None:
            raise HTTPException(status_code=400, detail="value_int obrigatorio para INT")
        return value_type, payload.value_int, {"value_int": payload.value_int}
    if payload.value_string is None:
        raise HTTPException(status_code=400, detail="value_string obrigatorio para STRING")
    return value_type, payload.value_string, {"value_string": payload.value_string}


def _validate_product_status(status_value: str) -> str:
    normalized = status_value.strip().upper()
    if normalized not in PRODUCT_STATUSES:
        raise HTTPException(status_code=400, detail="Status do produto invalido")
    return normalized


def _extract_product_rule(payload: "ProductEntitlementMapItem") -> dict:
    rule_type = payload.rule_type.strip().upper()
    if rule_type not in PRODUCT_RULE_TYPES:
        raise HTTPException(status_code=400, detail="rule_type invalido")
    if rule_type == "ENABLE_BOOL":
        if payload.value_bool is None:
            raise HTTPException(status_code=400, detail="value_bool obrigatorio para ENABLE_BOOL")
        return {"rule_type": rule_type, "value_bool": payload.value_bool}
    if rule_type in {"SET_INT", "MIN_INT"}:
        if payload.value_int is None:
            raise HTTPException(status_code=400, detail="value_int obrigatorio para SET_INT/MIN_INT")
        return {"rule_type": rule_type, "value_int": payload.value_int}
    if payload.value_string is None:
        raise HTTPException(status_code=400, detail="value_string obrigatorio para SET_STRING")
    return {"rule_type": rule_type, "value_string": payload.value_string}


class PlatformLoginRequest(BaseModel):
    email: str
    senha: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    role: str


class TenantCreate(BaseModel):
    nome: str
    slug: Optional[str] = None
    cnpj: Optional[str] = None
    tenant_type: Optional[str] = "MSP"
    contato_email: Optional[str] = None
    razao_social: Optional[str] = None
    contato_nome: Optional[str] = None
    contato_telefone: Optional[str] = None
    segmento: Optional[str] = None
    porte_empresa: Optional[str] = None
    site_url: Optional[str] = None
    billing_email: Optional[str] = None
    billing_metodo: Optional[str] = None
    billing_ciclo: Optional[str] = None
    billing_dia_vencimento: Optional[int] = Field(default=None, ge=1, le=31)
    billing_proximo_vencimento: Optional[date] = None
    billing_observacoes: Optional[str] = None
    timezone: str = "America/Sao_Paulo"
    plan_id: str
    trial_days: Optional[int] = Field(default=None, ge=0, le=365)
    admin_nome: str
    admin_email: str
    admin_login: Optional[str] = None
    admin_senha: str


class TenantUpdate(BaseModel):
    nome: Optional[str] = None
    contato_email: Optional[str] = None
    timezone: Optional[str] = None
    cnpj: Optional[str] = None
    razao_social: Optional[str] = None
    contato_nome: Optional[str] = None
    contato_telefone: Optional[str] = None
    segmento: Optional[str] = None
    porte_empresa: Optional[str] = None
    site_url: Optional[str] = None
    billing_email: Optional[str] = None
    billing_metodo: Optional[str] = None
    billing_ciclo: Optional[str] = None
    billing_dia_vencimento: Optional[int] = Field(default=None, ge=1, le=31)
    billing_proximo_vencimento: Optional[date] = None
    billing_observacoes: Optional[str] = None


class ChangePlanRequest(BaseModel):
    plan_id: str
    trial_days: Optional[int] = Field(default=None, ge=0, le=365)


class TenantUserCreate(BaseModel):
    nome: str
    login: str
    email: Optional[str] = None
    role: str = "TENANT_USER"
    senha: str


class TenantUserUpdate(BaseModel):
    nome: Optional[str] = None
    login: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    senha: Optional[str] = None
    status: Optional[str] = None


class TenantContactPayload(BaseModel):
    nome: str
    email: str
    telefone: Optional[str] = None


class EntitlementValue(BaseModel):
    key: str
    value_type: str
    value_bool: Optional[bool] = None
    value_int: Optional[int] = None
    value_string: Optional[str] = None


class OverrideCreate(EntitlementValue):
    reason: str


class PlanCreate(BaseModel):
    nome: str
    descricao: Optional[str] = None
    preco_mensal_centavos: int = 0
    preco_anual_centavos: int = 0
    is_active: bool = True


class PlanUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    preco_mensal_centavos: Optional[int] = None
    preco_anual_centavos: Optional[int] = None
    is_active: Optional[bool] = None


class ProductCreate(BaseModel):
    name: str
    code: str
    status: str = "BETA"
    description: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None


class ProductEntitlementMapItem(BaseModel):
    entitlement_key: str
    rule_type: str
    value_bool: Optional[bool] = None
    value_int: Optional[int] = None
    value_string: Optional[str] = None


class RolloutRulePayload(BaseModel):
    enabled_global: bool = False
    rollout_percent: int = Field(default=0, ge=0, le=100)
    kill_switch: bool = False


class PlatformUserCreate(BaseModel):
    nome: str
    email: str
    role: str
    senha: str
    is_active: bool = True
    mfa_enabled: Optional[bool] = False


class PlatformUserUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    senha: Optional[str] = None
    is_active: Optional[bool] = None
    mfa_enabled: Optional[bool] = None


class ImpersonationStart(BaseModel):
    tenant_id: str
    reason: str


class ImpersonationEnd(BaseModel):
    session_id: str


def _authenticate_platform(db: Session, email: str, password: str) -> models.PlatformUser:
    normalized = email.strip().lower()
    user = (
        db.query(models.PlatformUser)
        .filter(func.lower(models.PlatformUser.email) == normalized)
        .first()
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario ou senha invalidos")
    ok, needs_upgrade = verify_password_with_upgrade(password, user.password_hash)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario ou senha invalidos")
    if needs_upgrade:
        user.password_hash = get_password_hash(password)
        db.add(user)
        db.commit()
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inativo")
    return user


@router.post("/auth/login", response_model=LoginResponse, summary="Login JSON Platform Console")
def platform_login(payload: PlatformLoginRequest, db: Session = Depends(get_db)):
    user = _authenticate_platform(db, payload.email, payload.senha)
    token = create_access_token({"platform_user_id": user.id, "role": user.role})
    return {"access_token": token, "token_type": "bearer", "role": user.role}


@router.post("/auth/token", response_model=LoginResponse, summary="Login Swagger Platform Console")
def platform_login_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = _authenticate_platform(db, form_data.username, form_data.password)
    token = create_access_token({"platform_user_id": user.id, "role": user.role})
    return {"access_token": token, "token_type": "bearer", "role": user.role}


@router.get("/me")
def platform_me(current_user: models.PlatformUser = Depends(get_current_platform_user)):
    return _serialize_platform_user(current_user)


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    tenants_ativos = db.query(models.Tenant).filter(models.Tenant.status == "ATIVO").count()
    trials = db.query(models.Tenant).filter(models.Tenant.status == "TRIAL").count()
    inadimplentes = db.query(models.Tenant).filter(models.Tenant.status == "INADIMPLENTE").count()

    mrr = (
        db.query(func.coalesce(func.sum(models.Plan.preco_mensal_centavos), 0))
        .join(models.Subscription, models.Subscription.plan_id == models.Plan.id)
        .filter(models.Subscription.status == "ATIVA")
        .scalar()
    )

    tenants_em_risco = (
        db.query(models.Tenant)
        .filter(models.Tenant.status != "ATIVO")
        .order_by(models.Tenant.updated_at.desc())
        .limit(10)
        .all()
    )
    audit_recent = (
        db.query(models.AuditEvent).order_by(models.AuditEvent.created_at.desc()).limit(10).all()
    )
    decisoes = _build_governance_decisions(db)

    return {
        "tenants_ativos": tenants_ativos,
        "trials": trials,
        "inadimplentes": inadimplentes,
        "mrr_estimado_centavos": mrr or 0,
        "tickets": 0,
        "incidentes": 0,
        "decisoes_pendentes": decisoes[:5],
        "tenants_em_risco": [_serialize_tenant(t) for t in tenants_em_risco],
        "audit_recent": [
            {
                "id": event.id,
                "action": event.action,
                "severity": event.severity,
                "tenant_id": event.tenant_id,
                "created_at": event.created_at,
            }
            for event in audit_recent
        ],
    }


@router.get("/governance/decisions")
def governance_decisions(
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    decisions = _build_governance_decisions(db)
    return {"items": decisions[:100]}


@router.get("/usage/alerts")
def list_usage_alerts(
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    alerts = (
        db.query(models.TenantAlert, models.Tenant)
        .join(models.Tenant, models.Tenant.id == models.TenantAlert.tenant_id)
        .filter(models.TenantAlert.resolved_at.is_(None))
        .order_by(models.TenantAlert.created_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": alert.id,
            "tenant_id": tenant.id,
            "tenant_nome": tenant.name,
            "type": alert.type,
            "severity": alert.severity,
            "message": alert.message,
            "suggested_action": alert.suggested_action,
            "created_at": alert.created_at,
            "resolved_at": alert.resolved_at,
        }
        for alert, tenant in alerts
    ]


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    alert = db.query(models.TenantAlert).filter(models.TenantAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta nao encontrado")
    before = _model_to_dict(alert)
    alert.resolved_at = _now()
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=alert.tenant_id,
        action="TENANT_ALERT_RESOLVE",
        severity="INFO",
        payload={"before": before, "after": _model_to_dict(alert)},
        request=request,
    )
    db.commit()
    db.refresh(alert)
    return {"status": "ok"}


@router.get("/tenants")
def list_tenants(
    status: Optional[str] = None,
    tenant_type: Optional[str] = Query(default=None, alias="type"),
    q: Optional[str] = None,
    page: int = 1,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    page_size = 20
    query = db.query(models.Tenant)
    if status:
        query = query.filter(models.Tenant.status == status)
    else:
        query = query.filter(models.Tenant.status != "ARQUIVADO")
    if tenant_type:
        query = query.filter(models.Tenant.tenant_type == tenant_type)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(models.Tenant.name).like(like),
                func.lower(models.Tenant.slug).like(like),
                func.lower(models.Tenant.contato_email).like(like),
            )
        )
    total = query.count()
    items = (
        query.order_by(models.Tenant.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [_serialize_tenant(t) for t in items],
    }


@router.post("/tenants", status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    tenant_type = (payload.tenant_type or "MSP").upper()
    if tenant_type not in {"MSP", "ENTERPRISE"}:
        raise HTTPException(status_code=400, detail="Tipo de tenant invalido")
    slug = payload.slug.strip().lower() if payload.slug else payload.nome.strip().lower().replace(" ", "-")
    if db.query(models.Tenant).filter(models.Tenant.slug == slug).first():
        raise HTTPException(status_code=400, detail="Slug ja existe")

    plan = db.query(models.Plan).filter(models.Plan.id == payload.plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plano nao encontrado")

    tenant = models.Tenant(
        name=payload.nome,
        slug=slug,
        cnpj=payload.cnpj,
        status="TRIAL" if payload.trial_days else "ATIVO",
        tenant_type=tenant_type,
        timezone=payload.timezone,
        contato_email=payload.contato_email,
        razao_social=payload.razao_social,
        contato_nome=payload.contato_nome,
        contato_telefone=payload.contato_telefone,
        segmento=payload.segmento,
        porte_empresa=payload.porte_empresa,
        site_url=payload.site_url,
        billing_email=payload.billing_email or payload.contato_email,
        billing_metodo=payload.billing_metodo,
        billing_ciclo=payload.billing_ciclo,
        billing_dia_vencimento=payload.billing_dia_vencimento,
        billing_proximo_vencimento=payload.billing_proximo_vencimento,
        billing_observacoes=payload.billing_observacoes,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(tenant)
    db.flush()

    now = _now()
    subscription = models.Subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status="TRIAL" if payload.trial_days else "ATIVA",
        trial_ends_at=now + timedelta(days=payload.trial_days) if payload.trial_days else None,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
        cancel_at_period_end=False,
    )
    db.add(subscription)

    admin_login = (payload.admin_login or payload.admin_email).strip()
    admin_user = models.User(
        tenant_id=tenant.id,
        name=payload.admin_nome,
        login=admin_login,
        email=payload.admin_email,
        password_hash=get_password_hash(payload.admin_senha),
        role="TENANT_ADMIN",
        status="active",
        client_id=None,
    )
    db.add(admin_user)

    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=tenant.id,
        action="TENANT_CREATE",
        severity="INFO",
        payload={
            "tenant": _model_to_dict(tenant),
            "subscription": _model_to_dict(subscription),
            "admin_user": _model_to_dict(admin_user),
        },
        request=request,
    )
    db.commit()

    return {
        "tenant": _serialize_tenant(tenant),
        "subscription": _serialize_subscription(subscription),
        "admin_user": {
            "id": admin_user.id,
            "nome": admin_user.name,
            "login": admin_user.login,
            "email": admin_user.email,
            "role": admin_user.role,
            "status": admin_user.status,
        },
    }


@router.get("/tenants/{tenant_id}")
def get_tenant(
    tenant_id: str,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant nao encontrado")

    subscription = (
        db.query(models.Subscription)
        .filter(models.Subscription.tenant_id == tenant_id)
        .order_by(models.Subscription.created_at.desc())
        .first()
    )
    plan = subscription.plan if subscription else None
    return {
        "tenant": _serialize_tenant(tenant),
        "subscription": _serialize_subscription(subscription) if subscription else None,
        "plan": _serialize_plan(plan) if plan else None,
    }


@router.patch("/tenants/{tenant_id}")
def update_tenant(
    tenant_id: str,
    payload: TenantUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant nao encontrado")
    before = _model_to_dict(tenant)

    if payload.nome is not None:
        tenant.name = payload.nome
    if payload.contato_email is not None:
        tenant.contato_email = payload.contato_email
    if payload.timezone is not None:
        tenant.timezone = payload.timezone
    if payload.cnpj is not None:
        tenant.cnpj = payload.cnpj
    if payload.razao_social is not None:
        tenant.razao_social = payload.razao_social
    if payload.contato_nome is not None:
        tenant.contato_nome = payload.contato_nome
    if payload.contato_telefone is not None:
        tenant.contato_telefone = payload.contato_telefone
    if payload.segmento is not None:
        tenant.segmento = payload.segmento
    if payload.porte_empresa is not None:
        tenant.porte_empresa = payload.porte_empresa
    if payload.site_url is not None:
        tenant.site_url = payload.site_url
    if payload.billing_email is not None:
        tenant.billing_email = payload.billing_email
    if payload.billing_metodo is not None:
        tenant.billing_metodo = payload.billing_metodo
    if payload.billing_ciclo is not None:
        tenant.billing_ciclo = payload.billing_ciclo
    if payload.billing_dia_vencimento is not None:
        tenant.billing_dia_vencimento = payload.billing_dia_vencimento
    if payload.billing_proximo_vencimento is not None:
        tenant.billing_proximo_vencimento = payload.billing_proximo_vencimento
    if payload.billing_observacoes is not None:
        tenant.billing_observacoes = payload.billing_observacoes
    tenant.updated_at = _now()

    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=tenant.id,
        action="TENANT_UPDATE",
        severity="INFO",
        payload={"before": before, "after": _model_to_dict(tenant)},
        request=request,
    )
    db.commit()
    db.refresh(tenant)
    return _serialize_tenant(tenant)


def _set_tenant_status(
    tenant_id: str,
    status_value: str,
    action: str,
    request: Request,
    db: Session,
    current_user: models.PlatformUser,
) -> dict:
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant nao encontrado")
    before = _model_to_dict(tenant)
    tenant.status = status_value
    tenant.updated_at = _now()
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=tenant.id,
        action=action,
        severity="CRITICAL",
        payload={"before": before, "after": _model_to_dict(tenant)},
        request=request,
    )
    db.commit()
    db.refresh(tenant)
    return _serialize_tenant(tenant)


@router.post("/tenants/{tenant_id}/suspend")
def suspend_tenant(
    tenant_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    return _set_tenant_status(tenant_id, "SUSPENSO", "TENANT_SUSPEND", request, db, current_user)


@router.post("/tenants/{tenant_id}/reactivate")
def reactivate_tenant(
    tenant_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    return _set_tenant_status(tenant_id, "ATIVO", "TENANT_REACTIVATE", request, db, current_user)


@router.post("/tenants/{tenant_id}/block")
def block_tenant(
    tenant_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    return _set_tenant_status(tenant_id, "BLOQUEADO", "TENANT_BLOCK", request, db, current_user)


@router.post("/tenants/{tenant_id}/archive")
def archive_tenant(
    tenant_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    return _set_tenant_status(tenant_id, "ARQUIVADO", "TENANT_ARCHIVE", request, db, current_user)


@router.post("/tenants/{tenant_id}/cancel")
def cancel_tenant(
    tenant_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant nao encontrado")
    before = _model_to_dict(tenant)
    tenant.status = "CANCELADO"
    tenant.updated_at = _now()
    subscription = (
        db.query(models.Subscription)
        .filter(models.Subscription.tenant_id == tenant_id, models.Subscription.status != "CANCELADA")
        .first()
    )
    if subscription:
        subscription.status = "CANCELADA"
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=tenant_id,
        action="TENANT_CANCEL",
        severity="CRITICAL",
        payload={
            "before": before,
            "after": _model_to_dict(tenant),
            "subscription_id": subscription.id if subscription else None,
        },
        request=request,
    )
    db.commit()
    db.refresh(tenant)
    return _serialize_tenant(tenant)


@router.get("/tenants/{tenant_id}/contacts")
def list_tenant_contacts(
    tenant_id: str,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    contacts = (
        db.query(models.TenantContact)
        .filter(models.TenantContact.tenant_id == tenant_id)
        .order_by(models.TenantContact.created_at.desc())
        .all()
    )
    return [_serialize_tenant_contact(contact) for contact in contacts]


@router.post("/tenants/{tenant_id}/contacts", status_code=status.HTTP_201_CREATED)
def create_tenant_contact(
    tenant_id: str,
    payload: TenantContactPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN", "PLATFORM_SUPPORT")
    ),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant nao encontrado")
    contact = models.TenantContact(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        nome=payload.nome,
        email=payload.email,
        telefone=payload.telefone,
    )
    db.add(contact)
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=tenant_id,
        action="TENANT_CONTACT_CREATE",
        severity="INFO",
        payload={"contact": _model_to_dict(contact)},
        request=request,
    )
    db.commit()
    db.refresh(contact)
    return _serialize_tenant_contact(contact)


@router.delete("/tenants/{tenant_id}/contacts/{contact_id}")
def delete_tenant_contact(
    tenant_id: str,
    contact_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    contact = (
        db.query(models.TenantContact)
        .filter(models.TenantContact.id == contact_id, models.TenantContact.tenant_id == tenant_id)
        .first()
    )
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    before = _model_to_dict(contact)
    db.delete(contact)
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=tenant_id,
        action="TENANT_CONTACT_DELETE",
        severity="INFO",
        payload={"contact": before},
        request=request,
    )
    db.commit()
    return {"status": "ok"}


@router.post("/tenants/{tenant_id}/change-plan")
def change_plan(
    tenant_id: str,
    payload: ChangePlanRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant nao encontrado")
    plan = db.query(models.Plan).filter(models.Plan.id == payload.plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plano nao encontrado")

    subscription = (
        db.query(models.Subscription)
        .filter(models.Subscription.tenant_id == tenant_id)
        .order_by(models.Subscription.created_at.desc())
        .first()
    )
    if not subscription:
        subscription = models.Subscription(
            tenant_id=tenant_id,
            plan_id=plan.id,
            status="ATIVA",
            current_period_start=_now(),
            current_period_end=_now() + timedelta(days=30),
            cancel_at_period_end=False,
        )
        db.add(subscription)
    before = _model_to_dict(subscription)
    subscription.plan_id = plan.id
    if payload.trial_days:
        subscription.status = "TRIAL"
        subscription.trial_ends_at = _now() + timedelta(days=payload.trial_days)
    else:
        subscription.status = "ATIVA"
        subscription.trial_ends_at = None
    subscription.current_period_start = _now()
    subscription.current_period_end = _now() + timedelta(days=30)

    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=tenant.id,
        action="TENANT_CHANGE_PLAN",
        severity="CRITICAL",
        payload={"before": before, "after": _model_to_dict(subscription)},
        request=request,
    )
    db.commit()
    db.refresh(subscription)
    return _serialize_subscription(subscription)


@router.get("/tenants/{tenant_id}/entitlements-effective")
def entitlements_effective(
    tenant_id: str,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant nao encontrado")
    return {
        "tenant_id": tenant_id,
        "entitlements": EntitlementsService.get_effective_entitlements(db, tenant_id),
    }


@router.get("/tenants/{tenant_id}/overrides")
def list_overrides(
    tenant_id: str,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    overrides = (
        db.query(models.TenantOverride)
        .filter(models.TenantOverride.tenant_id == tenant_id)
        .order_by(models.TenantOverride.created_at.desc())
        .all()
    )
    return [
        {
            "id": o.id,
            "tenant_id": o.tenant_id,
            "key": o.key,
            "value_type": o.value_type,
            "value_bool": o.value_bool,
            "value_int": o.value_int,
            "value_string": o.value_string,
            "reason": o.reason,
            "created_by_platform_user_id": o.created_by_platform_user_id,
            "created_at": o.created_at,
        }
        for o in overrides
    ]


@router.post("/tenants/{tenant_id}/overrides", status_code=status.HTTP_201_CREATED)
def create_override(
    tenant_id: str,
    payload: OverrideCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant nao encontrado")
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Reason obrigatorio")
    _validate_entitlement_key(payload.key)
    value_type, _, value_payload = _extract_entitlement_value(payload)

    override = models.TenantOverride(
        tenant_id=tenant_id,
        key=payload.key,
        value_type=value_type,
        value_bool=value_payload.get("value_bool"),
        value_int=value_payload.get("value_int"),
        value_string=value_payload.get("value_string"),
        reason=payload.reason,
        created_by_platform_user_id=current_user.id,
    )
    db.add(override)
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=tenant.id,
        action="OVERRIDE_SET",
        severity="CRITICAL",
        payload={"override": _model_to_dict(override)},
        request=request,
    )
    db.commit()
    db.refresh(override)
    return {
        "id": override.id,
        "tenant_id": override.tenant_id,
        "key": override.key,
        "value_type": override.value_type,
        "value_bool": override.value_bool,
        "value_int": override.value_int,
        "value_string": override.value_string,
        "reason": override.reason,
        "created_by_platform_user_id": override.created_by_platform_user_id,
        "created_at": override.created_at,
    }


@router.delete("/tenants/{tenant_id}/overrides/{override_id}")
def delete_override(
    tenant_id: str,
    override_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    override = (
        db.query(models.TenantOverride)
        .filter(
            models.TenantOverride.tenant_id == tenant_id, models.TenantOverride.id == override_id
        )
        .first()
    )
    if not override:
        raise HTTPException(status_code=404, detail="Override nao encontrado")
    before = _model_to_dict(override)
    db.delete(override)
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=tenant_id,
        action="OVERRIDE_DELETE",
        severity="CRITICAL",
        payload={"before": before},
        request=request,
    )
    db.commit()
    return {"status": "ok"}


@router.get("/tenants/{tenant_id}/users")
def list_tenant_users(
    tenant_id: str,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    users = (
        db.query(models.User)
        .filter(models.User.tenant_id == tenant_id)
        .order_by(models.User.created_at.desc())
        .all()
    )
    return [_serialize_tenant_user(user) for user in users]


@router.post("/tenants/{tenant_id}/users", status_code=status.HTTP_201_CREATED)
def create_tenant_user(
    tenant_id: str,
    payload: TenantUserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant nao encontrado")
    existing = (
        db.query(models.User)
        .filter(models.User.tenant_id == tenant_id, models.User.login == payload.login)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Login ja existe")
    user = models.User(
        tenant_id=tenant_id,
        name=payload.nome,
        login=payload.login,
        email=payload.email,
        password_hash=get_password_hash(payload.senha),
        role=payload.role,
        status="active",
        client_id=None,
    )
    db.add(user)
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=tenant_id,
        action="TENANT_USER_CREATE",
        severity="INFO",
        payload={"user": _model_to_dict(user)},
        request=request,
    )
    db.commit()
    db.refresh(user)
    return _serialize_tenant_user(user)


@router.patch("/tenants/{tenant_id}/users/{user_id}")
def update_tenant_user(
    tenant_id: str,
    user_id: str,
    payload: TenantUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    user = (
        db.query(models.User)
        .filter(models.User.tenant_id == tenant_id, models.User.id == user_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    before = _model_to_dict(user)
    if payload.nome is not None:
        user.name = payload.nome
    if payload.login is not None:
        existing = (
            db.query(models.User)
            .filter(
                models.User.tenant_id == tenant_id,
                models.User.login == payload.login,
                models.User.id != user_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Login ja existe")
        user.login = payload.login
    if payload.email is not None:
        user.email = payload.email
    if payload.role is not None:
        user.role = payload.role
    if payload.status is not None:
        user.status = payload.status
    if payload.senha:
        user.password_hash = get_password_hash(payload.senha)
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=tenant_id,
        action="TENANT_USER_UPDATE",
        severity="INFO",
        payload={"before": before, "after": _model_to_dict(user)},
        request=request,
    )
    db.commit()
    db.refresh(user)
    return _serialize_tenant_user(user)


@router.post("/tenants/{tenant_id}/users/{user_id}/deactivate")
def deactivate_tenant_user(
    tenant_id: str,
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    user = (
        db.query(models.User)
        .filter(models.User.tenant_id == tenant_id, models.User.id == user_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    before = _model_to_dict(user)
    user.status = "inactive"
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=tenant_id,
        action="TENANT_USER_DEACTIVATE",
        severity="CRITICAL",
        payload={"before": before, "after": _model_to_dict(user)},
        request=request,
    )
    db.commit()
    db.refresh(user)
    return _serialize_tenant_user(user)


@router.delete("/tenants/{tenant_id}/users/{user_id}")
def delete_tenant_user(
    tenant_id: str,
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    user = (
        db.query(models.User)
        .filter(models.User.tenant_id == tenant_id, models.User.id == user_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    before = _model_to_dict(user)
    db.delete(user)
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=tenant_id,
        action="TENANT_USER_DELETE",
        severity="CRITICAL",
        payload={"before": before},
        request=request,
    )
    db.commit()
    return {"status": "ok"}


@router.get("/plans")
def list_plans(
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    plans = db.query(models.Plan).order_by(models.Plan.created_at.desc()).all()
    return [_serialize_plan(plan) for plan in plans]


@router.post("/plans", status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: PlanCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    if db.query(models.Plan).filter(models.Plan.nome == payload.nome).first():
        raise HTTPException(status_code=400, detail="Plano ja existe")
    plan = models.Plan(
        nome=payload.nome,
        descricao=payload.descricao,
        preco_mensal_centavos=payload.preco_mensal_centavos,
        preco_anual_centavos=payload.preco_anual_centavos,
        is_active=payload.is_active,
    )
    db.add(plan)
    _audit_event(
        db,
        actor_id=current_user.id,
        action="PLAN_CREATE",
        severity="INFO",
        payload={"plan": _model_to_dict(plan)},
        request=request,
    )
    db.commit()
    db.refresh(plan)
    return _serialize_plan(plan)


@router.get("/plans/{plan_id}")
def get_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plano nao encontrado")
    return _serialize_plan(plan)


@router.patch("/plans/{plan_id}")
def update_plan(
    plan_id: str,
    payload: PlanUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plano nao encontrado")
    before = _model_to_dict(plan)
    if payload.nome is not None:
        plan.nome = payload.nome
    if payload.descricao is not None:
        plan.descricao = payload.descricao
    if payload.preco_mensal_centavos is not None:
        plan.preco_mensal_centavos = payload.preco_mensal_centavos
    if payload.preco_anual_centavos is not None:
        plan.preco_anual_centavos = payload.preco_anual_centavos
    if payload.is_active is not None:
        plan.is_active = payload.is_active

    _audit_event(
        db,
        actor_id=current_user.id,
        action="PLAN_UPDATE",
        severity="INFO",
        payload={"before": before, "after": _model_to_dict(plan)},
        request=request,
    )
    db.commit()
    db.refresh(plan)
    return _serialize_plan(plan)


@router.post("/plans/{plan_id}/entitlements")
def set_plan_entitlements(
    plan_id: str,
    payload: list[EntitlementValue],
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plano nao encontrado")
    before = [_model_to_dict(ent) for ent in plan.entitlements]
    db.query(models.PlanEntitlement).filter(models.PlanEntitlement.plan_id == plan_id).delete()

    entitlements = []
    for ent in payload:
        _validate_entitlement_key(ent.key)
        value_type, _, values = _extract_entitlement_value(ent)
        entitlements.append(
            models.PlanEntitlement(
                plan_id=plan_id,
                key=ent.key,
                value_type=value_type,
                value_bool=values.get("value_bool"),
                value_int=values.get("value_int"),
                value_string=values.get("value_string"),
            )
        )
    db.add_all(entitlements)
    after = [_model_to_dict(ent) for ent in entitlements]
    _audit_event(
        db,
        actor_id=current_user.id,
        action="PLAN_ENTITLEMENTS_SET",
        severity="CRITICAL",
        payload={"before": before, "after": after, "plan_id": plan_id},
        request=request,
    )
    db.commit()
    return {"status": "ok"}


@router.get("/plans/{plan_id}/entitlements")
def list_plan_entitlements(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plano nao encontrado")
    return [
        {
            "id": ent.id,
            "plan_id": ent.plan_id,
            "key": ent.key,
            "value_type": ent.value_type,
            "value_bool": ent.value_bool,
            "value_int": ent.value_int,
            "value_string": ent.value_string,
        }
        for ent in plan.entitlements
    ]


@router.get("/products")
def list_products(
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    products = db.query(models.Product).order_by(models.Product.created_at.desc()).all()
    return [_serialize_product(product) for product in products]


@router.post("/products", status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    if db.query(models.Product).filter(models.Product.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Codigo ja existe")
    product = models.Product(
        name=payload.name,
        code=payload.code,
        status=_validate_product_status(payload.status),
        description=payload.description,
    )
    db.add(product)
    _audit_event(
        db,
        actor_id=current_user.id,
        action="PRODUCT_CREATE",
        severity="INFO",
        payload={"product": _model_to_dict(product)},
        request=request,
    )
    db.commit()
    db.refresh(product)
    return _serialize_product(product)


@router.get("/products/{product_id}")
def get_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    return _serialize_product(product)


@router.patch("/products/{product_id}")
def update_product(
    product_id: str,
    payload: ProductUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    before = _model_to_dict(product)
    if payload.name is not None:
        product.name = payload.name
    if payload.code is not None:
        if (
            db.query(models.Product)
            .filter(models.Product.code == payload.code, models.Product.id != product_id)
            .first()
        ):
            raise HTTPException(status_code=400, detail="Codigo ja existe")
        product.code = payload.code
    if payload.status is not None:
        product.status = _validate_product_status(payload.status)
    if payload.description is not None:
        product.description = payload.description
    _audit_event(
        db,
        actor_id=current_user.id,
        action="PRODUCT_UPDATE",
        severity="INFO",
        payload={"before": before, "after": _model_to_dict(product)},
        request=request,
    )
    db.commit()
    db.refresh(product)
    return _serialize_product(product)


@router.get("/products/{product_id}/entitlement-map")
def list_product_entitlement_map(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    return [
        {
            "id": item.id,
            "product_id": item.product_id,
            "entitlement_key": item.entitlement_key,
            "rule_type": item.rule_type,
            "value_bool": item.value_bool,
            "value_int": item.value_int,
            "value_string": item.value_string,
        }
        for item in product.entitlement_map
    ]


@router.post("/products/{product_id}/entitlement-map")
def set_product_entitlement_map(
    product_id: str,
    payload: list[ProductEntitlementMapItem],
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    before = [_model_to_dict(item) for item in product.entitlement_map]
    db.query(models.ProductEntitlementMap).filter(
        models.ProductEntitlementMap.product_id == product_id
    ).delete()
    items: list[models.ProductEntitlementMap] = []
    for entry in payload:
        _validate_entitlement_key(entry.entitlement_key)
        values = _extract_product_rule(entry)
        items.append(
            models.ProductEntitlementMap(
                product_id=product_id,
                entitlement_key=entry.entitlement_key,
                rule_type=values["rule_type"],
                value_bool=values.get("value_bool"),
                value_int=values.get("value_int"),
                value_string=values.get("value_string"),
            )
        )
    db.add_all(items)
    _audit_event(
        db,
        actor_id=current_user.id,
        action="PRODUCT_ENTITLEMENT_MAP_SET",
        severity="CRITICAL",
        payload={"before": before, "after": [_model_to_dict(item) for item in items]},
        request=request,
    )
    db.commit()
    return {"status": "ok"}


@router.get("/products/{product_id}/rollout")
def get_product_rollout(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    rule = (
        db.query(models.RolloutRule).filter(models.RolloutRule.product_id == product_id).first()
    )
    if not rule:
        return {
            "product_id": product_id,
            "enabled_global": False,
            "rollout_percent": 0,
            "kill_switch": False,
        }
    return {
        "product_id": rule.product_id,
        "enabled_global": rule.enabled_global,
        "rollout_percent": rule.rollout_percent,
        "kill_switch": rule.kill_switch,
        "updated_at": rule.updated_at,
    }


@router.post("/products/{product_id}/rollout")
def upsert_product_rollout(
    product_id: str,
    payload: RolloutRulePayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto nao encontrado")
    rule = (
        db.query(models.RolloutRule).filter(models.RolloutRule.product_id == product_id).first()
    )
    before = _model_to_dict(rule) if rule else None
    if not rule:
        rule = models.RolloutRule(
            product_id=product_id,
            enabled_global=payload.enabled_global,
            rollout_percent=payload.rollout_percent,
            kill_switch=payload.kill_switch,
        )
        db.add(rule)
    else:
        rule.enabled_global = payload.enabled_global
        rule.rollout_percent = payload.rollout_percent
        rule.kill_switch = payload.kill_switch
    _audit_event(
        db,
        actor_id=current_user.id,
        action="PRODUCT_ROLLOUT_UPDATE",
        severity="CRITICAL",
        payload={"before": before, "after": _model_to_dict(rule)},
        request=request,
    )
    db.commit()
    db.refresh(rule)
    return {
        "product_id": rule.product_id,
        "enabled_global": rule.enabled_global,
        "rollout_percent": rule.rollout_percent,
        "kill_switch": rule.kill_switch,
        "updated_at": rule.updated_at,
    }


@router.get("/billing/summary")
def billing_summary(
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN", "PLATFORM_FINANCE")
    ),
):
    total_pending = (
        db.query(func.coalesce(func.sum(models.Invoice.amount_centavos), 0))
        .filter(models.Invoice.status == "PENDENTE")
        .scalar()
    )
    total_overdue = (
        db.query(func.coalesce(func.sum(models.Invoice.amount_centavos), 0))
        .filter(models.Invoice.status == "VENCIDO")
        .scalar()
    )
    return {
        "total_pendente_centavos": total_pending or 0,
        "total_vencido_centavos": total_overdue or 0,
    }


@router.get("/invoices")
def list_invoices(
    status: Optional[str] = None,
    tenant_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN", "PLATFORM_FINANCE")
    ),
):
    query = db.query(models.Invoice)
    if status:
        query = query.filter(models.Invoice.status == status)
    if tenant_id:
        query = query.filter(models.Invoice.tenant_id == tenant_id)
    invoices = query.order_by(models.Invoice.created_at.desc()).all()
    return [_serialize_invoice(invoice) for invoice in invoices]


@router.post("/invoices/{invoice_id}/mark-paid")
def mark_invoice_paid(
    invoice_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN", "PLATFORM_FINANCE")
    ),
):
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura nao encontrada")
    before = _model_to_dict(invoice)
    invoice.status = "PAGO"
    invoice.paid_at = _now()
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=invoice.tenant_id,
        action="INVOICE_MARK_PAID",
        severity="INFO",
        payload={"before": before, "after": _model_to_dict(invoice)},
        request=request,
    )
    db.commit()
    db.refresh(invoice)
    return _serialize_invoice(invoice)


@router.post("/invoices/{invoice_id}/cancel")
def cancel_invoice(
    invoice_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN", "PLATFORM_FINANCE")
    ),
):
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura nao encontrada")
    before = _model_to_dict(invoice)
    invoice.status = "CANCELADO"
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=invoice.tenant_id,
        action="INVOICE_CANCEL",
        severity="INFO",
        payload={"before": before, "after": _model_to_dict(invoice)},
        request=request,
    )
    db.commit()
    db.refresh(invoice)
    return _serialize_invoice(invoice)


@router.get("/entitlements/catalog")
def entitlements_catalog(
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    return [
        {"key": key, "descricao": descricao, "value_type": "BOOL" if "module" in key else "INT"}
        for key, descricao in ENTITLEMENT_CATALOG.items()
    ]


@router.get("/platform-users")
def list_platform_users(
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    users = db.query(models.PlatformUser).order_by(models.PlatformUser.created_at.desc()).all()
    return [_serialize_platform_user(user) for user in users]


@router.post("/platform-users", status_code=status.HTTP_201_CREATED)
def create_platform_user(
    payload: PlatformUserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    if payload.role not in PLATFORM_ROLES:
        raise HTTPException(status_code=400, detail="Role invalida")
    if db.query(models.PlatformUser).filter(models.PlatformUser.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email ja existe")
    from app.core.security import get_password_hash

    user = models.PlatformUser(
        nome=payload.nome,
        email=payload.email,
        password_hash=get_password_hash(payload.senha),
        role=payload.role,
        is_active=payload.is_active,
        mfa_enabled=payload.mfa_enabled,
    )
    db.add(user)
    _audit_event(
        db,
        actor_id=current_user.id,
        action="PLATFORM_USER_CREATE",
        severity="INFO",
        payload={"user": _model_to_dict(user)},
        request=request,
    )
    db.commit()
    db.refresh(user)
    return _serialize_platform_user(user)


@router.patch("/platform-users/{user_id}")
def update_platform_user(
    user_id: str,
    payload: PlatformUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    user = db.query(models.PlatformUser).filter(models.PlatformUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    before = _model_to_dict(user)
    if payload.nome is not None:
        user.nome = payload.nome
    if payload.email is not None:
        user.email = payload.email
    if payload.role is not None:
        if payload.role not in PLATFORM_ROLES:
            raise HTTPException(status_code=400, detail="Role invalida")
        user.role = payload.role
    if payload.senha:
        from app.core.security import get_password_hash

        user.password_hash = get_password_hash(payload.senha)
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.mfa_enabled is not None:
        user.mfa_enabled = payload.mfa_enabled

    _audit_event(
        db,
        actor_id=current_user.id,
        action="PLATFORM_USER_UPDATE",
        severity="INFO",
        payload={"before": before, "after": _model_to_dict(user)},
        request=request,
    )
    db.commit()
    db.refresh(user)
    return _serialize_platform_user(user)


@router.post("/platform-users/{user_id}/deactivate")
def deactivate_platform_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN")
    ),
):
    user = db.query(models.PlatformUser).filter(models.PlatformUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    before = _model_to_dict(user)
    user.is_active = False
    _audit_event(
        db,
        actor_id=current_user.id,
        action="PLATFORM_USER_DEACTIVATE",
        severity="CRITICAL",
        payload={"before": before, "after": _model_to_dict(user)},
        request=request,
    )
    db.commit()
    db.refresh(user)
    return _serialize_platform_user(user)


@router.get("/audit")
def list_audit(
    tenant_id: Optional[str] = None,
    severity: Optional[str] = None,
    action: Optional[str] = None,
    q: Optional[str] = None,
    from_date: Optional[date] = Query(default=None, alias="from"),
    to_date: Optional[date] = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(require_platform_roles(*PLATFORM_ROLES)),
):
    query = db.query(models.AuditEvent)
    if tenant_id:
        query = query.filter(models.AuditEvent.tenant_id == tenant_id)
    if severity:
        query = query.filter(models.AuditEvent.severity == severity)
    if action:
        query = query.filter(models.AuditEvent.action == action)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(func.lower(models.AuditEvent.action).like(like))
    if from_date:
        query = query.filter(models.AuditEvent.created_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        query = query.filter(models.AuditEvent.created_at <= datetime.combine(to_date, datetime.max.time()))
    events = query.order_by(models.AuditEvent.created_at.desc()).limit(200).all()
    return [
        {
            "id": event.id,
            "actor_platform_user_id": event.actor_platform_user_id,
            "tenant_id": event.tenant_id,
            "action": event.action,
            "severity": event.severity,
            "payload_json": event.payload_json,
            "created_at": event.created_at,
        }
        for event in events
    ]


@router.post("/impersonation/start")
def start_impersonation(
    payload: ImpersonationStart,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN", "PLATFORM_SUPPORT")
    ),
):
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Reason obrigatorio")
    tenant = db.query(models.Tenant).filter(models.Tenant.id == payload.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant nao encontrado")
    session = models.ImpersonationSession(
        actor_platform_user_id=current_user.id,
        tenant_id=payload.tenant_id,
        reason=payload.reason,
        status="ACTIVE",
    )
    db.add(session)
    db.flush()
    token = create_access_token(
        {
            "tenant_id": payload.tenant_id,
            "is_impersonating": True,
            "session_id": session.id,
            "platform_user_id": current_user.id,
        },
        expires_delta=timedelta(minutes=30),
    )
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=payload.tenant_id,
        action="IMPERSONATION_START",
        severity="CRITICAL",
        payload={"session": _model_to_dict(session), "reason": payload.reason},
        request=request,
    )
    db.commit()
    return {
        "session_id": session.id,
        "impersonation_token": token,
        "tenant_id": payload.tenant_id,
        "link": f"/app?impersonation_token={token}",
    }


@router.post("/impersonation/end")
def end_impersonation(
    payload: ImpersonationEnd,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.PlatformUser = Depends(
        require_platform_roles("PLATFORM_OWNER", "PLATFORM_ADMIN", "PLATFORM_SUPPORT")
    ),
):
    session = (
        db.query(models.ImpersonationSession)
        .filter(models.ImpersonationSession.id == payload.session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada")
    before = _model_to_dict(session)
    session.status = "ENDED"
    session.ended_at = _now()
    _audit_event(
        db,
        actor_id=current_user.id,
        tenant_id=session.tenant_id,
        action="IMPERSONATION_END",
        severity="CRITICAL",
        payload={"before": before, "after": _model_to_dict(session)},
        request=request,
    )
    db.commit()
    return {"status": "ok"}
