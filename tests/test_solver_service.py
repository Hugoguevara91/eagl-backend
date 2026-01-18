import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import models
from app.solver import service
from app.solver.schemas import SolverResult


def _make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _seed_catalog(db):
    area = models.CatalogArea(id="area-1", code="HVAC", name="HVAC", is_active=True, tenant_id=None)
    equipment = models.CatalogEquipmentType(
        id="type-1", area_id=area.id, code="VRF", name="VRF / VRV", is_active=True, tenant_id=None
    )
    brand = models.CatalogBrand(
        id="brand-1", equipment_type_id=equipment.id, code="LG", name="LG", is_active=True, tenant_id=None
    )
    db.add_all([area, equipment, brand])
    db.commit()
    return area, equipment, brand


class SolverServiceTests(unittest.TestCase):
    def test_validate_required_tests(self):
        required = SolverResult.model_validate(
            {
                "summary": "Resumo",
                "probable_root_cause": "Causa",
                "severity": "media",
                "safety_risk": "nenhum",
                "confidence": 0.5,
                "tests_required": [
                    {
                        "key": "t1",
                        "label": "Teste 1",
                        "type": "text",
                        "unit": None,
                        "required": True,
                        "options": None,
                    }
                ],
                "tests_instructions": [],
                "action_plan": [],
                "when_to_escalate": [],
                "notes_for_work_order": {
                    "service_done": "OK",
                    "cause": "OK",
                    "solution": "OK",
                    "observations": "OK",
                },
            }
        ).tests_required
        with self.assertRaises(ValueError):
            service._validate_required_tests(required, [{"key": "t2", "label": "Teste 2", "value": "x"}])

    def test_tenant_isolation(self):
        db = _make_db()
        tenant_a = models.Tenant(id="tenant-a", name="A")
        tenant_b = models.Tenant(id="tenant-b", name="B")
        user_a = models.User(id="user-a", tenant_id=tenant_a.id, name="User A", login="a", password_hash="x", role="TECNICO")
        db.add_all([tenant_a, tenant_b, user_a])
        _seed_catalog(db)
        session_a = models.ProblemSession(
            id="sess-a",
            tenant_id=tenant_a.id,
            user_id=user_a.id,
            user_name_snapshot="User A",
            status="resolved",
            area_id="area-1",
            equipment_type_id="type-1",
            brand_id="brand-1",
            model_text="X",
            model_unknown=False,
            error_code_text="E1",
            error_code_unknown=False,
            short_problem_text="Falha",
        )
        db.add(session_a)
        db.commit()
        detail = service.get_session_detail(db, tenant_b.id, session_a.id)
        self.assertIsNone(detail)

    @patch("app.solver.service.request_solver_result")
    def test_run_quick_solve(self, mock_request):
        db = _make_db()
        tenant = models.Tenant(id="tenant-1", name="A")
        user = models.User(id="user-1", tenant_id=tenant.id, name="User", login="u", password_hash="x", role="TECNICO")
        db.add_all([tenant, user])
        _seed_catalog(db)
        session = models.ProblemSession(
            id="sess-1",
            tenant_id=tenant.id,
            user_id=user.id,
            user_name_snapshot="User",
            status="draft",
            area_id="area-1",
            equipment_type_id="type-1",
            brand_id="brand-1",
            model_text="X",
            model_unknown=False,
            error_code_text="E1",
            error_code_unknown=False,
            short_problem_text="Falha",
        )
        db.add(session)
        db.commit()

        dummy = SolverResult.model_validate(
            {
                "summary": "Resumo",
                "probable_root_cause": "Causa",
                "severity": "media",
                "safety_risk": "nenhum",
                "confidence": 0.5,
                "tests_required": [],
                "tests_instructions": [],
                "action_plan": [],
                "when_to_escalate": [],
                "notes_for_work_order": {
                    "service_done": "OK",
                    "cause": "OK",
                    "solution": "OK",
                    "observations": "OK",
                },
            }
        )
        mock_request.return_value = (dummy, {"model": "gpt-4o-mini", "input_tokens": 10, "output_tokens": 20, "latency_ms": 1})
        result = service.run_quick_solve(db, session)
        self.assertEqual(result.summary, "Resumo")
        self.assertEqual(session.status, "answered")
