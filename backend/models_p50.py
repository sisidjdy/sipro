"""Model permintaan Fase 50 — serah terima unit, garansi, klaim, dan antrean offline terpadu.

Aturan dipaksakan di lapisan model (bukan di layar): alasan wajib punya panjang minimum,
enum divalidasi lewat Kamus Data (SSOT `reference.py`) sehingga nilai di luar kamus dijawab
400 beserta daftar pilihan yang sah, dan bukti foto perbaikan wajib ada saat pekerjaan
garansi dinyatakan selesai (klaim tidak bisa "selesai" hanya karena diketik).
"""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

import reference as ref

MIN_REASON = 10


def _reason(v, what: str):
    if v is None:
        return v
    v = str(v).strip()
    if len(v) < MIN_REASON:
        raise ValueError(f"{what} minimal {MIN_REASON} huruf \u2014 tulis dasarnya supaya bisa "
                         "ditelusuri kembali.")
    return v


class HandoverIssue(BaseModel):
    """Terbitkan BAST serah terima unit. `override` hanya untuk peran berwenang (dijaga router)."""
    model_config = ConfigDict(extra="ignore")

    unit_id: str
    handed_over_at: Optional[str] = None      # ISO date (bawaan: hari ini)
    received_by: Optional[str] = None         # nama penerima kunci (bila bukan pembeli sendiri)
    note: Optional[str] = None
    meter_air: Optional[str] = None
    meter_listrik: Optional[str] = None
    keys_handed: Optional[int] = Field(default=None, ge=0, le=50)
    override: bool = False
    override_reason: Optional[str] = None
    client_ref: Optional[str] = None

    @field_validator("override_reason")
    @classmethod
    def _ov(cls, v):
        return _reason(v, "Alasan terobosan serah terima")


class HandoverCancel(BaseModel):
    """Batalkan BAST yang salah terbit — status unit & masa garansi dikembalikan."""
    model_config = ConfigDict(extra="ignore")

    reason: str

    @field_validator("reason")
    @classmethod
    def _r(cls, v):
        return _reason(v, "Alasan pembatalan serah terima")


class WarrantyClaimCreate(BaseModel):
    """Ajukan klaim garansi atas satu bagian pekerjaan pada unit yang sudah diserahterimakan."""
    model_config = ConfigDict(extra="ignore")

    unit_id: str
    category: str
    title: str = Field(min_length=4, max_length=140)
    description: Optional[str] = None
    source: str = "internal"
    complaint_id: Optional[str] = None
    photo_file_ids: Optional[List[str]] = None
    client_ref: Optional[str] = None

    @field_validator("category")
    @classmethod
    def _cat(cls, v):
        return ref.make_validator("warranty_category", required=True)(v)

    @field_validator("source")
    @classmethod
    def _src(cls, v):
        return ref.make_validator("warranty_claim_source", required=True)(v)


class WarrantyClaimDecision(BaseModel):
    """Terima (lahirkan pekerjaan perbaikan) atau tolak beralasan."""
    model_config = ConfigDict(extra="ignore")

    accept: bool
    reason: Optional[str] = None
    reject_reason: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None

    @field_validator("reason")
    @classmethod
    def _r(cls, v):
        return _reason(v, "Alasan keputusan klaim")

    @field_validator("reject_reason")
    @classmethod
    def _rr(cls, v):
        if v is None:
            return v
        return ref.make_validator("warranty_reject_reason", required=True)(v)


class WarrantyClaimComplete(BaseModel):
    """Nyatakan perbaikan selesai — WAJIB melampirkan bukti foto 'sesudah'."""
    model_config = ConfigDict(extra="ignore")

    note: Optional[str] = None
    photo_file_ids: List[str] = Field(min_length=1)
    client_ref: Optional[str] = None

    @field_validator("photo_file_ids")
    @classmethod
    def _photos(cls, v):
        rows = [str(x).strip() for x in (v or []) if str(x).strip()]
        if not rows:
            raise ValueError("Bukti foto perbaikan wajib \u2014 klaim garansi tidak bisa "
                             "dinyatakan selesai hanya dengan catatan.")
        return rows


class WarrantyClaimVerify(BaseModel):
    """Pemeriksaan mutu oleh orang LAIN (bukan yang mengerjakan)."""
    model_config = ConfigDict(extra="ignore")

    note: Optional[str] = None
    passed: bool = True
    reason: Optional[str] = None

    @field_validator("reason")
    @classmethod
    def _r(cls, v):
        return _reason(v, "Alasan perbaikan dikembalikan")


class WarrantyClaimClose(BaseModel):
    """Pengakuan pembeli bahwa perbaikan benar selesai."""
    model_config = ConfigDict(extra="ignore")

    ack_note: Optional[str] = None
    ack_by: Optional[str] = None


class PortalWarrantyClaim(BaseModel):
    """Klaim garansi yang diajukan PEMBELI dari portal (tanpa memilih `source`).

    `source` sengaja tidak ikut dikirim klien portal: asalnya sudah pasti `portal_pembeli`,
    dan membiarkan klien memilihnya berarti riwayat klaim bisa dipalsukan menjadi "temuan
    internal" sehingga laporan asal klaim tidak lagi bisa dipercaya.
    """
    model_config = ConfigDict(extra="ignore")

    unit_id: str
    category: str
    title: str = Field(min_length=4, max_length=140)
    description: Optional[str] = None
    photo_file_ids: Optional[List[str]] = None

    @field_validator("category")
    @classmethod
    def _cat(cls, v):
        return ref.make_validator("warranty_category", required=True)(v)
