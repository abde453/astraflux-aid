from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from . import batch

router = APIRouter(prefix="/api/batch")

class Line(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(max_length=40)
    mg_per_unit: float = Field(gt=0, le=1_000_000)
    assay_pct: float = Field(default=100.0, gt=0, le=100)
    lod_pct: float = Field(default=0.0, ge=0, lt=100)
    compensates: bool = False

class BatchReq(BaseModel):
    product: str = Field(min_length=1, max_length=120)
    requested_units: int = Field(gt=0, le=1_000_000_000)
    unit_label: str = Field(default="tablets", max_length=20)
    loss_pct: float = Field(default=0.0, ge=0, le=20)
    assay_basis: str = Field(default="dried", pattern="^(dried|as_is)$")
    lines: List[Line] = Field(min_length=1, max_length=40)

@router.get("/example")
def example(): return batch.EXAMPLE

@router.post("/calculate")
def calculate(r: BatchReq):
    try: return batch.calculate(r.model_dump())
    except batch.BatchError as e: raise HTTPException(422, str(e))
