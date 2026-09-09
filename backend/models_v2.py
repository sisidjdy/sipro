"""Model request Fase 39 (Fondasi Data V2) — hierarki proyek, katalog, dokumen syarat.

Dipisah dari `models.py` (sudah besar) agar tetap di bawah batas gate compliance.
Semua enum divalidasi lewat SSOT `reference.py` (Annotated validator), bukan string bebas.
"""
from typing import Annotated, List, Optional

from pydantic import AfterValidator, BaseModel, Field, field_validator

import reference as ref


def _req(group: str):
    return Annotated[str, AfterValidator(ref.make_validator(group, required=True))]


def _opt(group: str):
    return Annotated[Optional[str], AfterValidator(ref.make_validator(group))]


# Tipe SSOT Fase 39 didefinisikan DI SINI (bukan di reference.py) karena file itu sudah
# menyentuh batas gate compliance 800 baris. Sumber nilainya tetap satu: reference.GROUPS.
ClusterStatus = _opt("cluster_status")
AddonCategory = _opt("addon_category")
AddonCategoryReq = _req("addon_category")
AddonPricingMode = _opt("addon_pricing_mode")
AddonPricingModeReq = _req("addon_pricing_mode")
FinanceTreatment = _opt("finance_treatment")
FinanceTreatmentReq = _req("finance_treatment")
PriceComponentGroup = _opt("price_component_group")
PriceComponentGroupReq = _req("price_component_group")
DocRequirementGroup = _opt("doc_requirement_group")
DocRequirementGroupReq = _req("doc_requirement_group")


def _code(v: str) -> str:
    """Kode kosong = minta sistem membentuk kode dari aturan penomoran (Fase 71)."""
    v = (v or "").strip().upper()
    if not v:
        return ""
    if len(v) > 24:
        raise ValueError("Kode maksimal 24 karakter.")
    return v


# ------------------------------------------------------------------ cluster & blok
class ClusterCreate(BaseModel):
    code: str = ""
    name: str
    order: int = 0
    description: Optional[str] = None
    land_area: Optional[int] = None
    unit_target: Optional[int] = None
    price_multiplier: float = 1.0
    status: ClusterStatus = "selling"

    _c = field_validator("code")(_code)


class ClusterUpdate(BaseModel):
    name: Optional[str] = None
    order: Optional[int] = None
    description: Optional[str] = None
    land_area: Optional[int] = None
    unit_target: Optional[int] = None
    price_multiplier: Optional[float] = None
    status: ClusterStatus = None


class BlockCreate(BaseModel):
    code: str = ""
    name: Optional[str] = None
    order: int = 0
    orientation: Optional[str] = None
    notes: Optional[str] = None

    _c = field_validator("code")(_code)


class BlockUpdate(BaseModel):
    name: Optional[str] = None
    order: Optional[int] = None
    orientation: Optional[str] = None
    notes: Optional[str] = None


# ------------------------------------------------------------------ unit
class UnitCreateV2(BaseModel):
    no: str = Field(..., description="Nomor unit dalam blok, mis. '11'")
    unit_type_code: Optional[str] = None
    land_area: Optional[int] = None
    building_area: Optional[int] = None
    price: Optional[int] = None
    is_hook: bool = False
    excess_land_m2: int = 0
    notes: Optional[str] = None


class UnitGenerateV2(BaseModel):
    unit_type_code: str
    count: int = Field(1, ge=1, le=200)
    start_no: int = Field(1, ge=1)
    price: Optional[int] = None
    hook_numbers: List[int] = []


class UnitPatchV2(BaseModel):
    unit_type_code: Optional[str] = None
    land_area: Optional[int] = None
    building_area: Optional[int] = None
    price: Optional[int] = None
    is_hook: Optional[bool] = None
    excess_land_m2: Optional[int] = None
    excess_land_price_agreed: Optional[int] = None
    notes: Optional[str] = None
    reason: Optional[str] = None


class UnitBlockToggle(BaseModel):
    blocked: bool
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, v):
        if not (v or "").strip():
            raise ValueError("Alasan wajib diisi saat memblokir/membuka unit.")
        return v.strip()


class UnitImportRow(BaseModel):
    cluster_code: str
    block_code: str
    no: str
    unit_type_code: Optional[str] = None
    land_area: Optional[int] = None
    building_area: Optional[int] = None
    price: Optional[int] = None
    is_hook: bool = False


class UnitImport(BaseModel):
    project_id: str
    rows: List[UnitImportRow]
    dry_run: bool = True


