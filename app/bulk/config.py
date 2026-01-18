from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


Transformer = Callable[[str], object]


@dataclass
class TemplateColumn:
    label: str
    key: str
    instruction: str
    required: bool = False


@dataclass
class EntityImportConfig:
    entity: str
    template_version: str
    template_columns: List[TemplateColumn]
    unique_key_groups: List[List[str]]
    transformers: Dict[str, Transformer]


def normalize_header(value: str) -> str:
    import re
    import unicodedata

    if not value:
        return ""
    raw = unicodedata.normalize("NFKD", value)
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.lower().strip()
    raw = re.sub(r"[\\s\\-]+", "_", raw)
    raw = re.sub(r"[^a-z0-9_]", "", raw)
    return raw


def make_header_map(columns: List[TemplateColumn]) -> Dict[str, str]:
    mapping = {}
    for col in columns:
        mapping[normalize_header(col.label)] = col.key
        mapping[normalize_header(col.key)] = col.key
    return mapping


def label_for_key(config: EntityImportConfig, key: str) -> str:
    for col in config.template_columns:
        if col.key == key:
            return col.label
    return key


def normalize_text(value: str) -> str:
    return value.strip()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    raw = value.strip()
    return "".join(ch for ch in raw if ch.isdigit())


def normalize_bool(value: str) -> bool:
    raw = value.strip().lower()
    return raw in {"sim", "yes", "true", "1"}


def normalize_int(value: str) -> int:
    return int(value.strip())


def normalize_cnpj(value: str) -> str:
    raw = value.strip()
    return "".join(ch for ch in raw if ch.isdigit())


def normalize_list(value: str) -> List[str]:
    parts = [p.strip() for p in value.split(";")]
    return [p for p in parts if p]


def normalize_date(value: str):
    from dateutil import parser

    return parser.parse(value.strip()).date()


