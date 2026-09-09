"""Model masukan Fase 57A — skema pembayaran yang bisa dikonfigurasi pemakai.

Lapis pertama penjagaan (mesin memeriksa ulang semuanya): nama & label termin tidak boleh
kosong, nilai tidak boleh nol/negatif, dan perubahan skema yang dipakai kontrak WAJIB
beralasan — karena yang berubah adalah jadwal kewajiban orang lain.
"""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

MIN_REASON = 10


def _text(v, minimum: int, apa: str) -> str:
    s = (v or "").strip()
    if len(s) < minimum:
        raise ValueError(f"Tulis {apa} minimal {minimum} huruf.")
    return s


class TermIn(BaseModel):
    """Satu baris termin. Bentuknya sengaja datar supaya bisa disusun bebas dari layar."""
    label: str
    basis: str = "percent"
    value: float = 0
    due_mode: str = "offset_days"
    due_offset_days: int = 0
    due_day: Optional[int] = None
    month_index: Optional[int] = None
    grace_days: int = 0
    event_code: Optional[str] = None
    note: Optional[str] = None

    @field_validator("label")
    @classmethod
    def _v_label(cls, v):
        return _text(v, 3, "nama termin (yang dibaca pembeli di dokumen)")

    @field_validator("due_day")
    @classmethod
    def _v_day(cls, v):
        if v is not None and not (1 <= int(v) <= 28):
            raise ValueError("Tanggal jatuh tempo bulanan harus 1–28 (supaya Februari tidak "
                             "membuat tagihan meleset).")
        return v


class SchemeIn(BaseModel):
    code: Optional[str] = None
    name: str
    kind: str
    active: bool = True
    is_default: bool = False
    applies_project_ids: List[str] = Field(default_factory=list)
    note: Optional[str] = None
    terms: List[TermIn] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _v_name(cls, v):
        return _text(v, 3, "nama skema")


class SchemeUpdate(SchemeIn):
    pass


class SchemeSimulateIn(BaseModel):
    """Pratinjau: skema (tersimpan ATAU rancangan yang belum disimpan) atas satu harga."""
    scheme_id: Optional[str] = None
    price: int = 0
    base_date: Optional[str] = None
    kind: Optional[str] = None
    terms: Optional[List[TermIn]] = None

    @field_validator("price")
    @classmethod
    def _v_price(cls, v):
        if int(v or 0) <= 0:
            raise ValueError("Harga contoh harus lebih besar dari nol — pratinjau tanpa "
                             "harga hanya akan menampilkan angka nol yang menyesatkan.")
        return int(v)


class InstallmentGenIn(BaseModel):
    """Pembantu: 'buat N cicilan' — tetap menjadi baris termin biasa yang bisa diubah."""
    count: int = 6
    percent_total: float = 20
    start_month: int = 1
    due_day: int = 7
    grace_days: int = 13
    label_prefix: str = "Cicilan"

    @field_validator("count")
    @classmethod
    def _v_count(cls, v):
        if not (1 <= int(v) <= 120):
            raise ValueError("Jumlah cicilan wajar antara 1 dan 120.")
        return int(v)


class ContractSchemeIn(BaseModel):
    """Menetapkan skema pada satu kontrak. Alasan wajib: jadwal kewajiban pembeli berubah."""
    scheme_id: str
    reason: str

    @field_validator("reason")
    @classmethod
    def _v_reason(cls, v):
        return _text(v, MIN_REASON, "alasan penggantian skema")
