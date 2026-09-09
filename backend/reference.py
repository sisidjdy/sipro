"""SSOT reference registry — satu-satunya sumber nilai enum & vocabulary terkontrol.

Masalah yang diperbaiki (audit forensik):
- models.py sebelumnya TIDAK punya satu pun validator: backend menerima string apa pun
  untuk status/type/category/uom/stage/dll.
- Frontend meng-hardcode ~40 daftar dropdown yang saling bertentangan
  (mis. STAGES beda di 3 file; kategori 'Struktur' vs 'struktur' vs 'structural').
- Field relasi/enum di-input sebagai teks bebas -> data kotor & tidak bisa diagregasi.

Semua nilai kanonik ada di GROUPS. Backend memvalidasi lewat Annotated types di models.py;
frontend mengambil daftar yang sama dari GET /api/reference. Tidak ada daftar ganda.
"""
from typing import Annotated, Optional

from pydantic import AfterValidator



from reference_groups import GROUPS, _o  # noqa: F401  (registry dasar; _o dipakai grup lanjutan)


# Grup enum modul fase lanjutan (27 Kas Bon/Aset, 28 Site Plan, 29 Work Hub, 31 Jadwal
# Bangun, 33 Termin Subkon, 34 Jadwal Massal, 35 Antrean Offline) hidup di
# `reference_p<NN>.py` agar file ini tetap di bawah batas compliance, tetapi REGISTRY-nya
# tetap SATU — dimuat di sini sehingga validator backend, endpoint /api/reference, dan
# tab Kamus Data otomatis mengenalinya. Fase baru cukup menambah nomornya ke `_PHASES`
# (sebelumnya setiap fase menambah satu baris import dan file ini sudah menyentuh batas).
import importlib  # noqa: E402

from reference_p28 import SYNONYMS_P28 as _SYN_P28  # noqa: E402
from reference_p43 import SYNONYMS_P43 as _SYN_P43  # noqa: E402
_PHASES = (27, 28, 29, 31, 33, 34, 35, 36, 37, 39, 41, 43, 44, 45, 46, 47, 48, 49, 50, 51,
           53, 54, 56, 57, 58, 59, 60, 62, 63, 64, 65, 69, 95, 99, 100)
for _ph in _PHASES:
    GROUPS.update(getattr(importlib.import_module(f"reference_p{_ph}"), f"GROUPS_P{_ph}"))
SYNONYMS: dict = {
    **_SYN_P28,
    **_SYN_P43,
    "uom": {
        "m³": "m3", "m²": "m2", "kubik": "m3", "m1": "m", "m'": "m", "btg": "batang",
        "bh": "buah", "lbr": "lembar", "zak": "sak", "lot": "ls", "lumpsum": "ls",
        "lump sum": "ls", "org": "orang", "hr": "hari", "box": "dus", "kaleng": "kaleng",
    },
    "work_category": {
        "umum": "lainnya", "general": "lainnya", "lain-lain": "lainnya", "lain lain": "lainnya",
        "structural": "struktur", "sipil": "struktur", "beton": "struktur",
        "architectural": "arsitektur", "m.e.p": "mep", "m/e": "mep", "me": "mep",
        "mekanikal": "mep", "elektrikal": "mep", "plumbing": "mep",
        "jalan": "infrastruktur", "drainase": "infrastruktur", "jalan & drainase": "infrastruktur",
        "landscape": "lansekap", "taman": "lansekap",
    },
    "inspection_category": {
        "struktur": "structural", "arsitektur": "architectural", "serah terima": "handover",
        "umum": "lainnya",
    },
    "subcon_specialty": {
        "struktur & beton": "struktur", "mep (listrik & plumbing)": "mep",
        "listrik": "mep", "plumbing": "mep", "tanah & urugan": "tanah",
        "jalan & drainase": "infrastruktur", "landscape": "lansekap",
        "material": "supplier", "umum": "lainnya",
    },
    "weather": {
        "cerah berawan": "cerah_berawan", "hujan": "hujan_ringan", "mendung": "berawan",
        "gerimis": "hujan_ringan", "hujan deras": "hujan_lebat",
    },
    "lead_source": {
        "meta_lead_ads": "meta_ads", "facebook": "meta_ads", "instagram": "meta_ads",
        "fb": "meta_ads", "ig": "meta_ads", "tiktok_lead": "tiktok_ads",
        "tiktok": "tiktok_ads", "google": "google_lead", "google_ads": "google_lead",
        "web": "website", "wa": "whatsapp", "walkin": "walk_in", "walk in": "walk_in",
    },
    "channel_type": {
        "meta_ads": "meta_lead_ads", "tiktok_ads": "tiktok_lead", "web": "website",
        "google_ads": "google_lead",
    },
    "complaint_category": {"bangunan": "konstruksi", "legal": "dokumen", "umum": "lainnya"},
    "payment_method": {"va": "virtual_account", "tunai": "cash", "giro": "cheque"},
    "appointment_type": {"kunjungan": "survey", "telepon": "call"},
    "project_status": {"aktif": "active", "selesai": "completed"},
    # Fase konstruksi lama memakai "pending" padahal registry memakai "not_started"
    # (SSOT conflict sisa: nilai ini pernah lolos karena `construction_phases.status`
    # belum terdaftar sebagai field enum yang divalidasi/dimigrasi).
    "construction_status": {
        "pending": "not_started", "belum_mulai": "not_started", "belum mulai": "not_started",
        "berjalan": "in_progress", "progress": "in_progress", "qc": "qc_hold",
        "selesai": "done", "complete": "done", "completed": "done",
    },
}

