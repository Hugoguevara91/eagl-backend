import json
import logging
import os
import time
from typing import Any, Optional

import httpx

from app.scan.schemas import ScanReport, ScanSignals


class OpenAIError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


logger = logging.getLogger("eagl.scan")


def _get_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise OpenAIError("OPENAI_API_KEY nao configurada")
    return api_key


def _extract_json_candidate(raw_text: str) -> str:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON nao encontrado no texto")
    return raw_text[start : end + 1]


def _extract_error_message(res: httpx.Response) -> str:
    try:
        payload = res.json()
    except Exception:
        return res.text
    if isinstance(payload, dict):
        err = payload.get("error") or {}
        return err.get("message") or payload.get("message") or res.text
    return res.text


def _request_with_retry(
    client: httpx.Client,
    url: str,
    body: dict,
    max_attempts: int = 2,
) -> dict:
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            res = client.post(url, json=body)
            if res.status_code >= 400:
                message = _extract_error_message(res)
                raise OpenAIError(f"OpenAI erro HTTP {res.status_code}: {message}", status_code=res.status_code)
            return res.json()
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= max_attempts:
                break
            time.sleep(0.4)
    raise OpenAIError(str(last_exc) if last_exc else "Falha na chamada OpenAI")


def _parse_scan_signals(raw_text: str) -> ScanSignals:
    if not raw_text or not raw_text.strip():
        raise OpenAIError("Resposta vazia do modelo")
    try:
        return ScanSignals.model_validate_json(raw_text)
    except Exception:
        try:
            data = json.loads(raw_text)
        except Exception:
            candidate = _extract_json_candidate(raw_text)
            data = json.loads(candidate)
    return ScanSignals.model_validate(data)


def _parse_scan_report(raw_text: str) -> ScanReport:
    if not raw_text or not raw_text.strip():
        raise OpenAIError("Resposta vazia do modelo")
    try:
        return ScanReport.model_validate_json(raw_text)
    except Exception:
        try:
            data = json.loads(raw_text)
        except Exception:
            candidate = _extract_json_candidate(raw_text)
            data = json.loads(candidate)
    return ScanReport.model_validate(data)


def _scan_signals_json_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "extraction_confidence",
            "observacoes_gerais",
            "alarmes",
            "status_pontos",
            "leituras",
            "tendencias",
            "comunicacao",
            "inconsistencias",
        ],
        "properties": {
            "extraction_confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "observacoes_gerais": {"type": "string"},
            "alarmes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["texto", "codigo", "gravidade", "fonte_imagem_index"],
                    "properties": {
                        "texto": {"type": "string"},
                        "codigo": {"type": "string"},
                        "gravidade": {"type": "string", "enum": ["baixa", "media", "alta"]},
                        "fonte_imagem_index": {"type": "integer", "minimum": 0},
                    },
                },
            },
            "status_pontos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["ponto", "valor", "unidade", "fonte_imagem_index"],
                    "properties": {
                        "ponto": {"type": "string"},
                        "valor": {"type": "string"},
                        "unidade": {"type": "string"},
                        "fonte_imagem_index": {"type": "integer", "minimum": 0},
                    },
                },
            },
            "leituras": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["nome", "valor", "unidade", "fonte_imagem_index"],
                    "properties": {
                        "nome": {"type": "string"},
                        "valor": {"type": "string"},
                        "unidade": {"type": "string"},
                        "fonte_imagem_index": {"type": "integer", "minimum": 0},
                    },
                },
            },
            "tendencias": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["variavel", "comportamento", "observacao", "fonte_imagem_index"],
                    "properties": {
                        "variavel": {"type": "string"},
                        "comportamento": {
                            "type": "string",
                            "enum": ["estavel", "oscilando", "subindo", "descendo", "travado"],
                        },
                        "observacao": {"type": "string"},
                        "fonte_imagem_index": {"type": "integer", "minimum": 0},
                    },
                },
            },
            "comunicacao": {
                "type": "object",
                "additionalProperties": False,
                "required": ["possivel_falha", "indicadores"],
                "properties": {
                    "possivel_falha": {"type": "boolean"},
                    "indicadores": {"type": "array", "items": {"type": "string"}},
                },
            },
            "inconsistencias": {"type": "array", "items": {"type": "string"}},
        },
    }


def _scan_report_json_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "confidence_overall",
            "top_hypotheses",
            "o_que_validar_em_campo_agora",
            "risco_operacao",
            "limites",
        ],
        "properties": {
            "confidence_overall": {"type": "number", "minimum": 0, "maximum": 1},
            "top_hypotheses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "rank",
                        "bloco_local",
                        "probabilidade",
                        "titulo",
                        "evidencias",
                        "o_que_validar",
                        "observacoes",
                    ],
                    "properties": {
                        "rank": {"type": "integer", "minimum": 1},
                        "bloco_local": {"type": "string"},
                        "probabilidade": {"type": "number", "minimum": 0, "maximum": 1},
                        "titulo": {"type": "string"},
                        "evidencias": {"type": "array", "items": {"type": "string"}},
                        "o_que_validar": {"type": "array", "items": {"type": "string"}},
                        "observacoes": {"type": "string"},
                    },
                },
            },
            "o_que_validar_em_campo_agora": {"type": "array", "items": {"type": "string"}},
            "risco_operacao": {
                "type": "object",
                "additionalProperties": False,
                "required": ["nivel", "motivo"],
                "properties": {
                    "nivel": {"type": "string", "enum": ["Baixo", "Medio", "Alto"]},
                    "motivo": {"type": "string"},
                },
            },
            "limites": {"type": "array", "items": {"type": "string"}},
        },
    }


