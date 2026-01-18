import os

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.bulk.config import ENTITY_CONFIGS
from app.bulk.exporter import count_records, run_export_job
from app.bulk.importer import ImportValidationError, run_job, validate_job
from app.bulk.storage import StorageClient, StorageError
from app.bulk.tasks import enqueue_http_task
from app.core.security import require_permission
from app.db import models
from app.db.session import get_db

router = APIRouter(prefix="/bulk", tags=["Bulk"])


def _ensure_entity(entity: str):
    if entity not in ENTITY_CONFIGS:
        raise HTTPException(status_code=404, detail="Entidade nao suportada")


@router.get("/templates/{entity}")
def download_template(entity: str):
    from app.bulk.templates import build_template

    _ensure_entity(entity)
    content, filename = build_template(entity)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/import/{entity}/upload")
def upload_import_file(
    entity: str,
    file: UploadFile = File(...),
    mode: str = "upsert",
    db=Depends(get_db),
    current_user: models.User = Depends(require_permission("cadastros.importar")),
):
    _ensure_entity(entity)
    if mode not in {"upsert", "create_only", "update_only"}:
        raise HTTPException(status_code=400, detail="Modo invalido")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo nao informado")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".xlsx", ".csv", ".xls"}:
        raise HTTPException(status_code=400, detail="Formato nao suportado")
    if file.content_type and file.content_type not in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "text/csv",
        "application/csv",
        "application/octet-stream",
    }:
        raise HTTPException(status_code=400, detail="Tipo de arquivo nao suportado")

    storage = StorageClient()
    dest_path = f"bulk/imports/{current_user.tenant_id}/{entity}/{file.filename}"
    max_mb = int(os.getenv("BULK_MAX_FILE_MB", "50"))
    max_bytes = max_mb * 1024 * 1024
    try:
        file_url, file_size, file_hash = storage.upload_file(
            file.file,
            dest_path,
            file.content_type or "application/octet-stream",
            max_bytes=max_bytes,
        )
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if file_size <= 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    existing = (
        db.query(models.ImportJob)
        .filter(
            models.ImportJob.tenant_id == current_user.tenant_id,
            models.ImportJob.entity == entity,
            models.ImportJob.file_hash == file_hash,
        )
        .first()
    )
    if existing and existing.status == "completed":
        raise HTTPException(status_code=409, detail="Este arquivo ja foi processado.")
    if existing and existing.status in {"queued", "running", "ready_to_confirm"}:
        raise HTTPException(status_code=409, detail="Ja existe uma importacao em andamento para este arquivo.")

    job = models.ImportJob(
        tenant_id=current_user.tenant_id,
        entity=entity,
        mode=mode,
        status="queued",
        file_url=file_url,
        file_name=file.filename,
        file_size=file_size,
        file_hash=file_hash,
        template_version=ENTITY_CONFIGS[entity].template_version,
        created_by_user_id=current_user.id,
    )
    db.add(job)
    _log_audit(
        db,
        current_user.tenant_id,
        current_user.id,
        "bulk.import.upload",
        {"job_id": job.id, "entity": entity, "file_name": file.filename, "file_size": file_size},
    )
    db.commit()
    db.refresh(job)
    return {"job_id": job.id}


