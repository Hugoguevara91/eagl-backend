from jinja2 import Template
from weasyprint import HTML


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _normalize_result(result: object) -> dict:
    if not isinstance(result, dict):
        result = {}
    action_plan = []
    for idx, item in enumerate(_as_list(result.get("action_plan"))):
        if isinstance(item, dict):
            action_plan.append(
                {
                    "step": item.get("step") or (idx + 1),
                    "action": item.get("action") or "Nao informado",
                    "why": item.get("why") or "Nao informado",
                    "validation": item.get("validation") or "Nao informado",
                }
            )
    tests_required = []
    for item in _as_list(result.get("tests_required")):
        if isinstance(item, dict):
            tests_required.append(
                {
                    "label": item.get("label") or "Nao informado",
                    "type": item.get("type") or "Nao informado",
                    "unit": item.get("unit"),
                }
            )
    when_to_escalate = [item for item in _as_list(result.get("when_to_escalate")) if item]
    return {
        "summary": result.get("summary") or "Nao informado",
        "probable_root_cause": result.get("probable_root_cause") or "Nao informado",
        "action_plan": action_plan,
        "tests_required": tests_required,
        "when_to_escalate": when_to_escalate,
    }


_TEMPLATE = Template(
    """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8" />
  <style>
    :root {
      --eagl-cyan: #00c8ff;
      --eagl-pink: #ec4899;
      --dark: #0b1220;
      --text: #0f172a;
      --muted: #475569;
      --border: #e2e8f0;
      --card: #f8fafc;
    }
    * { box-sizing: border-box; }
    body {
      font-family: "Segoe UI", Arial, sans-serif;
      color: var(--text);
      margin: 24px;
      background: #ffffff;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      padding: 18px 20px;
      border-radius: 16px;
      background: linear-gradient(120deg, #0b1220 0%, #111827 55%, #0b1220 100%);
      color: #f8fafc;
      margin-bottom: 20px;
      border: 1px solid rgba(0, 200, 255, 0.25);
      box-shadow: 0 12px 24px rgba(2, 6, 23, 0.2);
    }
    .brand {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      font-size: 18px;
      font-weight: 700;
    }
    .logo {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      height: 32px;
      padding: 0 12px;
      border-radius: 999px;
      background: var(--eagl-cyan);
      color: var(--dark);
      font-size: 12px;
      letter-spacing: 0.24em;
      font-weight: 800;
      flex-shrink: 0;
    }
    .brand-text {
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 0;
    }
    .divider {
      height: 4px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--eagl-cyan), var(--eagl-pink));
      margin: 12px 0 18px;
    }
    .subtitle {
      font-size: 12px;
      color: #cbd5f5;
    }
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }
    .chip {
      padding: 4px 10px;
      border-radius: 999px;
      background: rgba(0, 200, 255, 0.2);
      font-size: 11px;
      font-weight: 700;
      color: #dbeafe;
      border: 1px solid rgba(0, 200, 255, 0.35);
    }
    .section {
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px;
      margin-bottom: 16px;
      background: #ffffff;
    }
    .section h2 {
      font-size: 15px;
      margin: 0 0 10px;
      color: var(--dark);
      border-left: 4px solid var(--eagl-cyan);
      padding-left: 8px;
      letter-spacing: 0.02em;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px 16px;
    }
    .field {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 10px 12px;
    }
    .field label {
      display: block;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 4px;
    }
    .field span {
      font-size: 13px;
      font-weight: 600;
      color: var(--dark);
    }
    .summary {
      background: var(--card);
      border-radius: 12px;
      padding: 12px 14px;
      font-size: 13px;
      color: var(--muted);
      border: 1px solid var(--border);
    }
    .list {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .list-item {
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: #fff;
    }
    .list-item h4 {
      margin: 0 0 6px;
      font-size: 13px;
      color: var(--dark);
    }
    .list-item p {
      margin: 0;
      font-size: 12px;
      color: var(--muted);
    }
    .footer {
      margin-top: 18px;
      font-size: 11px;
      color: var(--muted);
      display: flex;
      justify-content: space-between;
      border-top: 1px solid var(--border);
      padding-top: 8px;
    }
  </style>
</head>
<body>
  <div class="header">
    <div class="brand">
      <span class="logo">EAGL</span>
      <div class="brand-text">
        <div>EAGL Solver</div>
        <div class="subtitle">Solucionador guiado de problemas tecnicos</div>
        <div class="subtitle">Emitido em {{ now }}</div>
      </div>
    </div>
    <div class="chips">
      {% if session.status %}<span class="chip">{{ session.status }}</span>{% endif %}
      {% if names.area %}<span class="chip">{{ names.area }}</span>{% endif %}
    </div>
  </div>

  <div class="divider"></div>

  <div class="section">
    <h2>Dados informados</h2>
    <div class="grid">
      <div class="field"><label>Cliente</label><span>{{ names.client }}</span></div>
      <div class="field"><label>Area</label><span>{{ names.area }}</span></div>
      <div class="field"><label>Tipo</label><span>{{ names.equipment_type }}</span></div>
      <div class="field"><label>Marca</label><span>{{ names.brand }}</span></div>
      <div class="field"><label>Modelo</label><span>{{ session.model_text or ("Nao sei" if session.model_unknown else "Nao informado") }}</span></div>
      <div class="field"><label>Codigo de erro</label><span>{{ session.error_code_text or ("Nao sei" if session.error_code_unknown else "Nao informado") }}</span></div>
      <div class="field"><label>Problema</label><span>{{ session.short_problem_text }}</span></div>
      <div class="field"><label>Registrado por</label><span>{{ session.user_name_snapshot }}</span></div>
      <div class="field"><label>Data</label><span>{{ session.created_at }}</span></div>
    </div>
  </div>

  <div class="section">
    <h2>Resumo do diagnostico</h2>
    <div class="summary">{{ result.summary or "Nao informado" }}</div>
  </div>

  <div class="section">
    <h2>Causa provavel</h2>
    <div class="summary">{{ result.probable_root_cause or "Nao informado" }}</div>
  </div>

  <div class="section">
    <h2>Plano de acao</h2>
    <div class="list">
      {% for step in result.action_plan %}
        <div class="list-item">
          <h4>Passo {{ step.step }} - {{ step.action }}</h4>
          <p>{{ step.why }}</p>
          <p>Validacao: {{ step.validation }}</p>
        </div>
      {% endfor %}
    </div>
  </div>

  <div class="section">
    <h2>Testes solicitados</h2>
    <div class="list">
      {% for test in result.tests_required %}
        <div class="list-item">
          <h4>{{ test.label }}</h4>
          {% if test.unit %}<p>Unidade: {{ test.unit }}</p>{% endif %}
        </div>
      {% endfor %}
    </div>
  </div>

  <div class="section">
    <h2>Quando escalar</h2>
    <div class="list">
      {% for item in result.when_to_escalate %}
        <div class="list-item">{{ item }}</div>
      {% endfor %}
    </div>
  </div>

  <div class="footer">
    <span>EAGL - Tecnologia aplicada a manutencao e engenharia</span>
    <span>Gerado pelo EAGL Solver</span>
  </div>
</body>
</html>
"""
)


def render_solver_pdf(payload: dict) -> bytes:
    safe_payload = dict(payload)
    safe_payload["result"] = _normalize_result(payload.get("result"))
    html = _TEMPLATE.render(**safe_payload)
    return HTML(string=html).write_pdf()
