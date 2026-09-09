"""Request models Fase 29 — Work Hub v2 (divisi, jobdesk, bukti kerja, verifikasi).

File terpisah karena `models.py` sudah dekat batas compliance (≤800 baris).
"""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

import reference as ref


class TaskAssign(BaseModel):
    """Supervisor menugaskan/mengalihkan tugas ke staf divisinya."""
    assigned_to: str
    note: Optional[str] = Field(default=None, max_length=300)
    due_date: Optional[str] = None
    priority: ref.Priority = None


class TaskSubmit(BaseModel):
    """Staf mengajukan hasil kerja + BUKTI (sesuai `proof_kind` jobdesk)."""
    note: Optional[str] = Field(default=None, max_length=1000)
    photos: List[str] = []          # file_id hasil unggah ke object storage
    documents: List[str] = []       # file_id / doc_id
    amount: Optional[float] = None


class TaskVerify(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class TaskReject(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class JobdeskConfig(BaseModel):
    """Konfigurasi jobdesk oleh supervisor (bukan hardcode)."""
    is_active: Optional[bool] = None
    assignee_rule: Optional[str] = None
    assignee_email: Optional[str] = None
    sla_hours: Optional[float] = Field(default=None, ge=0.05, le=2000)
    priority: ref.Priority = None
    verify_mode: Optional[str] = None
    proof_kind: Optional[str] = None
    recurrence: Optional[str] = None


class JobdeskRun(BaseModel):
    """Jalankan jobdesk manual sekarang (supervisor)."""
    assigned_to: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=300)
    due_date: Optional[str] = None


class UserOrgAssign(BaseModel):
    """Tempatkan pengguna pada divisi + level (admin/owner)."""
    division: Optional[str] = None
    level: Optional[str] = None
    supervisor_email: Optional[str] = None


class LeadDisposition(BaseModel):
    """Penilaian KUALITATIF agen atas respons lead (Fase 29b)."""
    disposition: str
    note: Optional[str] = Field(default=None, max_length=500)
    intent_tags: List[str] = []


class LeadWaManual(BaseModel):
    """Catat chat WA yang dilakukan DI LUAR sistem (HP pribadi) — wajib bukti foto."""
    note: str = Field(min_length=3, max_length=1000)
    evidence_file_ids: List[str] = Field(min_length=1, max_length=3)
    task_id: Optional[str] = None   # tugas Work Hub (contact/follow-up) yang ikut ditutup

    @field_validator("evidence_file_ids")
    @classmethod
    def _dedupe(cls, v):
        return list(dict.fromkeys(v))


class LeadStageOverride(BaseModel):
    """Override stage oleh supervisor — WAJIB beralasan, tercatat di stage_history."""
    stage: str
    reason: str = Field(min_length=5, max_length=300)
