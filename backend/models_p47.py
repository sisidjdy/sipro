"""Model request Fase 47 (rekonsiliasi bank, bukti transfer portal, penawaran, upah harian).

Semua enum divalidasi lewat SSOT `reference.GROUPS` sehingga nilai liar ditolak 400 dengan
pesan berbahasa Indonesia. Validasi yang diletakkan di lapisan model adalah yang tidak boleh
bergantung pada kebaikan hati pemanggil:

  * **alasan** saat membatalkan pencocokan bank / menolak bukti transfer / menolak diskon —
    keputusan yang membalik uang harus bisa dipertanggungjawabkan;
  * **nominal** transfer & upah harian harus bilangan bulat positif (rupiah, tanpa sen);
  * **tanggal** memakai format ISO `YYYY-MM-DD` supaya tidak ada tafsir dd/mm vs mm/dd
    ketika angka masuk ke jurnal.

Catatan penting: panjang alasan diperiksa DI SINI **dan** di lapisan service (engine).
Itu bukan duplikasi asal-asalan — jalur non-HTTP (seed, migrasi, uji) tidak melewati model,
jadi aturan yang hanya hidup di model akan bocor. Uji-mutasi menyerang KEDUA lapis sekaligus.
"""
from typing import Annotated, List, Optional

from pydantic import AfterValidator, BaseModel, Field, field_validator

import reference as ref

MIN_REASON = 5
MIN_REJECT_REASON = 10


def _opt(group: str):
    return Annotated[Optional[str], AfterValidator(ref.make_validator(group))]


def _req(group: str):
    return Annotated[str, AfterValidator(ref.make_validator(group, required=True))]


MatchKindReq = _req("bank_match_kind")
AttendanceStatusReq = _req("attendance_status")
LaborRoleReq = _req("labor_role")


def _reason(v, minimum: int, what: str):
    text = (v or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Alasan minimal {minimum} huruf — tulis {what} agar keputusan ini "
                         "bisa dipertanggungjawabkan.")
    return text


# ============================================================ 47A — rekonsiliasi bank
class BankAccountIn(BaseModel):
    """Rekening yang direkonsiliasi. `gl_account_code` mengikat mutasi ke pembukuan."""
    name: str = Field(min_length=3, max_length=80)
    bank_name: str = Field(min_length=2, max_length=60)
    account_no: str = Field(min_length=4, max_length=40)
    holder: Optional[str] = None
    gl_account_code: str = Field(min_length=4, max_length=12)
    opening_balance: int = 0
    note: Optional[str] = None
    is_active: bool = True


class BankImportIn(BaseModel):
    """Impor mutasi rekening dari CSV. `dry_run=True` WAJIB tidak menulis apa pun."""
    account_id: str
    filename: str = Field(min_length=1, max_length=160)
    csv_text: str = Field(min_length=1)
    dry_run: bool = True


class BankMatchIn(BaseModel):
    """Cocokkan satu mutasi ke satu dokumen. Tidak ada pencocokan otomatis diam-diam."""
    kind: MatchKindReq
    target_id: Optional[str] = None
    note: Optional[str] = None


