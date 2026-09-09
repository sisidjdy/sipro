"""Model masukan Fase 56 — pembatalan kontrak & refund berjurnal.

Aturan yang dipaksakan di lapis model (mesinnya memeriksa ulang — lapis ini hanya yang
pertama): keputusan yang mengubah uang orang lain WAJIB membawa alasan yang bisa dibaca
manusia lain di kemudian hari, dan nominal tidak boleh negatif.
"""
from typing import Optional

from pydantic import BaseModel, field_validator

MIN_REASON = 10


def _reason(v, minimum: int, apa: str) -> str:
    text = (v or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Tulis {apa} minimal {minimum} huruf — jejak keputusan ini dibaca "
                         "orang lain (dan pembeli) di kemudian hari.")
    return text


class CancellationRequestIn(BaseModel):
    """Pengajuan pembatalan oleh Manajer Sales/Marketing."""
    contract_id: str
    reason: str

    @field_validator("reason")
    @classmethod
    def _v_reason(cls, v):
        return _reason(v, MIN_REASON, "alasan pembatalan")


class CancellationDecisionIn(BaseModel):
    """Keputusan Manajer Keuangan. Menolak pun WAJIB beralasan."""
    approved: bool
    note: str

    @field_validator("note")
    @classmethod
    def _v_note(cls, v):
        return _reason(v, MIN_REASON, "catatan keputusan")


class RefundPayIn(BaseModel):
    """Pembayaran refund (boleh bertahap, idempoten lewat `client_ref`)."""
    method: str = "transfer"
    amount: Optional[int] = None
    note: Optional[str] = None
    client_ref: Optional[str] = None
    override: bool = False
    override_reason: Optional[str] = None

    @field_validator("method")
    @classmethod
    def _v_method(cls, v):
        if (v or "") not in ("transfer", "tunai"):
            raise ValueError("Cara pembayaran refund hanya `transfer` atau `tunai`.")
        return v

    @field_validator("amount")
    @classmethod
    def _v_amount(cls, v):
        if v is not None and int(v) <= 0:
            raise ValueError("Nominal refund harus lebih dari 0 (kosongkan untuk membayar "
                             "seluruh sisa).")
        return v

    @field_validator("override_reason")
    @classmethod
    def _v_override(cls, v):
        if v is None or not str(v).strip():
            return None
        return _reason(v, MIN_REASON, "alasan pengabaian penahanan refund")
