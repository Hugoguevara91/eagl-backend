from datetime import datetime, timedelta
from io import BytesIO
import os
import hashlib
import uuid
import base64
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from PIL import Image
import qrcode

from app.core.authorization import (
    apply_scope_to_query,
    enforce_client_user_scope,
    require_scope_or_admin,
)
from app.core.security import (
    get_current_user,
    get_user_permissions,
    get_user_roles,
    require_permission,
)
from app.db import models
from app.db.session import get_db
from app.services.geocode import reverse_geocode
from app.services.os_pdf import render_os_pdf
from app.services.storage import delete_object, generate_signed_url, upload_bytes

router = APIRouter(tags=["Work Orders"])


class WorkOrderItemResponse(BaseModel):
    id: str
    question_text: str
    answer_type: str
    required: bool
    order_index: int
    answer_value: Optional[str] = None
    answer_numeric: Optional[int] = None
    note: Optional[str] = None
    attachments: list = Field(default_factory=list)

    class Config:
        from_attributes = True


class WorkOrderResponse(BaseModel):
    id: str
    code_human: Optional[str] = None
    title: str
    materials: Optional[str] = None
    conclusion: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    client_id: Optional[str] = None
    contract_id: Optional[str] = None
    site_id: Optional[str] = None
    requester_name: Optional[str] = None
    requester_phone: Optional[str] = None
    responsible_user_id: Optional[str] = None
    clienteNome: Optional[str] = None
    asset_id: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    sla_due_at: Optional[datetime] = None
    sla_breached: Optional[bool] = None
    assigned_user_id: Optional[str] = None
    assigned_team_id: Optional[str] = None
    completion_percent: Optional[int] = None
    checkin_data: Optional[dict] = None
    checkout_data: Optional[dict] = None
    totals: Optional[dict] = None
    signatures: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkOrderDetailResponse(WorkOrderResponse):
    description: Optional[str] = None
    items: List[WorkOrderItemResponse] = Field(default_factory=list)
    attachments: list = Field(default_factory=list)


class WorkOrderActivityResponse(BaseModel):
    id: str
    name: str
    status: str
    started_at_client: Optional[datetime] = None
    ended_at_client: Optional[datetime] = None
    started_at_server: Optional[datetime] = None
    ended_at_server: Optional[datetime] = None
    duration_ms_client: Optional[int] = None
    duration_ms_server: Optional[int] = None

    class Config:
        from_attributes = True


class WorkOrderItemCreate(BaseModel):
    question_text: str
    answer_type: str
    required: bool = False
    order_index: int = 0


class WorkOrderCreate(BaseModel):
    client_id: str
    contract_id: Optional[str] = None
    site_id: Optional[str] = None
    requester_name: Optional[str] = None
    requester_phone: Optional[str] = None
    responsible_user_id: Optional[str] = None
    code_human: Optional[str] = None
    asset_id: Optional[str] = None
    materials: Optional[str] = None
    conclusion: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    title: str
    description: Optional[str] = None
    status: Optional[str] = "aberta"
    items: Optional[List[WorkOrderItemCreate]] = None


class WorkOrderUpdate(BaseModel):
    client_id: Optional[str] = None
    contract_id: Optional[str] = None
    site_id: Optional[str] = None
    requester_name: Optional[str] = None
    requester_phone: Optional[str] = None
    responsible_user_id: Optional[str] = None
    code_human: Optional[str] = None
    asset_id: Optional[str] = None
    materials: Optional[str] = None
    conclusion: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    completion_percent: Optional[int] = None


class ActivityPayload(BaseModel):
    name: Optional[str] = None
    client_timestamp: Optional[datetime] = None
    offline_event_id: Optional[str] = None
    device_id: Optional[str] = None
    app_version: Optional[str] = None


class OfflineEventPayload(BaseModel):
    id: str
    type: str
    work_order_id: str
    client_timestamp: Optional[datetime] = None
    payload: dict = Field(default_factory=dict)


class SyncBatchPayload(BaseModel):
    batch_id: str
    events: list[OfflineEventPayload]


class PublicLinkCreate(BaseModel):
    allowed_view: str = "read_only"
    expires_in_hours: int | None = 24


class PublicLinkResponse(BaseModel):
    token: str
    public_url: str
    expires_at: Optional[datetime] = None
    allowed_view: str


def _safe_signed_url(object_name: Optional[str]) -> Optional[str]:
    if not object_name:
        return None
    try:
        return generate_signed_url(object_name)
    except Exception:
        return None


def _attachment_to_dict(att: models.WorkOrderAttachment) -> dict:
    return {
        "id": att.id,
        "file_name": att.file_name,
        "url": _safe_signed_url(att.url),
        "thumb_url": _safe_signed_url(att.thumb_url),
        "item_id": att.item_id,
        "question_id": att.question_id,
        "scope": att.scope,
        "mime": att.mime,
        "size": att.size,
        "created_at": att.created_at,
    }


def _build_object_name(work_order_id: str, scope: str, filename: str) -> str:
    safe_name = filename.replace(" ", "_")
    return f"work_orders/{work_order_id}/{scope}/{uuid.uuid4().hex}_{safe_name}"


