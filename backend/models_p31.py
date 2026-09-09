"""Request models Fase 31 — Jadwal Pembangunan Berbukti per Unit.

File terpisah agar `models.py` (±800 baris) tetap di bawah batas gate compliance.
Semua field enum memakai tipe tervalidasi SSOT (`reference._req/_opt`) supaya nilai
liar tidak bisa masuk lewat API — bukan hanya dijaga dropdown di UI.
"""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

import reference as ref


class ChecklistItemIn(BaseModel):
    """Satu baris checklist mutu pada template."""
    code: Optional[str] = None
    text: str = Field(min_length=3, max_length=200)
    critical: bool = False


class BuildStepIn(BaseModel):
    """Satu item pekerjaan pada template jadwal (bisa dikonfigurasi supervisor)."""
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=3, max_length=160)
    week: int = Field(ge=1, le=104)
    day_from: int = Field(ge=1, le=1000)
    day_to: int = Field(ge=1, le=1000)
    weight: float = Field(gt=0, le=100)
    work_category: ref.WorkCategory = None
    predecessors: List[str] = []
    wait_days: int = Field(default=0, ge=0, le=60)
    wait_reason: Optional[str] = Field(default=None, max_length=200)
    hold_point: bool = False
    hold_note: Optional[str] = Field(default=None, max_length=300)
    min_photos: int = Field(default=1, ge=0, le=10)
    checklist: List[ChecklistItemIn] = []
    assignee_role: Optional[str] = None
    verify_role: Optional[str] = None
    handover_gate: bool = False
    tasks: List[str] = []          # rincian pekerjaan (uraian, bukan enum)

    @field_validator("day_to")
    @classmethod
    def _range_ok(cls, v, info):
        start = (info.data or {}).get("day_from")
        if start and v < start:
            raise ValueError("hari selesai tidak boleh lebih awal dari hari mulai")
        return v


class BuildTemplateIn(BaseModel):
    """Template jadwal per TIPE unit (default bisa diduplikasi lalu diubah)."""
    code: str = Field(min_length=2, max_length=30)
    name: str = Field(min_length=3, max_length=120)
    unit_types: List[str] = []
    project_id: Optional[str] = None
    calendar_mode: str = "working_days"
    work_days_per_week: int = Field(default=6, ge=5, le=7)
    holidays: List[str] = []
    description: Optional[str] = Field(default=None, max_length=400)
    steps: List[BuildStepIn] = []

    @field_validator("calendar_mode")
    @classmethod
    def _mode_ok(cls, v):
        if v not in ("working_days", "calendar_days"):
            raise ValueError("perhitungan hari harus 'working_days' atau 'calendar_days'")
        return v


class BuildTemplateClone(BaseModel):
    clone_from: str
    code: str = Field(min_length=2, max_length=30)
    name: str = Field(min_length=3, max_length=120)
    unit_types: List[str] = []
    project_id: Optional[str] = None


class ScheduleGenerate(BaseModel):
    """Bangkitkan jadwal untuk satu unit (tanggal mulai wajib supaya bisa ditagih)."""
    unit_id: str
    start_date: str = Field(min_length=10, max_length=10)   # YYYY-MM-DD
    template_id: Optional[str] = None
    regenerate: bool = False


class ChecklistAnswer(BaseModel):
    code: str
    result: ref.InspectionItemResult = None      # pass | fail | na (SSOT)
    note: Optional[str] = Field(default=None, max_length=200)


class GeoIn(BaseModel):
    """Koordinat saat foto/hasil kerja diambil (Fase 32).

    Dikirim EKSPLISIT oleh aplikasi, bukan dibaca dari EXIF — pipeline foto SIPRO
    memang membuang metadata EXIF/GPS agar berkas yang dibagikan tidak membocorkan
    lokasi rumah pembeli. Kewajiban merekam lokasi bisa dimatikan admin.
    """
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy: Optional[float] = Field(default=None, ge=0, le=100000)
    captured_at: Optional[str] = Field(default=None, max_length=40)


class ItemSubmit(BaseModel):
    """Staf mengajukan hasil kerja: catatan + foto bukti + checklist mutu (+ lokasi).

    `client_ref` (Fase 35): penanda dari perangkat untuk antrean offline. Bila pengiriman
    diulang (sinyal putus lalu antrean dikirim lagi), server MEMUTAR ULANG hasil lama
    alih-alih membuat pengajuan kedua — jadi bukti tidak pernah dobel.
    """
    note: str = Field(min_length=10, max_length=1000)
    photo_file_ids: List[str] = []
    document_file_ids: List[str] = []
    checklist: List[ChecklistAnswer] = []
    geo: Optional[GeoIn] = None
    client_ref: Optional[str] = Field(default=None, max_length=64)


class ItemVerify(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class ItemReject(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


class ItemOverride(BaseModel):
    """Menerobos gerbang — alasan WAJIB dan selalu dilaporkan ke direksi."""
    reason_code: str
    note: str = Field(min_length=15, max_length=500)


class ItemDelayCause(BaseModel):
    """Penyebab keterlambatan dicatat memakai kode SSOT (untuk analitik nyata)."""
    cause: str
    note: Optional[str] = Field(default=None, max_length=300)


class ScheduleHold(BaseModel):
    cause: str
    note: str = Field(min_length=10, max_length=300)


# ============================ Fase 32 ============================
class BuildPolicyIn(BaseModel):
    """Kebijakan bukti kerja — diatur admin, dibaca semua jalur pengajuan hasil."""
    geo_required: bool = False
    camera_only: bool = False
    min_note_chars: int = Field(default=10, ge=5, le=200)
    min_accuracy_m: int = Field(default=200, ge=10, le=5000)


class WeeklyReportRun(BaseModel):
    """Jalankan laporan mingguan (idempoten per pekan)."""
    project_id: Optional[str] = None
    ref_date: Optional[str] = Field(default=None, min_length=10, max_length=10)
