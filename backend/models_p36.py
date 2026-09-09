"""Request models Fase 36 — Kalender Jadwal & master kalender kerja.

Batas & bentuk data ditegakkan di MODEL supaya API tidak bisa dipakai menerobos aturan
lewat curl (mis. mengirim pola hari yang tidak dikenal, ambang bentrok 0, atau tanggal
inspeksi berformat bebas).
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

import build_calendar as bcal
from reference_p36 import HOLIDAY_KINDS

DATE_LEN = 10


class HolidayIn(BaseModel):
    """Satu hari libur pada master kalender kerja."""
    date: str = Field(min_length=DATE_LEN, max_length=DATE_LEN)
    name: str = Field(min_length=3, max_length=80)
    kind: str = "national"
    note: Optional[str] = Field(default=None, max_length=200)

    @field_validator("kind")
    @classmethod
    def _kind_ok(cls, v):
        if v not in HOLIDAY_KINDS:
            raise ValueError("jenis hari libur tidak dikenal")
        return v

    @field_validator("date")
    @classmethod
    def _date_ok(cls, v):
        try:
            bcal._d(v)
        except Exception:
            raise ValueError("tanggal harus format YYYY-MM-DD")
        return v[:DATE_LEN]


class WorkCalendarIn(BaseModel):
    """Pola hari kerja + ambang bentrok (+ daftar libur bila dikirim sekaligus)."""
    pattern: Dict[str, str] = Field(default_factory=dict)
    thresholds: Dict[str, int] = Field(default_factory=dict)
    holidays: Optional[List[HolidayIn]] = None
    note: Optional[str] = Field(default=None, max_length=300)
    project_id: Optional[str] = None

    @field_validator("pattern")
    @classmethod
    def _pattern_ok(cls, v):
        for key, val in (v or {}).items():
            if key not in bcal.WEEKDAY_KEYS:
                raise ValueError(f"hari '{key}' tidak dikenal")
            if val not in bcal.DAY_MODES:
                raise ValueError(f"pola hari '{val}' tidak dikenal")
        return v


class InspectionScheduleIn(BaseModel):
    """Menjadwalkan inspeksi/QC agar muncul di Kalender Jadwal (boleh dikosongkan)."""
    scheduled_date: Optional[str] = Field(default=None, min_length=DATE_LEN, max_length=DATE_LEN)
    note: Optional[str] = Field(default=None, max_length=300)

    @field_validator("scheduled_date")
    @classmethod
    def _date_ok(cls, v):
        if v is None:
            return v
        try:
            bcal._d(v)
        except Exception:
            raise ValueError("tanggal harus format YYYY-MM-DD")
        return v[:DATE_LEN]
