"""Model request Fase 82 — Kas & Bank (master rekening/kas terpadu + transfer internal)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class CashAccountIn(BaseModel):
    kind: Literal["bank", "cash"] = "bank"
    name: str = Field(min_length=3, max_length=80)
    bank_name: Optional[str] = Field(default=None, max_length=60)
    account_no: str = Field(min_length=2, max_length=40)
    holder: Optional[str] = None
    opening_balance: int = Field(default=0, ge=0)
    opening_date: Optional[str] = None
    note: Optional[str] = None
    is_default: bool = False
    imprest_limit: Optional[int] = Field(default=None, ge=0)

    @field_validator("bank_name")
    @classmethod
    def _bank(cls, v, info):
        if info.data.get("kind") == "bank" and not (v or "").strip():
            raise ValueError("Nama bank wajib diisi untuk rekening bank.")
        return v


class CashAccountUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=80)
    bank_name: Optional[str] = None
    account_no: Optional[str] = None
    holder: Optional[str] = None
    opening_balance: Optional[int] = Field(default=None, ge=0)
    opening_date: Optional[str] = None
    note: Optional[str] = None
    is_active: Optional[bool] = None
    imprest_limit: Optional[int] = Field(default=None, ge=0)


class CashTransferIn(BaseModel):
    kind: Literal["transfer", "setor_tunai", "tarik_tunai", "isi_kas_kecil"] = "transfer"
    from_account_id: str
    to_account_id: str
    amount: int = Field(gt=0)
    fee: int = Field(default=0, ge=0)
    date: Optional[str] = None
    reference: Optional[str] = None
    note: Optional[str] = None


class CashTransferReject(BaseModel):
    reason: str = Field(min_length=5)
