"""Request models Fase 37 — Kalibrasi Sekali Klik.

Batas ditegakkan di MODEL supaya API tidak bisa dipakai menerobos aturan lewat curl:
jenis kalibrasi harus dari SSOT, alasan harus dari SSOT, catatan wajib panjang cukup untuk
bisa dipertanggungjawabkan, dan besaran perubahan dibatasi masuk akal (tidak ada template
yang mendadak bertambah 200 hari karena salah ketik).
"""
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from reference_p37 import CALIBRATION_CAUSES, CALIBRATION_KINDS

NOTE_MIN = 10


class CalibrationIn(BaseModel):
    """Satu kalibrasi pada SATU langkah template.

    `delta_days` dipakai oleh `step_duration` & `wait_time`; `wait_into_plan` menghitung
    sendiri pergeseran yang dibutuhkan (tidak perlu angka dari UI) sehingga pengguna tidak
    bisa "mengarang" jumlah hari tunggu yang tidak ada di template.
    """
    template_id: str = Field(min_length=8)
    step_code: str = Field(min_length=1, max_length=32)
    kind: str
    delta_days: int = Field(default=0, ge=-60, le=60)
    cause: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=400)
    client_ref: Optional[str] = Field(default=None, max_length=64)
    source: Optional[str] = Field(default=None, max_length=40)

    @field_validator("kind")
    @classmethod
    def _kind_ok(cls, v):
        if v not in CALIBRATION_KINDS:
            raise ValueError("jenis kalibrasi tidak dikenal")
        return v

    @field_validator("cause")
    @classmethod
    def _cause_ok(cls, v):
        if v is not None and v not in CALIBRATION_CAUSES:
            raise ValueError("alasan kalibrasi tidak dikenal")
        return v


class CalibrationApplyIn(CalibrationIn):
    """Eksekusi kalibrasi: alasan + catatan WAJIB (pratinjau tidak mewajibkan).

    PENTING (cacat nyata yang pernah terjadi): kewajiban ini TIDAK boleh hanya ditulis
    sebagai `field_validator` di atas field warisan yang `Optional[...] = None`. Pydantic
    tidak menjalankan validator untuk field yang TIDAK DIKIRIM (nilai default dipakai apa
    adanya), sehingga `POST /apply` tanpa `cause`/`note` sempat lolos 200 dan mengubah
    template tanpa alasan. Karena itu kedua field dinyatakan ulang sebagai WAJIB di sini.
    """
    cause: str = Field(min_length=3)
    note: str = Field(min_length=NOTE_MIN, max_length=400)

    @field_validator("cause")
    @classmethod
    def _cause_known(cls, v):
        if v not in CALIBRATION_CAUSES:
            raise ValueError("alasan kalibrasi tidak dikenal")
        return v

    @field_validator("note")
    @classmethod
    def _note_meaningful(cls, v):
        text = (v or "").strip()
        if len(text) < NOTE_MIN:
            raise ValueError(f"catatan kalibrasi wajib minimal {NOTE_MIN} karakter")
        return text


class CalibrationRollbackIn(BaseModel):
    """Kembalikan kalibrasi ke nilai sebelumnya (tetap wajib beralasan)."""
    note: str = Field(min_length=NOTE_MIN, max_length=400)
    client_ref: Optional[str] = Field(default=None, max_length=64)
