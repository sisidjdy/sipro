"""reminders_router.py — pengingat WhatsApp otomatis (Fase 51B).

Rute (prefix `/reminders`, tanpa pintu sidebar baru — dipakai tab pada halaman
"Automasi & Channel"):

  GET  /reminders/settings    ambang batas + mode kirim (simulasi/nyata) apa adanya
  GET  /reminders/candidates  siapa yang LAYAK diingatkan hari ini + sebab yang menghalangi
  GET  /reminders             riwayat pengingat (audit: siapa, kapan, isi, statusnya)
  POST /reminders/run         jalankan sekarang (butuh izin `reminders:manage`)

Pemisahan yang disengaja: SEMUA peran yang berhubungan dengan pembeli boleh MELIHAT
(pertanyaan "pembeli ini sudah diingatkan belum?" adalah pekerjaan harian), tetapi hanya
peran pengelola yang boleh MENJALANKAN — karena menjalankannya berarti mengirim pesan
sungguhan ke pelanggan.
"""
from fastapi import APIRouter, Depends

import wa_reminder_engine as re
from core_utils import parse_pagination, serialize_doc
from db import ORG_ID
from models_p51 import ReminderRunIn
from rbac import audit_log, require_permission

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("/settings")
async def reminder_settings(user: dict = Depends(require_permission("reminders", "view"))):
    return {"data": await re.config(user.get("org_id", ORG_ID)),
            "hint": re.next_run_hint()}


@router.get("/candidates")
async def reminder_candidates(kind: str = None,
                              user: dict = Depends(require_permission("reminders", "view"))):
    org = user.get("org_id", ORG_ID)
    rows = await re.candidates(org)
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    siap = [r for r in rows if not r.get("blocked_code")]
    return {"data": serialize_doc(rows), "total": len(rows),
            "ready": len(siap),
            "blocked": len(rows) - len(siap),
            "detail": (f"{len(siap)} siap dikirim, {len(rows) - len(siap)} tertahan "
                       f"(lihat sebabnya per baris)." if rows else
                       "Belum ada yang perlu diingatkan hari ini — bukan berarti data hilang: "
                       "tidak ada garansi hampir habis, termin jatuh tempo, atau tunggakan.")}


@router.get("")
async def reminder_history(kind: str = None, status: str = None, customer_id: str = None,
                           skip: int = 0, limit: int = 100,
                           user: dict = Depends(require_permission("reminders", "view"))):
    skip, limit = parse_pagination(skip, limit)
    out = await re.history(user.get("org_id", ORG_ID), kind=kind, status=status,
                           customer_id=customer_id, limit=limit, skip=skip)
    return {"data": serialize_doc(out["rows"]), "total": out["total"],
            "by_status": out["by_status"]}


@router.post("/run")
async def reminder_run(payload: ReminderRunIn,
                       user: dict = Depends(require_permission("reminders", "manage"))):
    org = user.get("org_id", ORG_ID)
    out = await re.run(org, actor=user.get("email"), kinds=payload.kinds,
                       limit=payload.limit)
    await audit_log(user, "run", "reminder", "batch",
                    {"sent": out["sent"], "simulated": out["simulated"],
                     "skipped": out["skipped"]})
    return {"data": out, "message": out["detail"]}
