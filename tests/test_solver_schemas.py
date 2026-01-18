import unittest

from app.solver.schemas import SolverResult


class SolverSchemaTests(unittest.TestCase):
    def test_solver_result_valid(self):
        payload = {
            "summary": "Resumo simples",
            "probable_root_cause": "Causa provavel",
            "severity": "media",
            "safety_risk": "nenhum",
            "confidence": 0.6,
            "tests_required": [
                {
                    "key": "pressao_succao",
                    "label": "Pressao de succao",
                    "type": "number",
                    "unit": "psi",
                    "required": True,
                    "options": None,
                },
                {
                    "key": "temperatura",
                    "label": "Temperatura de retorno",
                    "type": "number",
                    "unit": "C",
                    "required": False,
                    "options": None,
                },
                {
                    "key": "energia",
                    "label": "Energia presente",
                    "type": "boolean",
                    "unit": None,
                    "required": True,
                    "options": None,
                },
            ],
            "tests_instructions": ["Teste 1", "Teste 2"],
            "action_plan": [
                {
                    "step": 1,
                    "action": "Verificar filtro",
                    "why": "Filtro sujo reduz fluxo",
                    "validation": "Pressao normalizada",
                }
            ],
            "when_to_escalate": ["Se persistir, acionar suporte"],
            "notes_for_work_order": {
                "service_done": "Inspecao",
                "cause": "Filtro sujo",
                "solution": "Limpeza",
                "observations": "Monitorar",
            },
        }
        result = SolverResult.model_validate(payload)
        self.assertEqual(result.severity, "media")

    def test_solver_result_invalid_confidence(self):
        payload = {
            "summary": "Resumo",
            "probable_root_cause": "Causa",
            "severity": "media",
            "safety_risk": "nenhum",
            "confidence": 1.5,
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
        with self.assertRaises(Exception):
            SolverResult.model_validate(payload)
