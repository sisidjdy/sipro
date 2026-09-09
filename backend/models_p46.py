"""Model request Fase 46 (papan unit, gerbang mulai bangun, izin bertingkat).

Dipisah dari `models*.py` lain karena `models.py`, `reference.py`, dan `engine.py` sudah
menyentuh batas gate compliance (≤800 baris). Semua enum tetap divalidasi lewat SSOT
`reference.GROUPS` sehingga nilai liar ditolak 400 dengan pesan berbahasa Indonesia.

Satu validasi sengaja diletakkan di lapisan model, bukan router: **alasan** saat memulai
pembangunan meski ada peringatan. Keputusan "jalan dulu, DP menyusul" adalah keputusan
manajerial yang harus bisa dipertanggungjawabkan; tanpa alasan, jejaknya tidak berarti.
"""
from typing import Annotated, List, Optional

from pydantic import AfterValidator, BaseModel, Field, field_validator

import reference as ref

MIN_REASON = 5


def _opt(group: str):
    return Annotated[Optional[str], AfterValidator(ref.make_validator(group))]


def _req(group: str):
    return Annotated[str, AfterValidator(ref.make_validator(group, required=True))]


PermitScope = _opt("permit_scope")
PermitScopeReq = _req("permit_scope")


class StartBuildIn(BaseModel):
    """Mulai bangun. `ack` = mengakui peringatan; `reason` wajib bila ada peringatan."""
    ack: bool = False
    reason: Optional[str] = None

    @field_validator("reason")
    @classmethod
    def _reason_len(cls, v):
        if v is not None and v.strip() and len(v.strip()) < MIN_REASON:
            raise ValueError(f"Alasan minimal {MIN_REASON} huruf — tulis dasar keputusan "
                             "memulai pembangunan meski ada peringatan.")
        return v.strip() if isinstance(v, str) else v


class PermitScopeSet(BaseModel):
    """Pindahkan/lekatkan izin ke objek tertentu (proyek/cluster/blok/unit)."""
    scope: PermitScopeReq
    scope_id: Optional[str] = None
    reason: Optional[str] = None


class PermitRenew(BaseModel):
    """Perpanjangan izin: tanggal berlaku baru + nomor acuan baru (bila ada)."""
    expiry_at: str = Field(min_length=8)
    reference_no: Optional[str] = None
    note: Optional[str] = None


class UnitBoardFilter(BaseModel):
    """Bentuk filter papan unit — didokumentasikan agar frontend & gate memakai nama sama."""
    project_id: Optional[str] = None
    cluster_id: Optional[str] = None
    block_id: Optional[str] = None
    construction_status: List[str] = []
    readiness: List[str] = []
    late_only: bool = False
    unscheduled_only: bool = False
    q: Optional[str] = None
