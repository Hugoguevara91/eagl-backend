from jinja2 import Template
from weasyprint import HTML


_TEMPLATE = Template(
    """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8" />
  <style>
    :root {
      --ink: #0b1220;
      --text: #0f172a;
      --muted: #5b6472;
      --border: #e5e7eb;
      --card: #f8fafc;
      --cyan: #00b7d4;
      --pink: #f472b6;
      --chip: #e0f2fe;
    }
    * { box-sizing: border-box; }
    body {
      font-family: "Segoe UI", Arial, sans-serif;
      color: var(--text);
      margin: 20px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      padding: 18px 20px;
      border-radius: 18px;
      background: linear-gradient(120deg, #0b1220, #101827);
      color: #fff;
      margin-bottom: 18px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .brand img {
      width: 52px;
      height: 52px;
      object-fit: contain;
      background: #0b1220;
      padding: 6px;
      border-radius: 12px;
    }
    .brand-title {
      font-size: 18px;
      font-weight: 700;
    }
    .brand-subtitle {
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
      background: #111827;
      border: 1px solid #1f2937;
      font-size: 11px;
      font-weight: 600;
      color: #e2e8f0;
    }
    .section {
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px;
      margin-bottom: 14px;
      background: #fff;
    }
    .section h2 {
      font-size: 14px;
      margin: 0 0 10px;
      color: var(--ink);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px 16px;
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
    }
    .summary {
      background: var(--card);
      border-radius: 12px;
      padding: 12px 14px;
      font-size: 13px;
      color: var(--muted);
    }
    .timeline {
      display: grid;
      gap: 10px;
    }
    .timeline-item {
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 10px 12px;
    }
    .timeline-item strong {
      display: block;
      font-size: 13px;
    }
    .timeline-item span {
      font-size: 11px;
      color: var(--muted);
    }
    .check-list {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .question {
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: #fff;
    }
    .question h4 {
      margin: 0 0 6px;
      font-size: 13px;
      color: var(--ink);
    }
    .question p {
      margin: 0 0 8px;
      font-size: 12px;
      color: var(--muted);
    }
    .photos {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }
    .photos img {
      width: 100%;
      height: 100px;
      object-fit: cover;
      border-radius: 8px;
      border: 1px solid var(--border);
    }
    .footer {
      margin-top: 18px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .signature {
      border-top: 1px dashed var(--border);
      padding-top: 10px;
      font-size: 12px;
      color: var(--muted);
    }
    .signature img {
      margin-top: 8px;
      max-height: 80px;
      object-fit: contain;
    }
    .qr {
      margin-top: 16px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 12px;
      color: var(--muted);
    }
    .qr img {
      width: 84px;
      height: 84px;
    }
    .evidence {
      page-break-before: always;
    }
    .evidence h2 {
      margin-top: 0;
    }
  </style>
</head>
<body>
  <div class="header">
    <div class="brand">
      {% if logo_url %}<img src="{{ logo_url }}" alt="EAGL" />{% endif %}
      <div>
        <div class="brand-title">Ordem de Servico Guiada - EAGL</div>
        <div class="brand-subtitle">Emitido em {{ now }}</div>
      </div>
    </div>
    <div class="chips">
      {% if os.code_human %}<span class="chip">{{ os.code_human }}</span>{% endif %}
      {% if os.status %}<span class="chip">{{ os.status }}</span>{% endif %}
      {% if os.priority %}<span class="chip">Prioridade {{ os.priority }}</span>{% endif %}
      {% if os.type %}<span class="chip">Tipo {{ os.type }}</span>{% endif %}
    </div>
  </div>

  <div class="section">
    <h2>Resumo executivo</h2>
    <div class="summary">{{ os.description or "Nao informado" }}</div>
  </div>

  <div class="section">
    <h2>Cliente e contrato</h2>
    <div class="grid">
      <div class="field"><label>Cliente</label><span>{{ client.name or "Nao informado" }}</span></div>
      <div class="field"><label>Contrato</label><span>{{ os.contract_id or "Nao informado" }}</span></div>
      <div class="field"><label>Solicitante</label><span>{{ os.requester_name or "Nao informado" }}</span></div>
      <div class="field"><label>Telefone</label><span>{{ os.requester_phone or "Nao informado" }}</span></div>
      <div class="field"><label>Unidade</label><span>{{ site.name or "Nao informado" }}</span></div>
      <div class="field"><label>Responsavel</label><span>{{ os.responsible_user_id or "Nao informado" }}</span></div>
    </div>
  </div>

  <div class="section">
    <h2>Check-in e check-out</h2>
    <div class="grid">
      <div class="field"><label>Check-in</label><span>{{ checkin.timestamp or "Nao informado" }}</span></div>
      <div class="field"><label>Check-out</label><span>{{ checkout.timestamp or "Nao informado" }}</span></div>
      <div class="field"><label>Endereco check-in</label><span>{{ checkin.address.formatted or "Nao informado" }}</span></div>
      <div class="field"><label>Precisao</label><span>{{ checkin.accuracy or "Nao informado" }}</span></div>
      <div class="field"><label>Endereco check-out</label><span>{{ checkout.address.formatted or "Nao informado" }}</span></div>
      <div class="field"><label>Precisao</label><span>{{ checkout.accuracy or "Nao informado" }}</span></div>
    </div>
    {% if checkin.photos %}
      <div style="margin-top:10px;" class="photos">
        {% for photo in checkin.photos %}
          <img src="{{ photo }}" alt="Check-in" />
        {% endfor %}
      </div>
    {% endif %}
    {% if checkout.photos %}
      <div style="margin-top:10px;" class="photos">
        {% for photo in checkout.photos %}
          <img src="{{ photo }}" alt="Check-out" />
        {% endfor %}
      </div>
    {% endif %}
  </div>

  <div class="section">
    <h2>Equipamento</h2>
    <div class="grid">
      <div class="field"><label>Ativo</label><span>{{ asset.name or "Nao informado" }}</span></div>
      <div class="field"><label>Tag</label><span>{{ asset.tag or "Nao informado" }}</span></div>
      <div class="field"><label>Tipo</label><span>{{ asset.asset_type or "Nao informado" }}</span></div>
      <div class="field"><label>Status</label><span>{{ asset.status or "Nao informado" }}</span></div>
    </div>
  </div>

  <div class="section">
    <h2>Linha do tempo das atividades</h2>
    <div class="timeline">
      {% if activities %}
        {% for activity in activities %}
          <div class="timeline-item">
            <strong>{{ activity.name }}</strong>
            <span>Status {{ activity.status }} ? Duracao {{ activity.duration_text or "00:00:00" }}</span>
          </div>
        {% endfor %}
      {% else %}
        <span class="summary">Nenhuma atividade registrada.</span>
      {% endif %}
    </div>
  </div>

  <div class="section">
    <h2>Checklist guiado</h2>
    <div class="check-list">
      {% for item in answers %}
        <div class="question">
          <h4>{{ item.question_text }}</h4>
          <p>{{ item.answer or "Nao informado" }}</p>
          {% if item.photos %}
            <div class="photos">
              {% for photo in item.photos %}
                <img src="{{ photo }}" alt="Anexo" />
              {% endfor %}
            </div>
          {% endif %}
        </div>
      {% endfor %}
    </div>
  </div>

  <div class="section">
    <h2>Materiais / Pecas / Servicos</h2>
    <div class="summary">{{ materials or "Nao informado" }}</div>
  </div>

  <div class="section">
    <h2>Conclusao</h2>
    <div class="summary">{{ conclusion or "Nao informado" }}</div>
  </div>

  <div class="footer">
    <div class="signature">
      Assinatura tecnico: {{ signatures.tecnico.name or "Nao informado" }}
      {% if signatures.tecnico.image_url %}<img src="{{ signatures.tecnico.image_url }}" alt="Assinatura tecnico" />{% endif %}
    </div>
    <div class="signature">
      Assinatura cliente: {{ signatures.cliente.name or "Nao informado" }}
      {% if signatures.cliente.image_url %}<img src="{{ signatures.cliente.image_url }}" alt="Assinatura cliente" />{% endif %}
    </div>
  </div>

  {% if qr_data_url %}
    <div class="qr">
      <img src="{{ qr_data_url }}" alt="QR" />
      <div>Acesse esta OS online.</div>
    </div>
  {% endif %}

  {% if evidence %}
    <div class="evidence">
      <h2>Anexo de evidencias</h2>
      {% for section in evidence %}
        <div style="margin-bottom:12px;">
          <strong>{{ section.title }}</strong>
          <div class="photos" style="margin-top:8px;">
            {% for photo in section.photos %}
              <img src="{{ photo }}" alt="Evidencia" />
            {% endfor %}
          </div>
        </div>
      {% endfor %}
    </div>
  {% endif %}
</body>
</html>
"""
)



def render_os_pdf(payload: dict) -> bytes:
    html = _TEMPLATE.render(**payload)
    pdf = HTML(string=html).write_pdf()
    return pdf
