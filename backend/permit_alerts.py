"""PERINGATAN IZIN (Fase 46) — masa berlaku, bukan hanya tenggat pengurusan.

Dipisah dari `engine.py` karena berkas itu sudah menyentuh batas 800 baris, dan supaya
logika "apa yang dianggap kedaluwarsa" hanya ada di SATU tempat: `permit_scope.health()`.

Apa yang dikerjakan `expiry_tick()`:
  1. mengambil izin yang punya `expiry_at` dan berstatus `approved`;
  2. menilai kesehatannya lewat `permit_scope.health()` (SSOT yang sama dipakai layar);
  3. bila `expiring`/`expired` → notifikasi + tugas Work Hub ke PIC proyek, MENYEBUT objek
     yang dilekati izin (unit/blok/cluster/proyek) supaya penerima tahu apa yang berhenti
     bila izin itu mati.

Idempoten per hari per izin (`expiry_notified_on`), jadi menjalankan tick berulang tidak
membuat tugas dobel.
"""
import logging

import permit_scope as ps
import workhub as wh
from core_utils import now_iso, today_iso_date
from db import ORG_ID, db
from engine import create_notification
from reference_p46 import PERMIT_SCOPE_LABEL

logger = logging.getLogger("sipro.permits.alerts")
JOBDESK = "TK-08"          # tugas administrasi/perizinan proyek (katalog Fase 29)


async def _scope_label(org: str, permit: dict) -> str:
    """Nama objek yang dilekati izin — supaya pesan tidak berbunyi "izin proyek" saja."""
    scope = permit.get("scope") or "project"
    sid = permit.get("scope_id") or permit.get("project_id")
    coll = {"project": db.projects, "cluster": db.clusters, "block": db.blocks,
            "unit": db.units}.get(scope, db.projects)
    doc = await coll.find_one({"id": sid, "org_id": org},
                              {"_id": 0, "name": 1, "code": 1}) or {}
    name = doc.get("name") or doc.get("code") or "objek tidak dikenal"
    return f"{PERMIT_SCOPE_LABEL.get(scope, scope).split(' (')[0]} {name}"


async def _pic(org: str, project_id: str) -> str:
    proj = await db.projects.find_one({"id": project_id, "org_id": org},
                                      {"_id": 0, "members": 1}) or {}
    members = proj.get("members") or []
    if members:
        pm = await db.users.find_one({"org_id": org, "email": {"$in": members},
                                     "role": "project_manager"}, {"_id": 0, "email": 1})
        if pm:
            return pm["email"]
        return members[0]
    pm = await db.users.find_one({"org_id": org, "role": "project_manager",
                                  "is_active": True}, {"_id": 0, "email": 1}) or {}
    return pm.get("email")


async def expiry_tick(org: str = None) -> int:
    """Satu putaran peringatan masa berlaku izin. Mengembalikan jumlah peringatan baru."""
    today = today_iso_date()
    q = {"expiry_at": {"$nin": [None, ""]}, "status": "approved"}
    if org:
        q["org_id"] = org
    rows = await db.permits.find(q, {"_id": 0}).to_list(2000)
    made = 0
    for p in rows:
        h = ps.health(p, today)
        if h["health"] not in ("expiring", "expired"):
            continue
        if p.get("expiry_notified_on") == today:
            continue
        porg = p.get("org_id", ORG_ID)
        where = await _scope_label(porg, p)
        assignee = await _pic(porg, p.get("project_id"))
        expired = h["health"] == "expired"
        title = (f"Izin {p.get('type')} KEDALUWARSA — {where}" if expired
                 else f"Izin {p.get('type')} berakhir {h['days_to_expiry']} hari lagi — {where}")
        body = (f"{p.get('name') or p.get('type')} berlaku sampai "
                f"{str(p.get('expiry_at'))[:10]}. "
                + ("Pekerjaan/serah terima yang bergantung pada izin ini berisiko "
                   "dihentikan." if expired else "Ajukan perpanjangan sekarang."))
        if assignee:
            await create_notification(
                user_email=assignee, title=title, body=body, type="permit",
                related_entity_type="project", related_entity_id=p.get("project_id"),
                org_id=porg)
        await wh.spawn(porg, JOBDESK,
                       source_event=f"permit.expiry:{p['id']}:{today}",
                       assignee_override=assignee, entity_type="project",
                       entity_id=p.get("project_id"), title=title, description=body,
                       due_date=p.get("expiry_at"),
                       meta={"permit_id": p["id"], "health": h["health"],
                             "scope": p.get("scope") or "project",
                             "scope_id": p.get("scope_id")})
        await db.permits.update_one({"id": p["id"]}, {"$set": {
            "expiry_notified_on": today, "expiry_health": h["health"],
            "updated_at": now_iso()}})
        made += 1
    return made
