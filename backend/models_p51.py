"""models_p51.py — kontrak permintaan Fase 51 (retensi↔garansi, pengingat WA, portal).

Aturan yang dijaga DI SINI (bukan hanya di mesin): alasan yang dibaca auditor tidak boleh
kosong atau seadanya. Pengabaian penahanan retensi memindahkan risiko mutu ke perusahaan,
jadi alasannya wajib ≥10 huruf — sama seperti terobosan daftar periksa serah terima
(Fase 50) dan penerobosan tagihan tiga-arah (Fase 48).
"""
from pydantic import BaseModel, Field, field_validator

MIN_REASON = 10


def _reason(v: str, minimum: int, saran: str) -> str:
    s = (v or "").strip()
    if len(s) < minimum:
        raise ValueError(f"Alasan wajib ditulis minimal {minimum} huruf — tulis {saran}.")
    return s


class RetentionWaiveIn(BaseModel):
    """Abaikan penahanan pencairan retensi (butuh izin `subcon_finance:override`)."""
    codes: list[str] = Field(default_factory=list)
    reason: str

    @field_validator("reason")
    @classmethod
    def _check(cls, v):
        return _reason(v, MIN_REASON, "dasar keputusannya (mis. nomor adendum/kesepakatan)")


class RetentionReleaseIn(BaseModel):
    """Pencairan retensi; `client_ref` membuat kiriman ulang AMAN (bukan tagihan kedua)."""
    reason: str
    client_ref: str | None = None

    @field_validator("reason")
    @classmethod
    def _check(cls, v):
        return _reason(v, 5, "dasar pencairannya")


class ReminderRunIn(BaseModel):
    """Jalankan pengingat sekarang (peran ber-izin `reminders:manage`)."""
    kinds: list[str] | None = None
    limit: int = 200


class PortalClaimAckIn(BaseModel):
    """Pengakuan pembeli bahwa perbaikan garansi memang selesai.

    Mesin Fase 50 MEWAJIBKAN pengakuan pembeli untuk menutup klaim, tetapi tidak pernah
    memberi pembeli pintunya — jadi selama ini stafnya yang mengetik nama pembeli. Di sini
    pengakuan datang dari sesi portal pembeli itu sendiri.
    """
    note: str | None = None
    satisfied: bool = True