def build_entity_configs() -> Dict[str, EntityImportConfig]:
    return {
        "employees": EntityImportConfig(
            entity="employees",
            template_version="v1",
            template_columns=[
                TemplateColumn("Nome", "nome", "Obrigatorio", True),
                TemplateColumn("Funcao", "funcao", "Obrigatorio", True),
                TemplateColumn("Email", "email", "Obrigatorio", True),
                TemplateColumn("Telefone", "telefone", "Opcional"),
                TemplateColumn("Status", "status", "Opcional (ATIVO/INATIVO)"),
                TemplateColumn("Contrato", "contrato", "Opcional"),
                TemplateColumn("Unidade", "unidade", "Opcional"),
                TemplateColumn("Coordenador", "coordenador_nome", "Opcional"),
                TemplateColumn("Supervisor", "supervisor_nome", "Opcional"),
                TemplateColumn("Especialidades", "especialidades", "Separar por ;"),
                TemplateColumn("Observacoes", "observacoes", "Opcional"),
            ],
            unique_key_groups=[["email"]],
            transformers={
                "nome": normalize_text,
                "funcao": normalize_text,
                "email": normalize_email,
                "telefone": normalize_phone,
                "status": normalize_text,
                "contrato": normalize_text,
                "unidade": normalize_text,
                "coordenador_nome": normalize_text,
                "supervisor_nome": normalize_text,
                "especialidades": normalize_list,
                "observacoes": normalize_text,
            },
        ),
        "clients": EntityImportConfig(
            entity="clients",
            template_version="v1",
            template_columns=[
                TemplateColumn("Nome", "name", "Obrigatorio", True),
                TemplateColumn("Codigo do cliente", "client_code", "Obrigatorio se CNPJ vazio"),
                TemplateColumn("CNPJ", "document", "Obrigatorio se codigo vazio"),
                TemplateColumn("Status", "status", "Opcional (active/suspended)"),
                TemplateColumn("Contrato", "contract", "Opcional"),
                TemplateColumn("Endereco", "address", "Opcional"),
            ],
            unique_key_groups=[["document"], ["client_code"]],
            transformers={
                "name": normalize_text,
                "client_code": normalize_text,
                "document": normalize_cnpj,
                "status": normalize_text,
                "contract": normalize_text,
                "address": normalize_text,
            },
        ),
        "sites": EntityImportConfig(
            entity="sites",
            template_version="v1",
            template_columns=[
                TemplateColumn("Codigo do site", "site_code", "Obrigatorio", True),
                TemplateColumn("Nome", "name", "Obrigatorio", True),
                TemplateColumn("CNPJ do cliente", "customer_account_cnpj", "Obrigatorio"),
                TemplateColumn("Nome do cliente", "customer_account_name", "Opcional"),
                TemplateColumn("Status", "status", "Opcional (ATIVO/INATIVO)"),
                TemplateColumn("Endereco", "address", "Opcional"),
            ],
            unique_key_groups=[["site_code", "customer_account_cnpj"], ["site_code"]],
            transformers={
                "site_code": normalize_text,
                "name": normalize_text,
                "customer_account_cnpj": normalize_cnpj,
                "customer_account_name": normalize_text,
                "status": normalize_text,
                "address": normalize_text,
            },
        ),
        "assets": EntityImportConfig(
            entity="assets",
            template_version="v1",
            template_columns=[
                TemplateColumn("Tag", "tag", "Obrigatorio", True),
                TemplateColumn("Nome", "name", "Obrigatorio", True),
                TemplateColumn("Tipo", "asset_type", "Opcional"),
                TemplateColumn("Status", "status", "Opcional"),
                TemplateColumn("CNPJ do cliente", "client_cnpj", "Opcional"),
                TemplateColumn("Codigo do cliente", "client_code", "Opcional"),
                TemplateColumn("Codigo do site", "site_code", "Opcional"),
            ],
            unique_key_groups=[["tag"]],
            transformers={
                "tag": normalize_text,
                "name": normalize_text,
                "asset_type": normalize_text,
                "status": normalize_text,
                "client_cnpj": normalize_cnpj,
                "client_code": normalize_text,
                "site_code": normalize_text,
            },
        ),
        "os_types": EntityImportConfig(
            entity="os_types",
            template_version="v1",
            template_columns=[
                TemplateColumn("Nome", "name", "Obrigatorio", True),
                TemplateColumn("Descricao", "description", "Opcional"),
                TemplateColumn("CNPJ do cliente", "client_cnpj", "Opcional"),
                TemplateColumn("Codigo do cliente", "client_code", "Opcional"),
                TemplateColumn("Ativo", "is_active", "Opcional (SIM/NAO)"),
            ],
            unique_key_groups=[["name", "client_cnpj"], ["name"]],
            transformers={
                "name": normalize_text,
                "description": normalize_text,
                "client_cnpj": normalize_cnpj,
                "client_code": normalize_text,
                "is_active": normalize_bool,
            },
        ),
        "questionnaires": EntityImportConfig(
            entity="questionnaires",
            template_version="v1",
            template_columns=[
                TemplateColumn("Titulo do questionario", "title", "Obrigatorio", True),
                TemplateColumn("Versao", "version", "Opcional (padrao 1)"),
                TemplateColumn("Pergunta", "question_text", "Obrigatorio", True),
                TemplateColumn("Pergunta obrigatoria?", "required", "SIM/NAO"),
                TemplateColumn("Tipo de resposta", "answer_type", "Obrigatorio", True),
                TemplateColumn("Itens da pergunta", "items", "Separar por ;"),
            ],
            unique_key_groups=[["title", "version"]],
            transformers={
                "title": normalize_text,
                "version": normalize_int,
                "question_text": normalize_text,
                "required": normalize_bool,
                "answer_type": normalize_text,
                "items": normalize_list,
            },
        ),
    }


ENTITY_CONFIGS = build_entity_configs()
