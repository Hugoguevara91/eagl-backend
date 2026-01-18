from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.scan.schemas import ScanSignals


BLOCKS = [
    "CONTROLE_COMUNICACAO",
    "SENSORIAMENTO",
    "ATUACAO",
    "REFRIGERACAO",
    "VENTILACAO_TROCA",
    "ELETRICA_ALIMENTACAO",
]

DEFAULT_TITLES = {
    "CONTROLE_COMUNICACAO": "Possivel falha de comunicacao ou controle",
    "SENSORIAMENTO": "Possivel falha de sensor/leitura",
    "ATUACAO": "Possivel falha de atuador/comando",
    "REFRIGERACAO": "Possivel falha no circuito de refrigeracao",
    "VENTILACAO_TROCA": "Possivel falha de ventilacao ou troca termica",
    "ELETRICA_ALIMENTACAO": "Possivel falha eletrica ou alimentacao",
}


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _flatten_texts(values: list[str]) -> str:
    return " ".join(_normalize(value) for value in values if value)


def _contains_any(text: str, keywords: list[str]) -> bool:
    if not text:
        return False
    return any(keyword in text for keyword in keywords)


def _collect_texts(signals: ScanSignals) -> dict[str, list[str]]:
    return {
        "alarms": [
            *(alarm.texto or "" for alarm in signals.alarmes),
            *(alarm.codigo or "" for alarm in signals.alarmes),
        ],
        "status": [
            *(status.ponto or "" for status in signals.status_pontos),
            *(status.valor or "" for status in signals.status_pontos),
        ],
        "readings": [
            *(reading.nome or "" for reading in signals.leituras),
            *(reading.valor or "" for reading in signals.leituras),
        ],
        "trends": [
            *(trend.variavel or "" for trend in signals.tendencias),
            *(trend.observacao or "" for trend in signals.tendencias),
        ],
        "comms": list(signals.comunicacao.indicadores or []),
        "inconsistencias": list(signals.inconsistencias or []),
    }


def _detect_command_feedback_mismatch(signals: ScanSignals) -> bool:
    command_values: dict[str, str] = {}
    feedback_values: dict[str, str] = {}
    for status in signals.status_pontos:
        name = _normalize(status.ponto)
        value = _normalize(status.valor)
        if not name or not value:
            continue
        if "command" in name or "comando" in name or "cmd" in name:
            command_values[name] = value
        if "feedback" in name or "retorno" in name or "fbk" in name:
            feedback_values[name] = value

    for cmd_name, cmd_value in command_values.items():
        if "on" in cmd_value or "ligado" in cmd_value:
            for fbk_value in feedback_values.values():
                if "off" in fbk_value or "desligado" in fbk_value:
                    return True
    return False


def _count_trends(signals: ScanSignals, behavior: str) -> int:
    return sum(1 for trend in signals.tendencias if trend.comportamento == behavior)


@dataclass
class Rule:
    id: str
    block: str
    points: int
    evidence: str
    match: Callable[[], bool]


