"""Model masukan Fase 58 — denda & keringanan keterlambatan."""
from pydantic import BaseModel, field_validator

MIN_REASON = 10


class LateFeeApplyIn(BaseModel):
    """Penagihan denda. `item_id` kosong = semua termin yang sudah lewat toleransi."""
    item_id: str | None = None
    client_ref: str | None = None


class LateFeeWaiveIn(BaseModel):
    """Keringanan denda. Wajib beralasan — keputusan ini dibaca auditor."""
    reason: str

    @field_validator("reason")
    @classmethod
    def _v_reason(cls, v):
        s = (v or "").strip()
        if len(s) < MIN_REASON:
            raise ValueError(f"Alasan keringanan wajib minimal {MIN_REASON} huruf.")
        return s
