"""Request models Fase 30 — pra-skrining SLIK berbukti & antrean lead gagal masuk.

File terpisah agar `models.py` (≈800 baris) dan `models_p29.py` tetap di bawah batas gate.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SlikPrescreen(BaseModel):
    """Hasil pra-skrining BI/SLIK + BUKTI iDeb (Fase 30a).

    `evidence_file_ids` adalah id berkas hasil unggah ke object storage (tangkapan layar
    atau PDF iDeb). Hasil yang MELOLOSKAN lead (clear/flagged) wajib punya minimal satu.
    """
    status: str
    note: Optional[str] = Field(default=None, max_length=400)
    evidence_file_ids: List[str] = []


class CaptureRetry(BaseModel):
    """Ulangi pemasukan lead yang gagal, dengan koreksi data opsional."""
    fixes: Dict[str, str] = {}


class CaptureDiscard(BaseModel):
    """Buang antrean gagal-masuk — alasan WAJIB (audit)."""
    reason: str = Field(min_length=3, max_length=300)
