from pydantic import BaseModel, Field


class NewRequest(BaseModel):
    patient_id: str
    needed_by: str
    units_needed: int | None = None
    component: str | None = None
    source: str | None = None


class Approval(BaseModel):
    by: str = Field(min_length=1)
    note: str | None = None


class GraphShape(BaseModel):
    nodes: list[dict]
    edges: list[dict]
