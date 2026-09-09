"""Model masukan Fase 53 — konversi pembeli, kontrak, KPR, generator dokumen.

Aturan yang dipaksakan di lapis model (lapis pertama; mesinnya memeriksa ulang):
  * alasan/keterangan yang menjadi DASAR KEPUTUSAN wajib berisi kalimat, bukan satu huruf;
  * nominal biaya boleh `None` = "belum diketahui" dan itu BERBEDA dari 0;
  * nomor & tanggal dokumen legal boleh dikosongkan (sistem yang menomori), tetapi bila
    diisi manual harus tetap masuk jejak.
"""
from typing import List, Optional

from pydantic import BaseModel, field_validator

MIN_REASON = 10


def _reason(v, minimum: int, apa: str):
    text = (v or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Tulis {apa} minimal {minimum} huruf — jejak keputusan ini dibaca "
                         "orang lain di kemudian hari.")
    return text


class ConvertToCustomerIn(BaseModel):
    """Konversi lead → pembeli. Data diri boleh dilengkapi sekaligus di sini."""
    nik: Optional[str] = None
    npwp: Optional[str] = None
    address: Optional[str] = None
    occupation: Optional[str] = None
    monthly_income: Optional[int] = None
    spouse_name: Optional[str] = None
    spouse_nik: Optional[str] = None
    heir_name: Optional[str] = None
    heir_relation: Optional[str] = None
    scheme: Optional[str] = None          # cash_keras | cash_bertahap | kpr
    note: Optional[str] = None


class ContractCostsIn(BaseModel):
    """Komponen biaya transaksi. `None` = belum diketahui (JANGAN dikirim 0 untuk itu)."""
    bphtb: Optional[int] = None
    notary_fee: Optional[int] = None
    bank_fee: Optional[int] = None
    insurance: Optional[int] = None
    pph_seller: Optional[int] = None
    promo_discount: Optional[int] = None
    plafon_kredit: Optional[int] = None
    dp_percent: Optional[float] = None
    note: Optional[str] = None


class ContractSchemeIn(BaseModel):
    scheme: str
    reason: Optional[str] = None


class LegalAdvanceIn(BaseModel):
    """Majukan satu tahap legal. Bukti (file) opsional untuk tahap yang tidak mensyaratkan."""
    number: Optional[str] = None
    date: Optional[str] = None
    notary: Optional[str] = None
    place: Optional[str] = None
    file_id: Optional[str] = None
    note: Optional[str] = None


class KprStageIn(BaseModel):
    """Majukan tahap KPR. Gerbang bukti diperiksa mesin (SP3K wajib file + plafon)."""
    number: Optional[str] = None
    date: Optional[str] = None
    plafon: Optional[int] = None
    tenor_months: Optional[int] = None
    rate: Optional[float] = None
    valid_until: Optional[str] = None
    bank: Optional[str] = None
    file_id: Optional[str] = None
    notary: Optional[str] = None
    place: Optional[str] = None
    amount: Optional[int] = None
    note: Optional[str] = None
    tranche_code: Optional[str] = None
    allow_deposit: Optional[bool] = None
    reason: Optional[str] = None
    cash_account_id: Optional[str] = None   # Fase 82: rekening penerima dana KPR


class KprRejectIn(BaseModel):
    reason: str
    file_id: Optional[str] = None

    @field_validator("reason")
    @classmethod
    def _r(cls, v):
        return _reason(v, MIN_REASON, "alasan penolakan bank")


class DocGenerateIn(BaseModel):
    """Terbitkan dokumen dari template owner. `template_code` kosong = pilih otomatis
    berdasarkan skema kontrak (SPR_CASH / SPR_CASH_STAGED / SPR_KPR)."""
    template_code: Optional[str] = None
    note: Optional[str] = None


class AddonSetIn(BaseModel):
    """Add-on/spek tambahan pada kontrak (change order sesudah SPR wajib beralasan)."""
    items: List[dict] = []
    reason: Optional[str] = None
