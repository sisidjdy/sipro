"""Pydantic request models (responses use plain dicts with {data,total})."""
from typing import Dict, Optional, List
from pydantic import BaseModel, EmailStr, Field

import reference as ref
import models_p46 as p46          # tipe `permit_scope` (Fase 46) — SSOT reference tetap


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    role: ref.UserRole
    phone: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: ref.OptUserRole = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class PermissionUpdate(BaseModel):
    matrix: dict


class TaskCreate(BaseModel):
    title: str
    type: ref.TaskType = "todo"
    priority: ref.Priority = "medium"
    description: Optional[str] = None
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    jobdesk_code: Optional[str] = None   # pilih dari katalog jobdesk, bukan nilai bebas


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    type: ref.TaskType = None
    priority: ref.Priority = None
    description: Optional[str] = None
    status: ref.TaskStatus = None
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None


class TaskComplete(BaseModel):
    outcome: Optional[str] = None


class TaskSnooze(BaseModel):
    until: str


class ActivityCreate(BaseModel):
    entity_type: str
    entity_id: str
    body: str
    type: ref.ActivityType = "comment"
    mentions: List[str] = []
    parent_id: Optional[str] = None


class CommentCreate(BaseModel):
    body: str
    mentions: List[str] = []


# ----------------------------- Slice A — Sales -----------------------------
class LeadCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    source: ref.LeadSource = "manual"
    campaign: Optional[str] = None
    interest_unit_type: ref.UnitType = None
    notes: Optional[str] = None
    assigned_to: Optional[str] = None
    # Fase 42 — atribusi mitra. Wajib bila `source="partner"`: lead mitra tanpa mitra
    # membuat hak fee tidak bisa dipertanggungjawabkan (dan analitik mitra jadi bohong).
    partner_id: Optional[str] = None


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    interest_unit_type: ref.UnitType = None
    notes: Optional[str] = None
    source: ref.LeadSource = None
    partner_id: Optional[str] = None


class LeadStageUpdate(BaseModel):
    stage: ref.LeadStageReq
    note: Optional[str] = None


class LeadAssign(BaseModel):
    assigned_to: str


class LeadImport(BaseModel):
    leads: List[LeadCreate]


class AppointmentCreate(BaseModel):
    # Fase 63: `lead_id` OPSIONAL — rapat internal, kunjungan proyek, dan rapat vendor tidak
    # punya lead, dan memaksa memilih lead membuat orang menempelkan agenda kerja ke lead
    # yang tidak bersangkutan (data pipeline jadi bohong).
    lead_id: Optional[str] = None
    title: str
    scheduled_at: str
    type: ref.AppointmentType = "survey"
    location: Optional[str] = None
    project_id: Optional[str] = None
    notes: Optional[str] = None
    participants: Optional[List[str]] = None


class AppointmentUpdate(BaseModel):
    title: Optional[str] = None
    scheduled_at: Optional[str] = None
    type: Optional[ref.AppointmentType] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    participants: Optional[List[str]] = None


class AppointmentStatus(BaseModel):
    status: ref.AppointmentStatusReq


class MessageCreate(BaseModel):
    body: str
    direction: ref.MsgDirection = "out"   # in = pesan masuk (memicu automasi)
    template_id: Optional[str] = None    # required to send when the 24h session window is closed
    template_code: Optional[str] = None


class WebhookLead(BaseModel):
    name: Optional[str] = None
    phone: str
    email: Optional[str] = None
    campaign: Optional[str] = None
    message: Optional[str] = None
    interest: Optional[str] = None
    # Ads attribution (EPIC 1.7) — carried from Meta/Google/TikTok lead forms.
    source: Optional[str] = None
    adset_id: Optional[str] = None
    ad_id: Optional[str] = None
    creative_id: Optional[str] = None
    form_id: Optional[str] = None
    # Fase 43 — atribusi LENGKAP (`docs/v2/30_MARKETING_INTEGRATION_SPEC.md` §3).
    # Tanpa `campaign_id` (ID kampanye di platform), lead hanya bisa dicocokkan lewat NAMA
    # kampanye: sekali tim marketing mengganti nama kampanye di Ads Manager, seluruh biaya
    # dan leadnya berhenti bertemu tanpa ada yang sadar. `utm_*`/`fbclid`/`gclid` adalah
    # satu-satunya jejak untuk lead dari form website & landing page.
    campaign_id: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    fbclid: Optional[str] = None
    gclid: Optional[str] = None
    landing_url: Optional[str] = None
    referrer: Optional[str] = None


