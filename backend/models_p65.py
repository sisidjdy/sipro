"""Model request Fase 65 — preferensi notifikasi & aksi pada kelompok notifikasi."""
from typing import Dict

from pydantic import BaseModel, Field


class NotifPrefsUpdate(BaseModel):
    """Sebagian preferensi: {"keuangan": {"push": false}} — kategori lain tidak tersentuh."""
    channels: Dict[str, Dict[str, bool]] = Field(default_factory=dict)


class NotifGroupAction(BaseModel):
    """Aksi untuk SATU kelompok notifikasi kembar (kuncinya dari daftar berkelompok)."""
    group_key: str = Field(min_length=1)
