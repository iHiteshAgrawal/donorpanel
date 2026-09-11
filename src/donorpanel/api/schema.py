from pydantic import BaseModel, Field


class NewRequest(BaseModel):
    patient_id: str
    needed_by: str
    units_needed: int | None = None
    component: str | None = None
    source: str | None = None
    prescription_ref: str | None = None


class ChatTurn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class Approval(BaseModel):
    by: str = Field(min_length=1)
    note: str | None = None


class GraphShape(BaseModel):
    nodes: list[dict]
    edges: list[dict]