# ----------------------------- EPIC 1.7 Omnichannel -----------------------------
class AutomationRuleCreate(BaseModel):
    name: str
    trigger_event: ref.AutomationTrigger = "message.received"
    keywords: List[str] = []
    no_response_days: Optional[int] = None
    # actions: [{type: create_task|send_template|suggest_stage|notify, template_code?, stage?, title?}]
    actions: List[dict] = []
    is_active: bool = True
    require_confirmation: bool = True


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    trigger_event: ref.OptAutomationTrigger = None
    keywords: Optional[List[str]] = None
    no_response_days: Optional[int] = None
    actions: Optional[List[dict]] = None
    is_active: Optional[bool] = None
    require_confirmation: Optional[bool] = None


class WaTemplateCreate(BaseModel):
    name: str
    code: Optional[str] = None   # opsional; bila kosong diturunkan dari nama
    category: ref.WaTemplateCategory = "utility"
    language: str = "id"
    body: str
    variables: List[str] = []
    examples: Optional[Dict[str, str]] = None   # contoh nilai per variabel (wajib Meta, WA-13)
    meta_name: Optional[str] = None
    components: Optional[List[dict]] = None
    header_type: Optional[str] = "none"
    header_text: Optional[str] = None
    header_sample_handle: Optional[str] = None


class WaReminderMappingIn(BaseModel):
    mapping: Dict[str, str]   # {kind pengingat: template_code}


class WaTemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: ref.WaTemplateCategory = None
    language: Optional[str] = None
    body: Optional[str] = None
    variables: Optional[List[str]] = None
    examples: Optional[Dict[str, str]] = None
    status: ref.WaTemplateStatus = None
    meta_name: Optional[str] = None
    components: Optional[List[dict]] = None
    header_type: Optional[str] = None
    header_text: Optional[str] = None
    header_sample_handle: Optional[str] = None


class ChannelCreate(BaseModel):
    code: str
    channel: ref.ChannelType
    name: str


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class DealReserve(BaseModel):
    """Reservasi langsung memakai MESIN HARGA yang sama dengan penawaran (Fase 69)."""
    unit_id: str
    lead_id: str
    booking_fee: int = 0
    notes: Optional[str] = None
    addons: List[dict] = []
    scheme_id: Optional[str] = None
    discount_scheme_id: Optional[str] = None
    promo_id: Optional[str] = None
    coupon_code: Optional[str] = None
    kpr: Optional[dict] = None
    # Biaya transaksi (BPHTB, notaris, bank, asuransi) + penanda "harga all-in" (biaya
    # ditanggung developer). Diisi saat SPR → dibawa ke kontrak (`contracts.costs`).
    costs: Optional[dict] = None
    # Alasan melewati batas `reservation.max_active_per_lead` (hanya `reservation.override_roles`).
    limit_override_reason: Optional[str] = None
    # Fase 76: sales MEMILIH skema all-in; input manual hanya finance_manager/superadmin + alasan.
    allin_scheme_id: Optional[str] = None
    costs_manual: Optional[List[dict]] = None
    costs_manual_reason: Optional[str] = None
    # Fase 77E: add-on harga master 0 → diblokir; override sales_manager+ dengan alasan
    # dicatat sebagai harga + diskon 100% (bukan Rp 0).
    addon_zero_override: Optional[dict] = None


class DealAction(BaseModel):
    note: Optional[str] = None


# ----------------------------- Phase 20 — EPIC 1.4 Legal (PPJB/AJB) -----------------------------
class PpjbSign(BaseModel):
    number: Optional[str] = None
    signed_date: Optional[str] = None
    note: Optional[str] = None


class AjbSign(BaseModel):
    number: Optional[str] = None
    notary: Optional[str] = None
    signed_date: Optional[str] = None
    note: Optional[str] = None


class DocumentCreate(BaseModel):
    template_code: ref.DocumentTemplate = "SPR"
    deal_id: str


class DocumentSign(BaseModel):
    role: ref.SignerRoleReq
    name: str


# ----------------------------- Slice B \u2014 Construction -----------------------------
class ProjectCreate(BaseModel):
    name: str
    code: str = ""
    location: Optional[str] = None
    marketing_office: Optional[str] = None
    members: List[str] = []


