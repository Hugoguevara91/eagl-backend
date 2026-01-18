import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.db import models
from app.services.storage import generate_signed_url, upload_bytes
from app.solver.openai_client import request_solver_result
from app.solver.schemas import SolverResult, TestRequirement


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
OPENAI_MODEL_DEFAULT = "gpt-4o-mini"


def _build_object_name(session_id: str, kind: str, filename: str) -> str:
    safe = filename.replace(" ", "_")
    return f"solver/{session_id}/{kind}/{uuid.uuid4().hex}_{safe}"


def _load_result(payload: Optional[dict]) -> Optional[SolverResult]:
    if not payload:
        return None
    return SolverResult.model_validate(payload)


def _build_system_prompt() -> str:
    return (
        "Voce e o EAGL Solver (solucionador guiado de problemas tecnicos) para manutencao. "
        "Responda sempre em pt-BR, frases curtas, linguagem simples para iniciante. "
        "Nao invente dados. Se algo nao foi informado, deixe claro. "
        "Sempre devolva um JSON valido seguindo o schema exigido. "
        "O EAGL Solver orienta a tomada de decisao. Nao assumir causa unica quando faltarem informacoes. "
        "tests_required deve ter entre 3 e 8 itens. "
        "notes_for_work_order deve conter service_done, cause, solution, observations. "
        "Para VRF / VRV, sugira testes simples e indique escalonamento quando houver parametro interno."
    )


def _build_quick_user_prompt(
    area: str,
    equipment_type: str,
    brand: str,
    other_equipment: Optional[str],
    other_brand: Optional[str],
    model_text: Optional[str],
    model_unknown: bool,
    error_code_text: Optional[str],
    error_code_unknown: bool,
    short_problem_text: str,
) -> str:
    model = "Nao sei" if model_unknown else (model_text or "Nao informado")
    error_code = "Nao sei" if error_code_unknown else (error_code_text or "Nao informado")
    other_eq = other_equipment or "Nao informado"
    other_br = other_brand or "Nao informado"
    return (
        "Dados do equipamento:\n"
        f"- Area: {area}\n"
        f"- Tipo: {equipment_type}\n"
        f"- Marca: {brand}\n"
        f"- Outro tipo: {other_eq}\n"
        f"- Outra marca: {other_br}\n"
        f"- Modelo: {model}\n"
        f"- Codigo de erro: {error_code}\n"
        f"- Problema relatado: {short_problem_text}\n\n"
        "Responda com JSON seguindo o schema."
    )


def _build_advanced_user_prompt(
    quick_result: SolverResult,
    test_inputs: list[models.ProblemTestInput],
    short_problem_text: str,
) -> str:
    tests_text = "\n".join(
        f"- {item.label}: {item.value}{(' ' + item.unit) if item.unit else ''}"
        for item in test_inputs
    )
    return (
        "Refine o diagnostico com os testes abaixo.\n"
        f"Problema relatado: {short_problem_text}\n\n"
        "Resultado inicial:\n"
        f"- Resumo: {quick_result.summary}\n"
        f"- Causa provavel: {quick_result.probable_root_cause}\n\n"
        "Resultados de testes:\n"
        f"{tests_text}\n\n"
        "Responda com JSON seguindo o schema."
    )


def _select_attachments(attachments: list[models.ProblemAttachment]) -> list[models.ProblemAttachment]:
    priority = ["brand", "model", "error_code", "other"]
    selected: list[models.ProblemAttachment] = []
    by_kind = {kind: [] for kind in priority}
    for att in attachments:
        by_kind.setdefault(att.kind, []).append(att)
    for kind in priority:
        for att in sorted(by_kind.get(kind, []), key=lambda a: a.created_at or datetime.utcnow(), reverse=True):
            if len(selected) >= 2:
                break
            selected.append(att)
        if len(selected) >= 2:
            break
    if len(selected) < 2:
        remaining = [att for att in attachments if att not in selected]
        remaining_sorted = sorted(remaining, key=lambda a: a.created_at or datetime.utcnow(), reverse=True)
        selected.extend(remaining_sorted[: 2 - len(selected)])
    return selected[:2]


