import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_db
from app.core.security import get_current_user
from app.services.storage import generate_signed_url
from app.solver import service
from app.solver.pdf_service import render_solver_pdf
from app.solver.public_page import render_public_solver_page

logger = logging.getLogger("eagl.solver")

router = APIRouter(tags=["Solver"])
public_router = APIRouter(tags=["Solver Public"])


class SessionCreatePayload(BaseModel):
    client_id: Optional[str] = None
    client_other_text: Optional[str] = None
    area_id: str
    equipment_type_id: str
    brand_id: str
    other_equipment_text: Optional[str] = None
    other_brand_text: Optional[str] = None
    model_text: Optional[str] = None
    model_unknown: bool = False
    error_code_text: Optional[str] = None
    error_code_unknown: bool = False
    short_problem_text: str = Field(max_length=200)

    @field_validator("short_problem_text")
    @classmethod
    def validate_problem(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("Problema obrigatorio")
        return cleaned


class TestInputItem(BaseModel):
    key: str
    label: str
    value: str
    unit: Optional[str] = None


class AdvancedSolvePayload(BaseModel):
    test_inputs: list[TestInputItem] = Field(default_factory=list)


def _internal_error():
    logger.exception("Erro interno no solver")
    return JSONResponse(status_code=500, content={"message": "Ocorreu um erro, tente novamente mais tarde"})


def _get_session_or_404(db: Session, tenant_id: str, session_id: str) -> models.ProblemSession:
    session = (
        db.query(models.ProblemSession)
        .filter(models.ProblemSession.id == session_id, models.ProblemSession.tenant_id == tenant_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessao nao encontrada")
    return session


@router.post("/solver/sessions", status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreatePayload,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        if not payload.client_id and not (payload.client_other_text or "").strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cliente obrigatorio")
        if payload.model_unknown and payload.model_text:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Modelo invalido")
        if not payload.model_unknown and not payload.model_text:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Modelo obrigatorio")
        if payload.error_code_unknown and payload.error_code_text:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Codigo de erro invalido")
        if not payload.error_code_unknown and not payload.error_code_text:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Codigo de erro obrigatorio")

        session = service.create_session(db, current_user, payload.model_dump())
        return {"session_id": session.id, "status": session.status}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception:
        return _internal_error()


@router.post("/solver/sessions/{session_id}/attachments", status_code=status.HTTP_201_CREATED)
def upload_attachment(
    session_id: str,
    file: UploadFile,
    kind: str = Form(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        if kind not in {"brand", "model", "error_code", "other"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Tipo invalido")
        session = _get_session_or_404(db, current_user.tenant_id, session_id)
        attachment = service.add_attachment(db, session, current_user, file, kind)
        try:
            url = generate_signed_url(attachment.file_path)
        except Exception:
            url = None
        return {"attachment_id": attachment.id, "url": url}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception:
        return _internal_error()


@router.post("/solver/sessions/{session_id}/quick-solve")
def quick_solve(
    session_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        session = _get_session_or_404(db, current_user.tenant_id, session_id)
        result = service.run_quick_solve(db, session)
        return result.model_dump(mode="json")
    except HTTPException:
        raise
    except Exception:
        return _internal_error()


@router.post("/solver/sessions/{session_id}/advanced-solve")
def advanced_solve(
    session_id: str,
    payload: AdvancedSolvePayload,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        session = _get_session_or_404(db, current_user.tenant_id, session_id)
        items = [item.model_dump() for item in payload.test_inputs]
        result = service.run_advanced_solve(db, session, items)
        return result.model_dump(mode="json")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception:
        return _internal_error()


@router.post("/solver/sessions/{session_id}/resolve")
def resolve_session(
    session_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        session = _get_session_or_404(db, current_user.tenant_id, session_id)
        service.resolve_session(db, session)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception:
        return _internal_error()


@router.get("/solver/history")
def history(
    status_filter: str = "resolved",
    limit: int = 50,
    user_id: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        if status_filter != "resolved":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Filtro invalido")
        items = service.list_history(db, current_user.tenant_id, limit=limit, user_id=user_id)
        return {"items": items}
    except HTTPException:
        raise
    except Exception:
        return _internal_error()


@router.get("/solver/sessions/{session_id}")
def get_session(
    session_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        detail = service.get_session_detail(db, current_user.tenant_id, session_id)
        if not detail:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessao nao encontrada")
        return detail
    except HTTPException:
        raise
    except Exception:
        return _internal_error()


@router.post("/solver/sessions/{session_id}/public-link")
def create_public_link(
    session_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        session = _get_session_or_404(db, current_user.tenant_id, session_id)
        link = service.create_public_link(db, session, current_user.id)
        return {"url": f"/public/solver/{link.token}", "token": link.token, "expires_at": link.expires_at}
    except HTTPException:
        raise
    except Exception:
        return _internal_error()


@router.get("/solver/sessions/{session_id}/pdf")
def get_pdf(
    session_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        session = _get_session_or_404(db, current_user.tenant_id, session_id)
        result_payload = session.ai_advanced_result_json or session.ai_quick_result_json
        if not result_payload:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Sem resultado")
        names = service.list_catalog_names(db, session)
        pdf_bytes = render_solver_pdf(
            {
                "session": session,
                "names": names,
                "result": result_payload if isinstance(result_payload, dict) else {},
                "now": datetime.utcnow().strftime("%d/%m/%Y %H:%M"),
            }
        )
        return Response(content=pdf_bytes, media_type="application/pdf")
    except HTTPException:
        raise
    except Exception:
        return _internal_error()


@public_router.get("/public/solver/{token}", response_class=HTMLResponse)
def public_page(
    token: str,
    db: Session = Depends(get_db),
):
    link = service.get_public_link(db, token)
    if not link:
        return HTMLResponse("<h3>Link expirado ou invalido.</h3>", status_code=404)
    session = (
        db.query(models.ProblemSession)
        .filter(models.ProblemSession.id == link.session_id)
        .first()
    )
    if not session:
        return HTMLResponse("<h3>Registro nao encontrado.</h3>", status_code=404)
    payload = service.build_public_payload(db, session)
    result = payload.get("result") or {}
    html = render_public_solver_page(
        {
            "session": session,
            "names": payload.get("names") or {},
            "result": result,
            "download_url": f"/public/solver/{token}/pdf",
        }
    )
    return HTMLResponse(html)


@public_router.get("/public/solver/{token}/pdf")
def public_pdf(
    token: str,
    db: Session = Depends(get_db),
):
    link = service.get_public_link(db, token)
    if not link:
        return HTMLResponse("<h3>Link expirado ou invalido.</h3>", status_code=404)
    session = (
        db.query(models.ProblemSession)
        .filter(models.ProblemSession.id == link.session_id)
        .first()
    )
    if not session:
        return HTMLResponse("<h3>Registro nao encontrado.</h3>", status_code=404)
    result_payload = session.ai_advanced_result_json or session.ai_quick_result_json
    if not result_payload:
        return HTMLResponse("<h3>Registro sem resultado.</h3>", status_code=404)
    names = service.list_catalog_names(db, session)
    pdf_bytes = render_solver_pdf(
        {
            "session": session,
            "names": names,
            "result": result_payload if isinstance(result_payload, dict) else {},
            "now": datetime.utcnow().strftime("%d/%m/%Y %H:%M"),
        }
    )
    return Response(content=pdf_bytes, media_type="application/pdf")