def _make_thumbnail(data: bytes) -> bytes:
    image = Image.open(BytesIO(data))
    image = image.convert("RGB")
    image.thumbnail((600, 600))
    out = BytesIO()
    image.save(out, format="JPEG", quality=82)
    return out.getvalue()


def _to_response(os: models.WorkOrder) -> WorkOrderResponse:
    return WorkOrderResponse(
        id=os.id,
        code_human=os.code_human,
        title=os.title,
        materials=os.materials,
        conclusion=os.conclusion,
        type=os.type,
        status=os.status,
        priority=os.priority,
        client_id=os.client_id,
        contract_id=os.contract_id,
        site_id=os.site_id,
        requester_name=os.requester_name,
        requester_phone=os.requester_phone,
        responsible_user_id=os.responsible_user_id,
        clienteNome=os.client.name if os.client else None,
        asset_id=os.asset_id,
        scheduled_start=os.scheduled_start,
        scheduled_end=os.scheduled_end,
        sla_due_at=os.sla_due_at,
        sla_breached=os.sla_breached,
        assigned_user_id=os.assigned_user_id,
        assigned_team_id=os.assigned_team_id,
        completion_percent=os.completion_percent,
        checkin_data=os.checkin_data,
        checkout_data=os.checkout_data,
        totals=os.totals,
        signatures=os.signatures,
        created_at=os.created_at,
        updated_at=os.updated_at,
    )


def _to_detail(os: models.WorkOrder) -> WorkOrderDetailResponse:
    items = [
        WorkOrderItemResponse(
            id=item.id,
            question_text=item.question_text,
            answer_type=item.answer_type,
            required=item.required,
            order_index=item.order_index,
            answer_value=item.answer_value,
            answer_numeric=item.answer_numeric,
            note=item.note,
            attachments=[_attachment_to_dict(att) for att in item.attachments],
        )
        for item in sorted(os.items, key=lambda i: i.order_index)
    ]
    return WorkOrderDetailResponse(
        **_to_response(os).model_dump(),
        description=os.description,
        items=items,
        attachments=[],
    )


def _assert_os_scope(db: Session, user: models.User, os: models.WorkOrder) -> None:
    scope = require_scope_or_admin(db, user)
    enforce_client_user_scope(user, os.client_id)
    if scope["clients"] and os.client_id not in scope["clients"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="OS fora do escopo")


def _assert_assignment(db: Session, user: models.User, os: models.WorkOrder) -> None:
    roles = {role.nome for role in get_user_roles(db, user)}
    if "TECNICO" in roles and os.assigned_user_id and os.assigned_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OS não atribuída ao técnico.",
        )


def _audit_log(
    db: Session,
    request: Request,
    user: models.User,
    action: str,
    resource_id: str,
    payload: dict | None = None,
) -> None:
    log = models.AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action=action,
        resource_type="WORK_ORDER",
        resource_id=resource_id,
        payload_resumo=payload or {},
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(log)


def _can_close_os(db: Session, user: models.User, os: models.WorkOrder) -> None:
    roles = {role.nome for role in get_user_roles(db, user)}
    permissions = get_user_permissions(db, user)

    if os.status == "AUDITORIA" and not roles.intersection(
        {"SUPERVISOR", "COORDENADOR", "GERENTE", "TENANT_ADMIN"}
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas supervisao pode fechar OS em auditoria.",
        )

    if os.priority == "critica" and "os.close.critical" not in permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissao necessária para fechar OS critica.",
        )

    missing_required = [
        item.question_text
        for item in os.items
        if item.required and not (item.answer_value or item.answer_numeric)
    ]
    if missing_required:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Checklist incompleto. Preencha os itens obrigatorios.",
        )

    if not os.checkin_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Check-in obrigatorio antes de fechar a OS.",
        )

    if not os.checkout_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Check-out obrigatorio antes de fechar a OS.",
        )

    pending_activities = [
        activity.name for activity in os.activities if activity.status != "FINALIZADA"
    ]
    if pending_activities:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Atividades pendentes. Finalize todas as atividades antes de fechar a OS.",
        )


