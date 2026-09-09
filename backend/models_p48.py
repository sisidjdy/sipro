"""Model request Fase 48 (vendor & harga, PR→PO, retur, uang muka/potongan/retensi, stok).

Aturan yang TIDAK BOLEH bergantung pada kebaikan hati pemanggil diletakkan di sini **dan**
di lapisan service — jalur non-HTTP (seed, migrasi, uji) tidak melewati model, jadi aturan
yang hanya hidup di model akan bocor. `scripts/mutasi_48.py` menyerang KEDUA lapis.

  * **alasan wajib** untuk setiap tindakan yang membalik/mengurangi uang atau barang
    (retur barang, menerobos 3-way match, membatalkan potongan, mencairkan retensi,
    transfer stok antar proyek);
  * **nominal rupiah** bilangan bulat > 0 (tanpa sen);
  * **tanggal** ISO `YYYY-MM-DD` supaya tidak ada tafsir dd/mm vs mm/dd di jurnal;
  * **enum** divalidasi lewat SSOT `reference.GROUPS` (nilai liar ditolak 400 berbahasa
    Indonesia).
"""
from typing import Annotated, List, Optional

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator

import reference as ref

MIN_REASON = 5
MIN_STRONG_REASON = 10


def _opt(group: str):
    return Annotated[Optional[str], AfterValidator(ref.make_validator(group))]


def _req(group: str):
    return Annotated[str, AfterValidator(ref.make_validator(group, required=True))]


VendorCategoryReq = _req("vendor_category")
VendorCategoryOpt = _opt("vendor_category")
PriceSourceOpt = _opt("price_source")
ReturnKindReq = _req("return_kind")
DeductionKindReq = _req("deduction_kind")
EvalCriteriaReq = _req("eval_criteria")
UomOpt = _opt("uom")


def _reason(v, minimum: int, what: str):
    text = (v or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Alasan minimal {minimum} huruf — tulis {what} agar keputusan ini "
                         "bisa dipertanggungjawabkan.")
    return text


# ============================================================ 48A — vendor & harga
class VendorIn(BaseModel):
    """Master vendor. Sebelum Fase 48 nama vendor hanya teks bebas di PO/tagihan."""
    code: str = Field("", max_length=20)
    name: str = Field(min_length=3, max_length=100)
    category: VendorCategoryReq = "material"
    npwp: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    pic_name: Optional[str] = None
    payment_terms_days: int = Field(default=30, ge=0, le=180)
    bank_name: Optional[str] = None
    bank_account_no: Optional[str] = None
    bank_account_holder: Optional[str] = None
    is_active: bool = True
    note: Optional[str] = None


class VendorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=100)
    category: VendorCategoryOpt = None
    npwp: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    pic_name: Optional[str] = None
    payment_terms_days: Optional[int] = Field(default=None, ge=0, le=180)
    bank_name: Optional[str] = None
    bank_account_no: Optional[str] = None
    bank_account_holder: Optional[str] = None
    is_active: Optional[bool] = None
    note: Optional[str] = None


class PriceIn(BaseModel):
    """Satu baris daftar harga. `material_id` ATAU `item_name` wajib ada."""
    vendor_id: str
    material_id: Optional[str] = None
    item_name: Optional[str] = Field(default=None, max_length=120)
    uom: UomOpt = None
    unit_price: int = Field(gt=0)
    source: PriceSourceOpt = "manual"
    valid_from: str = Field(min_length=10, max_length=10)
    valid_until: Optional[str] = Field(default=None, min_length=10, max_length=10)
    note: Optional[str] = None

    @field_validator("item_name")
    @classmethod
    def _need_item(cls, v, info):
        if not v and not (info.data or {}).get("material_id"):
            raise ValueError("Sebutkan material (material_id) atau nama barang (item_name).")
        return v


