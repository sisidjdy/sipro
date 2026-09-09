"""Broadcast / campaign blast WhatsApp — antrean NYATA (Fase 97D).

Tidak ada lagi status karangan (~60% "dibaca"). Setiap penerima menjadi baris `wa_outbox`
(queued → sending → sent|simulated|failed); delivered/read HANYA datang dari webhook `statuses[]`.
Template wajib `approved`; nomor opt-out dilewati untuk kategori marketing (tercatat `skipped`);
jam kirim & batas laju dari Pusat Konfigurasi; estimasi biaya percakapan per kategori.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import settings_store as st
import wa_compliance as wcomp
import wa_gateway as gw
import wa_outbox as ob
from core_utils import new_id, now_iso, parse_pagination, serialize_doc
from db import db, ORG_ID
from rbac import audit_log, require_permission

router = APIRouter(prefix="/broadcasts", tags=["broadcasts"])

SAMPLE_SIZE = 8
COST_KEYS = {"marketing": "wa.cost_marketing", "utility": "wa.cost_utility",
             "authentication": "wa.cost_authentication", "service": "wa.cost_utility"}


class BroadcastSegment(BaseModel):
    lead_stages: List[str] = []
    score_bands: List[str] = []
    sources: List[str] = []
    campaigns: List[str] = []
    include_customers: bool = False


class BroadcastPreview(BaseModel):
    segment: BroadcastSegment = BroadcastSegment()
    template_code: str = ""


class BroadcastCreate(BaseModel):
    name: str
    template_code: str
    segment: BroadcastSegment = BroadcastSegment()


def _seg_dict(seg) -> dict:
    return {"lead_stages": list(seg.lead_stages or []), "score_bands": list(seg.score_bands or []),
            "sources": list(seg.sources or []), "campaigns": list(seg.campaigns or []),
            "include_customers": bool(seg.include_customers)}


async def _resolve_recipients(org: str, seg: dict) -> list:
    """Penerima unik per nomor dari lead (+ customer) yang cocok segmen."""
    q = {"org_id": org, "phone": {"$nin": [None, ""]}}
    if seg["lead_stages"]:
        q["stage"] = {"$in": seg["lead_stages"]}
    if seg["score_bands"]:
        q["score_band"] = {"$in": seg["score_bands"]}
    if seg["sources"]:
        q["source"] = {"$in": seg["sources"]}
    if seg["campaigns"]:
        q["campaign"] = {"$in": seg["campaigns"]}
    leads = await db.leads.find(q, {"_id": 0, "id": 1, "name": 1, "phone": 1, "stage": 1, "source": 1}).to_list(5000)
    recips = [{"kind": "lead", "ref_id": l["id"], "lead_id": l["id"], "name": l.get("name"), "phone": l.get("phone"),
               "stage": l.get("stage"), "source": l.get("source")} for l in leads]
    if seg["include_customers"]:
        cust = await db.customers.find({"org_id": org, "phone": {"$nin": [None, ""]}},
                                       {"_id": 0, "id": 1, "name": 1, "phone": 1}).to_list(5000)
        recips += [{"kind": "customer", "ref_id": c["id"], "lead_id": None, "name": c.get("name"),
                    "phone": c.get("phone"), "stage": None, "source": "customer"} for c in cust]
    seen, uniq = set(), []
    for r in recips:
        if r["phone"] in seen:
            continue
        seen.add(r["phone"])
        uniq.append(r)
    return uniq


async def _annotate(org: str, recips: list, category: str) -> dict:
    """Tandai opt-out (marketing) & nomor tidak valid; hitung estimasi biaya."""
    optouts = set()
    if category == "marketing":
        async for o in db.wa_optouts.find({"org_id": org, "active": True}, {"_id": 0, "phone": 1}):
            optouts.add(o["phone"])
    eligible = skipped = 0
    for r in recips:
        e164 = gw.valid_phone(r["phone"])
        if not e164:
            r["skip_reason"] = "invalid_phone"
        elif e164 in optouts:
            r["skip_reason"] = "opt_out"
        else:
            r["skip_reason"] = None
            r["phone"] = e164
        if r["skip_reason"]:
            skipped += 1
        else:
            eligible += 1
    unit_cost = int(await st.get(COST_KEYS.get(category, "wa.cost_utility"), org_id=org) or 0)
    win = await wcomp.send_window(org)
    return {"eligible": eligible, "skipped": skipped, "unit_cost": unit_cost, "cost_estimate": unit_cost * eligible,
            "category": category, "send_window": f"{win['start']}–{win['end']} WIB", "rate": win["rate"],
            "in_window": wcomp.in_send_window(win["start"], win["end"]),
            "eta_seconds": int(eligible / max(1, win["rate"]))}


@router.post("/preview")
async def preview_broadcast(p: BroadcastPreview, user: dict = Depends(require_permission("broadcasts", "manage"))):
    org = user.get("org_id", ORG_ID)
    recips = await _resolve_recipients(org, _seg_dict(p.segment))
    tmpl = await db.wa_templates.find_one({"org_id": org, "code": p.template_code}, {"_id": 0}) if p.template_code else None
    category = wcomp.category_for("broadcast", tmpl)
    info = await _annotate(org, recips, category)
    by_kind = {"lead": 0, "customer": 0}
    for r in recips:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    return {"data": {"total": len(recips), "by_kind": by_kind, **info,
                     "template_ok": bool(tmpl and tmpl.get("status") == "approved"),
                     "template_status": (tmpl or {}).get("meta_status") or (tmpl or {}).get("status"),
                     "sample": serialize_doc(recips[:SAMPLE_SIZE])}}


@router.post("")
async def create_broadcast(p: BroadcastCreate, user: dict = Depends(require_permission("broadcasts", "manage"))):
    org = user.get("org_id", ORG_ID)
    tmpl = await db.wa_templates.find_one({"org_id": org, "code": p.template_code}, {"_id": 0})
    if not tmpl:
        raise HTTPException(404, "Template WA tidak ditemukan.")
    if tmpl.get("status") != "approved":
        raise HTTPException(400, f"Template '{tmpl.get('name')}' belum disetujui Meta "
                                 f"(status {tmpl.get('meta_status') or tmpl.get('status')}). Broadcast hanya boleh "
                                 "memakai template APPROVED.")
    seg = _seg_dict(p.segment)
    recips = await _resolve_recipients(org, seg)
    if not recips:
        raise HTTPException(400, "Segmen tidak menghasilkan penerima. Longgarkan filter.")
    category = wcomp.category_for("broadcast", tmpl)
    info = await _annotate(org, recips, category)
    ts, bid, cfg = now_iso(), new_id(), await gw.get_config(org)
    not_before = None if info["in_window"] else wcomp.next_window_start((await wcomp.send_window(org))["start"])
    docs = []
    for r in recips:
        rid = new_id()
        status = "skipped" if r["skip_reason"] else "queued"
        docs.append({"id": rid, "org_id": org, "broadcast_id": bid, "kind": r["kind"], "ref_id": r["ref_id"],
                     "lead_id": r.get("lead_id"), "name": r.get("name"), "phone": r["phone"], "status": status,
                     "skip_reason": r["skip_reason"], "message_id": None, "provider_message_id": None,
                     "error_code": None, "error_detail": None, "created_at": ts, "status_at": ts})
        if status == "queued":
            await ob.enqueue(org, to=r["phone"], kind="broadcast", category=category, template=tmpl,
                             ref={"broadcast_id": bid, "lead_id": r.get("lead_id")}, actor=user.get("email"),
                             broadcast_id=bid, recipient_id=rid, not_before=not_before)
    await db.broadcast_recipients.insert_many(docs)
    doc = {"id": bid, "org_id": org, "name": p.name, "template_code": tmpl["code"], "template_name": tmpl.get("name"),
           "category": category, "segment": seg, "channel": "whatsapp", "mode": cfg["effective_mode"],
           "status": "queued", "total": len(recips), "queued": info["eligible"], "sent": 0, "simulated": 0,
           "delivered": 0, "read": 0, "failed": 0, "skipped": info["skipped"], "cancelled": 0,
           "cost_estimate": info["cost_estimate"], "unit_cost": info["unit_cost"], "scheduled_for": not_before,
           "created_by": user.get("email"), "created_at": ts, "updated_at": ts}
    await db.broadcasts.insert_one(dict(doc))
    await audit_log(user, "create", "broadcast", bid, {"total": doc["total"], "category": category})
    return {"data": serialize_doc(doc)}


@router.get("")
async def list_broadcasts(skip: int = 0, limit: int = 50, user: dict = Depends(require_permission("broadcasts", "view"))):
    org = user.get("org_id", ORG_ID)
    skip, limit = parse_pagination(skip, limit)
    total = await db.broadcasts.count_documents({"org_id": org})
    rows = await db.broadcasts.find({"org_id": org}, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"data": serialize_doc(rows), "total": total}


@router.get("/{broadcast_id}")
async def get_broadcast(broadcast_id: str, user: dict = Depends(require_permission("broadcasts", "view"))):
    org = user.get("org_id", ORG_ID)
    b = await db.broadcasts.find_one({"id": broadcast_id, "org_id": org}, {"_id": 0})
    if not b:
        raise HTTPException(404, "Broadcast tidak ditemukan.")
    recips = await db.broadcast_recipients.find({"org_id": org, "broadcast_id": broadcast_id}, {"_id": 0}) \
        .sort("created_at", 1).to_list(5000)
    failures = {}
    for r in recips:
        if r.get("status") == "failed" or r.get("skip_reason"):
            code = r.get("error_code") or r.get("skip_reason") or "unknown"
            f = failures.setdefault(code, {"code": code, "count": 0, "detail": r.get("error_detail") or r.get("skip_reason")})
            f["count"] += 1
    return {"data": {"broadcast": serialize_doc(b), "recipients": serialize_doc(recips),
                     "failures": sorted(failures.values(), key=lambda x: -x["count"])}}


@router.post("/{broadcast_id}/{action}")
async def broadcast_action(broadcast_id: str, action: str,
                           user: dict = Depends(require_permission("broadcasts", "manage"))):
    """pause | resume | cancel | run (proses antrean sekarang, tetap hormati jam kirim)."""
    org = user.get("org_id", ORG_ID)
    if action == "run":
        res = await ob.process(org)
        b = await db.broadcasts.find_one({"id": broadcast_id, "org_id": org}, {"_id": 0})
        return {"data": {"broadcast": serialize_doc(b), "run": res}}
    if action not in ("pause", "resume", "cancel"):
        raise HTTPException(400, "Aksi tidak dikenal (pause|resume|cancel|run).")
    res = await ob.set_broadcast_state(org, broadcast_id, action, actor=user.get("email"))
    if res is None:
        raise HTTPException(404, "Broadcast tidak ditemukan.")
    if res.get("error"):
        raise HTTPException(400, res["error"])
    await audit_log(user, action, "broadcast", broadcast_id, {})
    return {"data": serialize_doc(res)}
