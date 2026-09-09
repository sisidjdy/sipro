"""Model request Fase 41 (jam tahap) & Fase 42 (mitra & aturan fee).

Dipisah dari `models.py`/`models_v2.py` karena keduanya sudah menyentuh batas gate
compliance. Semua enum divalidasi lewat SSOT `reference.GROUPS` (Annotated validator),
sehingga nilai liar ditolak 400 dengan pesan berbahasa Indonesia — bukan tersimpan diam-diam
lalu merusak laporan.
"""
from typing import Annotated, List, Optional

from pydantic import AfterValidator, BaseModel, Field, field_validator

import reference as ref


def _req(group: str):
    return Annotated[str, AfterValidator(ref.make_validator(group, required=True))]


def _opt(group: str):
    return Annotated[Optional[str], AfterValidator(ref.make_validator(group))]


PartnerKindReq = _req("partner_kind")
PartnerKind = _opt("partner_kind")
PartnerEntityType = _opt("partner_entity_type")
PartnerStatus = _opt("agent_status")
AgentTypeOpt = _opt("agent_type")
FeeBasisReq = _req("partner_fee_basis")
FeeBasisOpt = _opt("partner_fee_basis")
FeeTriggerOpt = _opt("partner_fee_trigger")
FeeTriggerReq = _req("partner_fee_trigger")
PriceBase = _opt("partner_price_base")
TierMode = _opt("partner_tier_mode")
FeePeriod = _opt("partner_fee_period")
QualifyRule = _opt("partner_qualify_rule")
RuleStatus = _opt("partner_rule_status")
TaxType = _opt("partner_tax_type")
AgingEntityReq = _req("aging_entity")


# ------------------------------------------------------------------ mitra
class PartnerContract(BaseModel):
    number: Optional[str] = Field(default=None, max_length=60)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    signed_by: Optional[str] = Field(default=None, max_length=120)
    status: Optional[str] = Field(default="active", max_length=20)
    file_ids: List[str] = Field(default_factory=list)


class PartnerCreate(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    partner_kind: PartnerKindReq
    entity_type: PartnerEntityType = "individual"
    company: Optional[str] = Field(default=None, max_length=120)
    phone: str = Field(min_length=6, max_length=24)
    email: Optional[str] = Field(default=None, max_length=120)
    nik: Optional[str] = Field(default=None, max_length=32)
    npwp: Optional[str] = Field(default=None, max_length=32)
    address: Optional[str] = Field(default=None, max_length=240)
    pic_name: Optional[str] = Field(default=None, max_length=120)
    pic_phone: Optional[str] = Field(default=None, max_length=24)
    bank_name: Optional[str] = Field(default=None, max_length=60)
    bank_account: Optional[str] = Field(default=None, max_length=40)
    bank_account_name: Optional[str] = Field(default=None, max_length=120)
    contract: Optional[PartnerContract] = None
    note: Optional[str] = Field(default=None, max_length=400)


class PartnerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=120)
    partner_kind: PartnerKind = None
    entity_type: PartnerEntityType = None
    company: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, min_length=6, max_length=24)
    email: Optional[str] = Field(default=None, max_length=120)
    nik: Optional[str] = Field(default=None, max_length=32)
    npwp: Optional[str] = Field(default=None, max_length=32)
    address: Optional[str] = Field(default=None, max_length=240)
    pic_name: Optional[str] = Field(default=None, max_length=120)
    pic_phone: Optional[str] = Field(default=None, max_length=24)
    bank_name: Optional[str] = Field(default=None, max_length=60)
    bank_account: Optional[str] = Field(default=None, max_length=40)
    bank_account_name: Optional[str] = Field(default=None, max_length=120)
    contract: Optional[PartnerContract] = None
    note: Optional[str] = Field(default=None, max_length=400)


class PartnerStatusUpdate(BaseModel):
    """Status mitra memblokir lead & fee baru → wajib beralasan (jejak untuk mitra)."""
    status: PartnerStatus
    reason: str = Field(min_length=5, max_length=300)


# ------------------------------------------------------------------ aturan fee
class FeeTier(BaseModel):
    min: float = Field(ge=0)
    max: Optional[float] = None
    value: float = Field(gt=0)
    mode: TierMode = "percent"


class FeeSplit(BaseModel):
    trigger: FeeTriggerReq
    pct: float = Field(gt=0, le=100)


class FeeTax(BaseModel):
    pph_type: TaxType = None
    rate: Optional[float] = Field(default=None, ge=0, lt=100)
    gross_up: bool = False


class FeeScope(BaseModel):
    project_id: Optional[str] = None
    cluster_id: Optional[str] = None
    unit_type: Optional[str] = None


class FeeComponent(BaseModel):
    basis: FeeBasisReq
    value: Optional[float] = Field(default=None, ge=0)
    price_base: PriceBase = None
    by_unit_type: dict = Field(default_factory=dict)
    tiers: List[FeeTier] = Field(default_factory=list)
    qualify_rule: QualifyRule = None


class FeeRuleCreate(BaseModel):
    name: str = Field(min_length=4, max_length=140)
    partner_id: Optional[str] = None
    basis: FeeBasisReq
    value: Optional[float] = Field(default=None, ge=0)
    price_base: PriceBase = "gross"
    by_unit_type: dict = Field(default_factory=dict)
    tiers: List[FeeTier] = Field(default_factory=list)
    period: FeePeriod = "monthly"
    qualify_rule: QualifyRule = None
    components: List[FeeComponent] = Field(default_factory=list)
    trigger: FeeTriggerOpt = None
    splits: List[FeeSplit] = Field(default_factory=list)
    tax: Optional[FeeTax] = None
    scope: Optional[FeeScope] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    status: RuleStatus = "active"
    note: Optional[str] = Field(default=None, max_length=400)

    @field_validator("by_unit_type")
    @classmethod
    def _amounts(cls, v):
        for code, amount in (v or {}).items():
            try:
                if float(amount) <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError(f"Nominal fee tipe {code} harus angka lebih dari 0.")
        return v


class FeeRuleUpdate(FeeRuleCreate):
    name: Optional[str] = Field(default=None, min_length=4, max_length=140)
    basis: FeeBasisOpt = None


class FeePreview(BaseModel):
    """Pratinjau perhitungan: mitra + deal + pemicu → angka yang AKAN terbit."""
    partner_id: str
    deal_id: str
    trigger: FeeTriggerReq


class FeeIssue(FeePreview):
    """Terbitkan tagihan fee dari aturan secara manual (mis. pemicu lama yang terlewat)."""
    note: Optional[str] = Field(default=None, max_length=300)


class ConflictDecision(BaseModel):
    partner_id: str
    reason: str = Field(min_length=5, max_length=300)


class LeadAttribution(BaseModel):
    partner_id: Optional[str] = None
    reason: Optional[str] = Field(default=None, max_length=300)