class UnitGenerate(BaseModel):
    prefix: str = "A"
    type: ref.UnitTypeReq = "Tipe 45/90"
    price: int
    count: int = 1
    start_index: int = 1


class PhaseCreate(BaseModel):
    project_id: str
    name: str
    weight: int = 10
    planned_pct: int = 0
    order: int = 0
    work_category: Optional[str] = None



class ProgressUpdate(BaseModel):
    progress: int
    note: Optional[str] = None
    photo: Optional[str] = None


class QCCreate(BaseModel):
    project_id: str
    phase_id: Optional[str] = None
    unit_id: Optional[str] = None
    result: ref.QcResultReq
    notes: Optional[str] = None
    photo: Optional[str] = None


class MaterialCreate(BaseModel):
    project_id: str
    code: str = ""
    name: str
    uom: ref.Uom = "unit"
    boq_item_id: Optional[str] = None
    budget_qty: float = 0


class MaterialTxn(BaseModel):
    project_id: str
    material_id: str
    type: ref.StockMovement
    qty: float
    note: Optional[str] = None
    ref: Optional[str] = None


class OpnameCreate(BaseModel):
    project_id: str
    material_id: str
    physical_qty: float
    note: Optional[str] = None


# ----------------------------- Slice Finance -----------------------------
class SchemeItem(BaseModel):
    label: str
    basis: ref.SchemeBasisReq = "percent"
    value: float = 0
    due_offset_days: int = 0


class PaymentSchemeCreate(BaseModel):
    name: str
    items: List[SchemeItem]
    is_default: bool = False


class CommissionTier(BaseModel):
    min_amount: int = 0
    max_amount: Optional[int] = None
    rate_pct: float = 0


class CommissionSchemeCreate(BaseModel):
    name: str
    basis: ref.CommissionBasis = "price"
    trigger: ref.CommissionTrigger = "booked"
    tiers: List[CommissionTier]
    is_default: bool = False


class TaxConfigUpdate(BaseModel):
    ppn_rate: float
    bphtb_rate: float
    pph_rate: float
    npoptkp: int = 80000000


class ArScheduleCreate(BaseModel):
    scheme_id: str


class ReceiptAllocation(BaseModel):
    item_id: str
    amount: int


class ReceiptCreate(BaseModel):
    deal_id: str
    amount: int
    method: ref.PaymentMethod = "transfer"
    note: Optional[str] = None
    allow_overpay: bool = False   # True = kelebihan dicatat sbg titipan pelanggan
    cash_account_id: Optional[str] = None   # Fase 82: rekening/kas tempat uang mendarat
    allocations: Optional[List[ReceiptAllocation]] = None   # termin yang dipilih kasir (sisanya FIFO)


class ApBillCreate(BaseModel):
    vendor: str
    project_id: Optional[str] = None
    claimed: int
    retention_pct: float = 5
    due_date: Optional[str] = None
    note: Optional[str] = None


class ApPay(BaseModel):
    amount: int
    note: Optional[str] = None
    cash_account_id: Optional[str] = None


class CommissionComputeReq(BaseModel):
    scheme_id: Optional[str] = None


class CollectionConfigUpdate(BaseModel):
    denda_rate_pct_month: float = 2.0
    grace_days: int = 7



# ----------------------------- EPIC 1.5 — Customers / KYC / Financing -----------------------------
class CustomerCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    nik: Optional[str] = None
    npwp: Optional[str] = None
    address: Optional[str] = None
    occupation: Optional[str] = None
    monthly_income: Optional[int] = None
    spouse_name: Optional[str] = None
    spouse_nik: Optional[str] = None
    heir_name: Optional[str] = None
    heir_relation: Optional[str] = None
    lead_id: Optional[str] = None
    notes: Optional[str] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    nik: Optional[str] = None
    npwp: Optional[str] = None
    address: Optional[str] = None
    occupation: Optional[str] = None
    monthly_income: Optional[int] = None
    spouse_name: Optional[str] = None
    spouse_nik: Optional[str] = None
    heir_name: Optional[str] = None
    heir_relation: Optional[str] = None
    kyc_status: ref.KycStatus = None
    notes: Optional[str] = None


class FinancingCreate(BaseModel):
    deal_id: str
    customer_id: Optional[str] = None
    bank_name: ref.FinancingBankReq
    plafon: int
    dp_amount: int = 0
    tenor_months: int = 180
    interest_rate_pct: float = 0


