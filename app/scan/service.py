import json
import logging
import time
import uuid
from typing import Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.db import models
from app.scan.openai_client import request_scan_report, request_scan_signals
from app.scan.rules_engine import evaluate_scan_rules
from app.scan.schemas import ScanReport, ScanSignals
from app.services.storage import generate_signed_url, upload_bytes


logger = logging.getLogger("eagl.scan")

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
OPENAI_MODEL_DEFAULT = "gpt-4o-mini"
ALLOWED_CATEGORIES = {"alarmes", "tendencias", "pontos", "geral", "equipamento"}


def _build_object_name(scan_id: str, category: str, filename: str) -> str:
    safe = filename.replace(" ", "_")
    return f"scan/{scan_id}/{category}/{uuid.uuid4().hex}_{safe}"


def _safe_signed_url(object_name: str) -> str:
    if object_name.startswith("http://") or object_name.startswith("https://"):
        return object_name
    return generate_signed_url(object_name)


def _build_extraction_system_prompt() -> str:
    return (
        "Voce extrai sinais, nao diagnostica. "
        "Nao invente nada. Se nao enxergar, diga 'nao identificado'. "
        "Sempre preencha JSON valido seguindo o schema."
    )


def _build_report_system_prompt() -> str:
    return (
        "Voce gera um laudo tecnico baseado em sinais e regras. "
        "Nao invente dados. Sempre justificar por evidencias. "
        "Probabilidade nunca 100%. Se dados insuficientes, reduza a confianca e explique. "
        "Responda sempre em pt-BR, frases curtas, linguagem simples de campo. "
        "Sempre devolva JSON valido seguindo o schema."
    )


def _build_extraction_user_prompt(
    payload: dict,
    image_categories: list[str],
) -> str:
    tags = ", ".join(payload.get("problema_tags") or []) or "Nao informado"
    images_text = "\n".join(
        f"- {idx}: {category}" for idx, category in enumerate(image_categories)
    )
    return (
        "Dados do equipamento:\n"
        f"- Tipo: {payload.get('tipo_equipamento')}\n"
        f"- Marca: {payload.get('marca')}\n"
        f"- Modelo: {payload.get('modelo')}\n"
        f"- Problema: {payload.get('problema_texto')}\n"
        f"- Tags: {tags}\n\n"
        "Imagens (index e categoria):\n"
        f"{images_text}\n\n"
        "Extraia sinais estruturados. Nao diagnostique."
    )


def _build_report_user_prompt(
    payload: dict,
    signals: ScanSignals,
    rules_payload: dict,
) -> str:
    return (
        "Dados do formulario:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Sinais extraidos:\n"
        f"{signals.model_dump_json(indent=2)}\n\n"
        "Scores por bloco e hipoteses:\n"
        f"{json.dumps(rules_payload, ensure_ascii=False, indent=2)}\n\n"
        "Gere o laudo final seguindo o schema."
    )


