import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.authorization import enforce_client_user_scope, require_scope_or_admin
from app.core.security import get_current_user, require_permission
from app.db import models
from app.db.session import get_db
from app.scan import service


logger = logging.getLogger("eagl.scan")
router = APIRouter(tags=["Scan"])


def _internal_error():
    logger.exception("Erro interno no scan")
    return JSONResponse(status_code=500, content={"message": "Ocorreu um erro, tente novamente mais tarde"})


def _parse_json_list(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except Exception:
        return []
    if isinstance(payload, list):
        return payload
    return []


def _parse_tags(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        if raw.startswith("["):
            items = _parse_json_list(raw)
            return [str(item).strip() for item in items if str(item).strip()]
        return [item.strip() for item in raw.split(",") if item.strip()]
    return []


def _normalize_category(value: str) -> str:
    lowered = (value or "").strip().lower()
    if lowered in service.ALLOWED_CATEGORIES:
        return lowered
    return "geral"


def _get_scan_or_404(db: Session, tenant_id: str, scan_id: str) -> models.ScanSession:
    scan = (
        db.query(models.ScanSession)
        .filter(models.ScanSession.id == scan_id, models.ScanSession.tenant_id == tenant_id)
        .first()
    )
    if not scan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan nao encontrado")
    return scan


@router.post("/scan", status_code=status.HTTP_201_CREATED)
async def create_scan(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        content_type = (request.headers.get("content-type") or "").lower()
        payload: dict = {}
        image_categories: list[str] = []
        files: list = []
        image_urls: list[dict] = []

        if "multipart/form-data" in content_type:
            form = await request.form()
            payload = {
                "tipo_equipamento": (form.get("tipo_equipamento") or "").strip(),
                "marca": (form.get("marca") or "").strip(),
                "modelo": (form.get("modelo") or "").strip(),
                "problema_texto": (form.get("problema_texto") or "").strip(),
                "problema_tags": _parse_tags(form.get("problema_tags")),
            }
            image_categories = [
                _normalize_category(cat)
                for cat in _parse_json_list(form.get("image_categories"))
            ]
            files = form.getlist("images") or form.getlist("imagens") or []
            image_urls = _parse_json_list(form.get("image_urls"))
        else:
            body = await request.json()
            payload = {
                "tipo_equipamento": (body.get("tipo_equipamento") or "").strip(),
                "marca": (body.get("marca") or "").strip(),
                "modelo": (body.get("modelo") or "").strip(),
                "problema_texto": (body.get("problema_texto") or "").strip(),
                "problema_tags": body.get("problema_tags") or [],
            }
            image_urls = body.get("images") or body.get("image_urls") or []
            image_categories = [_normalize_category(img.get("categoria")) for img in image_urls if img]

        if not payload["tipo_equipamento"]:
            raise HTTPException(status_code=422, detail="Tipo de equipamento obrigatorio")
        if not payload["marca"]:
            raise HTTPException(status_code=422, detail="Marca obrigatoria")
        if not payload["modelo"]:
            raise HTTPException(status_code=422, detail="Modelo obrigatorio")
        if not payload["problema_texto"]:
            raise HTTPException(status_code=422, detail="Descricao do problema obrigatoria")
        if len(payload["problema_texto"]) > 500:
            raise HTTPException(status_code=422, detail="Descricao do problema muito longa")

        if not files and not image_urls:
            raise HTTPException(status_code=422, detail="Envie pelo menos uma imagem")

        scan = service.create_scan_session(db, current_user, payload)
        images: list[models.ScanImage] = []
        total_bytes = 0

        for idx, file in enumerate(files):
            category = image_categories[idx] if idx < len(image_categories) else "geral"
            image, size = service.add_scan_image(db, scan, file, category)
            images.append(image)
            total_bytes += size

        for idx, image_payload in enumerate(image_urls):
            if not isinstance(image_payload, dict):
                continue
            url = (image_payload.get("url") or "").strip()
            if not url:
                continue
            category = _normalize_category(image_payload.get("categoria") or "geral")
            image = service.add_scan_image_url(db, scan, url, category)
            images.append(image)

        logger.info(
            "scan received id=%s images=%s total_bytes=%s",
            scan.id,
            len(images),
            total_bytes,
        )

        signals, report = service.run_scan_pipeline(db, scan, payload, images)
        detail = service.get_scan_detail(db, current_user.tenant_id, scan.id)
        return detail or {
            "session": {"id": scan.id, "status": scan.status},
            "signals": signals.model_dump(mode="json"),
            "result": report.model_dump(mode="json"),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Erro ao criar scan")
        try:
            if "scan" in locals() and scan:
                scan.status = "error"
                scan.error_message = str(exc)
                db.commit()
        except Exception:
            logger.exception("Erro ao atualizar status do scan")
        return _internal_error()


@router.get("/scan/{scan_id}")
def get_scan(
    scan_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        detail = service.get_scan_detail(db, current_user.tenant_id, scan_id)
        if not detail:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan nao encontrado")
        return detail
    except HTTPException:
        raise
    except Exception:
        return _internal_error()


@router.post("/scan/{scan_id}/generate-os")
def generate_os(
    scan_id: str,
    body: Optional[dict] = None,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    try:
        scan = _get_scan_or_404(db, current_user.tenant_id, scan_id)
        result_row = (
            db.query(models.ScanResult)
            .filter(models.ScanResult.scan_id == scan.id, models.ScanResult.tenant_id == scan.tenant_id)
            .order_by(models.ScanResult.created_at.desc())
            .first()
        )
        if not result_row:
            raise HTTPException(status_code=422, detail="Resultado do scan nao encontrado")

        client_id = None
        if isinstance(body, dict):
            client_id = body.get("client_id")

        scope = require_scope_or_admin(db, current_user)
        if not client_id and scope["clients"] and len(scope["clients"]) == 1:
            client_id = scope["clients"][0]

        if client_id:
            enforce_client_user_scope(current_user, client_id)
            if scope["clients"] and client_id not in scope["clients"]:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cliente fora do escopo")

        os = service.create_os_from_scan(
            db,
            current_user,
            scan,
            result_row.result_json,
            client_id=client_id,
        )
        return {"os_id": os.id}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        return _internal_error()


@router.post("/scan/{scan_id}/link-asset")
def link_asset(
    scan_id: str,
    body: dict,
    current_user: models.User = Depends(require_permission("assets.view")),
    db: Session = Depends(get_db),
):
    try:
        asset_id = (body or {}).get("asset_id")
        if not asset_id:
            raise HTTPException(status_code=422, detail="asset_id obrigatorio")
        asset = (
            db.query(models.Asset)
            .filter(models.Asset.id == asset_id, models.Asset.tenant_id == current_user.tenant_id)
            .first()
        )
        if not asset:
            raise HTTPException(status_code=404, detail="Ativo nao encontrado")
        scan = _get_scan_or_404(db, current_user.tenant_id, scan_id)
        service.link_asset(db, scan, asset_id)
        return {"status": "ok", "asset_id": asset_id}
    except HTTPException:
        raise
    except Exception:
        return _internal_error()
