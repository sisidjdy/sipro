"""Model request Fase 33 (opname berbukti & termin berbasis item pekerjaan).

File terpisah karena `models.py` sudah mendekati batas gate compliance (800 baris).
"""
from typing import List, Optional

from pydantic import BaseModel


class ScopeLineIn(BaseModel):
    build_item_id: str
    value: int = 0
    boq_item_id: Optional[str] = None


class ScopeAddIn(BaseModel):
    lines: List[ScopeLineIn]


class ClaimOpnameIn(BaseModel):
    """Opname termin. Mode item: `exclude` = baris yang DIKELUARKAN (wajib beralasan).
    Mode lump-sum lama: `verified_pct` tetap dipakai."""
    exclude: List[str] = []
    reason: Optional[str] = None
    verified_pct: Optional[int] = None
    note: Optional[str] = None


class BoQStepMapIn(BaseModel):
    step_codes: List[str] = []
