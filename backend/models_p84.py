"""Model request Fase 84 — kas kecil imprest (pengeluaran langsung + pengisian)."""
from typing import List, Optional

from pydantic import BaseModel, Field


class PettyExpenseIn(BaseModel):
    cash_account_id: str
    category: str = Field(min_length=2, max_length=40)
    description: str = Field(min_length=3, max_length=200)
    amount: int = Field(gt=0)
    date: Optional[str] = None
    payee: Optional[str] = Field(default=None, max_length=120)
    project_id: Optional[str] = None
    file_ids: List[str] = Field(default_factory=list)


class PettyExpenseVoid(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


class ReplenishIn(BaseModel):
    from_account_id: Optional[str] = None
    amount: Optional[int] = Field(default=None, gt=0)
    note: Optional[str] = Field(default=None, max_length=300)