# Attribution SSOT: channel_accounts.channel <-> leads.source (dulu tidak pernah cocok:
# 'meta_lead_ads' vs 'meta_ads', 'tiktok_lead' vs 'tiktok_ads').
CHANNEL_TO_SOURCE = {
    "whatsapp": "whatsapp", "meta_lead_ads": "meta_ads", "google_lead": "google_lead",
    "tiktok_lead": "tiktok_ads", "website": "website",
}
SOURCE_TO_CHANNEL = {v: k for k, v in CHANNEL_TO_SOURCE.items()}

# Skor kualitas per sumber lead — SSOT (dulu google_lead & tiktok_ads tidak terdaftar
# sehingga lead iklan Google/TikTok diberi skor terendah sama seperti import manual).
SOURCE_SCORE = {
    "walk_in": 25, "meta_ads": 25, "google_lead": 25, "tiktok_ads": 22,
    "whatsapp": 20, "referral": 20, "website": 15, "manual": 10, "import": 10,
    # Fase 28b showroom publik & Fase 39 kanal mitra/event/marketing inhouse (niatnya lebih
    # tinggi daripada form website umum: sudah ada interaksi nyata sebelum data diisi).
    "showroom_public": 24, "partner": 24, "event": 22, "inhouse_marketing": 23,
}


def values(group: str) -> tuple:
    return tuple(o["value"] for o in GROUPS[group]["options"])


def labels(group: str) -> dict:
    return {o["value"]: o["label"] for o in GROUPS[group]["options"]}


def label_of(group: str, value: str) -> str:
    return labels(group).get(value, value)


def is_strict(group: str) -> bool:
    return bool(GROUPS[group].get("strict"))


