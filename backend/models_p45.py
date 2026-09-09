"""Model request Fase 45 (target proyek, master anggaran, revisi & pencatatan manual).

Dipisah dari `models*.py` lain karena semuanya sudah menyentuh batas gate compliance
(<800 baris). Semua enum divalidasi lewat SSOT `reference.GROUPS` (Annotated validator)
sehingga nilai liar ditolak 400 dengan pesan berbahasa Indonesia — bukan tersimpan lalu
merusak laporan anggaran.

Dua validasi yang sengaja ada di lapisan model (bukan di router):
  * format periode `YYYY-MM` — target bicara BULAN, dan tanggal harian yang lolos ke sini
    akan membuat horizon target tidak bisa dihitung;
  * alasan wajib pada revisi anggaran & hitung-ulang target — jejak tanpa alasan sama saja
    tidak ada jejak.
"""
from typing import Annotated, Dict, List, Optional

from pydantic import AfterValidator, BaseModel, Field, field_validator

import reference as ref
import target_engine as te


def _req(group: str):
    return Annotated[str, AfterValidator(ref.make_validator(group, required=True))]


def _opt(group: str):
    return Annotated[Optional[str], AfterValidator(ref.make_validator(group))]


TargetMethod = _opt("target_method")
TargetBasis = _opt("target_basis")
TargetScope = _opt("target_scope")
TargetStatus = _opt("target_status")
RecalcMode = _opt("target_recalc_mode")
BudgetCategoryReq = _req("budget_category")
BudgetCategoryOpt = _opt("budget_category")
MatchRuleReq = _req("budget_match_rule")
MatchRuleOpt = _opt("budget_match_rule")
BudgetPeriod = _opt("budget_period")


def _check_period(value):
    if value is not None and not te.valid_period(str(value)):
        raise ValueError("Periode harus berformat YYYY-MM (contoh 2026-08) — target "
                         "dihitung per bulan, bukan per tanggal.")
    return value


PeriodStr = Annotated[str, AfterValidator(_check_period)]


class Horizon(BaseModel):
    start: PeriodStr
    end: PeriodStr

    @field_validator("end")
    @classmethod
    def _order(cls, v, info):
        start = (info.data or {}).get("start")
        if start and te.month_diff(start, v) < 0:
            raise ValueError("Bulan selesai tidak boleh lebih awal dari bulan mulai.")
        return v


class RecalcPolicy(BaseModel):
    mode: RecalcMode = "monthly"
    keep_total: bool = True
    lock_past: bool = True


class Assumptions(BaseModel):
    avg_price: int = Field(default=0, ge=0)
    opex_monthly: int = Field(default=0, ge=0)
    start_selling: Optional[PeriodStr] = None
    growth_pct: float = Field(default=0, ge=-100, le=500)


class TargetCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=3, max_length=140)
    scope: TargetScope = "project"
    cluster_id: Optional[str] = None
    owner_email: Optional[str] = Field(default=None, max_length=120)
    basis: TargetBasis = "both"
    method: TargetMethod = "linear_remaining"
    horizon: Horizon
    unit_target: int = Field(default=0, ge=0, le=100000)
    revenue_target: int = Field(default=0, ge=0)
    recalc_policy: RecalcPolicy = Field(default_factory=RecalcPolicy)
    weights: Dict[str, float] = Field(default_factory=dict)
    manual_plan: Dict[str, int] = Field(default_factory=dict)
    assumptions: Assumptions = Field(default_factory=Assumptions)
    note: Optional[str] = Field(default=None, max_length=400)


class TargetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=140)
    basis: TargetBasis = None
    method: TargetMethod = None
    horizon: Optional[Horizon] = None
    unit_target: Optional[int] = Field(default=None, ge=0, le=100000)
    revenue_target: Optional[int] = Field(default=None, ge=0)
    recalc_policy: Optional[RecalcPolicy] = None
    weights: Optional[Dict[str, float]] = None
    manual_plan: Optional[Dict[str, int]] = None
    assumptions: Optional[Assumptions] = None
    note: Optional[str] = Field(default=None, max_length=400)
    reason: Optional[str] = Field(default=None, max_length=300)


class TargetPreview(BaseModel):
    """Pratinjau dampak SEBELUM disimpan (DoD #1). Boleh dari target tersimpan + perubahan,
    atau dari rancangan target yang belum pernah disimpan."""
    target_id: Optional[str] = None
    project_id: Optional[str] = None
    cluster_id: Optional[str] = None
    owner_email: Optional[str] = None
    method: TargetMethod = None
    basis: TargetBasis = None
    horizon: Optional[Horizon] = None
    unit_target: Optional[int] = Field(default=None, ge=0, le=100000)
    revenue_target: Optional[int] = Field(default=None, ge=0)
    recalc_policy: Optional[RecalcPolicy] = None
    weights: Optional[Dict[str, float]] = None
    manual_plan: Optional[Dict[str, int]] = None
    assumptions: Optional[Assumptions] = None


class TargetRecalc(BaseModel):
    reason: str = Field(min_length=5, max_length=300)
    today: Optional[PeriodStr] = None


class TargetStatusChange(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=300)


class BudgetItemCreate(BaseModel):
    project_id: str
    cluster_id: Optional[str] = None
    unit_id: Optional[str] = None
    category: BudgetCategoryReq
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=3, max_length=140)
    description: Optional[str] = Field(default=None, max_length=400)
    planned_amount: int = Field(default=0, ge=0)
    currency: str = Field(default="IDR", max_length=8)
    gl_account: Optional[str] = Field(default=None, max_length=24)
    match_rule: MatchRuleReq
    boq_item_ids: List[str] = Field(default_factory=list)
    owner_role: Optional[str] = Field(default=None, max_length=40)
    period: BudgetPeriod = "project"
    order: int = Field(default=0, ge=0, le=999)
    note: Optional[str] = Field(default=None, max_length=400)


class BudgetItemUpdate(BaseModel):
    category: BudgetCategoryOpt = None
    name: Optional[str] = Field(default=None, min_length=3, max_length=140)
    description: Optional[str] = Field(default=None, max_length=400)
    gl_account: Optional[str] = Field(default=None, max_length=24)
    match_rule: MatchRuleOpt = None
    boq_item_ids: Optional[List[str]] = None
    owner_role: Optional[str] = Field(default=None, max_length=40)
    period: BudgetPeriod = None
    order: Optional[int] = Field(default=None, ge=0, le=999)
    active: Optional[bool] = None
    note: Optional[str] = Field(default=None, max_length=400)


class BudgetRevise(BaseModel):
    """Revisi anggaran: alasan WAJIB (spec §4 — overbudget menuntut revisi beralasan)."""
    planned_amount: int = Field(ge=0)
    reason: str = Field(min_length=5, max_length=300)


class BudgetManualEntry(BaseModel):
    amount: int = Field(gt=0)
    note: str = Field(min_length=5, max_length=300)
    kind: str = Field(default="realisasi", pattern="^(realisasi|komitmen)$")
    ref_no: Optional[str] = Field(default=None, max_length=60)