def _build_responses_messages(
    system_prompt: str,
    user_prompt: str,
    images: Optional[list[str]],
) -> list[dict]:
    messages = [
        {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
        {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
    ]
    if images:
        image_blocks = [{"type": "input_image", "image_url": url} for url in images]
        messages[-1]["content"].extend(image_blocks)
    return messages


def _build_chat_messages(
    system_prompt: str,
    user_prompt: str,
    images: Optional[list[str]],
) -> list[dict]:
    content: list[dict] = [{"type": "text", "text": user_prompt}]
    if images:
        content.extend({"type": "image_url", "image_url": {"url": url}} for url in images)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]


def _should_fallback_to_chat(exc: Exception) -> bool:
    if isinstance(exc, OpenAIError) and exc.status_code in {404, 405}:
        return True
    message = str(exc).lower()
    return "responses" in message and ("not found" in message or "unknown" in message)


def _extract_text(payload: dict) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    output = payload.get("output") or []
    for item in output:
        contents = item.get("content") or []
        for content in contents:
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text
    choices = payload.get("choices") or []
    if choices:
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            for part in content:
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    return text
    raise OpenAIError("Resposta sem texto")


def _request_openai_json(
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    images: Optional[list[str]],
    name: str,
) -> tuple[str, dict[str, Any], bool]:
    api_key = _get_api_key()
    start = time.perf_counter()
    headers = {"Authorization": f"Bearer {api_key}"}

    responses_body = {
        "model": model,
        "input": _build_responses_messages(system_prompt, user_prompt, images),
        "temperature": 0.2,
        "text": {
            "format": {
                "type": "json_schema",
                "name": name,
                "schema": schema,
                "strict": True,
            }
        },
    }
    chat_body = {
        "model": model,
        "messages": _build_chat_messages(system_prompt, user_prompt, images),
        "temperature": 0.2,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": name, "schema": schema, "strict": True},
        },
    }

    with httpx.Client(headers=headers, timeout=35.0) as client:
        try:
            payload = _request_with_retry(client, "https://api.openai.com/v1/responses", responses_body)
            used_chat = False
        except Exception as exc:
            if not _should_fallback_to_chat(exc):
                raise
            logger.warning("Falha no endpoint /responses, tentando /chat/completions: %s", exc)
            payload = _request_with_retry(client, "https://api.openai.com/v1/chat/completions", chat_body)
            used_chat = True

    raw_text = _extract_text(payload)
    latency_ms = int((time.perf_counter() - start) * 1000)
    usage = payload.get("usage") or {}
    meta = {
        "model": payload.get("model", model),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "latency_ms": latency_ms,
    }
    return raw_text, meta, used_chat


def request_scan_signals(
    model: str,
    system_prompt: str,
    user_prompt: str,
    images: Optional[list[str]],
) -> tuple[ScanSignals, dict[str, Any]]:
    schema = _scan_signals_json_schema()
    raw_text, meta, used_chat = _request_openai_json(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=schema,
        images=images,
        name="scan_signals",
    )
    try:
        result = _parse_scan_signals(raw_text)
    except Exception:
        correction_prompt = (
            "Corrija o JSON abaixo para seguir exatamente o schema solicitado. "
            "Responda somente com JSON valido, sem comentarios.\n\n"
            f"{raw_text}"
        )
        if used_chat:
            correction_body = {
                "model": model,
                "messages": _build_chat_messages(system_prompt, correction_prompt, None),
                "temperature": 0,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "scan_signals", "schema": schema, "strict": True},
                },
            }
            correction_url = "https://api.openai.com/v1/chat/completions"
        else:
            correction_body = {
                "model": model,
                "input": _build_responses_messages(system_prompt, correction_prompt, None),
                "temperature": 0,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "scan_signals",
                        "schema": schema,
                        "strict": True,
                    }
                },
            }
            correction_url = "https://api.openai.com/v1/responses"
        with httpx.Client(headers={"Authorization": f"Bearer {_get_api_key()}"}, timeout=35.0) as client:
            correction_payload = _request_with_retry(client, correction_url, correction_body)
        corrected_text = _extract_text(correction_payload)
        result = _parse_scan_signals(corrected_text)
    return result, meta


def request_scan_report(
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[ScanReport, dict[str, Any]]:
    schema = _scan_report_json_schema()
    raw_text, meta, used_chat = _request_openai_json(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=schema,
        images=None,
        name="scan_report",
    )
    try:
        result = _parse_scan_report(raw_text)
    except Exception:
        correction_prompt = (
            "Corrija o JSON abaixo para seguir exatamente o schema solicitado. "
            "Responda somente com JSON valido, sem comentarios.\n\n"
            f"{raw_text}"
        )
        if used_chat:
            correction_body = {
                "model": model,
                "messages": _build_chat_messages(system_prompt, correction_prompt, None),
                "temperature": 0,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "scan_report", "schema": schema, "strict": True},
                },
            }
            correction_url = "https://api.openai.com/v1/chat/completions"
        else:
            correction_body = {
                "model": model,
                "input": _build_responses_messages(system_prompt, correction_prompt, None),
                "temperature": 0,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "scan_report",
                        "schema": schema,
                        "strict": True,
                    }
                },
            }
            correction_url = "https://api.openai.com/v1/responses"
        with httpx.Client(headers={"Authorization": f"Bearer {_get_api_key()}"}, timeout=35.0) as client:
            correction_payload = _request_with_retry(client, correction_url, correction_body)
        corrected_text = _extract_text(correction_payload)
        result = _parse_scan_report(corrected_text)
    return result, meta
