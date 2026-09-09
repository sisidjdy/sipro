"""Request models Fase 28b — foto lapangan nyata, showroom publik, peta portal.

File terpisah karena `models.py` sudah menyentuh batas compliance (≤800 baris).
Model foto dibuat sebagai turunan model lama sehingga kontrak lama tetap berlaku
(`photo` base64 masih diterima) sementara klien baru mengirim `photos` = daftar
**file_id** hasil unggah ke object storage (`POST /api/files/upload`).
"""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from models import PunchCreate, PunchStatusUpdate, PunchUpdate, SiteDiaryCreate

MAX_PHOTOS = 6


class _PhotosMixin(BaseModel):
    photos: Optional[List[str]] = None
    # Fase 50B — penanda antrean perangkat. Kiriman ULANG dengan penanda yang sama
    # memutar ulang hasil lama (bukan membuat catatan kedua): buku harian & temuan punch
    # adalah dua hal yang paling sering dikerjakan di lokasi tanpa sinyal, jadi tanpa
    # penanda ini satu-satunya pilihan pemakai adalah "tekan ulang lalu dobel" atau
    # "jangan tekan lalu hilang".
    client_ref: Optional[str] = Field(default=None, max_length=120)

    @field_validator("photos")
    @classmethod
    def _limit(cls, v):
        if v and len(v) > MAX_PHOTOS:
            raise ValueError(f"Maksimal {MAX_PHOTOS} foto per catatan.")
        return [str(x) for x in (v or []) if str(x).strip()] or None


class DiaryCreateP28(SiteDiaryCreate, _PhotosMixin):
    """Buku harian + daftar file_id foto (unggahan nyata ke object storage)."""


class PunchCreateP28(PunchCreate, _PhotosMixin):
    """Temuan punch list + daftar file_id foto temuan."""


class PunchUpdateP28(PunchUpdate, _PhotosMixin):
    """Ubah data temuan + TAMBAH foto temuan.

    Sebelumnya foto temuan hanya bisa dilampirkan saat temuan DIBUAT; staf yang lupa
    memfoto tidak punya cara menambahkannya, sehingga pasangan bukti "sebelum → sesudah"
    tidak pernah lengkap. Foto baru DITAMBAHKAN (bukan menimpa) agar bukti lama tidak hilang.
    """


class PunchStatusP28(PunchStatusUpdate, _PhotosMixin):
    """Ubah status punch + foto BUKTI PERBAIKAN (foto 'sesudah')."""
    note: Optional[str] = None


class ShowroomConfig(BaseModel):
    """Konfigurasi halaman showroom publik per proyek (dikelola staf)."""
    enabled: bool
    regenerate: bool = False
    headline: Optional[str] = Field(default=None, max_length=140)
    contact_wa: Optional[str] = Field(default=None, max_length=25)
    show_price: bool = True


class ShowroomLeadCreate(BaseModel):
    """Form tangkap lead di halaman publik (nama + WhatsApp wajib)."""
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=8, max_length=20)
    unit_code: Optional[str] = Field(default=None, max_length=20)
    message: Optional[str] = Field(default=None, max_length=400)
    # Honeypot: bot mengisi field tersembunyi ini; manusia tidak pernah melihatnya.
    website: Optional[str] = None
