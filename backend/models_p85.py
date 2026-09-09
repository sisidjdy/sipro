"""Model request Fase 85–87 — kunci periode kas, giro mundur (PDC), bukti kas."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class PeriodLockIn(BaseModel):
    account_id: str
    period: str = Field(min_length=7, max_length=7)
    counted_balance: Optional[int] = Field(default=None, ge=0)
    note: Optional[str] = Field(default=None, max_length=300)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


class PdcReceiveIn(BaseModel):
    kind: Literal["cek", "bg"] = "bg"
    bank_name: str = Field(min_length=2, max_length=60)
    instrument_no: str = Field(min_length=2, max_length=40)
    issuer_name: Optional[str] = Field(default=None, max_length=120)
    amount: int = Field(gt=0)
    due_date: str = Field(min_length=10, max_length=10)
    received_date: Optional[str] = None
    deal_id: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=300)


class PdcClearIn(BaseModel):
    cash_account_id: str
    cleared_date: Optional[str] = None