def create_scan_session(db: Session, user: models.User, payload: dict) -> models.ScanSession:
    session = models.ScanSession(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        created_by_user_id=user.id,
        tipo_equipamento=payload["tipo_equipamento"],
        marca=payload["marca"],
        modelo=payload["modelo"],
        problema_texto=payload["problema_texto"],
        problema_tags=payload.get("problema_tags") or [],
        status="processing",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def add_scan_image(
    db: Session,
    scan: models.ScanSession,
    file: UploadFile,
    category: str,
) -> tuple[models.ScanImage, int]:
    data = file.file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Arquivo acima de 5MB")
    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError("Tipo de arquivo invalido")
    size = len(data)
    object_name = _build_object_name(scan.id, category, file.filename or "foto")
    upload_bytes(data, object_name, content_type=content_type)
    image = models.ScanImage(
        id=str(uuid.uuid4()),
        scan_id=scan.id,
        tenant_id=scan.tenant_id,
        storage_url=object_name,
        categoria=category,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image, size


def add_scan_image_url(
    db: Session,
    scan: models.ScanSession,
    url: str,
    category: str,
) -> models.ScanImage:
    image = models.ScanImage(
        id=str(uuid.uuid4()),
        scan_id=scan.id,
        tenant_id=scan.tenant_id,
        storage_url=url,
        categoria=category,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


def run_scan_pipeline(
    db: Session,
    scan: models.ScanSession,
    payload: dict,
    images: list[models.ScanImage],
) -> tuple[ScanSignals, ScanReport]:
    start = time.perf_counter()
    image_urls = [_safe_signed_url(img.storage_url) for img in images]
    image_categories = [img.categoria for img in images]

    system_prompt = _build_extraction_system_prompt()
    user_prompt = _build_extraction_user_prompt(payload, image_categories)
    signals, meta_extract = request_scan_signals(
        OPENAI_MODEL_DEFAULT,
        system_prompt,
        user_prompt,
        images=image_urls,
    )

    rules_payload = evaluate_scan_rules(signals, payload["problema_texto"], payload.get("problema_tags") or [])
    report_prompt = _build_report_user_prompt(payload, signals, rules_payload)
    report_system = _build_report_system_prompt()
    report, meta_report = request_scan_report(
        OPENAI_MODEL_DEFAULT,
        report_system,
        report_prompt,
    )

    if report.confidence_overall >= 1:
        report.confidence_overall = 0.99
    for hyp in report.top_hypotheses:
        if hyp.probabilidade >= 1:
            hyp.probabilidade = 0.99

    scan_signal = models.ScanSignal(
        id=str(uuid.uuid4()),
        scan_id=scan.id,
        tenant_id=scan.tenant_id,
        signals_json=signals.model_dump(mode="json"),
        extraction_confidence=signals.extraction_confidence,
    )
    scan_result = models.ScanResult(
        id=str(uuid.uuid4()),
        scan_id=scan.id,
        tenant_id=scan.tenant_id,
        result_json=report.model_dump(mode="json"),
    )
    scan.status = "done"
    scan.openai_model = meta_report.get("model") or meta_extract.get("model")
    scan.confidence_overall = report.confidence_overall
    scan.error_message = None
    db.add(scan_signal)
    db.add(scan_result)
    db.commit()

    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "scan completed id=%s status=done duration_ms=%s model=%s images=%s",
        scan.id,
        duration_ms,
        scan.openai_model,
        len(images),
    )
    return signals, report


def get_scan_detail(db: Session, tenant_id: str, scan_id: str) -> Optional[dict]:
    scan = (
        db.query(models.ScanSession)
        .filter(models.ScanSession.id == scan_id, models.ScanSession.tenant_id == tenant_id)
        .first()
    )
    if not scan:
        return None
    images = (
        db.query(models.ScanImage)
        .filter(models.ScanImage.scan_id == scan_id, models.ScanImage.tenant_id == tenant_id)
        .all()
    )
    signals = (
        db.query(models.ScanSignal)
        .filter(models.ScanSignal.scan_id == scan_id, models.ScanSignal.tenant_id == tenant_id)
        .order_by(models.ScanSignal.created_at.desc())
        .first()
    )
    results = (
        db.query(models.ScanResult)
        .filter(models.ScanResult.scan_id == scan_id, models.ScanResult.tenant_id == tenant_id)
        .order_by(models.ScanResult.created_at.desc())
        .first()
    )
    return {
        "session": {
            "id": scan.id,
            "status": scan.status,
            "created_at": scan.created_at,
            "tipo_equipamento": scan.tipo_equipamento,
            "marca": scan.marca,
            "modelo": scan.modelo,
            "problema_texto": scan.problema_texto,
            "problema_tags": scan.problema_tags or [],
            "confidence_overall": scan.confidence_overall,
            "os_id": scan.os_id,
            "asset_id": scan.asset_id,
        },
        "images": [
            {
                "id": image.id,
                "categoria": image.categoria,
                "url": _safe_signed_url(image.storage_url),
            }
            for image in images
        ],
        "signals": signals.signals_json if signals else None,
        "result": results.result_json if results else None,
    }


def link_asset(db: Session, scan: models.ScanSession, asset_id: str) -> models.ScanSession:
    scan.asset_id = asset_id
    db.commit()
    db.refresh(scan)
    return scan


def create_os_from_scan(
    db: Session,
    user: models.User,
    scan: models.ScanSession,
    result_json: dict,
    client_id: Optional[str] = None,
) -> models.WorkOrder:
    asset_client_id = None
    if scan.asset_id:
        asset = (
            db.query(models.Asset)
            .filter(models.Asset.id == scan.asset_id, models.Asset.tenant_id == scan.tenant_id)
            .first()
        )
        if asset:
            asset_client_id = asset.client_id

    resolved_client_id = client_id or asset_client_id or user.client_id
    if not resolved_client_id:
        raise ValueError("Cliente nao informado para gerar OS.")

    title = f"Diagnostico via EAGL Scan - {scan.tipo_equipamento} {scan.marca} {scan.modelo}"
    top_lines = []
    for hyp in result_json.get("top_hypotheses", [])[:5]:
        prob = int(round((hyp.get("probabilidade") or 0) * 100))
        top_lines.append(f"- {hyp.get('bloco_local')}: {hyp.get('titulo')} ({prob}%)")
    validations = result_json.get("o_que_validar_em_campo_agora") or []
    risco = result_json.get("risco_operacao") or {}
    description = (
        "Problema informado:\n"
        f"{scan.problema_texto}\n\n"
        "Hipoteses principais:\n"
        f"{chr(10).join(top_lines) if top_lines else '- Nao identificado'}\n\n"
        "Validacoes em campo:\n"
        f"{chr(10).join(f'- {item}' for item in validations) if validations else '- Nao informado'}\n\n"
        "Risco operacional:\n"
        f"{risco.get('nivel', 'Nao informado')}: {risco.get('motivo', 'Nao informado')}\n"
    )

    new_os = models.WorkOrder(
        id=str(uuid.uuid4()),
        tenant_id=scan.tenant_id,
        client_id=resolved_client_id,
        asset_id=scan.asset_id,
        title=title,
        description=description,
        status="aberta",
        completion_percent=0,
    )
    db.add(new_os)
    scan_item = models.WorkOrderItem(
        id=str(uuid.uuid4()),
        work_order_id=new_os.id,
        question_text="Evidencias do EAGL Scan",
        answer_type="text",
        required=False,
        order_index=0,
        note="Imagens enviadas no Scan.",
    )
    db.add(scan_item)

    images = (
        db.query(models.ScanImage)
        .filter(models.ScanImage.scan_id == scan.id, models.ScanImage.tenant_id == scan.tenant_id)
        .all()
    )
    for image in images:
        db.add(
            models.WorkOrderAttachment(
                id=str(uuid.uuid4()),
                work_order_id=new_os.id,
                item_id=scan_item.id,
                question_id=scan_item.id,
                scope="QUESTION",
                file_name=f"scan-{image.categoria}.jpg",
                mime="image/jpeg",
                size=None,
                url=image.storage_url,
                thumb_url=None,
                created_by=user.id,
            )
        )

    result_bytes = json.dumps(result_json, ensure_ascii=False, indent=2).encode("utf-8")
    result_object = _build_object_name(new_os.id, "result", "scan_result.json")
    upload_bytes(result_bytes, result_object, content_type="application/json")
    db.add(
        models.WorkOrderAttachment(
            id=str(uuid.uuid4()),
            work_order_id=new_os.id,
            item_id=None,
            question_id=None,
            scope="QUESTION",
            file_name="scan_result.json",
            mime="application/json",
            size=len(result_bytes),
            url=result_object,
            thumb_url=None,
            created_by=user.id,
        )
    )

    scan.os_id = new_os.id
    db.add(scan)
    db.commit()
    db.refresh(new_os)
    return new_os