class FinancingUpdate(BaseModel):
    bank_name: ref.FinancingBank = None
    plafon: Optional[int] = None
    dp_amount: Optional[int] = None
    tenor_months: Optional[int] = None
    interest_rate_pct: Optional[float] = None
    status: ref.FinancingStatus = None
    customer_id: Optional[str] = None


class SlikUpdate(BaseModel):
    slik_status: ref.SlikStatusReq
    note: Optional[str] = None


# ----------------------------- EPIC M1 — Customer Portal -----------------------------
class PortalOtpRequest(BaseModel):
    identifier: str  # phone or email


class PortalOtpVerify(BaseModel):
    identifier: str
    code: str


class ComplaintCreate(BaseModel):
    deal_id: Optional[str] = None
    category: ref.ComplaintCategory = "lainnya"
    subject: str
    message: str
    priority: ref.Priority = "medium"



class DisbursementCreate(BaseModel):
    amount: int
    milestone: str
    min_progress: int = 0
    note: Optional[str] = None
    book_to_ar: bool = True   # Fase 26: cairkan = kas masuk -> kurangi piutang pembeli
    cash_account_id: Optional[str] = None   # Fase 82: rekening penerima pencairan


# ----------------------------- Phase 9 — Staff Complaint / CS -----------------------------
class ComplaintRespond(BaseModel):
    message: str
    resolve: bool = False


class ComplaintStatusUpdate(BaseModel):
    status: ref.ComplaintStatusReq
    note: Optional[str] = None


class ComplaintAssign(BaseModel):
    assigned_to: str


# ----------------------------- Phase 10 — Permit / Document Tracker -----------------------------
class PermitCreate(BaseModel):
    project_id: str
    type: ref.PermitTypeReq
    name: Optional[str] = None
    reference_no: Optional[str] = None
    authority: ref.PermitAuthority = None
    deadline: Optional[str] = None  # ISO date/datetime — tenggat PENGURUSAN
    reminder_days: int = 14
    notes: Optional[str] = None
    # Fase 46 (docs/v2/29 §5): izin menempel pada OBJEK, punya masa berlaku, dan bisa
    # ditautkan ke master dokumen syarat sehingga gerbang "mulai bangun" bisa memakainya.
    scope: p46.PermitScope = None            # project (bawaan) | cluster | block | unit
    scope_id: Optional[str] = None
    expiry_at: Optional[str] = None          # masa BERLAKU habis (beda dari `deadline`)
    requirement_code: Optional[str] = None   # kode master dokumen syarat (bila ada)


class PermitUpdate(BaseModel):
    type: ref.PermitType = None
    name: Optional[str] = None
    reference_no: Optional[str] = None
    authority: ref.PermitAuthority = None
    deadline: Optional[str] = None
    reminder_days: Optional[int] = None
    notes: Optional[str] = None
    scope: p46.PermitScope = None
    scope_id: Optional[str] = None
    expiry_at: Optional[str] = None
    requirement_code: Optional[str] = None


class PermitStatusUpdate(BaseModel):
    status: ref.PermitStatusReq
    note: Optional[str] = None


# ----------------------------- Phase 11 — Field ops: Site Diary + Punch List -----------------------------
class SiteDiaryCreate(BaseModel):
    project_id: str
    log_date: Optional[str] = None  # ISO; defaults to now
    weather: ref.Weather = None
    workforce: Optional[int] = 0
    work_description: str
    materials: Optional[str] = None
    equipment: Optional[str] = None
    obstacles: Optional[str] = None
    photo: Optional[str] = None  # base64 data URL


class PunchCreate(BaseModel):
    project_id: str
    unit_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    category: ref.WorkCategory = None
    severity: ref.PunchSeverity = None
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    photo: Optional[str] = None


class PunchUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    category: ref.WorkCategory = None
    severity: ref.PunchSeverity = None
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None


class PunchStatusUpdate(BaseModel):
    status: ref.PunchStatusReq


# ----------------------------- Phase 12/13 — Pengadaan & Buku Besar (pindah ke models_procurement.py) -----------------------------
# Pindah karena models.py melewati batas NFR 800 baris; diekspor ulang di sini supaya
# `from models import POCreate/BoQItemCreate/JournalCreate/...` di router lama tidak pecah.
from models_procurement import (  # noqa: E402,F401  (re-export sengaja)
    SubcontractorCreate,
    SubcontractorUpdate,
    SPKCreate,
    SPKUpdate,
    SPKStatusUpdate,
    ProgressClaimCreate,
    StatusNote,
    ChangeOrderCreate,
    BoQItemCreate,
    BoQItemUpdate,
    POItemIn,
    POCreate,
    POAction,
    GRNItemIn,
    GRNCreate,
    ProcurementBillCreate,
    AccountCreate,
    JournalLineIn,
    JournalCreate,
)

