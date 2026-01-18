from typing import Any

from sqlalchemy.orm import Session

from app.db import models


def _entitlement_value(ent: models.PlanEntitlement | models.TenantOverride) -> Any:
    if ent.value_type == "BOOL":
        return ent.value_bool
    if ent.value_type == "INT":
        return ent.value_int
    return ent.value_string


class EntitlementsService:
    @staticmethod
    def get_effective_entitlements(db: Session, tenant_id: str) -> list[dict]:
        effective: dict[str, dict] = {}

        subscription = (
            db.query(models.Subscription)
            .filter(
                models.Subscription.tenant_id == tenant_id,
                models.Subscription.status.in_(["ATIVA", "TRIAL", "PAST_DUE"]),
            )
            .order_by(models.Subscription.created_at.desc())
            .first()
        )
        if subscription and subscription.plan:
            for ent in subscription.plan.entitlements:
                effective[ent.key] = {
                    "key": ent.key,
                    "value_type": ent.value_type,
                    "value": _entitlement_value(ent),
                    "source": "plan",
                }

        overrides = (
            db.query(models.TenantOverride)
            .filter(models.TenantOverride.tenant_id == tenant_id)
            .all()
        )
        for override in overrides:
            effective[override.key] = {
                "key": override.key,
                "value_type": override.value_type,
                "value": _entitlement_value(override),
                "source": "override",
                "override_id": override.id,
            }

        return list(effective.values())
