"""Konfigurasi tahapan catatan survey (Pusat Konfigurasi › Tahapan Survey)."""
from fastapi import APIRouter, Depends

import survey_stages as ss
from core_utils import serialize_doc
from db import ORG_ID
from models import SurveyStagesConfigIn
from rbac import audit_log, require_permission

router = APIRouter(prefix="/survey-stages", tags=["survey-stages"])


@router.get("")
async def get_survey_stages(user: dict = Depends(require_permission("surveys", "view"))):
    return {"data": serialize_doc(await ss.get_config(user.get("org_id", ORG_ID)))}


@router.put("")
async def put_survey_stages(payload: SurveyStagesConfigIn,
                            user: dict = Depends(require_permission("settings", "update"))):
    org = user.get("org_id", ORG_ID)
    conf = await ss.save_config(org, [s.model_dump() for s in payload.stages], user.get("email"))
    await audit_log(user, "update", ss.COLL, conf["id"],
                    {"stages": len(conf["stages"]),
                     "items": sum(len(s["items"]) for s in conf["stages"])})
    return {"data": serialize_doc(conf), "warnings": conf.get("warnings") or [],
            "note": "Berlaku untuk survey yang dibuat SETELAH ini; survey berjalan tidak berubah."}