# ----------------------------- Phase 14 — EPIC 1.2 Appointment & Survey -----------------------------
class SurveyChecklistItem(BaseModel):
    key: str
    label: str
    status: ref.SurveyCheckStatus = "na"
    note: Optional[str] = None
    stage_key: Optional[str] = None
    required: Optional[bool] = None


class SurveyCreate(BaseModel):
    lead_id: str
    appointment_id: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class SurveyUpdate(BaseModel):
    location: Optional[str] = None
    notes: Optional[str] = None
    summary: Optional[str] = None
    checklist: Optional[List[SurveyChecklistItem]] = None
    current_stage: Optional[int] = Field(default=None, ge=0, le=50)


class SurveyStageItemIn(BaseModel):
    label: str = Field(min_length=2, max_length=160)
    required: bool = False
    hint: Optional[str] = Field(default=None, max_length=300)


class SurveyStageIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: Optional[str] = Field(default=None, max_length=400)
    items: List[SurveyStageItemIn] = []


class SurveyStagesConfigIn(BaseModel):
    stages: List[SurveyStageIn] = Field(min_length=1, max_length=20)


class PhaseTemplateRowIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    weight: int = Field(ge=1, le=100)
    planned_pct: int = Field(default=0, ge=0, le=100)
    # Kategori pekerjaan pada langkah jadwal unit yang menjadi sumber progres fase ini.
    # Kosong = progres fase diisi manual (mis. infrastruktur kawasan yang bukan per unit).
    work_category: Optional[str] = Field(default=None, max_length=40)


class PhaseTemplateIn(BaseModel):
    code: str = Field(min_length=2, max_length=30)
    name: str = Field(min_length=3, max_length=120)
    description: Optional[str] = Field(default=None, max_length=400)
    phases: List[PhaseTemplateRowIn] = Field(min_length=1, max_length=40)


class PhaseTemplateApply(BaseModel):
    template_id: str


class SurveyResult(BaseModel):
    result: ref.SurveyResultReq
    summary: Optional[str] = None


# ----------------------------- Perpajakan (EPIC 3.3) -----------------------------
class TaxRecordUpdate(BaseModel):
    status: ref.TaxStatus = None
    report_date: Optional[str] = None       # tanggal lapor SPT
    paid_date: Optional[str] = None         # tanggal setor
    ntpn: Optional[str] = None              # Nomor Transaksi Penerimaan Negara
    note: Optional[str] = None
    cash_account_id: Optional[str] = None   # Fase 82: rekening sumber setoran


class FakturIssue(BaseModel):
    deal_id: str
    buyer_npwp: Optional[str] = None
    transaction_code: Optional[str] = "010"  # kode transaksi Faktur Pajak



# EPIC 2.4 — QC / Inspeksi (checklist multi-item)
class InspectionItemInput(BaseModel):
    key: str
    label: Optional[str] = None
    result: ref.InspectionItemResult = None
    note: Optional[str] = None


class InspectionCreate(BaseModel):
    project_id: str
    template_code: ref.InspectionTemplate = None
    unit_id: Optional[str] = None
    phase_id: Optional[str] = None
    title: Optional[str] = None
    category: ref.InspectionCategory = None
    items: Optional[List[InspectionItemInput]] = None  # dipakai bila tanpa template


class InspectionItemsUpdate(BaseModel):
    items: List[InspectionItemInput]


# ----------------------------- Phase 18 — EPIC 2.6 Material Requisition + Budget -----------------------------
class RequisitionItemIn(BaseModel):
    material_id: str
    qty: float


class RequisitionCreate(BaseModel):
    project_id: str
    phase_id: Optional[str] = None
    task_id: Optional[str] = None
    purpose: Optional[str] = None
    items: List[RequisitionItemIn]
    note: Optional[str] = None


class RequisitionIssue(BaseModel):
    items: Optional[List[RequisitionItemIn]] = None   # subset/partial; default = semua sisa
    note: Optional[str] = None


class MaterialBudgetSet(BaseModel):
    boq_item_id: Optional[str] = None
    budget_qty: float = 0