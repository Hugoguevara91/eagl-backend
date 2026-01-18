from typing import Literal, Optional

from pydantic import BaseModel, Field


class TestRequirement(BaseModel):
    key: str
    label: str
    type: Literal["number", "text", "select", "boolean"]
    unit: Optional[str] = None
    required: bool
    options: Optional[list[str]] = None

    model_config = {"extra": "forbid"}


class ActionStep(BaseModel):
    step: int
    action: str
    why: str
    validation: str

    model_config = {"extra": "forbid"}


class NotesForWorkOrder(BaseModel):
    service_done: str
    cause: str
    solution: str
    observations: str

    model_config = {"extra": "forbid"}


class SolverResult(BaseModel):
    summary: str
    probable_root_cause: str
    severity: Literal["baixa", "media", "alta", "critica"]
    safety_risk: Literal["nenhum", "atencao", "alto"]
    confidence: float = Field(ge=0, le=1)
    tests_required: list[TestRequirement]
    tests_instructions: list[str]
    action_plan: list[ActionStep]
    when_to_escalate: list[str]
    notes_for_work_order: NotesForWorkOrder

    model_config = {"extra": "forbid"}
