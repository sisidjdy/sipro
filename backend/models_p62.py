"""Model permintaan Fase 62 — surat peringatan tunggakan, lampiran SPK, kirim dokumen."""
from typing import Optional

from pydantic import BaseModel, Field


class WarningLetterIn(BaseModel):
    deal_id: str
    level: int = Field(ge=1, le=3)


class SpkAttachmentIn(BaseModel):
    file_id: str
    kind: str = "gambar_kerja"
    label: Optional[str] = None


class DocShareIn(BaseModel):
    kind: str
    id: str
