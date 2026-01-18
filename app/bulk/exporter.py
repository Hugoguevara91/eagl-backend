from datetime import datetime

from app.bulk.storage import StorageClient
from app.bulk.templates import build_export
from app.db import models


def count_records(db, tenant_id: str, entity: str) -> int:
    if entity == "employees":
        return db.query(models.Colaborador).filter(models.Colaborador.tenant_id == tenant_id).count()
    if entity == "clients":
        return db.query(models.Client).filter(models.Client.tenant_id == tenant_id).count()
    if entity == "sites":
        return db.query(models.Site).filter(models.Site.tenant_id == tenant_id).count()
    if entity == "assets":
        return db.query(models.Asset).filter(models.Asset.tenant_id == tenant_id).count()
    if entity == "os_types":
        return db.query(models.OSType).filter(models.OSType.tenant_id == tenant_id).count()
    if entity == "questionnaires":
        return db.query(models.Questionnaire).filter(models.Questionnaire.tenant_id == tenant_id).count()
    return 0


def run_export_job(db, job: models.ExportJob) -> dict:
    if job.status not in {"queued", "running"}:
        return job.summary_json or {}

    job.status = "running"
    if not job.started_at:
        job.started_at = datetime.utcnow()
    db.commit()

    content, filename = build_export(db, job.tenant_id, job.entity)
    storage = StorageClient()
    dest = f"bulk/exports/{job.tenant_id}/{job.entity}/{filename}"
    file_url = storage.upload_bytes(content, dest, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    exported_count = count_records(db, job.tenant_id, job.entity)
    job.file_url = file_url
    job.file_name = filename
    job.file_size = len(content)
    job.status = "completed"
    job.finished_at = datetime.utcnow()
    job.summary_json = {"exported": exported_count}
    db.add(
        models.AuditLog(
            tenant_id=job.tenant_id,
            user_id=job.created_by_user_id,
            action="bulk.export.completed",
            resource_type="export_job",
            resource_id=job.id,
            payload_resumo={"exported": exported_count},
        )
    )
    db.commit()
    return job.summary_json
