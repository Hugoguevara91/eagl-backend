import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db import models
from app.db.session import get_db

router = APIRouter(tags=["Questionnaires"])


class QuestionnaireCreate(BaseModel):
    title: str = Field(..., min_length=1)
    status: str = "ATIVO"


class QuestionnaireUpdate(BaseModel):
    title: str | None = None
    status: str | None = None


class QuestionnaireResponse(BaseModel):
    id: str
    title: str
    version: int
    status: str
    created_at: str
    updated_at: str


def _to_response(item: models.Questionnaire) -> QuestionnaireResponse:
    return QuestionnaireResponse(
        id=item.id,
        title=item.title,
        version=item.version,
        status=item.status,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


@router.get("/questionnaires")
def list_questionnaires(
    current_user: models.User = Depends(require_permission("os.view")),
    db: Session = Depends(get_db),
):
    items = (
        db.query(models.Questionnaire)
        .filter(models.Questionnaire.tenant_id == current_user.tenant_id)
        .order_by(models.Questionnaire.created_at.desc())
        .all()
    )
    return {"items": [_to_response(item) for item in items]}


@router.post("/questionnaires", status_code=status.HTTP_201_CREATED)
def create_questionnaire(
    payload: QuestionnaireCreate,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    item = models.Questionnaire(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        title=payload.title,
        status=payload.status or "ATIVO",
        version=1,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"item": _to_response(item)}


@router.patch("/questionnaires/{questionnaire_id}")
def update_questionnaire(
    questionnaire_id: str,
    payload: QuestionnaireUpdate,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.Questionnaire)
        .filter(
            models.Questionnaire.id == questionnaire_id,
            models.Questionnaire.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionario nao encontrado")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return {"item": _to_response(item)}


@router.delete("/questionnaires/{questionnaire_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_questionnaire(
    questionnaire_id: str,
    current_user: models.User = Depends(require_permission("os.edit")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.Questionnaire)
        .filter(
            models.Questionnaire.id == questionnaire_id,
            models.Questionnaire.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionario nao encontrado")
    db.delete(item)
    db.commit()
    return None