class BankUnmatchIn(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def _check(cls, v):
        return _reason(v, MIN_REASON, "sebab pembatalan pencocokan")


class BankIgnoreIn(BaseModel):
    """Mutasi yang memang bukan urusan kita (mis. mutasi pribadi) — tetap berjejak."""
    reason: str

    @field_validator("reason")
    @classmethod
    def _check(cls, v):
        return _reason(v, MIN_REASON, "sebab mutasi ini diabaikan")


# ============================================================ 47B — bukti transfer portal
class PaymentProofIn(BaseModel):
    """Setoran yang DIAKUI PELANGGAN — belum mengubah tagihan sampai finance memverifikasi."""
    deal_id: str
    amount: int = Field(gt=0)
    transfer_date: str = Field(min_length=10, max_length=10)
    bank_name: Optional[str] = None
    file_ids: List[str] = Field(min_length=1)
    note: Optional[str] = None


class IntakeVerifyIn(BaseModel):
    """Verifikasi finance. `bank_txn_id` opsional: menautkan bukti ke mutasi rekening."""
    bank_txn_id: Optional[str] = None
    note: Optional[str] = None
    allow_overpay: bool = False


class IntakeRejectIn(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def _check(cls, v):
        return _reason(v, MIN_REJECT_REASON,
                       "alasan yang akan DIBACA PELANGGAN di portal")


# ============================================================ 47C — penawaran
class QuotationAddonIn(BaseModel):
    code: str
    qty: float = Field(gt=0, default=1)


class KprInput(BaseModel):
    """Bahan simulasi KPR. Kosong = simulasi TIDAK dihitung (bukan angka karangan)."""
    tenor_months: Optional[int] = Field(default=None, ge=0, le=360)
    annual_rate_pct: Optional[float] = Field(default=None, ge=0, le=40)
    dp_pct: Optional[float] = Field(default=None, ge=0, le=100)


class QuotationSimulateIn(BaseModel):
    unit_id: str
    addons: List[QuotationAddonIn] = []
    scheme_id: Optional[str] = None
    # Fase 69: `discount_amount` bebas TIDAK lagi diterima (>0 → 400). Potongan dipilih dari
    # aturan yang dikonfigurasi: skema diskon, promo, kupon.
    discount_amount: int = Field(default=0, ge=0)
    discount_scheme_id: Optional[str] = None
    promo_id: Optional[str] = None
    coupon_code: Optional[str] = None
    lead_id: Optional[str] = None
    kpr: Optional[KprInput] = None
    # Fase 88C: skema all-in ikut disimulasikan agar potongan bersasaran komponen biaya
    # (mis. "potong biaya notaris") dihitung di layar — bukan Rp 0 "menunggu reservasi".
    allin_scheme_id: Optional[str] = None
    booking_fee: Optional[int] = Field(default=None, ge=0)


class QuotationCreateIn(QuotationSimulateIn):
    lead_id: str
    valid_days: Optional[int] = Field(default=None, ge=1, le=90)
    note: Optional[str] = None
    discount_reason: Optional[str] = None


class QuotationDecisionIn(BaseModel):
    approve: bool
    reason: str

    @field_validator("reason")
    @classmethod
    def _check(cls, v):
        return _reason(v, MIN_REASON, "dasar keputusan diskon")


class QuotationSendIn(BaseModel):
    channel: Optional[str] = "whatsapp"
    note: Optional[str] = None


# ============================================================ 47D — tenaga kerja & upah
class WorkerIn(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    role: LaborRoleReq
    daily_wage: int = Field(gt=0)
    phone: Optional[str] = None
    subcon_id: Optional[str] = None
    project_ids: List[str] = []
    note: Optional[str] = None
    is_active: bool = True


class AttendanceEntryIn(BaseModel):
    worker_id: str
    status: AttendanceStatusReq
    overtime_hours: float = Field(default=0, ge=0, le=12)
    unit_id: Optional[str] = None
    note: Optional[str] = None


class AttendanceIn(BaseModel):
    """Absensi satu hari untuk satu proyek (sekali kirim untuk banyak orang)."""
    project_id: str
    work_date: str = Field(min_length=10, max_length=10)
    entries: List[AttendanceEntryIn] = Field(min_length=1)
    # Fase 50B — penanda antrean perangkat: absensi dikerjakan di lokasi yang sering tanpa
    # sinyal. Tanpa penanda ini, mandor yang menekan "kirim" dua kali membuat absensi ganda
    # dan upah ganda; yang tidak menekan ulang kehilangan absensi seharian tanpa jejak.
    client_ref: Optional[str] = Field(default=None, max_length=120)


class PayrollBuildIn(BaseModel):
    project_id: str
    period_start: str = Field(min_length=10, max_length=10)
    period_end: str = Field(min_length=10, max_length=10)
    budget_item_id: Optional[str] = None
    note: Optional[str] = None


class PayrollDecisionIn(BaseModel):
    approve: bool
    reason: Optional[str] = None

    @field_validator("reason")
    @classmethod
    def _check(cls, v):
        if v is None or not str(v).strip():
            return None
        return _reason(v, MIN_REASON, "dasar keputusan")


class PayrollPayIn(BaseModel):
    bank_txn_id: Optional[str] = None
    note: Optional[str] = None