def canonicalize(group: str, value):
    """Normalisasi nilai ke bentuk kanonik. Mengembalikan nilai asli bila tak dikenal."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    valid = values(group)
    if raw in valid:
        return raw
    syn = SYNONYMS.get(group, {})
    low = raw.lower()
    if low in syn:
        return syn[low]
    snake = low.replace(" ", "_").replace("-", "_").replace("/", "_")
    if snake in valid:
        return snake
    if snake in syn:
        return syn[snake]
    for v in valid:
        if v.lower() == low:
            return v
    return raw


def make_validator(group: str, *, required: bool = False):
    """Validator untuk Annotated types di models.py (pydantic AfterValidator)."""
    def _validate(v):
        if v is None or (isinstance(v, str) and not v.strip()):
            if required:
                raise ValueError(f"{GROUPS[group]['label']} wajib diisi.")
            return None
        cv = canonicalize(group, v)
        if is_strict(group) and cv not in values(group):
            allowed = ", ".join(values(group))
            raise ValueError(
                f"{GROUPS[group]['label']} '{v}' tidak dikenal. Pilihan yang sah: {allowed}.")
        return cv
    return _validate


def public_registry(dynamic_extra: dict = None) -> dict:
    """Bentuk yang dikonsumsi frontend: {group: {label, strict, options:[{value,label}]}}."""
    out = {}
    for name, g in GROUPS.items():
        opts = list(g["options"])
        extra = (dynamic_extra or {}).get(name) or []
        known = {o["value"] for o in opts}
        for v in extra:
            if v and v not in known:
                opts.append(_o(v, v))
                known.add(v)
        out[name] = {"label": g["label"], "strict": bool(g.get("strict")),
                     "dynamic": bool(g.get("dynamic")),
                     "allow_new": g.get("allow_new", True), "options": opts}
    return out


# --------------------------------------------------------------------------
# Annotated types dipakai models.py (validasi otomatis di seluruh endpoint)
# --------------------------------------------------------------------------
def _opt(group: str):
    return Annotated[Optional[str], AfterValidator(make_validator(group))]


def _req(group: str):
    return Annotated[str, AfterValidator(make_validator(group, required=True))]


Uom = _req("uom")
OptUom = _opt("uom")
WorkCategory = _opt("work_category")
InspectionCategory = _opt("inspection_category")
SubconSpecialty = _opt("subcon_specialty")
Weather = _opt("weather")
LeadStage = _opt("lead_stage")
LeadStageReq = _req("lead_stage")
LeadSource = _opt("lead_source")
ScoreBand = _opt("score_band")
ChannelType = _req("channel_type")
OptChannelType = _opt("channel_type")
WaTemplateCategory = _opt("wa_template_category")
AppointmentType = _opt("appointment_type")
UnitType = _opt("unit_type")
UnitStatus = _opt("unit_status")
UnitOrientation = _opt("unit_orientation")   # Fase 28b
ConstructionStatus = _opt("construction_status")
ProjectStatus = _opt("project_status")
PermitType = _opt("permit_type")
PermitAuthority = _opt("permit_authority")
PermitStatus = _opt("permit_status")
PunchSeverity = _opt("punch_severity")
TaskType = _opt("task_type")
TaskStatus = _opt("task_status")
Priority = _opt("priority")
ComplaintCategory = _opt("complaint_category")
ComplaintStatus = _opt("complaint_status")
KycStatus = _opt("kyc_status")
AccountType = _req("account_type")
PaymentMethod = _opt("payment_method")
PoType = _opt("po_type")
TaxType = _opt("tax_type")
CommissionBasis = _opt("commission_basis")
CommissionTrigger = _opt("commission_trigger")
PoStatus = _opt("po_status")
SpkStatus = _opt("spk_status")
PunchStatus = _opt("punch_status")
StockMovement = _req("stock_movement")
QcResult = _opt("qc_result")
SignerRole = _opt("signer_role")
SchemeBasis = _opt("scheme_basis")
FinancingStatus = _opt("financing_status")
SlikStatusReq = _req("slik_status")
FinancingBank = _opt("financing_bank")
UserRole = _req("user_role")
OptUserRole = _opt("user_role")

ComplaintStatusReq = _req("complaint_status")
PermitStatusReq = _req("permit_status")
PermitTypeReq = _req("permit_type")
OptAccountType = _opt("account_type")
UnitTypeReq = _req("unit_type")

# ---------------- Fase 26 ----------------
AppointmentStatusReq = _req("appointment_status")
ActivityType = _opt("activity_type")
MsgDirection = _req("msg_direction")
AutomationTrigger = _req("automation_trigger")
OptAutomationTrigger = _opt("automation_trigger")
AutomationAction = _req("automation_action")
SurveyCheckStatus = _opt("survey_check_status")
SurveyResultReq = _req("survey_result")
InspectionItemResult = _opt("inspection_item_result")
InspectionStatus = _opt("inspection_status")
DocumentStatus = _opt("document_status")
DealStatus = _opt("deal_status")
LegalStage = _opt("legal_stage")
UnitPaymentStatus = _opt("unit_payment_status")
ArStatus = _opt("ar_status")
ApStatus = _opt("ap_status")
CommissionStatus = _opt("commission_status")
CollectionBucket = _opt("collection_bucket")
DepositTxn = _req("deposit_txn")
TaxStatus = _opt("tax_status")
TaxTypeReq = _req("tax_type")
RequisitionStatus = _opt("requisition_status")
ClaimStatus = _opt("claim_status")
ChangeOrderStatus = _opt("change_order_status")
OrgStatus = _opt("org_status")
PoStatusReq = _req("po_status")
SpkStatusReq = _req("spk_status")
PunchStatusReq = _req("punch_status")
QcResultReq = _req("qc_result")
SchemeBasisReq = _req("scheme_basis")
PaymentMethodOpt = _opt("payment_method")
SignerRoleReq = _req("signer_role")
FinancingBankReq = _req("financing_bank")
DocumentTemplate = _opt("document_template")
InspectionTemplate = _opt("inspection_template")
WaTemplateStatus = _opt("wa_template_status")
NotificationType = _opt("notification_type")