def list_catalog_names(db: Session, session: models.ProblemSession) -> dict:
    area = db.query(models.CatalogArea).filter(models.CatalogArea.id == session.area_id).first()
    equipment = (
        db.query(models.CatalogEquipmentType)
        .filter(models.CatalogEquipmentType.id == session.equipment_type_id)
        .first()
    )
    brand = db.query(models.CatalogBrand).filter(models.CatalogBrand.id == session.brand_id).first()
    client_name = session.client_name_snapshot
    if not client_name and session.client_id:
        client = (
            db.query(models.Client)
            .filter(models.Client.id == session.client_id, models.Client.tenant_id == session.tenant_id)
            .first()
        )
        if client:
            client_name = client.name
    return {
        "client": client_name or "Nao informado",
        "area": area.name if area else "Nao informado",
        "equipment_type": equipment.name if equipment else "Nao informado",
        "brand": brand.name if brand else "Nao informado",
    }


def create_session(
    db: Session,
    user: models.User,
    payload: dict,
) -> models.ProblemSession:
    client_id = payload.get("client_id")
    client_other_text = (payload.get("client_other_text") or "").strip()
    client_name_snapshot = None
    if client_id:
        client = (
            db.query(models.Client)
            .filter(models.Client.id == client_id, models.Client.tenant_id == user.tenant_id)
            .first()
        )
        if not client:
            raise ValueError("Cliente invalido")
        client_name_snapshot = client.name
        client_other_text = ""
    elif client_other_text:
        client_name_snapshot = client_other_text
    session = models.ProblemSession(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        user_id=user.id,
        user_name_snapshot=user.name,
        client_id=client_id,
        client_name_snapshot=client_name_snapshot,
        client_other_text=client_other_text or None,
        status="draft",
        area_id=payload["area_id"],
        equipment_type_id=payload["equipment_type_id"],
        brand_id=payload["brand_id"],
        other_equipment_text=payload.get("other_equipment_text"),
        other_brand_text=payload.get("other_brand_text"),
        model_text=payload.get("model_text"),
        model_unknown=payload.get("model_unknown", False),
        error_code_text=payload.get("error_code_text"),
        error_code_unknown=payload.get("error_code_unknown", False),
        short_problem_text=payload["short_problem_text"],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def add_attachment(
    db: Session,
    session: models.ProblemSession,
    user: models.User,
    file: UploadFile,
    kind: str,
) -> models.ProblemAttachment:
    data = file.file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Arquivo acima de 5MB")
    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError("Tipo de arquivo invalido")
    object_name = _build_object_name(session.id, kind, file.filename or "foto")
    upload_bytes(data, object_name, content_type=content_type)
    attachment = models.ProblemAttachment(
        id=str(uuid.uuid4()),
        session_id=session.id,
        kind=kind,
        file_path=object_name,
        content_type=content_type,
        file_size=len(data),
        created_by=user.id,
    )
    session.attachments_count = (session.attachments_count or 0) + 1
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


def run_quick_solve(db: Session, session: models.ProblemSession) -> SolverResult:
    names = list_catalog_names(db, session)
    system_prompt = _build_system_prompt()
    user_prompt = _build_quick_user_prompt(
        names["area"],
        names["equipment_type"],
        names["brand"],
        session.other_equipment_text,
        session.other_brand_text,
        session.model_text,
        session.model_unknown,
        session.error_code_text,
        session.error_code_unknown,
        session.short_problem_text,
    )
    result, meta = request_solver_result(OPENAI_MODEL_DEFAULT, system_prompt, user_prompt)
    session.ai_quick_result_json = result.model_dump(mode="json")
    session.status = "answered"
    session.ai_model_used = meta.get("model")
    session.input_tokens = meta.get("input_tokens")
    session.output_tokens = meta.get("output_tokens")
    session.latency_ms = meta.get("latency_ms")
    db.commit()
    return result


def _validate_required_tests(required: list[TestRequirement], provided: list[dict]) -> None:
    provided_map = {item["key"]: item for item in provided if item.get("value") not in (None, "")}
    missing = [item.label for item in required if item.required and item.key not in provided_map]
    if missing:
        raise ValueError("Campos obrigatorios nao preenchidos: " + ", ".join(missing))


def run_advanced_solve(
    db: Session,
    session: models.ProblemSession,
    test_inputs: list[dict],
) -> SolverResult:
    quick_result = _load_result(session.ai_quick_result_json)
    if not quick_result:
        raise ValueError("Sessao sem resultado inicial")
    _validate_required_tests(quick_result.tests_required, test_inputs)

    db.query(models.ProblemTestInput).filter(models.ProblemTestInput.session_id == session.id).delete()
    input_rows: list[models.ProblemTestInput] = []
    for item in test_inputs:
        row = models.ProblemTestInput(
            id=str(uuid.uuid4()),
            session_id=session.id,
            key=item["key"],
            label=item["label"],
            value=str(item.get("value") or ""),
            unit=item.get("unit"),
        )
        input_rows.append(row)
        db.add(row)
    db.commit()

    attachments = (
        db.query(models.ProblemAttachment)
        .filter(models.ProblemAttachment.session_id == session.id)
        .order_by(models.ProblemAttachment.created_at.desc())
        .all()
    )
    selected = _select_attachments(attachments)
    image_urls = []
    for att in selected:
        try:
            image_urls.append(generate_signed_url(att.file_path))
        except Exception:
            continue

    system_prompt = _build_system_prompt()
    user_prompt = _build_advanced_user_prompt(quick_result, input_rows, session.short_problem_text)
    result, meta = request_solver_result(OPENAI_MODEL_DEFAULT, system_prompt, user_prompt, images=image_urls)
    session.ai_advanced_result_json = result.model_dump(mode="json")
    session.status = "advanced"
    session.ai_model_used = meta.get("model")
    session.input_tokens = meta.get("input_tokens")
    session.output_tokens = meta.get("output_tokens")
    session.latency_ms = meta.get("latency_ms")
    db.commit()
    return result


def resolve_session(db: Session, session: models.ProblemSession) -> None:
    session.status = "resolved"
    session.resolved_at = datetime.utcnow()
    db.commit()


def list_history(
    db: Session,
    tenant_id: str,
    limit: int = 50,
    user_id: Optional[str] = None,
) -> list[dict]:
    query = db.query(models.ProblemSession).filter(models.ProblemSession.tenant_id == tenant_id)
    query = query.filter(models.ProblemSession.status == "resolved")
    if user_id:
        query = query.filter(models.ProblemSession.user_id == user_id)
    sessions = (
        query.order_by(models.ProblemSession.resolved_at.desc().nullslast(), models.ProblemSession.created_at.desc())
        .limit(limit)
        .all()
    )
    results = []
    for session in sessions:
        result_payload = session.ai_advanced_result_json or session.ai_quick_result_json or {}
        summary = result_payload.get("summary") if isinstance(result_payload, dict) else None
        names = list_catalog_names(db, session)
        results.append(
            {
                "id": session.id,
                "user_name_snapshot": session.user_name_snapshot,
                "created_at": session.created_at,
                "resolved_at": session.resolved_at,
                "summary": summary,
                "area": names.get("area"),
                "client_name_snapshot": names.get("client"),
            }
        )
    return results


def get_session_detail(db: Session, tenant_id: str, session_id: str) -> Optional[dict]:
    session = (
        db.query(models.ProblemSession)
        .filter(models.ProblemSession.id == session_id, models.ProblemSession.tenant_id == tenant_id)
        .first()
    )
    if not session:
        return None
    names = list_catalog_names(db, session)
    attachments = (
        db.query(models.ProblemAttachment)
        .filter(models.ProblemAttachment.session_id == session.id)
        .order_by(models.ProblemAttachment.created_at.desc())
        .all()
    )
    attachment_payloads = []
    for att in attachments:
        try:
            url = generate_signed_url(att.file_path)
        except Exception:
            url = None
        attachment_payloads.append(
            {
                "id": att.id,
                "kind": att.kind,
                "file_path": att.file_path,
                "url": url,
                "content_type": att.content_type,
                "file_size": att.file_size,
                "created_at": att.created_at,
            }
        )
    tests = (
        db.query(models.ProblemTestInput)
        .filter(models.ProblemTestInput.session_id == session.id)
        .order_by(models.ProblemTestInput.captured_at.asc())
        .all()
    )
    return {
        "session": {
            "id": session.id,
            "tenant_id": session.tenant_id,
            "user_id": session.user_id,
            "user_name_snapshot": session.user_name_snapshot,
            "client_id": session.client_id,
            "client_name_snapshot": session.client_name_snapshot,
            "client_other_text": session.client_other_text,
            "status": session.status,
            "area_id": session.area_id,
            "equipment_type_id": session.equipment_type_id,
            "brand_id": session.brand_id,
            "other_equipment_text": session.other_equipment_text,
            "other_brand_text": session.other_brand_text,
            "model_text": session.model_text,
            "model_unknown": session.model_unknown,
            "error_code_text": session.error_code_text,
            "error_code_unknown": session.error_code_unknown,
            "short_problem_text": session.short_problem_text,
            "attachments_count": session.attachments_count,
            "ai_quick_result_json": session.ai_quick_result_json,
            "ai_advanced_result_json": session.ai_advanced_result_json,
            "ai_model_used": session.ai_model_used,
            "input_tokens": session.input_tokens,
            "output_tokens": session.output_tokens,
            "latency_ms": session.latency_ms,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "resolved_at": session.resolved_at,
            "client_name": names.get("client"),
            "area_name": names.get("area"),
            "equipment_type_name": names.get("equipment_type"),
            "brand_name": names.get("brand"),
        },
        "attachments": attachment_payloads,
        "test_inputs": [
            {
                "id": item.id,
                "key": item.key,
                "label": item.label,
                "value": item.value,
                "unit": item.unit,
                "captured_at": item.captured_at,
            }
            for item in tests
        ],
    }


def create_public_link(
    db: Session,
    session: models.ProblemSession,
    created_by: str,
) -> models.ProblemPublicLink:
    token = uuid.uuid4().hex
    link = models.ProblemPublicLink(
        id=str(uuid.uuid4()),
        session_id=session.id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(days=30),
        created_by=created_by,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def get_public_link(db: Session, token: str) -> Optional[models.ProblemPublicLink]:
    link = db.query(models.ProblemPublicLink).filter(models.ProblemPublicLink.token == token).first()
    if not link:
        return None
    if link.expires_at and link.expires_at < datetime.utcnow():
        return None
    return link


def build_public_payload(db: Session, session: models.ProblemSession) -> dict:
    names = list_catalog_names(db, session)
    result_payload = session.ai_advanced_result_json or session.ai_quick_result_json or {}
    attachments = (
        db.query(models.ProblemAttachment)
        .filter(models.ProblemAttachment.session_id == session.id)
        .order_by(models.ProblemAttachment.created_at.desc())
        .all()
    )
    attachment_payloads = []
    for att in attachments:
        try:
            url = generate_signed_url(att.file_path)
        except Exception:
            url = None
        attachment_payloads.append(
            {
                "id": att.id,
                "kind": att.kind,
                "url": url,
                "created_at": att.created_at,
            }
        )
    tests = (
        db.query(models.ProblemTestInput)
        .filter(models.ProblemTestInput.session_id == session.id)
        .order_by(models.ProblemTestInput.captured_at.asc())
        .all()
    )
    return {
        "session": session,
        "names": names,
        "result": result_payload,
        "attachments": attachment_payloads,
        "tests": [
            {"key": item.key, "label": item.label, "value": item.value, "unit": item.unit}
            for item in tests
        ],
    }
