from jinja2 import Template


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
    when_to_escalate = [item for item in _as_list(result.get("when_to_escalate")) if item]
    return {
        "summary": result.get("summary") or "Nao informado",
        "probable_root_cause": result.get("probable_root_cause") or "Nao informado",
        "action_plan": action_plan,
        "when_to_escalate": when_to_escalate,
    }


_TEMPLATE = Template(
    """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>EAGL Solver</title>
  <style>
    :root {
      --bg: #0b1220;
      --card: #111827;
      --text: #e2e8f0;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --border: rgba(148, 163, 184, 0.2);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Inter", "Segoe UI", Arial, sans-serif;
      background: radial-gradient(circle at top, #0f172a, #0b1220 60%);
      color: var(--text);
    }
    .wrap {
      max-width: 980px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }
    header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 16px 20px;
      border-radius: 16px;
      background: var(--card);
      border: 1px solid var(--border);
      margin-bottom: 20px;
    }
    header h1 {
      margin: 0;
      font-size: 20px;
    }
    .chip {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent);
      font-size: 12px;
      font-weight: 600;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 18px;
      margin-bottom: 16px;
    }
    .card h2 {
      margin: 0 0 10px;
      font-size: 16px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }
    .field {
      background: rgba(15, 23, 42, 0.5);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 10px 12px;
    }
    .field label {
      display: block;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 6px;
    }
    .field span {
      font-size: 14px;
      font-weight: 600;
    }
    .summary {
      background: rgba(15, 23, 42, 0.5);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      color: var(--muted);
    }
    .list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .list-item {
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      background: rgba(15, 23, 42, 0.4);
    }
    .cta {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 12px 16px;
      border-radius: 12px;
      background: #38bdf8;
      color: #0b1220;
      font-weight: 700;
      text-decoration: none;
    }
    .muted {
      color: var(--muted);
      font-size: 13px;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>EAGL Solver</h1>
        <div class="muted">Solucionador guiado de problemas tecnicos</div>
        <div class="muted">Registro publico do diagnostico</div>
      </div>
      {% if names.area %}<span class="chip">{{ names.area }}</span>{% endif %}
    </header>

    <div class="card">
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

    <div class="card">
      <h2>Resumo do diagnostico</h2>
      <div class="summary">{{ result.summary or "Nao informado" }}</div>
    </div>

    <div class="card">
      <h2>Causa provavel</h2>
      <div class="summary">{{ result.probable_root_cause or "Nao informado" }}</div>
    </div>

    <div class="card">
      <h2>Plano de acao</h2>
      <div class="list">
        {% for step in result.action_plan %}
          <div class="list-item">
            <strong>Passo {{ step.step }} - {{ step.action }}</strong>
            <div class="muted">{{ step.why }}</div>
            <div class="muted">Validacao: {{ step.validation }}</div>
          </div>
        {% endfor %}
      </div>
    </div>

    <div class="card">
      <h2>Quando escalar</h2>
      <div class="list">
        {% for item in result.when_to_escalate %}
          <div class="list-item">{{ item }}</div>
        {% endfor %}
      </div>
    </div>

    {% if download_url %}
      <div class="card">
        <a class="cta" href="{{ download_url }}">Baixar PDF</a>
      </div>
    {% endif %}
  </div>
</body>
</html>
"""
)


def render_public_solver_page(payload: dict) -> str:
    safe_payload = dict(payload)
    safe_payload["result"] = _normalize_result(payload.get("result"))
    return _TEMPLATE.render(**safe_payload)
