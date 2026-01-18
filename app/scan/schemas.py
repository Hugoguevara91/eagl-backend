from typing import Literal, Optional

from pydantic import BaseModel, Field


class AlarmSignal(BaseModel):
    texto: str
    codigo: str
    gravidade: Literal["baixa", "media", "alta"]
    fonte_imagem_index: int = Field(ge=0)

    model_config = {"extra": "forbid"}


class StatusPontoSignal(BaseModel):
    ponto: str
    valor: str
    unidade: str
    fonte_imagem_index: int = Field(ge=0)

    model_config = {"extra": "forbid"}


class LeituraSignal(BaseModel):
    nome: str
    valor: str
    unidade: str
    fonte_imagem_index: int = Field(ge=0)

    model_config = {"extra": "forbid"}


class TendenciaSignal(BaseModel):
    variavel: str
    comportamento: Literal["estavel", "oscilando", "subindo", "descendo", "travado"]
    observacao: str
    fonte_imagem_index: int = Field(ge=0)

    model_config = {"extra": "forbid"}


class ComunicacaoSignal(BaseModel):
    possivel_falha: bool
    indicadores: list[str]

    model_config = {"extra": "forbid"}


class ScanSignals(BaseModel):
    extraction_confidence: float = Field(ge=0, le=1)
    observacoes_gerais: str
    alarmes: list[AlarmSignal]
    status_pontos: list[StatusPontoSignal]
    leituras: list[LeituraSignal]
    tendencias: list[TendenciaSignal]
    comunicacao: ComunicacaoSignal
    inconsistencias: list[str]

    model_config = {"extra": "forbid"}


class ScanHypothesis(BaseModel):
    rank: int = Field(ge=1)
    bloco_local: str
    probabilidade: float = Field(ge=0, le=1)
    titulo: str
    evidencias: list[str]
    o_que_validar: list[str]
    observacoes: Optional[str] = ""

    model_config = {"extra": "forbid"}


class RiscoOperacao(BaseModel):
    nivel: Literal["Baixo", "Medio", "Alto"]
    motivo: str

    model_config = {"extra": "forbid"}


class ScanReport(BaseModel):
    confidence_overall: float = Field(ge=0, le=1)
    top_hypotheses: list[ScanHypothesis]
    o_que_validar_em_campo_agora: list[str]
    risco_operacao: RiscoOperacao
    limites: list[str]

    model_config = {"extra": "forbid"}