class AssessmentIn(BaseModel):
    """Penilaian MANUSIA (melengkapi skor berbukti; tidak menggantikannya)."""
    period: str = Field(min_length=4, max_length=10)      # mis. 2026-Q3 / 2026-08
    scores: dict = Field(description="kriteria SSOT eval_criteria → 1..5")
    note: str

    @field_validator("scores")
    @classmethod
    def _check_scores(cls, v):
        valid = {o["value"] for o in ref.GROUPS["eval_criteria"]["options"]}
        if not v:
            raise ValueError("Isi minimal satu kriteria penilaian.")
        for key, val in v.items():
            if key not in valid:
                raise ValueError(f"Kriteria '{key}' tidak dikenal (lihat Kamus Data eval_criteria).")
            if not isinstance(val, (int, float)) or not 1 <= float(val) <= 5:
                raise ValueError(f"Nilai kriteria '{key}' harus angka 1 sampai 5.")
        return {k: float(x) for k, x in v.items()}

    @field_validator("note")
    @classmethod
    def _check_note(cls, v):
        return _reason(v, MIN_STRONG_REASON, "dasar penilaian (apa yang Anda amati)")


# ============================================================ 48B — PR→PO, retur, 3-way
class ReqToPoItemIn(BaseModel):
    material_id: str
    qty: float = Field(gt=0)
    unit_price: int = Field(gt=0)


class ReqToPoIn(BaseModel):
    """Ubah kekurangan stok pada permintaan material menjadi PO ke vendor terdaftar."""
    vendor_id: str
    items: Optional[List[ReqToPoItemIn]] = None   # default: seluruh kekurangan
    due_date: Optional[str] = Field(default=None, min_length=10, max_length=10)
    note: Optional[str] = None


class ReturnItemIn(BaseModel):
    grn_item_index: int = Field(ge=0)
    qty_returned: float = Field(gt=0)


class ReturnIn(BaseModel):
    """Retur barang: membalik penerimaan (stok & nilai diterima) dengan alasan wajib."""
    grn_id: str
    kind: ReturnKindReq
    items: List[ReturnItemIn] = Field(min_length=1)
    reason: str

    @field_validator("reason")
    @classmethod
    def _check(cls, v):
        return _reason(v, MIN_STRONG_REASON, "sebab barang dikembalikan ke vendor")


class BillOverrideIn(BaseModel):
    """Menerobos tahanan 3-way match — hanya manajer keuangan, wajib beralasan."""
    reason: str

    @field_validator("reason")
    @classmethod
    def _check(cls, v):
        return _reason(v, MIN_STRONG_REASON,
                       "dasar tagihan tetap diproses walau melebihi barang diterima")


# ============================================================ 48C — uang muka, potongan, retensi
class AdvanceIn(BaseModel):
    spk_id: str
    amount: int = Field(gt=0)
    reason: str
    due_date: Optional[str] = Field(default=None, min_length=10, max_length=10)

    @field_validator("reason")
    @classmethod
    def _check(cls, v):
        return _reason(v, MIN_STRONG_REASON, "keperluan uang muka (mis. mobilisasi alat)")


class AdvanceDecisionIn(BaseModel):
    approve: bool
    reason: str

    @field_validator("reason")
    @classmethod
    def _check(cls, v):
        return _reason(v, MIN_REASON, "dasar keputusan")


class AdvancePayIn(BaseModel):
    amortize_pct: float = Field(default=100, gt=0, le=100)
    note: Optional[str] = None


class DeductionIn(BaseModel):
    spk_id: str
    kind: DeductionKindReq
    amount: int = Field(gt=0)
    reason: str
    advance_id: Optional[str] = None

    @field_validator("reason")
    @classmethod
    def _check(cls, v):
        return _reason(v, MIN_STRONG_REASON, "dasar potongan (angka ini mengurangi uang orang)")


class ReasonIn(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def _check(cls, v):
        return _reason(v, MIN_STRONG_REASON, "alasannya selengkap mungkin")


# ============================================================ 48E — stok
class TransferIn(BaseModel):
    """Pindah material antar proyek: keluar dari satu, masuk ke yang lain (tidak menciptakan barang)."""
    from_project_id: str
    to_project_id: str
    material_id: str
    qty: float = Field(gt=0)
    reason: str

    @field_validator("reason")
    @classmethod
    def _check(cls, v):
        return _reason(v, MIN_STRONG_REASON, "sebab material dipindahkan")


class MinStockIn(BaseModel):
    min_qty: float = Field(ge=0)
