from sqlalchemy.orm import Session

from app.db import models


def list_areas(db: Session, tenant_id: str) -> list[models.CatalogArea]:
    return (
        db.query(models.CatalogArea)
        .filter(
            models.CatalogArea.is_active.is_(True),
            (models.CatalogArea.tenant_id == tenant_id) | (models.CatalogArea.tenant_id.is_(None)),
        )
        .order_by(models.CatalogArea.name.asc())
        .all()
    )


def list_equipment_types(db: Session, tenant_id: str, area_id: str) -> list[models.CatalogEquipmentType]:
    return (
        db.query(models.CatalogEquipmentType)
        .filter(
            models.CatalogEquipmentType.area_id == area_id,
            models.CatalogEquipmentType.is_active.is_(True),
            (models.CatalogEquipmentType.tenant_id == tenant_id)
            | (models.CatalogEquipmentType.tenant_id.is_(None)),
        )
        .order_by(models.CatalogEquipmentType.name.asc())
        .all()
    )


def list_brands(db: Session, tenant_id: str, equipment_type_id: str) -> list[models.CatalogBrand]:
    return (
        db.query(models.CatalogBrand)
        .filter(
            models.CatalogBrand.equipment_type_id == equipment_type_id,
            models.CatalogBrand.is_active.is_(True),
            (models.CatalogBrand.tenant_id == tenant_id) | (models.CatalogBrand.tenant_id.is_(None)),
        )
        .order_by(models.CatalogBrand.name.asc())
        .all()
    )