# ------------------------------------------------------------------ katalog
class UnitTypeCreate(BaseModel):
    code: str = ""
    name: str
    building_area: int = Field(..., ge=1)
    land_area_std: int = Field(..., ge=1)
    base_price: int = Field(..., ge=0)
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    floors: int = 1
    spec: dict = {}
    active: bool = True

    _c = field_validator("code")(_code)


class UnitTypeUpdate(BaseModel):
    name: Optional[str] = None
    building_area: Optional[int] = None
    land_area_std: Optional[int] = None
    base_price: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    floors: Optional[int] = None
    spec: Optional[dict] = None
    active: Optional[bool] = None


class AddonCreate(BaseModel):
    code: str = ""
    name: str
    category: AddonCategoryReq = "spek_bangunan"
    pricing_mode: AddonPricingModeReq = "lump_sum"
    unit_price: int = 0
    uom: Optional[str] = None
    finance_treatment: FinanceTreatmentReq = "revenue"
    gl_account: Optional[str] = None
    requires_document: Optional[str] = None
    needs_approval_role: Optional[str] = None
    applies_project_ids: List[str] = []
    applies_unit_types: List[str] = []
    negotiable: bool = False
    active: bool = True
    note: Optional[str] = None

    _c = field_validator("code")(_code)


class AddonUpdate(BaseModel):
    name: Optional[str] = None
    category: AddonCategory = None
    pricing_mode: AddonPricingMode = None
    unit_price: Optional[int] = None
    uom: Optional[str] = None
    finance_treatment: FinanceTreatment = None
    gl_account: Optional[str] = None
    requires_document: Optional[str] = None
    needs_approval_role: Optional[str] = None
    applies_project_ids: Optional[List[str]] = None
    applies_unit_types: Optional[List[str]] = None
    negotiable: Optional[bool] = None
    active: Optional[bool] = None
    note: Optional[str] = None


class PriceComponentCreate(BaseModel):
    code: str
    label: str
    group: PriceComponentGroupReq = "biaya"
    applies_schemes: List[str] = []
    calc: str = "fixed"
    value: int = 0
    percent_of: Optional[str] = None
    finance_treatment: FinanceTreatmentReq = "pass_through"
    gl_account: Optional[str] = None
    editable_by_role: Optional[str] = None
    order: int = 0
    active: bool = True
    note: Optional[str] = None

    _c = field_validator("code")(_code)


class PriceComponentUpdate(BaseModel):
    label: Optional[str] = None
    group: PriceComponentGroup = None
    applies_schemes: Optional[List[str]] = None
    calc: Optional[str] = None
    value: Optional[int] = None
    percent_of: Optional[str] = None
    finance_treatment: FinanceTreatment = None
    gl_account: Optional[str] = None
    editable_by_role: Optional[str] = None
    order: Optional[int] = None
    active: Optional[bool] = None
    note: Optional[str] = None


# ------------------------------------------------------------------ dokumen syarat
class DocRequirementCreate(BaseModel):
    code: str
    label: str
    group: DocRequirementGroupReq = "identitas"
    applies_to: List[str] = []
    mandatory: bool = True
    conditional_note: Optional[str] = None
    allowed_mime: List[str] = []
    max_mb: int = 10
    expiry_days: Optional[int] = None
    needs_verification: Optional[bool] = None  # None → ikut `doc.require_verification_default`
    order: int = 0
    active: bool = True
    note: Optional[str] = None

    _c = field_validator("code")(_code)


class DocRequirementUpdate(BaseModel):
    label: Optional[str] = None
    group: DocRequirementGroup = None
    applies_to: Optional[List[str]] = None
    mandatory: Optional[bool] = None
    conditional_note: Optional[str] = None
    allowed_mime: Optional[List[str]] = None
    max_mb: Optional[int] = None
    expiry_days: Optional[int] = None
    needs_verification: Optional[bool] = None
    order: Optional[int] = None
    active: Optional[bool] = None
    note: Optional[str] = None


class DocSubmissionCreate(BaseModel):
    requirement_code: str
    entity_type: str
    entity_id: str
    file_id: str
    note: Optional[str] = None


class DocVerifyPayload(BaseModel):
    note: Optional[str] = None


class DocRejectPayload(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def _r(cls, v):
        if not (v or "").strip():
            raise ValueError("Alasan penolakan wajib diisi.")
        return v.strip()


# ------------------------------------------------------------------ setting
class SettingUpdate(BaseModel):
    value: object
    reason: Optional[str] = None
    scope: str = "org"
    scope_id: Optional[str] = None


class SettingBulkItem(BaseModel):
    key: str
    value: object
    reason: Optional[str] = None
    scope: str = "org"
    scope_id: Optional[str] = None


class SettingBulk(BaseModel):
    items: List[SettingBulkItem]
