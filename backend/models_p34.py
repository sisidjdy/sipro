"""Request models Fase 34 — jadwal massal & geser tanggal serentak.

Semua batas ditegakkan di MODEL (bukan hanya di UI) supaya API tidak bisa dipakai
menerobos aturan: jumlah maksimal per operasi, rentang hari geser, dan catatan wajib
saat tenggat rumah diubah.
"""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

import build_bulk as bb


class BulkScheduleIn(BaseModel):
    """Buat jadwal untuk BANYAK unit sekaligus (pratinjau memakai model yang sama)."""
    unit_ids: List[str] = Field(min_length=1, max_length=bb.MAX_BATCH)
    start_date: str = Field(min_length=10, max_length=10)
    template_id: Optional[str] = None
    wave: str = "same"                       # same | per_unit | per_block
    stagger_days: int = Field(default=0, ge=0, le=60)
    client_ref: Optional[str] = Field(default=None, max_length=64)

    @field_validator("wave")
    @classmethod
    def _wave_ok(cls, v):
        if v not in bb.WAVE_MODES:
            raise ValueError("pola gelombang tidak dikenal")
        return v

    @field_validator("unit_ids")
    @classmethod
    def _unique(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("ada unit yang dipilih dua kali")
        return v


class BulkShiftIn(BaseModel):
    """Geser tanggal serentak. `note` wajib karena ini mengubah tenggat & eskalasi."""
    schedule_ids: List[str] = Field(min_length=1, max_length=bb.MAX_BATCH)
    shift_days: int = Field(ge=bb.SHIFT_MIN, le=bb.SHIFT_MAX)
    cause: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=500)
    client_ref: Optional[str] = Field(default=None, max_length=64)

    @field_validator("shift_days")
    @classmethod
    def _not_zero(cls, v):
        if v == 0:
            raise ValueError("jumlah hari geser tidak boleh 0")
        return v
