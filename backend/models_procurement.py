"""models_procurement.py — model permintaan (request) pilar PENGADAAN & BUKU BESAR.

Dipisah dari `models.py` (Fase 44) karena berkas itu melewati batas NFR 800 baris
(`scripts/validate_compliance.py`). Pemisahannya per DOMAIN, bukan per ukuran: semua
model di sini milik alur Subkontraktor/SPK → Klaim Progres/Change Order → BoQ/RAB →
PO/GRN/3-way match → Jurnal & CoA.

PENTING: `models.py` MENG-EKSPOR ULANG seluruh kelas di berkas ini, sehingga
`from models import POCreate` (dipakai belasan router lama) TETAP bekerja. Router baru
sebaiknya mengimpor langsung dari sini agar ketergantungannya jelas.
"""
from typing import Optional, List
from pydantic import BaseModel, EmailStr

import reference as ref


# ----------------------------- Phase 12 — Procurement pillar (BoQ + Subcon/SPK + PO/GRN/3-way) -----------------------------
# EPIC 2.2 — Subkontraktor & SPK
class SubcontractorCreate(BaseModel):
    code: str = ""
    name: str
    specialty: ref.SubconSpecialty = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    npwp: Optional[str] = None
    address: Optional[str] = None
    pic_name: Optional[str] = None
    rating: Optional[float] = None
    notes: Optional[str] = None


class SubcontractorUpdate(BaseModel):
    name: Optional[str] = None
    specialty: ref.SubconSpecialty = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    npwp: Optional[str] = None
    address: Optional[str] = None
    pic_name: Optional[str] = None
    rating: Optional[float] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class SPKCreate(BaseModel):
    subcontractor_id: str
    project_id: str
    title: str
    scope: Optional[str] = None
    contract_value: int = 0
    retention_pct: float = 5
    # Fase 48C: masa pemeliharaan (defect liability) \u2014 dasar gerbang pencairan retensi.
    maintenance_days: int = 90
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None


class SPKUpdate(BaseModel):
    title: Optional[str] = None
    scope: Optional[str] = None
    contract_value: Optional[int] = None
    retention_pct: Optional[float] = None
    maintenance_days: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    progress_pct: Optional[int] = None
    notes: Optional[str] = None


class SPKStatusUpdate(BaseModel):
    status: ref.SpkStatusReq
    note: Optional[str] = None


# EPIC 2.3 — Progress Claim (Termin) & Change Order (Subcon)
class ProgressClaimCreate(BaseModel):
    spk_id: str
    period: Optional[str] = None          # label, mis. "Termin 2"
    progress_pct: Optional[int] = None    # hanya SPK lump-sum lama (mode item: dihitung)
    due_date: Optional[str] = None
    note: Optional[str] = None


class StatusNote(BaseModel):
    note: Optional[str] = None


class ChangeOrderCreate(BaseModel):
    spk_id: str
    title: str
    description: Optional[str] = None
    value_delta: int                      # +/- IDR terhadap nilai kontrak
    time_extension_days: Optional[int] = 0
    reason: Optional[str] = None


# EPIC 2.1 — BoQ / RAB
class BoQItemCreate(BaseModel):
    project_id: str
    cost_code: Optional[str] = None
    category: ref.WorkCategory = "lainnya"
    description: str
    uom: ref.Uom = "unit"
    quantity: float = 1
    unit_price: int = 0
    notes: Optional[str] = None
    # Fase 80: lingkup RAB (unit | fasum | umum), fasilitas/jenis, tautan fase konstruksi proyek
    scope: Optional[str] = "unit"
    facility: Optional[str] = None
    phase_id: Optional[str] = None


class BoQItemUpdate(BaseModel):
    cost_code: Optional[str] = None
    category: ref.WorkCategory = None
    description: Optional[str] = None
    uom: ref.OptUom = None
    quantity: Optional[float] = None
    unit_price: Optional[int] = None
    notes: Optional[str] = None
    scope: Optional[str] = None
    facility: Optional[str] = None
    phase_id: Optional[str] = None


# EPIC 3.6 — Purchase Order + GRN + 3-way match
class POItemIn(BaseModel):
    description: str
    material_id: Optional[str] = None
    boq_item_id: Optional[str] = None
    uom: ref.Uom = "unit"
    qty: float = 1
    unit_price: int = 0


class POCreate(BaseModel):
    project_id: str
    po_type: ref.PoType = "material"
    vendor: str
    # Fase 48A: PO baru sebaiknya menunjuk MASTER vendor. `vendor` (teks) tetap ada sebagai
    # SNAPSHOT nama agar dokumen lama tidak berubah isi ketika master di-rename.
    vendor_id: Optional[str] = None
    subcontractor_id: Optional[str] = None
    spk_id: Optional[str] = None
    items: List[POItemIn]
    due_date: Optional[str] = None
    note: Optional[str] = None


class POAction(BaseModel):
    note: Optional[str] = None


class GRNItemIn(BaseModel):
    po_item_index: int
    qty_received: float


class GRNCreate(BaseModel):
    po_id: str
    items: List[GRNItemIn]
    note: Optional[str] = None


class ProcurementBillCreate(BaseModel):
    po_id: str
    grn_id: Optional[str] = None
    claimed: int
    retention_pct: float = 5
    due_date: Optional[str] = None
    note: Optional[str] = None
    # Fase 48B: 3-way match MENAHAN tagihan yang melebihi barang diterima/nilai PO.
    # Terobosan hanya boleh dilakukan manajer keuangan dan WAJIB beralasan (\u2265 10 huruf).
    override_hold: bool = False
    override_reason: Optional[str] = None


# ----------------------------- Phase 13 — CoA / General Ledger (EPIC 3.4) -----------------------------
class AccountCreate(BaseModel):
    code: str
    name: str
    type: ref.AccountType
    parent_code: Optional[str] = None


class JournalLineIn(BaseModel):
    account_code: str
    debit: int = 0
    credit: int = 0
    memo: Optional[str] = None


class JournalCreate(BaseModel):
    memo: str
    date: Optional[str] = None
    lines: List[JournalLineIn]
