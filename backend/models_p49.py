"""Model permintaan Fase 49 — penutupan buku, laporan owner, pajak & kepatuhan.

Aturan yang DIPAKSAKAN di lapisan model (bukan di layar): alasan wajib punya panjang minimum,
nominal harus > 0, periode wajib `YYYY-MM`, tahun wajib 4 angka, dan setiap enum divalidasi
lewat Kamus Data (SSOT `reference.py`) sehingga nilai di luar kamus dijawab 400 beserta daftar
pilihan yang sah.
"""
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

import reference as ref

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
YEAR_RE = re.compile(r"^\d{4}$")


def _enum(group: str, value):
    """Validasi nilai terhadap Kamus Data; pesan menyebut pilihan yang sah."""
    return ref.make_validator(group, required=True)(value)


class PeriodCloseAction(BaseModel):
    """Tutup periode. `override` hanya boleh dipakai peran berwenang (dijaga router)."""
    model_config = ConfigDict(extra="ignore")

    period: str = Field(..., description="Periode YYYY-MM")
    note: str = None
    override: bool = False
    override_reason: str = None

    @field_validator("period")
    @classmethod
    def _period(cls, v):
        if not PERIOD_RE.match(v or ""):
            raise ValueError("Format periode harus YYYY-MM (mis. 2026-08).")
        return v

    @field_validator("override_reason")
    @classmethod
    def _reason(cls, v):
        if v is not None and len(v.strip()) < 10:
            raise ValueError("Alasan terobosan minimal 10 huruf — tulis dasar periode ini tetap "
                             "ditutup walau daftar periksa belum bersih.")
        return v.strip() if v else v


class YearAction(BaseModel):
    """Tutup/buka tahun buku."""
    model_config = ConfigDict(extra="ignore")

    year: str = Field(..., description="Tahun buku YYYY")
    note: str = None
    reason: str = None

    @field_validator("year")
    @classmethod
    def _year(cls, v):
        if not YEAR_RE.match(str(v or "")):
            raise ValueError("Format tahun harus YYYY (mis. 2026).")
        return str(v)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v):
        if v is not None and len(v.strip()) < 10:
            raise ValueError("Alasan minimal 10 huruf — buka kembali tahun buku membalik jurnal "
                             "penutup, jadi dasarnya harus tertulis.")
        return v.strip() if v else v


class FakturReplace(BaseModel):
    """Faktur pengganti: nomor baru, berjejak ke nomor lama, alasan wajib."""
    model_config = ConfigDict(extra="ignore")

    reason: str
    buyer_npwp: str = None
    buyer_name: str = None
    dpp: int = None

    @field_validator("reason")
    @classmethod
    def _reason(cls, v):
        if len((v or "").strip()) < 10:
            raise ValueError("Alasan minimal 10 huruf — sebutkan apa yang salah pada faktur lama.")
        return v.strip()

    @field_validator("dpp")
    @classmethod
    def _dpp(cls, v):
        if v is not None and int(v) <= 0:
            raise ValueError("DPP harus lebih dari 0.")
        return v


class FakturCancel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, v):
        if len((v or "").strip()) < 10:
            raise ValueError("Alasan pembatalan minimal 10 huruf — faktur batal ikut mengubah "
                             "SPT Masa PPN, jadi dasarnya harus tertulis.")
        return v.strip()


class WithholdingIssue(BaseModel):
    """Terbitkan bukti potong atas potongan yang BENAR-BENAR terjadi."""
    model_config = ConfigDict(extra="ignore")

    kind: str
    basis: str = "manual"
    party_name: str
    party_npwp: str = None
    party_kind: str = "company"
    base: int
    rate: float
    object_code: str = None
    ref_id: str = None
    ref_label: str = None
    date: str = None
    note: str = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        return _enum("withholding_kind", v)

    @field_validator("basis")
    @classmethod
    def _basis(cls, v):
        return _enum("withholding_basis", v or "manual")

    @field_validator("party_name")
    @classmethod
    def _party(cls, v):
        if len((v or "").strip()) < 3:
            raise ValueError("Nama pihak yang dipotong wajib diisi.")
        return v.strip()

    @field_validator("base")
    @classmethod
    def _base(cls, v):
        if int(v) <= 0:
            raise ValueError("Dasar pengenaan pajak harus lebih dari 0.")
        return int(v)

    @field_validator("rate")
    @classmethod
    def _rate(cls, v):
        if float(v) <= 0 or float(v) > 100:
            raise ValueError("Tarif harus di antara 0 dan 100 persen.")
        return float(v)

    @field_validator("object_code")
    @classmethod
    def _obj(cls, v):
        if v and not re.match(r"^\d{2}-\d{3}-\d{2}$", v.strip()):
            raise ValueError("Kode objek pajak ditulis NN-NNN-NN sesuai lampiran DJP "
                             "(mis. 24-104-01) atau dibiarkan kosong.")
        return v.strip() if v else None


class WithholdingCorrect(BaseModel):
    """Pembetulan bukti potong — nomornya TETAP (PER-24/PJ/2021), versinya naik."""
    model_config = ConfigDict(extra="ignore")

    reason: str
    base: int = None
    rate: float = None
    party_npwp: str = None
    object_code: str = None

    @field_validator("reason")
    @classmethod
    def _reason(cls, v):
        if len((v or "").strip()) < 10:
            raise ValueError("Alasan pembetulan minimal 10 huruf — pihak yang dipotong menerima "
                             "bukti baru dengan nomor yang sama.")
        return v.strip()

    @field_validator("base")
    @classmethod
    def _base(cls, v):
        if v is not None and int(v) <= 0:
            raise ValueError("Dasar pengenaan pajak harus lebih dari 0.")
        return v


class WithholdingCancel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, v):
        if len((v or "").strip()) < 10:
            raise ValueError("Alasan pembatalan minimal 10 huruf — nomor bukti potong yang "
                             "dibatalkan tidak boleh dipakai lagi.")
        return v.strip()


class BillPayWithholding(BaseModel):
    """Bayar tagihan AP dengan memotong PPh: vendor menerima NET, potongan jadi utang pajak."""
    model_config = ConfigDict(extra="ignore")

    bill_id: str
    amount: int
    kind: str
    rate: float
    base: int = None
    object_code: str = None
    note: str = None
    cash_account_id: str = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        return _enum("withholding_kind", v)

    @field_validator("amount")
    @classmethod
    def _amount(cls, v):
        if int(v) <= 0:
            raise ValueError("Nominal pembayaran harus lebih dari 0.")
        return int(v)

    @field_validator("rate")
    @classmethod
    def _rate(cls, v):
        if float(v) <= 0 or float(v) > 100:
            raise ValueError("Tarif harus di antara 0 dan 100 persen.")
        return float(v)

    @field_validator("object_code")
    @classmethod
    def _obj(cls, v):
        if v and not re.match(r"^\d{2}-\d{3}-\d{2}$", v.strip()):
            raise ValueError("Kode objek pajak ditulis NN-NNN-NN (mis. 24-104-01) atau kosong.")
        return v.strip() if v else None
