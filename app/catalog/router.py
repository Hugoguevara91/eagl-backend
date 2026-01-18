import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.catalog import service
from app.core.security import get_current_user
from app.db import models
from app.db.session import get_db

logger = logging.getLogger("eagl.catalog")

router = APIRouter(tags=["Catalog"])


@router.get("/catalog/areas")
def get_areas(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        items = service.list_areas(db, current_user.tenant_id)
        return {
            "items": [
                {"id": area.id, "code": area.code, "name": area.name}
                for area in items
            ]
        }
    except Exception:
        logger.exception("Erro ao listar areas do catalogo")
        return JSONResponse(status_code=500, content={"message": "Ocorreu um erro, tente novamente mais tarde"})


@router.get("/catalog/equipment-types")
def get_equipment_types(
    area_id: str = Query(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        items = service.list_equipment_types(db, current_user.tenant_id, area_id)
        return {
            "items": [
                {"id": item.id, "code": item.code, "name": item.name, "area_id": item.area_id}
                for item in items
            ]
        }
    except Exception:
        logger.exception("Erro ao listar tipos de equipamento")
        return JSONResponse(status_code=500, content={"message": "Ocorreu um erro, tente novamente mais tarde"})


@router.get("/catalog/brands")
def get_brands(
    equipment_type_id: str = Query(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        items = service.list_brands(db, current_user.tenant_id, equipment_type_id)
        return {
            "items": [
                {
                    "id": item.id,
                    "code": item.code,
                    "name": item.name,
                    "equipment_type_id": item.equipment_type_id,
                }
                for item in items
            ]
        }
    except Exception:
        logger.exception("Erro ao listar marcas do catalogo")
        return JSONResponse(status_code=500, content={"message": "Ocorreu um erro, tente novamente mais tarde"})
