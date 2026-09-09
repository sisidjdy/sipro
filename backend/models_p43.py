"""Model request Fase 43 (kampanye, biaya iklan, impor CSV, CAPI).

Dipisah dari `models.py`/`models_v2.py`/`models_p41.py` karena semuanya sudah menyentuh batas
gate compliance. Semua enum divalidasi lewat SSOT `reference.GROUPS` (Annotated validator),
sehingga nilai liar ditolak 400 dengan pesan berbahasa Indonesia — bukan tersimpan diam-diam
lalu merusak laporan biaya.
"""
from typing import Annotated, Dict, List, Optional

from pydantic import AfterValidator, BaseModel, Field

import reference as ref


def _req(group: str):
    return Annotated[str, AfterValidator(ref.make_validator(group, required=True))]


def _opt(group: str):
    return Annotated[Optional[str], AfterValidator(ref.make_validator(group))]


AdPlatformReq = _req("ad_platform")
AdPlatformOpt = _opt("ad_platform")
CampaignObjective = _opt("campaign_objective")
CampaignStatus = _opt("campaign_status")
AdsPeriod = _opt("ads_period")
AttributionLevel = _opt("ads_attribution_level")


class CampaignCreate(BaseModel):
    name: str = Field(min_length=3, max_length=140)
    platform: AdPlatformReq
    external_id: Optional[str] = Field(default=None, max_length=64)
    objective: CampaignObjective = "leads"
    status: CampaignStatus = "draft"
    project_ids: List[str] = Field(default_factory=list)
    cluster_ids: List[str] = Field(default_factory=list)
    audience_note: Optional[str] = Field(default=None, max_length=400)
    budget_daily: int = Field(default=0, ge=0)
    budget_total: int = Field(default=0, ge=0)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    owner_email: Optional[str] = Field(default=None, max_length=120)
    note: Optional[str] = Field(default=None, max_length=400)


class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=140)
    platform: AdPlatformOpt = None
    external_id: Optional[str] = Field(default=None, max_length=64)
    objective: CampaignObjective = None
    status: CampaignStatus = None
    project_ids: Optional[List[str]] = None
    cluster_ids: Optional[List[str]] = None
    audience_note: Optional[str] = Field(default=None, max_length=400)
    budget_daily: Optional[int] = Field(default=None, ge=0)
    budget_total: Optional[int] = Field(default=None, ge=0)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    owner_email: Optional[str] = Field(default=None, max_length=120)
    note: Optional[str] = Field(default=None, max_length=400)


class SpendEntry(BaseModel):
    """Entri biaya harian manual. `spend` bertipe str supaya angka gaya laporan platform
    ('1.250.000') tidak ditolak pydantic sebelum sempat dinormalkan mesin biaya."""
    campaign_id: str
    date: str
    spend: str
    adset_id: Optional[str] = Field(default=None, max_length=64)
    adset_name: Optional[str] = Field(default=None, max_length=140)
    ad_id: Optional[str] = Field(default=None, max_length=64)
    ad_name: Optional[str] = Field(default=None, max_length=140)
    impressions: Optional[str] = None
    clicks: Optional[str] = None
    leads_platform: Optional[str] = None


class SpendImport(BaseModel):
    csv_text: str = Field(min_length=5)
    filename: Optional[str] = Field(default=None, max_length=160)
    mapping: Dict[str, str] = Field(default_factory=dict)
    dry_run: bool = True


class AdsSync(BaseModel):
    platform: AdPlatformReq
    date_from: Optional[str] = None
    date_to: Optional[str] = None