@router.get("/work-orders")
def list_work_orders(
    status_filter: Optional[str] = None,
    type: Optional[str] = None,
    priority: Optional[str] = None,
    client_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: models.User = Depends(require_permission("os.view")),
    db: Session = Depends(get_db),
):
    scope = require_scope_or_admin(db, current_user)
    query = db.query(models.WorkOrder).filter(models.WorkOrder.tenant_id == current_user.tenant_id)
    query = apply_scope_to_query(query, scope, client_field=models.WorkOrder.client_id)
    if status_filter:
        query = query.filter(models.WorkOrder.status == status_filter)
    if type:
        query = query.filter(models.WorkOrder.type == type)
    if priority:
        query = query.filter(models.WorkOrder.priority == priority)
    if client_id:
        query = query.filter(models.WorkOrder.client_id == client_id)

    total = query.count()
    items = (
        query.order_by(models.WorkOrder.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"items": [_to_response(os) for os in items], "total": total}


@router.post("/work-orders", status_code=status.HTTP_201_CREATED)
def create_work_order(
    payload: WorkOrderCreate,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    scope = require_scope_or_admin(db, current_user)
    enforce_client_user_scope(current_user, payload.client_id)
    if scope["clients"] and payload.client_id not in scope["clients"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cliente fora do escopo")
    new_os = models.WorkOrder(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        code_human=payload.code_human,
        client_id=payload.client_id,
        contract_id=payload.contract_id,
        site_id=payload.site_id,
        requester_name=payload.requester_name,
        requester_phone=payload.requester_phone,
        responsible_user_id=payload.responsible_user_id,
        asset_id=payload.asset_id,
        materials=payload.materials,
        conclusion=payload.conclusion,
        type=payload.type,
        priority=payload.priority,
        scheduled_start=payload.scheduled_start,
        scheduled_end=payload.scheduled_end,
        title=payload.title,
        description=payload.description,
        status=payload.status or "aberta",
        sla_breached=False,
        completion_percent=0,
    )
    db.add(new_os)
    if payload.items:
        for item in payload.items:
            db.add(
                models.WorkOrderItem(
                    id=str(uuid.uuid4()),
                    work_order_id=new_os.id,
                    question_text=item.question_text,
                    answer_type=item.answer_type,
                    required=item.required,
                    order_index=item.order_index,
                )
            )
    db.commit()
    db.refresh(new_os)
    return _to_detail(new_os)


@router.get("/work-orders/{work_order_id}")
def get_work_order(
    work_order_id: str,
    current_user: models.User = Depends(require_permission("os.view")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS nao encontrada")
    _assert_os_scope(db, current_user, os)
    return {"os": _to_detail(os)}


@router.post("/work-orders/{work_order_id}/public-link", response_model=PublicLinkResponse)
def create_public_link(
    work_order_id: str,
    payload: PublicLinkCreate,
    request: Request,
    current_user: models.User = Depends(require_permission("os.share")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS nao encontrada")
    _assert_os_scope(db, current_user, os)

    token = uuid.uuid4().hex
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = None
    if payload.expires_in_hours:
        expires_at = datetime.utcnow() + timedelta(hours=payload.expires_in_hours)

    link = models.PublicLink(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        resource_type="WORK_ORDER",
        resource_id=os.id,
        token_hash=token_hash,
        expires_at=expires_at,
        allowed_view=payload.allowed_view or "read_only",
        created_by=current_user.id,
    )
    db.add(link)
    _audit_log(db, request, current_user, "OS_SHARE", os.id, {"link_id": link.id})
    db.commit()
    return {
        "token": token,
        "public_url": f"/public/os/{token}",
        "expires_at": expires_at,
        "allowed_view": link.allowed_view,
    }


@router.get("/public/work-orders/{token}")
def get_public_work_order(
    token: str,
    db: Session = Depends(get_db),
):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    link = (
        db.query(models.PublicLink)
        .filter(models.PublicLink.token_hash == token_hash)
        .first()
    )
    if not link or link.revoked_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link invalido")
    if link.expires_at and link.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link expirado")
    if link.resource_type != "WORK_ORDER":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link invalido")
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == link.resource_id, models.WorkOrder.tenant_id == link.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS nao encontrada")
    return {"os": _to_detail(os), "allowed_view": link.allowed_view}


@router.get("/work-orders/{work_order_id}/activities")
def list_work_order_activities(
    work_order_id: str,
    current_user: models.User = Depends(require_permission("os.view")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS nao encontrada")
    _assert_os_scope(db, current_user, os)
    activities = (
        db.query(models.WorkOrderActivity)
        .filter(
            models.WorkOrderActivity.work_order_id == work_order_id,
            models.WorkOrderActivity.tenant_id == current_user.tenant_id,
        )
        .order_by(models.WorkOrderActivity.name.asc())
        .all()
    )
    return {"items": [WorkOrderActivityResponse.model_validate(item).model_dump() for item in activities]}


@router.put("/work-orders/{work_order_id}")
@router.patch("/work-orders/{work_order_id}")
def update_work_order(
    work_order_id: str,
    payload: WorkOrderUpdate,
    request: Request,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS não encontrada")
    _assert_os_scope(db, current_user, os)

    updates = payload.model_dump(exclude_unset=True)
    if updates.get("status") in {"concluida", "fechada"}:
        _can_close_os(db, current_user, os)
    for field, value in updates.items():
        setattr(os, field, value)
    db.commit()
    db.refresh(os)
    if updates.get("status") in {"concluida", "fechada"}:
        _audit_log(db, request, current_user, "OS_CLOSE", os.id, {"status": os.status})
    return _to_detail(os)


class LocationPayload(BaseModel):
    client_timestamp: Optional[datetime] = None
    lat: Optional[str] = None
    lng: Optional[str] = None
    accuracy_m: Optional[int] = None
    altitude: Optional[int] = None
    heading: Optional[int] = None
    speed: Optional[int] = None
    provider: Optional[str] = None
    is_mock_location: Optional[bool] = None
    device_id: Optional[str] = None
    app_version: Optional[str] = None
    offline_event_id: Optional[str] = None
    reason: Optional[str] = None
    address: Optional[dict] = None


def _create_event(
    db: Session,
    os: models.WorkOrder,
    user: models.User,
    event_type: str,
    payload: LocationPayload,
) -> models.WorkOrderEvent:
    event = models.WorkOrderEvent(
        id=str(uuid.uuid4()),
        tenant_id=os.tenant_id,
        work_order_id=os.id,
        user_id=user.id,
        type=event_type,
        client_timestamp=payload.client_timestamp,
        lat=payload.lat,
        lng=payload.lng,
        accuracy_m=payload.accuracy_m,
        altitude=payload.altitude,
        heading=payload.heading,
        speed=payload.speed,
        provider=payload.provider,
        is_mock_location=payload.is_mock_location,
        device_id=payload.device_id,
        app_version=payload.app_version,
        offline_event_id=payload.offline_event_id,
        payload_resumo={"reason": payload.reason} if payload.reason else {},
    )
    db.add(event)
    return event


def _build_check_data(payload: LocationPayload, geo: Optional[dict], event_id: str) -> dict:
    address = None
    address_status = "PENDING" if payload.lat and payload.lng else "MISSING"
    address_error = None
    if geo:
        if geo.get("status") == "OK":
            address = geo.get("address") or {}
            address_status = "OK"
        else:
            address_error = geo.get("error") or "UNKNOWN"
    elif payload.address:
        address = payload.address
        address_status = "OK"
    return {
        "event_id": event_id,
        "timestamp": payload.client_timestamp.isoformat() if payload.client_timestamp else None,
        "lat": payload.lat,
        "lng": payload.lng,
        "accuracy": payload.accuracy_m,
        "provider": payload.provider,
        "address": address or {},
        "address_status": address_status,
        "address_error": address_error,
        "reason": payload.reason,
    }


def _get_or_create_activity(
    db: Session,
    os: models.WorkOrder,
    activity_id: str,
    name: str | None,
    user: models.User,
) -> models.WorkOrderActivity:
    activity = (
        db.query(models.WorkOrderActivity)
        .filter(
            models.WorkOrderActivity.id == activity_id,
            models.WorkOrderActivity.work_order_id == os.id,
            models.WorkOrderActivity.tenant_id == os.tenant_id,
        )
        .first()
    )
    if activity:
        return activity
    activity = models.WorkOrderActivity(
        id=activity_id,
        tenant_id=os.tenant_id,
        work_order_id=os.id,
        name=name or "Atividade",
        status="PENDENTE",
        created_by=user.id,
    )
    db.add(activity)
    return activity


def _register_activity_event(
    db: Session,
    os: models.WorkOrder,
    activity: models.WorkOrderActivity,
    user: models.User,
    event_type: str,
    payload: ActivityPayload,
):
    event = models.WorkOrderEvent(
        id=str(uuid.uuid4()),
        tenant_id=os.tenant_id,
        work_order_id=os.id,
        user_id=user.id,
        type=event_type,
        client_timestamp=payload.client_timestamp,
        device_id=payload.device_id,
        app_version=payload.app_version,
        offline_event_id=payload.offline_event_id,
        payload_resumo={"activity_id": activity.id, "activity_name": activity.name},
    )
    db.add(event)
    return event


@router.post("/work-orders/{work_order_id}/checkin")
def checkin_work_order(
    work_order_id: str,
    payload: LocationPayload,
    request: Request,
    current_user: models.User = Depends(require_permission("os.checkin")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS não encontrada")
    _assert_os_scope(db, current_user, os)
    _assert_assignment(db, current_user, os)
    if payload.accuracy_m and payload.accuracy_m > 100 and not payload.reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Precisao baixa. Informe justificativa.",
        )
    geo = None
    if payload.lat and payload.lng:
        try:
            geo = reverse_geocode(float(payload.lat), float(payload.lng))
        except Exception:
            geo = {"status": "ERROR", "error": "EXCEPTION"}
    event = _create_event(db, os, current_user, "CHECKIN", payload)
    os.checkin_data = _build_check_data(payload, geo, event.id)
    _audit_log(db, request, current_user, "OS_CHECKIN", os.id, {"event_id": event.id})
    db.commit()
    db.refresh(event)
    return {"status": "ok", "event_id": event.id}


@router.post("/work-orders/{work_order_id}/checkout")
def checkout_work_order(
    work_order_id: str,
    payload: LocationPayload,
    request: Request,
    current_user: models.User = Depends(require_permission("os.checkout")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS nao encontrada")
    _assert_os_scope(db, current_user, os)
    _assert_assignment(db, current_user, os)
    if payload.accuracy_m and payload.accuracy_m > 100 and not payload.reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Precisao baixa. Informe justificativa.",
        )
    geo = None
    if payload.lat and payload.lng:
        try:
            geo = reverse_geocode(float(payload.lat), float(payload.lng))
        except Exception:
            geo = {"status": "ERROR", "error": "EXCEPTION"}
    event = _create_event(db, os, current_user, "CHECKOUT", payload)
    os.checkout_data = _build_check_data(payload, geo, event.id)
    _audit_log(db, request, current_user, "OS_CHECKOUT", os.id, {"event_id": event.id})
    db.commit()
    db.refresh(event)
    return {"status": "ok", "event_id": event.id}


@router.post("/work-orders/geocode/retry")
def retry_pending_geocodes(
    limit: int = 50,
    request: Request = None,
    current_user: models.User = Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
):
    queue = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.tenant_id == current_user.tenant_id)
        .filter(
            (models.WorkOrder.checkin_data.isnot(None)) | (models.WorkOrder.checkout_data.isnot(None))
        )
        .limit(max(1, min(limit, 200)))
        .all()
    )
    updated = 0
    for os in queue:
        for field_name in ("checkin_data", "checkout_data"):
            payload = getattr(os, field_name) or {}
            if payload.get("address_status") != "PENDING":
                continue
            lat = payload.get("lat")
            lng = payload.get("lng")
            if not lat or not lng:
                continue
            geo = None
            try:
                geo = reverse_geocode(float(lat), float(lng))
            except Exception:
                geo = {"status": "ERROR", "error": "EXCEPTION"}
            if geo and geo.get("status") == "OK":
                payload["address"] = geo.get("address") or {}
                payload["address_status"] = "OK"
                payload["address_error"] = None
                setattr(os, field_name, payload)
                updated += 1
    if request is not None:
        _audit_log(db, request, current_user, "OS_GEOCODE_RETRY", current_user.id, {"updated": updated})
    db.commit()
    return {"status": "ok", "updated": updated}


@router.post("/work-orders/{work_order_id}/activities/{activity_id}/start")
def start_activity(
    work_order_id: str,
    activity_id: str,
    payload: ActivityPayload,
    request: Request,
    current_user: models.User = Depends(require_permission("os.activity")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS não encontrada")
    _assert_os_scope(db, current_user, os)
    _assert_assignment(db, current_user, os)
    activity = _get_or_create_activity(db, os, activity_id, payload.name, current_user)
    activity.status = "EM_ANDAMENTO"
    activity.started_at_client = payload.client_timestamp
    activity.started_at_server = datetime.utcnow()
    activity.updated_by = current_user.id
    event = _register_activity_event(db, os, activity, current_user, "ACTIVITY_START", payload)
    _audit_log(db, request, current_user, "OS_ACTIVITY_START", os.id, {"activity_id": activity.id})
    db.commit()
    return {"status": "ok", "event_id": event.id}


@router.post("/work-orders/{work_order_id}/activities/{activity_id}/pause-start")
def pause_activity(
    work_order_id: str,
    activity_id: str,
    payload: ActivityPayload,
    request: Request,
    current_user: models.User = Depends(require_permission("os.activity")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS não encontrada")
    _assert_os_scope(db, current_user, os)
    _assert_assignment(db, current_user, os)
    activity = _get_or_create_activity(db, os, activity_id, payload.name, current_user)
    activity.status = "PAUSADA"
    activity.updated_by = current_user.id
    event = _register_activity_event(db, os, activity, current_user, "PAUSE_START", payload)
    _audit_log(db, request, current_user, "OS_ACTIVITY_PAUSE_START", os.id, {"activity_id": activity.id})
    db.commit()
    return {"status": "ok", "event_id": event.id}


@router.post("/work-orders/{work_order_id}/activities/{activity_id}/pause-end")
def resume_activity(
    work_order_id: str,
    activity_id: str,
    payload: ActivityPayload,
    request: Request,
    current_user: models.User = Depends(require_permission("os.activity")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS não encontrada")
    _assert_os_scope(db, current_user, os)
    _assert_assignment(db, current_user, os)
    activity = _get_or_create_activity(db, os, activity_id, payload.name, current_user)
    activity.status = "EM_ANDAMENTO"
    activity.updated_by = current_user.id
    event = _register_activity_event(db, os, activity, current_user, "PAUSE_END", payload)
    _audit_log(db, request, current_user, "OS_ACTIVITY_PAUSE_END", os.id, {"activity_id": activity.id})
    db.commit()
    return {"status": "ok", "event_id": event.id}


@router.post("/work-orders/{work_order_id}/activities/{activity_id}/end")
def end_activity(
    work_order_id: str,
    activity_id: str,
    payload: ActivityPayload,
    request: Request,
    current_user: models.User = Depends(require_permission("os.activity")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS não encontrada")
    _assert_os_scope(db, current_user, os)
    _assert_assignment(db, current_user, os)
    activity = _get_or_create_activity(db, os, activity_id, payload.name, current_user)
    activity.status = "FINALIZADA"
    activity.ended_at_client = payload.client_timestamp
    activity.ended_at_server = datetime.utcnow()
    if activity.started_at_client and activity.ended_at_client:
        activity.duration_ms_client = int(
            (activity.ended_at_client - activity.started_at_client).total_seconds() * 1000
        )
    if activity.started_at_server and activity.ended_at_server:
        activity.duration_ms_server = int(
            (activity.ended_at_server - activity.started_at_server).total_seconds() * 1000
        )
    activity.updated_by = current_user.id
    event = _register_activity_event(db, os, activity, current_user, "ACTIVITY_END", payload)
    _audit_log(db, request, current_user, "OS_ACTIVITY_END", os.id, {"activity_id": activity.id})
    db.commit()
    return {"status": "ok", "event_id": event.id}


@router.delete("/work-orders/{work_order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work_order(
    work_order_id: str,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS não encontrada")
    _assert_os_scope(db, current_user, os)
    db.delete(os)
    db.commit()
    return None


@router.patch("/work-orders/{work_order_id}/items/{item_id}")
def update_work_order_item(
    work_order_id: str,
    item_id: str,
    body: dict,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS não encontrada")
    _assert_os_scope(db, current_user, os)
    item = (
        db.query(models.WorkOrderItem)
        .filter(models.WorkOrderItem.id == item_id, models.WorkOrderItem.work_order_id == work_order_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado")
    if "answer_value" in body:
        item.answer_value = body.get("answer_value")
    if "answer_numeric" in body:
        item.answer_numeric = body.get("answer_numeric")
    db.commit()
    db.refresh(item)
    return {"status": "ok"}


@router.post("/work-orders/{work_order_id}/items/{item_id}/attachments", status_code=status.HTTP_201_CREATED)
def upload_attachment(
    work_order_id: str,
    item_id: str,
    file: UploadFile,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS não encontrada")
    _assert_os_scope(db, current_user, os)
    item = (
        db.query(models.WorkOrderItem)
        .filter(models.WorkOrderItem.id == item_id, models.WorkOrderItem.work_order_id == work_order_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado")

    data = file.file.read()
    object_name = _build_object_name(work_order_id, "QUESTION", file.filename or "anexo")
    upload_bytes(data, object_name, content_type=file.content_type)
    thumb_name = None
    if file.content_type and file.content_type.startswith("image/"):
        thumb_data = _make_thumbnail(data)
        thumb_name = _build_object_name(work_order_id, "QUESTION_THUMB", file.filename or "thumb.jpg")
        upload_bytes(thumb_data, thumb_name, content_type="image/jpeg")

    attachment = models.WorkOrderAttachment(
        id=str(uuid.uuid4()),
        work_order_id=work_order_id,
        item_id=item_id,
        question_id=item_id,
        scope="QUESTION",
        file_name=file.filename or "anexo",
        mime=file.content_type,
        size=len(data),
        url=object_name,
        thumb_url=thumb_name,
        created_by=current_user.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return _attachment_to_dict(attachment)


@router.post("/work-orders/{work_order_id}/attachments", status_code=status.HTTP_201_CREATED)
def upload_work_order_attachment(
    work_order_id: str,
    file: UploadFile,
    scope: str = Form(...),
    question_id: Optional[str] = Form(None),
    item_id: Optional[str] = Form(None),
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS nao encontrada")
    _assert_os_scope(db, current_user, os)
    normalized_scope = scope.upper()
    if normalized_scope not in {"QUESTION", "CHECKIN", "CHECKOUT", "SIGNATURE"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Scope invalido")
    attachment_item_id = item_id or question_id
    if normalized_scope == "QUESTION" and not attachment_item_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="item_id e obrigatorio")

    data = file.file.read()
    object_name = _build_object_name(work_order_id, normalized_scope, file.filename or "anexo")
    upload_bytes(data, object_name, content_type=file.content_type)
    thumb_name = None
    if file.content_type and file.content_type.startswith("image/"):
        thumb_data = _make_thumbnail(data)
        thumb_name = _build_object_name(work_order_id, f"{normalized_scope}_THUMB", file.filename or "thumb.jpg")
        upload_bytes(thumb_data, thumb_name, content_type="image/jpeg")

    attachment = models.WorkOrderAttachment(
        id=str(uuid.uuid4()),
        work_order_id=work_order_id,
        item_id=attachment_item_id,
        question_id=question_id,
        scope=normalized_scope,
        file_name=file.filename or "anexo",
        mime=file.content_type,
        size=len(data),
        url=object_name,
        thumb_url=thumb_name,
        created_by=current_user.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return _attachment_to_dict(attachment)


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: str,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    attachment = (
        db.query(models.WorkOrderAttachment)
        .join(models.WorkOrder, models.WorkOrder.id == models.WorkOrderAttachment.work_order_id)
        .filter(
            models.WorkOrderAttachment.id == attachment_id,
            models.WorkOrder.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anexo não encontrado")
    if attachment.url:
        delete_object(attachment.url)
    if attachment.thumb_url:
        delete_object(attachment.thumb_url)
    db.delete(attachment)
    db.commit()
    return None


@router.post("/work-orders/{work_order_id}/signatures")
def upload_signature(
    work_order_id: str,
    role: str = Form(...),
    name: Optional[str] = Form(None),
    file: Optional[UploadFile] = None,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS nao encontrada")
    _assert_os_scope(db, current_user, os)
    role_key = role.lower()
    if role_key not in {"tecnico", "cliente"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Role invalida")

    signatures = os.signatures or {"tecnico": {}, "cliente": {}}
    if name:
        signatures[role_key]["name"] = name

    if file:
        data = file.file.read()
        object_name = _build_object_name(work_order_id, "SIGNATURE", file.filename or "assinatura.png")
        upload_bytes(data, object_name, content_type=file.content_type)
        signatures[role_key]["image_object"] = object_name

    os.signatures = signatures
    db.commit()
    return {"status": "ok", "signatures": signatures}


@router.get("/work-orders/{work_order_id}/print-data")
def get_print_data(
    work_order_id: str,
    current_user: models.User = Depends(require_permission("os.view")),
    db: Session = Depends(get_db),
):
    os = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.id == work_order_id, models.WorkOrder.tenant_id == current_user.tenant_id)
        .first()
    )
    if not os:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OS não encontrada")
    _assert_os_scope(db, current_user, os)

    def _backfill_check_address(field_name: str) -> dict:
        payload = getattr(os, field_name) or {}
        if not payload:
            return {}
        if payload.get("address_status") == "OK" and payload.get("address"):
            return payload
        lat = payload.get("lat")
        lng = payload.get("lng")
        if not lat or not lng:
            return payload
        geo = None
        try:
            geo = reverse_geocode(float(lat), float(lng))
        except Exception:
            geo = {"status": "ERROR", "error": "EXCEPTION"}
        if geo and geo.get("status") == "OK":
            payload["address"] = geo.get("address") or {}
            payload["address_status"] = "OK"
            payload["address_error"] = None
        else:
            payload["address"] = payload.get("address") or {}
            payload["address_status"] = payload.get("address_status") or "PENDING"
            payload["address_error"] = geo.get("error") if geo else payload.get("address_error")
        setattr(os, field_name, payload)
        return payload

    updated = False
    if os.checkin_data:
        before = dict(os.checkin_data)
        _backfill_check_address("checkin_data")
        updated = updated or before != (os.checkin_data or {})
    if os.checkout_data:
        before = dict(os.checkout_data)
        _backfill_check_address("checkout_data")
        updated = updated or before != (os.checkout_data or {})
    if updated:
        db.commit()


    attachments = (
        db.query(models.WorkOrderAttachment)
        .filter(models.WorkOrderAttachment.work_order_id == work_order_id)
        .all()
    )
    attachment_payloads = [_attachment_to_dict(att) for att in attachments]
    activities = []
    for activity in sorted(os.activities, key=lambda a: a.name or ""):
        duration = activity.duration_ms_server or activity.duration_ms_client
        activities.append(
            {
                "id": activity.id,
                "name": activity.name,
                "status": activity.status,
                "started_at": activity.started_at_server or activity.started_at_client,
                "ended_at": activity.ended_at_server or activity.ended_at_client,
                "duration_ms": duration,
            }
        )
    item_photo_map: dict[str, list[str]] = {}
    checkin_photos: list[str] = []
    checkout_photos: list[str] = []
    for att in attachment_payloads:
        if att["scope"] == "CHECKIN" and att["url"]:
            checkin_photos.append(att["url"])
        elif att["scope"] == "CHECKOUT" and att["url"]:
            checkout_photos.append(att["url"])
        elif att["scope"] == "QUESTION" and att["item_id"] and att["url"]:
            item_photo_map.setdefault(att["item_id"], []).append(att["url"])

    answers = []
    for item in sorted(os.items, key=lambda i: i.order_index):
        answer = item.answer_value or (str(item.answer_numeric) if item.answer_numeric is not None else None)
        answers.append(
            {
                "id": item.id,
                "question_text": item.question_text,
                "answer_type": item.answer_type,
                "required": item.required,
                "answer": answer,
                "note": item.note,
                "photos": item_photo_map.get(item.id, []),
            }
        )

    client_payload = {}
    if os.client:
        client_payload = {
            "id": os.client.id,
            "name": os.client.name,
            "document": os.client.document,
            "address": os.client.address,
            "status": os.client.status,
        }
    site_payload = {}
    if os.site:
        site_payload = {
            "id": os.site.id,
            "name": os.site.name,
            "code": os.site.code,
            "address": os.site.address,
            "status": os.site.status,
        }

    asset_payload = {}
    if os.asset_id:
        asset = (
            db.query(models.Asset)
            .filter(models.Asset.id == os.asset_id, models.Asset.tenant_id == current_user.tenant_id)
            .first()
        )
        if asset:
            asset_payload = {
                "id": asset.id,
                "name": asset.name,
                "tag": asset.tag,
                "asset_type": asset.asset_type,
                "status": asset.status,
            }

    signatures = os.signatures or {"tecnico": {}, "cliente": {}}
    for key in ("tecnico", "cliente"):
        img_obj = signatures.get(key, {}).get("image_object")
        if img_obj:
            signatures[key]["image_url"] = generate_signed_url(img_obj)

    detail_payload = _to_detail(os).model_dump()
    detail_payload["signatures"] = signatures

    return {
        "os": detail_payload,
        "client": client_payload,
        "site": site_payload,
        "asset": asset_payload,
        "answers": answers,
        "attachments": attachment_payloads,
        "activities": activities,
        "checkin": os.checkin_data or {},
        "checkout": os.checkout_data or {},
        "checkin_photos": checkin_photos,
        "checkout_photos": checkout_photos,
    }


@router.post("/work-orders/{work_order_id}/generate-pdf")
def generate_pdf(
    work_order_id: str,
    current_user: models.User = Depends(require_permission("os.view")),
    db: Session = Depends(get_db),
):
    data = get_print_data(work_order_id, current_user=current_user, db=db)
    checkin = data.get("checkin") or {}
    checkout = data.get("checkout") or {}
    answers = data.get("answers") or []
    attachments = data.get("attachments") or []
    activities = data.get("activities") or []
    for activity in activities:
        duration_ms = activity.get("duration_ms") or 0
        total_seconds = int(duration_ms / 1000) if duration_ms else 0
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        activity["duration_text"] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    evidence_sections = []
    for item in answers:
        photos = item.get("photos") or []
        if len(photos) > 3:
            evidence_sections.append({"title": item.get("question_text"), "photos": photos[3:]})
            item["photos"] = photos[:3]

    token = uuid.uuid4().hex
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    link = models.PublicLink(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        resource_type="WORK_ORDER",
        resource_id=work_order_id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(hours=168),
        allowed_view="read_only",
        created_by=current_user.id,
    )
    db.add(link)
    db.commit()
    public_url = f"/public/os/{token}"

    base_url = os.getenv("PUBLIC_APP_BASE_URL")
    qr_target = f"{base_url}{public_url}" if base_url and public_url else None
    qr_data_url = None
    if qr_target:
        qr = qrcode.make(qr_target)
        buf = BytesIO()
        qr.save(buf, format="PNG")
        qr_data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    pdf_payload = {
        "logo_url": os.getenv("OS_PDF_LOGO_URL"),
        "now": datetime.utcnow().strftime("%d/%m/%Y %H:%M"),
        "os": data.get("os", {}).get("id") and data.get("os", {}) or {},
        "client": data.get("client") or {},
        "site": data.get("site") or {},
        "asset": data.get("asset") or {},
        "checkin": {**checkin, "photos": data.get("checkin_photos") or []},
        "checkout": {**checkout, "photos": data.get("checkout_photos") or []},
        "answers": answers,
        "activities": activities,
        "materials": (data.get("os") or {}).get("materials"),
        "conclusion": (data.get("os") or {}).get("conclusion"),
        "signatures": (data.get("os") or {}).get("signatures") or {"tecnico": {}, "cliente": {}},
        "evidence": evidence_sections,
        "qr_data_url": qr_data_url,
    }
    pdf_bytes = render_os_pdf(pdf_payload)
    object_name = _build_object_name(work_order_id, "PDF", f"os-{work_order_id}.pdf")
    upload_bytes(pdf_bytes, object_name, content_type="application/pdf")
    return {"url": generate_signed_url(object_name), "object": object_name}


@router.post("/sync/events")
def sync_events(
    payload: SyncBatchPayload,
    request: Request,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    created = 0
    for event in payload.events:
        exists = (
            db.query(models.WorkOrderEvent)
            .filter(
                models.WorkOrderEvent.offline_event_id == event.id,
                models.WorkOrderEvent.tenant_id == current_user.tenant_id,
            )
            .first()
        )
        if exists:
            continue
        os = (
            db.query(models.WorkOrder)
            .filter(
                models.WorkOrder.id == event.work_order_id,
                models.WorkOrder.tenant_id == current_user.tenant_id,
            )
            .first()
        )
        if not os:
            continue
        _assert_os_scope(db, current_user, os)
        if event.type in {"ACTIVITY_START", "PAUSE_START", "PAUSE_END", "ACTIVITY_END"}:
            activity_id = event.payload.get("activity_id")
            activity_name = event.payload.get("activity_name")
            if activity_id:
                activity = _get_or_create_activity(db, os, activity_id, activity_name, current_user)
                if event.type == "ACTIVITY_START":
                    activity.status = "EM_ANDAMENTO"
                    activity.started_at_client = event.client_timestamp
                    activity.started_at_server = datetime.utcnow()
                elif event.type == "PAUSE_START":
                    activity.status = "PAUSADA"
                elif event.type == "PAUSE_END":
                    activity.status = "EM_ANDAMENTO"
                elif event.type == "ACTIVITY_END":
                    activity.status = "FINALIZADA"
                    activity.ended_at_client = event.client_timestamp
                    activity.ended_at_server = datetime.utcnow()
                    if activity.started_at_client and activity.ended_at_client:
                        activity.duration_ms_client = int(
                            (activity.ended_at_client - activity.started_at_client).total_seconds() * 1000
                        )
                    if activity.started_at_server and activity.ended_at_server:
                        activity.duration_ms_server = int(
                            (activity.ended_at_server - activity.started_at_server).total_seconds() * 1000
                        )
                activity.updated_by = current_user.id
        if event.type in {"CHECKIN", "CHECKOUT"} and event.payload:
            payload = event.payload
            geo = None
            lat = payload.get("lat")
            lng = payload.get("lng")
            if lat and lng:
                try:
                    geo = reverse_geocode(float(lat), float(lng))
                except Exception:
                    geo = {"status": "ERROR", "error": "EXCEPTION"}
            if geo and geo.get("status") == "OK":
                payload["address"] = geo.get("address") or {}
                payload["address_status"] = "OK"
                payload["address_error"] = None
            else:
                payload["address"] = payload.get("address") or {}
                payload["address_status"] = "PENDING" if lat and lng else payload.get("address_status") or "MISSING"
                payload["address_error"] = geo.get("error") if geo else payload.get("address_error")
            if event.type == "CHECKIN":
                os.checkin_data = payload
            else:
                os.checkout_data = payload
        db.add(
            models.WorkOrderEvent(
                id=str(uuid.uuid4()),
                tenant_id=current_user.tenant_id,
                work_order_id=event.work_order_id,
                user_id=current_user.id,
                type=event.type,
                client_timestamp=event.client_timestamp,
                server_received_at=datetime.utcnow(),
                offline_event_id=event.id,
                sync_batch_id=payload.batch_id,
                payload_resumo=event.payload,
            )
        )
        created += 1
    _audit_log(db, request, current_user, "SYNC_EVENTS", current_user.id, {"created": created})
    db.commit()
    return {"status": "ok", "created": created}
