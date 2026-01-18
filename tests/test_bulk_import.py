from datetime import datetime
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.bulk.importer import ImportValidationError, run_job, validate_job
from app.bulk.storage import StorageClient
from app.db import models


def _make_xlsx(headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    ws.append(["" for _ in headers])
    for row in rows:
        ws.append(row)
    data = BytesIO()
    wb.save(data)
    return data.getvalue()


def _seed_tenant_user(db):
    tenant = models.Tenant(name="Tenant", status="ATIVO", tenant_type="MSP", timezone="America/Sao_Paulo")
    db.add(tenant)
    db.commit()
    user = models.User(
        tenant_id=tenant.id,
        name="User",
        login="user",
        email="user@example.com",
        password_hash="x",
        role="TENANT_ADMIN",
        status="active",
    )
    db.add(user)
    db.commit()
    return tenant, user


def _create_job(db, tenant_id, user_id, entity, content):
    storage = StorageClient()
    file_url = storage.upload_bytes(content, f"tests/{entity}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    job = models.ImportJob(
        tenant_id=tenant_id,
        entity=entity,
        mode="upsert",
        status="queued",
        file_url=file_url,
        file_name=f"{entity}.xlsx",
        file_size=len(content),
        file_hash="hash",
        template_version="v1",
        created_by_user_id=user_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_validate_missing_column(db_session):
    tenant, user = _seed_tenant_user(db_session)
    content = _make_xlsx(
        ["Nome", "Email"],
        [["Ana", "ana@example.com"]],
    )
    job = _create_job(db_session, tenant.id, user.id, "employees", content)
    with pytest.raises(ImportValidationError):
        validate_job(db_session, job)


def test_validate_duplicate_unique_key(db_session):
    tenant, user = _seed_tenant_user(db_session)
    content = _make_xlsx(
        ["Nome", "Funcao", "Email"],
        [
            ["Ana", "Tecnica", "ana@example.com"],
            ["Ana 2", "Tecnica", "ana@example.com"],
        ],
    )
    job = _create_job(db_session, tenant.id, user.id, "employees", content)
    preview = validate_job(db_session, job)
    assert preview["errors"] > 0
    assert job.status == "failed"


def test_validate_relationship_error(db_session):
    tenant, user = _seed_tenant_user(db_session)
    content = _make_xlsx(
        ["Codigo do site", "Nome", "CNPJ do cliente"],
        [["SITE01", "Site A", "12345678000199"]],
    )
    job = _create_job(db_session, tenant.id, user.id, "sites", content)
    preview = validate_job(db_session, job)
    assert preview["errors"] > 0
    assert job.status == "failed"


def test_upsert_client(db_session):
    tenant, user = _seed_tenant_user(db_session)
    existing = models.Client(
        tenant_id=tenant.id,
        name="Cliente Antigo",
        document="12345678000199",
        status="active",
        created_at=datetime.utcnow(),
    )
    db_session.add(existing)
    db_session.commit()

    content = _make_xlsx(
        ["Nome", "CNPJ"],
        [["Cliente Novo", "12.345.678/0001-99"]],
    )
    job = _create_job(db_session, tenant.id, user.id, "clients", content)
    validate_job(db_session, job)
    job.status = "queued"
    db_session.commit()
    run_job(db_session, job)

    updated = db_session.query(models.Client).filter(models.Client.id == existing.id).first()
    assert updated.name == "Cliente Novo"