@router.post("/import/{job_id}/validate")
def validate_import(
    job_id: str,
    db=Depends(get_db),
    current_user: models.User = Depends(require_permission("cadastros.importar")),
):
    job = (
        db.query(models.ImportJob)
        .filter(models.ImportJob.id == job_id, models.ImportJob.tenant_id == current_user.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job nao encontrado")
    try:
        _log_audit(
            db,
            current_user.tenant_id,
            current_user.id,
            "bulk.import.validate",
            {"job_id": job.id, "entity": job.entity},
        )
        preview = validate_job(db, job)
        return {"preview": preview, "status": job.status}
    except ImportValidationError as exc:
        job.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/import/{job_id}/confirm")
def confirm_import(
    job_id: str,
    background: BackgroundTasks,
    db=Depends(get_db),
    current_user: models.User = Depends(require_permission("cadastros.importar")),
):
    job = (
        db.query(models.ImportJob)
        .filter(models.ImportJob.id == job_id, models.ImportJob.tenant_id == current_user.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job nao encontrado")
    if job.status != "ready_to_confirm":
        raise HTTPException(status_code=400, detail="Job ainda nao validado")
    running = (
        db.query(models.ImportJob)
        .filter(
            models.ImportJob.tenant_id == current_user.tenant_id,
            models.ImportJob.entity == job.entity,
            models.ImportJob.status.in_(["queued", "running"]),
            models.ImportJob.id != job.id,
        )
        .first()
    )
    if running:
        raise HTTPException(status_code=409, detail="Ja existe importacao em andamento para esta entidade.")

    job.status = "queued"
    db.commit()
    _log_audit(
        db,
        current_user.tenant_id,
        current_user.id,
        "bulk.import.confirm",
        {"job_id": job.id, "entity": job.entity},
    )
    db.commit()
    queued = enqueue_http_task(f"/api/bulk/worker/import/{job.id}", {"job_id": str(job.id)})
    if not queued:
        background.add_task(_run_import_inline, job.id)
    return {"status": "queued"}


def _run_import_inline(job_id: str):
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        job = db.query(models.ImportJob).filter(models.ImportJob.id == job_id).first()
        if not job:
            return
        run_job(db, job)
    finally:
        db.close()


@router.post("/worker/import/{job_id}")
def run_import_worker(job_id: str, request: Request, db=Depends(get_db)):
    _verify_worker(request)
    job = db.query(models.ImportJob).filter(models.ImportJob.id == job_id).first()
    if not job:
        return {"status": "not_found"}
    run_job(db, job)
    return {"status": job.status}


@router.get("/import/{job_id}")
def get_import_job(
    job_id: str,
    db=Depends(get_db),
    current_user: models.User = Depends(require_permission("cadastros.importar")),
):
    job = (
        db.query(models.ImportJob)
        .filter(models.ImportJob.id == job_id, models.ImportJob.tenant_id == current_user.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job nao encontrado")
    storage = StorageClient()
    return {
        "id": job.id,
        "entity": job.entity,
        "status": job.status,
        "summary": job.summary_json,
        "preview": job.preview_json,
        "error_report_url": storage.generate_signed_url(job.error_report_url) if job.error_report_url else None,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


@router.get("/import")
def list_import_jobs(
    entity: str | None = None,
    status_filter: str | None = None,
    db=Depends(get_db),
    current_user: models.User = Depends(require_permission("auditoria.visualizar_importacoes")),
):
    query = db.query(models.ImportJob).filter(models.ImportJob.tenant_id == current_user.tenant_id)
    if entity:
        query = query.filter(models.ImportJob.entity == entity)
    if status_filter:
        query = query.filter(models.ImportJob.status == status_filter)
    jobs = query.order_by(models.ImportJob.created_at.desc()).limit(200).all()
    return [
        {
            "id": job.id,
            "entity": job.entity,
            "status": job.status,
            "summary": job.summary_json,
            "created_at": job.created_at,
        }
        for job in jobs
    ]


@router.get("/import/{job_id}/errors")
def list_import_errors(
    job_id: str,
    db=Depends(get_db),
    current_user: models.User = Depends(require_permission("auditoria.visualizar_importacoes")),
):
    job = (
        db.query(models.ImportJob)
        .filter(models.ImportJob.id == job_id, models.ImportJob.tenant_id == current_user.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job nao encontrado")
    errors = (
        db.query(models.ImportRowError)
        .filter(models.ImportRowError.import_job_id == job_id)
        .order_by(models.ImportRowError.row_number.asc())
        .limit(5000)
        .all()
    )
    return [
        {
            "row_number": err.row_number,
            "field": err.field,
            "message": err.message,
            "severity": err.severity,
        }
        for err in errors
    ]


@router.get("/import/{job_id}/download-errors")
def download_errors(job_id: str, db=Depends(get_db), current_user: models.User = Depends(require_permission("auditoria.visualizar_importacoes"))):
    job = (
        db.query(models.ImportJob)
        .filter(models.ImportJob.id == job_id, models.ImportJob.tenant_id == current_user.tenant_id)
        .first()
    )
    if not job or not job.error_report_url:
        raise HTTPException(status_code=404, detail="Relatorio nao encontrado")
    storage = StorageClient()
    return {"url": storage.generate_signed_url(job.error_report_url)}


@router.get("/export/{entity}")
def export_entity(
    entity: str,
    background: BackgroundTasks,
    db=Depends(get_db),
    current_user: models.User = Depends(require_permission("cadastros.exportar")),
):
    _ensure_entity(entity)
    limit = int(os.getenv("BULK_EXPORT_SYNC_LIMIT", "2000"))
    total = count_records(db, current_user.tenant_id, entity)
    if total <= limit:
        from app.bulk.templates import build_export

        content, filename = build_export(db, current_user.tenant_id, entity)
        storage = StorageClient()
        dest = f"bulk/exports/{current_user.tenant_id}/{entity}/{filename}"
        url = storage.upload_bytes(content, dest, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        _log_audit(
            db,
            current_user.tenant_id,
            current_user.id,
            "bulk.export.completed",
            {"entity": entity, "exported": total},
        )
        db.commit()
        return {"url": storage.generate_signed_url(url)}

    job = models.ExportJob(
        tenant_id=current_user.tenant_id,
        entity=entity,
        status="queued",
        template_version=ENTITY_CONFIGS[entity].template_version,
        created_by_user_id=current_user.id,
    )
    db.add(job)
    _log_audit(
        db,
        current_user.tenant_id,
        current_user.id,
        "bulk.export.queued",
        {"job_id": job.id, "entity": entity, "total": total},
    )
    db.commit()
    queued = enqueue_http_task(f"/api/bulk/worker/export/{job.id}", {"job_id": str(job.id)})
    if not queued:
        background.add_task(_run_export_inline, job.id)
    return {"job_id": job.id, "status": job.status}


@router.get("/export/jobs")
def list_export_jobs(
    db=Depends(get_db),
    current_user: models.User = Depends(require_permission("auditoria.visualizar_importacoes")),
):
    jobs = (
        db.query(models.ExportJob)
        .filter(models.ExportJob.tenant_id == current_user.tenant_id)
        .order_by(models.ExportJob.created_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": job.id,
            "entity": job.entity,
            "status": job.status,
            "summary": job.summary_json,
            "created_at": job.created_at,
        }
        for job in jobs
    ]


@router.get("/export/jobs/{job_id}")
def get_export_job(
    job_id: str,
    db=Depends(get_db),
    current_user: models.User = Depends(require_permission("auditoria.visualizar_importacoes")),
):
    job = (
        db.query(models.ExportJob)
        .filter(models.ExportJob.id == job_id, models.ExportJob.tenant_id == current_user.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Export nao encontrado")
    storage = StorageClient()
    return {
        "id": job.id,
        "entity": job.entity,
        "status": job.status,
        "summary": job.summary_json,
        "url": storage.generate_signed_url(job.file_url) if job.file_url else None,
    }


@router.post("/worker/export/{job_id}")
def run_export_worker(job_id: str, request: Request, db=Depends(get_db)):
    _verify_worker(request)
    job = db.query(models.ExportJob).filter(models.ExportJob.id == job_id).first()
    if not job:
        return {"status": "not_found"}
    run_export_job(db, job)
    return {"status": job.status}


def _run_export_inline(job_id: str):
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        job = db.query(models.ExportJob).filter(models.ExportJob.id == job_id).first()
        if not job:
            return
        run_export_job(db, job)
    finally:
        db.close()


def _verify_worker(request: Request) -> None:
    secret = os.getenv("BULK_TASKS_SECRET")
    if secret:
        header = request.headers.get("X-Tasks-Secret")
        if header != secret:
            raise HTTPException(status_code=403, detail="Acesso negado")


def _log_audit(db, tenant_id: str, user_id: str | None, action: str, payload: dict) -> None:
    db.add(
        models.AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type="bulk",
            resource_id=payload.get("job_id"),
            payload_resumo=payload,
        )
    )
