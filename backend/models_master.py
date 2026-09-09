"""Model request untuk master data & koreksi data (hasil audit forensik).

Dipisah dari models.py agar tetap di bawah batas ukuran file (gate compliance).
"""
from typing import List, Optional

from pydantic import BaseModel, Field

import reference as ref


class ProjectUpdate(BaseModel):
    """Sebelumnya TIDAK ADA: proyek tak bisa dikoreksi setelah dibuat."""
    name: Optional[str] = None
    code: Optional[str] = None
    location: Optional[str] = None
    marketing_office: Optional[str] = None
    status: ref.ProjectStatus = None
    members: Optional[List[str]] = None


class AccountUpdate(BaseModel):
    """CoA sebelumnya hanya bisa dibuat, tidak bisa dikoreksi/dinonaktifkan."""
    name: Optional[str] = None
    type: ref.OptAccountType = None
    parent_code: Optional[str] = None
    is_active: Optional[bool] = None


class DocTemplateCreate(BaseModel):
    code: str
    name: str
    content: str


class DocTemplateUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None


class QcTemplateItem(BaseModel):
    label: str
    critical: bool = False


class QcTemplateCreate(BaseModel):
    code: str
    name: str
    category: ref.InspectionCategory = "lainnya"
    items: List[QcTemplateItem]


class QcTemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: ref.InspectionCategory = None
    items: Optional[List[QcTemplateItem]] = None
    is_active: Optional[bool] = None


class UnitUpdate(BaseModel):
    """Koreksi master unit. Fase 28b: luas/orientasi/hoek jadi FIELD NYATA.

    Sebelumnya luas hanya diturunkan dari nama tipe ("Tipe 45/90") dan orientasi/hoek
    tidak bisa diisi dari UI sama sekali, padahal keduanya dipakai peta, showroom
    publik, dan perhitungan harga per m².
    """
    type: ref.UnitType = None
    price: Optional[int] = None
    luas_tanah: Optional[int] = Field(default=None, ge=0, le=100000)
    luas_bangunan: Optional[int] = Field(default=None, ge=0, le=100000)
    orientation: ref.UnitOrientation = None
    corner: Optional[bool] = None


class MaterialUpdate(BaseModel):
    """Koreksi master material (nama/satuan) + arsip."""
    name: Optional[str] = None
    uom: ref.OptUom = None
    is_active: Optional[bool] = None


class PhaseUpdate(BaseModel):
    """Koreksi fase konstruksi (nama/bobot/rencana) — sebelumnya hanya progres yang bisa diubah."""
    name: Optional[str] = None
    weight: Optional[int] = None
    planned_pct: Optional[int] = None
    order: Optional[int] = None
    work_category: Optional[str] = None


class SchemeUpdate(BaseModel):
    """Ubah nama skema pembayaran/komisi; item/tier hanya bila skema belum terpakai."""
    name: Optional[str] = None
    is_default: Optional[bool] = None
    items: Optional[List[dict]] = None
    tiers: Optional[List[dict]] = None
