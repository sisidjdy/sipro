"""Request models Fase 27 — Kas Bon, Aset Tetap, Pembiayaan Korporat, Marketing Fee.

File terpisah karena `models.py` sudah menyentuh batas compliance (≤800 baris).
Semua field pilihan memakai Annotated type dari registry SSOT (`reference.py` +
`reference_p27.py`) sehingga nilai liar ditolak 400 dengan pesan berbahasa Indonesia.
"""
from typing import Annotated, List, Optional

from pydantic import AfterValidator, BaseModel, Field

import reference as ref


def _opt(group: str):
    return Annotated[Optional[str], AfterValidator(ref.make_validator(group))]


def _req(group: str):
    return Annotated[str, AfterValidator(ref.make_validator(group, required=True))]


CashbonCategory = _req("cashbon_category")
CashSource = _req("cash_source")
AssetCategory = _req("asset_category")
AssetTaxGroup = _req("asset_tax_group")
DepreciationMethod = _req("depreciation_method")
AssetFunding = _req("asset_funding")
Lender = _req("lender")
LenderType = _req("lender_type")
LoanType = _req("loan_type")
AmortizationMethod = _req("amortization_method")
AgentType = _req("agent_type")
AgentStatus = _opt("agent_status")
FeeBasis = _req("scheme_basis")
FeeTrigger = _req("marketing_fee_trigger")
BankName = _opt("financing_bank")


# ----------------------------- Kas Bon -----------------------------
class CashAdvanceCreate(BaseModel):
    purpose: str = Field(min_length=3, max_length=200)
    amount: int = Field(gt=0)
    category: CashbonCategory
    needed_date: Optional[str] = None
    project_id: Optional[str] = None
    note: Optional[str] = None


class CashAdvanceDisburse(BaseModel):
    amount: Optional[int] = None
    source: CashSource = "bank"
    note: Optional[str] = None
    cash_account_id: Optional[str] = None


class CashbonExpenseItem(BaseModel):
    category: CashbonCategory
    description: str = Field(min_length=2, max_length=200)
    amount: int = Field(gt=0)
    date: Optional[str] = None


class CashAdvanceSettle(BaseModel):
    items: List[CashbonExpenseItem] = Field(min_length=1)
    note: Optional[str] = None


class NoteOnly(BaseModel):
    note: Optional[str] = None


# ----------------------------- Aset Tetap -----------------------------
class AssetCreate(BaseModel):
    name: str = Field(min_length=3, max_length=140)
    category: AssetCategory
    tax_group: AssetTaxGroup
    method: DepreciationMethod
    cost: int = Field(gt=0)
    salvage_value: int = Field(default=0, ge=0)
    useful_life_months: Optional[int] = Field(default=None, ge=0, le=600)
    acquired_date: Optional[str] = None
    funding: AssetFunding = "bank"
    vendor: Optional[str] = None
    project_id: Optional[str] = None
    location: Optional[str] = None
    note: Optional[str] = None


class DepreciationRun(BaseModel):
    period: str = Field(min_length=7, max_length=7)


class AssetDispose(BaseModel):
    proceeds: int = Field(default=0, ge=0)
    source: CashSource = "bank"
    date: Optional[str] = None
    note: Optional[str] = None


# ----------------------------- Pembiayaan korporat -----------------------------
class LoanCreate(BaseModel):
    lender: Lender
    lender_type: LenderType
    loan_type: LoanType
    principal: int = Field(gt=0)
    interest_rate_pct: float = Field(ge=0, le=60)
    tenor_months: int = Field(ge=1, le=360)
    amortization_method: AmortizationMethod
    start_date: Optional[str] = None
    provision_fee: int = Field(default=0, ge=0)
    collateral: Optional[str] = None
    note: Optional[str] = None


class LoanActivate(BaseModel):
    source: CashSource = "bank"
    date: Optional[str] = None
    note: Optional[str] = None


class InstallmentPay(BaseModel):
    installment_no: int = Field(ge=1)
    amount: int = Field(gt=0)
    source: CashSource = "bank"
    date: Optional[str] = None
    note: Optional[str] = None


# ----------------------------- Marketing fee -----------------------------
class AgentCreate(BaseModel):
    name: str = Field(min_length=3, max_length=140)
    agent_type: AgentType
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    npwp: Optional[str] = None
    bank_name: BankName = None
    bank_account: Optional[str] = None
    note: Optional[str] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=140)
    agent_type: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    npwp: Optional[str] = None
    bank_name: BankName = None
    bank_account: Optional[str] = None
    status: AgentStatus = None
    note: Optional[str] = None


class MarketingFeeCreate(BaseModel):
    agent_id: str
    deal_id: str
    basis: FeeBasis
    value: float = Field(gt=0)
    trigger: FeeTrigger
    pph_pct: float = Field(default=0, ge=0, le=30)
    note: Optional[str] = None


class MarketingFeePay(BaseModel):
    amount: Optional[int] = None
    source: CashSource = "bank"
    note: Optional[str] = None
