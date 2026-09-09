"""Model request Fase 26 — titipan pelanggan (kelebihan bayar).

Dipisah dari `models.py` agar file itu tetap di bawah batas compliance (800 baris).
"""
from typing import Optional

from pydantic import BaseModel


class DepositReceive(BaseModel):
    """Terima titipan di muka (belum dialokasikan ke termin)."""
    amount: int
    note: Optional[str] = None


class DepositApply(BaseModel):
    """Pakai titipan untuk termin. amount None = sebanyak mungkin (min saldo, sisa tagihan)."""
    amount: Optional[int] = None
    note: Optional[str] = None


class DepositRefund(BaseModel):
    """Kembalikan titipan ke pelanggan. amount None = seluruh saldo."""
    amount: Optional[int] = None
    note: Optional[str] = None