def evaluate_scan_rules(
    signals: ScanSignals,
    problema_texto: str,
    problema_tags: list[str],
) -> dict:
    scores: dict[str, int] = {block: 0 for block in BLOCKS}
    evidence_map: dict[str, list[str]] = {block: [] for block in BLOCKS}

    text_groups = _collect_texts(signals)
    alarms_text = _flatten_texts(text_groups["alarms"])
    status_text = _flatten_texts(text_groups["status"])
    readings_text = _flatten_texts(text_groups["readings"])
    trends_text = _flatten_texts(text_groups["trends"])
    comms_text = _flatten_texts(text_groups["comms"])
    inconsistencias_text = _flatten_texts(text_groups["inconsistencias"])
    problema_text = _normalize(problema_texto)
    tags_text = _flatten_texts(problema_tags)

    rules: list[Rule] = [
        Rule(
            id="comm_alarm_terms",
            block="CONTROLE_COMUNICACAO",
            points=30,
            evidence="Alarmes mencionam falha de comunicacao/controle",
            match=lambda: _contains_any(
                alarms_text,
                ["comm", "offline", "no response", "communication fault", "comunicacao", "sem resposta"],
            ),
        ),
        Rule(
            id="comm_problem_text",
            block="CONTROLE_COMUNICACAO",
            points=20,
            evidence="Problema relatado indica falha de comunicacao",
            match=lambda: _contains_any(problema_text, ["sem comunic", "offline", "sem resposta"]),
        ),
        Rule(
            id="comm_signal_flag",
            block="CONTROLE_COMUNICACAO",
            points=40,
            evidence="Sinal de comunicacao com possivel falha",
            match=lambda: bool(signals.comunicacao.possivel_falha),
        ),
        Rule(
            id="comm_trends_stuck",
            block="CONTROLE_COMUNICACAO",
            points=15,
            evidence="Tendencias travadas em varias variaveis",
            match=lambda: _count_trends(signals, "travado") >= 2,
        ),
        Rule(
            id="comm_status_terms",
            block="CONTROLE_COMUNICACAO",
            points=20,
            evidence="Status indica timeout/no response",
            match=lambda: _contains_any(status_text, ["timeout", "no response", "sem resposta"]),
        ),
        Rule(
            id="sensor_trend_stuck",
            block="SENSORIAMENTO",
            points=35,
            evidence="Tendencia travada em sensor critico",
            match=lambda: _contains_any(trends_text, ["sensor", "temp", "temperatura", "pressao", "pressure"])
            and _count_trends(signals, "travado") >= 1,
        ),
        Rule(
            id="sensor_out_of_range",
            block="SENSORIAMENTO",
            points=40,
            evidence="Leitura fora de faixa ou invalida",
            match=lambda: _contains_any(readings_text, ["-40", "999", "open", "short", "aberto", "curto"]),
        ),
        Rule(
            id="sensor_alarm_terms",
            block="SENSORIAMENTO",
            points=30,
            evidence="Alarmes citam sensores/termistores",
            match=lambda: _contains_any(
                alarms_text, ["sensor", "thermistor", "temp probe", "pressure transducer", "termistor"]
            ),
        ),
        Rule(
            id="sensor_status_terms",
            block="SENSORIAMENTO",
            points=20,
            evidence="Status menciona falha de sensor",
            match=lambda: _contains_any(status_text, ["sensor", "thermistor", "probe"]),
        ),
        Rule(
            id="sensor_inconsistencias",
            block="SENSORIAMENTO",
            points=15,
            evidence="Inconsistencias encontradas nas leituras",
            match=lambda: bool(inconsistencias_text),
        ),
        Rule(
            id="actuation_cmd_feedback",
            block="ATUACAO",
            points=35,
            evidence="Comando ON sem retorno de atuacao",
            match=lambda: _detect_command_feedback_mismatch(signals),
        ),
        Rule(
            id="actuation_alarm_terms",
            block="ATUACAO",
            points=30,
            evidence="Alarmes indicam falha de atuacao",
            match=lambda: _contains_any(
                alarms_text, ["valve", "damper", "actuator", "relay", "valvula", "damper", "atuador", "rele"]
            ),
        ),
        Rule(
            id="actuation_status_terms",
            block="ATUACAO",
            points=25,
            evidence="Status aponta falha de atuador",
            match=lambda: _contains_any(status_text, ["actuator", "atuador", "valve", "valvula", "damper"]),
        ),
        Rule(
            id="actuation_tag_no_start",
            block="ATUACAO",
            points=20,
            evidence="Tag indica falha de partida/atuacao",
            match=lambda: _contains_any(tags_text, ["nao liga", "arme e desarma", "arma e desarma"])
            and _contains_any(status_text, ["command", "comando", "off", "desligado"]),
        ),
        Rule(
            id="ventilation_tag_low_cooling",
            block="VENTILACAO_TROCA",
            points=25,
            evidence="Baixa capacidade com alarmes de alta temperatura/condensacao",
            match=lambda: _contains_any(tags_text, ["gela pouco"])
            and _contains_any(alarms_text, ["high temp", "alta temperatura", "condensing", "condensacao"]),
        ),
        Rule(
            id="ventilation_fan_fault",
            block="VENTILACAO_TROCA",
            points=35,
            evidence="Falha ou baixa rotacao do ventilador",
            match=lambda: _contains_any(
                readings_text + " " + alarms_text, ["fan", "blower", "rpm", "ventilador", "fan fault", "low"]
            ),
        ),
        Rule(
            id="ventilation_trend_stuck",
            block="VENTILACAO_TROCA",
            points=25,
            evidence="Tendencia de fan travada",
            match=lambda: _contains_any(trends_text, ["fan", "ventilador"])
            and _count_trends(signals, "travado") >= 1,
        ),
        Rule(
            id="ventilation_airflow_text",
            block="VENTILACAO_TROCA",
            points=15,
            evidence="Problema relatado indica baixa ventilacao",
            match=lambda: _contains_any(problema_text, ["fluxo de ar", "ventilacao", "troca termica"]),
        ),
        Rule(
            id="refrigeration_alarm_terms",
            block="REFRIGERACAO",
            points=30,
            evidence="Alarmes/leituras indicam falha de refrigeracao",
            match=lambda: _contains_any(
                alarms_text + " " + readings_text,
                ["low pressure", "high pressure", "eev", "superheat", "subcool", "pressao"],
            ),
        ),
        Rule(
            id="refrigeration_cycle_tag",
            block="REFRIGERACAO",
            points=35,
            evidence="Ciclos de arme/desarme com alarme de pressao",
            match=lambda: _contains_any(tags_text, ["arma e desarma"])
            and _contains_any(alarms_text, ["pressure", "pressao"]),
        ),
        Rule(
            id="refrigeration_superheat",
            block="REFRIGERACAO",
            points=20,
            evidence="Leituras de superheat/subcool fora do normal",
            match=lambda: _contains_any(readings_text, ["superheat", "subcool"]),
        ),
        Rule(
            id="refrigeration_leak_text",
            block="REFRIGERACAO",
            points=25,
            evidence="Problema relatado sugere falha de refrigerante",
            match=lambda: _contains_any(problema_text, ["vazamento", "refrigerante", "gas", "gas refrigerante"]),
        ),
        Rule(
            id="power_alarm_terms",
            block="ELETRICA_ALIMENTACAO",
            points=40,
            evidence="Alarmes indicam falha eletrica/alimentacao",
            match=lambda: _contains_any(
                alarms_text,
                ["phase", "under voltage", "over voltage", "power fault", "subtensao", "sobretensao"],
            ),
        ),
        Rule(
            id="power_reset_terms",
            block="ELETRICA_ALIMENTACAO",
            points=25,
            evidence="Status indica reset ou power cycle",
            match=lambda: _contains_any(
                status_text + " " + alarms_text, ["reset", "reboot", "power cycle", "queda de energia"]
            ),
        ),
        Rule(
            id="power_problem_text",
            block="ELETRICA_ALIMENTACAO",
            points=20,
            evidence="Problema relatado indica falha eletrica",
            match=lambda: _contains_any(problema_text, ["disjuntor", "energia", "fase", "eletrico"]),
        ),
        Rule(
            id="comms_indicator_terms",
            block="CONTROLE_COMUNICACAO",
            points=15,
            evidence="Indicadores de comunicacao mencionados",
            match=lambda: _contains_any(comms_text, ["offline", "no response", "sem comunicacao", "timeout"]),
        ),
    ]

    for rule in rules:
        if rule.match():
            scores[rule.block] = min(100, scores[rule.block] + rule.points)
            evidence_map[rule.block].append(rule.evidence)

    hypotheses = [
        {
            "block": block,
            "score": score,
            "titulo": DEFAULT_TITLES.get(block, block),
            "evidencias": evidence_map[block],
        }
        for block, score in scores.items()
        if score > 0
    ]
    hypotheses.sort(key=lambda item: item["score"], reverse=True)

    return {
        "scores_by_block": scores,
        "hypotheses": hypotheses,
        "evidence_map": evidence_map,
    }
