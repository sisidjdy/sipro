"""Mitra & Fee (Fase 42) — master mitra, aturan fee, tagihan fee, atribusi, analitik.

Keputusan penting yang tercermin di kode ini:
  1. **Koleksi tetap `agents`.** Master agen Fase 27 sudah memegang invarian akuntansi
     (`marketing_fees.agent_id` → `agents.id`, saldo `2-1500`). Mengganti nama koleksi berarti
     mempertaruhkan invarian yang sudah lulus gate; jadi endpoint ini adalah PINTU BARU untuk
     data yang sama (`docs/v2/25_PARTNER_SPEC.md` §2), dengan field mitra yang ditambahkan.
  2. **Tidak ada fee tanpa aturan** (INV-09). Pratinjau & penerbitan manual memakai mesin
     yang sama dengan pemicu otomatis (`partner_engine.compute`), sehingga angka di layar
     sama dengan angka yang dibukukan.
  3. **Status mitra wajib beralasan.** Menangguhkan mitra memblokir lead & fee barunya; itu
     keputusan yang berdampak uang, jadi harus punya jejak.
  4. Urutan rute: semua path statis (`/rules`, `/analytics`, `/conflicts`) didaftarkan
     SEBELUM `/{partner_id}` — pelajaran gate `verify_api_contract`.
"""
import logging
import secrets

import listing as lst
import partner_engine as pengine
import partner_fee as pfee
import partner_report as prep
import sequences as seq
from core_utils import new_id, now_iso, parse_pagination, serialize_doc
from db import db, ORG_ID
from engine import add_activity
from fastapi import APIRouter, Depends, HTTPException
from models_p41 import (ConflictDecision, FeeIssue, FeePreview, FeeRuleCreate, FeeRuleUpdate,
                        PartnerCreate, PartnerStatusUpdate, PartnerUpdate)
from rbac import audit_log, require_permission

logger = logging.getLogger("sipro.partners")
router = APIRouter(prefix="/partners", tags=["partners"])

PARTNER_SORTS = {"name": "name", "code": "code", "partner_kind": "partner_kind",
                 "status": "status", "fee_total": "fee_total", "fee_paid": "fee_paid",
                 "deals_count": "deals_count", "created_at": "created_at",
                 "updated_at": "updated_at"}
KIND_TO_AGENT_TYPE = {
    "agen_perorangan": "agen_properti", "kantor_broker": "broker_kantor",
    "aggregator": "lainnya", "referral_pembeli": "referral_pembeli",
    "influencer": "influencer", "korporat": "mitra_korporat",
}


async def _get_partner(partner_id: str, org_id: str) -> dict:
    doc = await db.agents.find_one({"id": partner_id, "org_id": org_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mitra tidak ditemukan.")
    return doc


# --------------------------------------------------------------- master mitra
@router.get("")
async def list_partners(q: str = None, partner_kind: str = None, status: str = None,
                        sort: str = None, direction: str = None,
                        skip: int = 0, limit: int = 50,
                        user: dict = Depends(require_permission("partners", "view"))):
    """Daftar mitra: cari + filter multi (jenis/status) + sort server-side + angka fee."""
    org = user.get("org_id", ORG_ID)
    skip, limit = parse_pagination(skip, limit)
    query = {"org_id": org}
    lst.apply_in(query, "partner_kind", partner_kind)
    lst.apply_in(query, "status", status)
    lst.apply_search(query, q, ("name", "code", "company", "phone", "email", "pic_name"))
    total = await db.agents.count_documents(query)
    rows = await (db.agents.find(query, {"_id": 0})
                  .sort(lst.sort_spec(sort, direction, PARTNER_SORTS, ("created_at", -1)))
                  .skip(skip).limit(limit).to_list(limit))
    today = now_iso()[:10]
    for row in rows:
        ok, why = pengine.contract_active(row, today)
        row["contract_ok"] = ok
        row["contract_note"] = why
        row["rules_count"] = await db.partner_fee_rules.count_documents(
            {"org_id": org, "partner_id": row["id"], "status": "active"})
    counts = {}
    for st in ("active", "suspended", "inactive", "expired", "blacklist"):
        counts[st] = await db.agents.count_documents({"org_id": org, "status": st})
    return {"data": serialize_doc(rows), "total": total, "counts": counts,
            "conflicts_pending": await db.partner_attribution_conflicts.count_documents(
                {"org_id": org, "status": "pending_review"})}


@router.post("")
async def create_partner(payload: PartnerCreate,
                         user: dict = Depends(require_permission("partners", "create"))):
    org = user.get("org_id", ORG_ID)
    dup = await db.agents.find_one({"org_id": org, "name": payload.name}, {"_id": 0, "id": 1})
    if dup:
        raise HTTPException(status_code=400,
                            detail=f"Mitra dengan nama '{payload.name}' sudah terdaftar.")
    dup_phone = await db.agents.find_one({"org_id": org, "phone": payload.phone},
                                        {"_id": 0, "name": 1})
    if dup_phone:
        raise HTTPException(status_code=400,
                            detail=f"Nomor {payload.phone} sudah dipakai mitra "
                                   f"{dup_phone['name']} — nomor ganda membuat atribusi lead "
                                   "tidak bisa dipertanggungjawabkan.")
    ts = now_iso()
    code = await seq.next_number("agent", org, prefix="AGN", width=4)
    doc = {
        "id": new_id(), "org_id": org, "code": code, "status": "active",
        "agent_type": KIND_TO_AGENT_TYPE.get(payload.partner_kind, "lainnya"),
        **payload.model_dump(exclude_none=True),
        "contract": (payload.contract.model_dump() if payload.contract else
                     {"number": None, "start_date": None, "end_date": None,
                      "signed_by": None, "status": "draft", "file_ids": []}),
        "settings": {}, "portal": {"enabled": False, "user_id": None, "last_login_at": None},
        "stats": {}, "fee_total": 0, "fee_paid": 0, "deals_count": 0,
        "created_by": user.get("email"), "created_at": ts, "updated_at": ts,
    }
    await db.agents.insert_one(dict(doc))
    doc.pop("_id", None)
    await add_activity(entity_type="agent", entity_id=doc["id"], type="system",
                       body=f"Mitra {code} — {payload.name} terdaftar "
                            f"({payload.partner_kind}).", actor=user.get("email"), org_id=org)
    await audit_log(user, "create", "partners", doc["id"], {"name": payload.name})
    return {"data": serialize_doc(doc)}


# --------------------------------------------------------------- aturan fee
@router.get("/rules")
async def list_rules(partner_id: str = None, status: str = None,
                     user: dict = Depends(require_permission("partners", "view"))):
    """Aturan fee yang berlaku (khusus mitra + aturan umum yang ikut menaunginya)."""
    org = user.get("org_id", ORG_ID)
    rows = await pfee.list_rules(org_id=org, partner_id=partner_id, status=status)
    names = {a["id"]: a["name"] async for a in db.agents.find({"org_id": org},
                                                             {"_id": 0, "id": 1, "name": 1})}
    for row in rows:
        row["partner_name"] = names.get(row.get("partner_id")) if row.get("partner_id") \
            else "Semua mitra"
        row["specificity"] = pfee.specificity(row)
        row["fee_count"] = await db.marketing_fees.count_documents(
            {"org_id": org, "rule_id": row["id"]})
    return {"data": serialize_doc(rows), "total": len(rows),
            "bases": pfee.BASES, "triggers": pfee.TRIGGERS}


@router.post("/rules")
async def create_rule(payload: FeeRuleCreate,
                      user: dict = Depends(require_permission("partners", "update"))):
    org = user.get("org_id", ORG_ID)
    body = payload.model_dump(exclude_none=True)
    body["tiers"] = [t for t in (body.get("tiers") or [])]
    try:
        rule = await pfee.create_rule(body, actor=user.get("email"), org_id=org)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await audit_log(user, "create", "partner_fee_rules", rule["id"], {"name": rule["name"]})
    return {"data": serialize_doc(rule)}


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, payload: FeeRuleUpdate,
                      user: dict = Depends(require_permission("partners", "update"))):
    org = user.get("org_id", ORG_ID)
    try:
        rule = await pfee.update_rule(rule_id, payload.model_dump(exclude_none=True),
                                     actor=user.get("email"), org_id=org)
    except ValueError as exc:
        code = 404 if "tidak ditemukan" in str(exc) else 400
        raise HTTPException(status_code=code, detail=str(exc))
    await audit_log(user, "update", "partner_fee_rules", rule_id, {"status": rule["status"]})
    return {"data": serialize_doc(rule)}


@router.post("/rules/preview")
async def preview_fee(payload: FeePreview,
                      user: dict = Depends(require_permission("partners", "view"))):
    """Pratinjau: aturan mana yang menang, angkanya berapa, dan kalau ditolak — kenapa."""
    org = user.get("org_id", ORG_ID)
    partner = await _get_partner(payload.partner_id, org)
    deal = await db.deals.find_one({"id": payload.deal_id, "org_id": org}, {"_id": 0})
    if not deal:
        raise HTTPException(status_code=404, detail="Deal tidak ditemukan.")
    calc = await pengine.compute(deal, payload.trigger, org_id=org, partner=partner)
    return {"data": serialize_doc(calc)}


@router.post("/rules/issue")
async def issue_fee(payload: FeeIssue,
                    user: dict = Depends(require_permission("marketing_fee", "create"))):
    """Terbitkan tagihan fee dari aturan secara manual (pemicu lama yang terlewat)."""
    org = user.get("org_id", ORG_ID)
    partner = await _get_partner(payload.partner_id, org)
    deal = await db.deals.find_one({"id": payload.deal_id, "org_id": org}, {"_id": 0})
    if not deal:
        raise HTTPException(status_code=404, detail="Deal tidak ditemukan.")
    if not deal.get("partner_id"):
        lead = await db.leads.find_one({"id": deal.get("lead_id")}, {"_id": 0, "partner_id": 1})
        if (lead or {}).get("partner_id") != partner["id"]:
            raise HTTPException(
                status_code=400,
                detail=f"Deal ini tidak beratribusi ke {partner['name']}. Setel atribusi "
                       "mitra pada lead-nya dulu supaya hak fee bisa dipertanggungjawabkan.")
    try:
        result = await pengine.create_fee_for_trigger(
            deal, payload.trigger, actor=user.get("email"), org_id=org, manual=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not result.get("created"):
        raise HTTPException(status_code=400, detail=result.get("reason")
                            or "Tagihan fee tidak bisa diterbitkan.")
    await audit_log(user, "create", "marketing_fee", result["fee"]["id"],
                    {"trigger": payload.trigger, "manual": True})
    return {"data": serialize_doc(result)}


# --------------------------------------------------------------- analitik & sengketa
@router.get("/analytics")
async def partner_analytics(created_from: str = None, created_to: str = None,
                            user: dict = Depends(require_permission("partners", "view"))):
    data = await prep.analytics(org_id=user.get("org_id", ORG_ID),
                               created_from=created_from, created_to=created_to)
    return {"data": serialize_doc(data["rows"]), "totals": serialize_doc(data["totals"]),
            "generated_at": data["generated_at"], "total": len(data["rows"])}


@router.get("/conflicts")
async def list_conflicts(status: str = None,
                         user: dict = Depends(require_permission("partners", "view"))):
    """Sengketa atribusi: dua mitra mengklaim nomor yang sama dalam jendela dedup."""
    org = user.get("org_id", ORG_ID)
    query = {"org_id": org}
    lst.apply_in(query, "status", status)
    rows = await db.partner_attribution_conflicts.find(query, {"_id": 0}) \
        .sort("created_at", -1).to_list(500)
    names = {a["id"]: a["name"] async for a in db.agents.find({"org_id": org},
                                                             {"_id": 0, "id": 1, "name": 1})}
    for row in rows:
        row["claimed_by_name"] = names.get(row.get("claimed_by"))
        row["held_by_name"] = names.get(row.get("held_by"))
        row["decision_name"] = names.get(row.get("decision"))
    return {"data": serialize_doc(rows), "total": len(rows),
            "pending": sum(1 for r in rows if r.get("status") == "pending_review")}


@router.post("/conflicts/{conflict_id}/decide")
async def decide_conflict(conflict_id: str, payload: ConflictDecision,
                          user: dict = Depends(require_permission("partners", "update"))):
    """Putuskan sengketa atribusi: lead berpindah ke mitra yang diputuskan + jejak alasan."""
    org = user.get("org_id", ORG_ID)
    conflict = await db.partner_attribution_conflicts.find_one(
        {"id": conflict_id, "org_id": org}, {"_id": 0})
    if not conflict:
        raise HTTPException(status_code=404, detail="Sengketa atribusi tidak ditemukan.")
    if payload.partner_id not in (conflict.get("claimed_by"), conflict.get("held_by")):
        raise HTTPException(status_code=400,
                            detail="Keputusan harus memilih salah satu mitra yang mengklaim.")
    partner = await _get_partner(payload.partner_id, org)
    ts = now_iso()
    await db.partner_attribution_conflicts.update_one({"id": conflict_id}, {"$set": {
        "status": "overridden", "decision": payload.partner_id, "decided_by": user.get("email"),
        "decided_at": ts, "decision_reason": payload.reason}})
    lead_ids = [i for i in (conflict.get("lead_id"), conflict.get("first_lead_id")) if i]
    if lead_ids:
        await db.leads.update_many({"id": {"$in": lead_ids}, "org_id": org}, {"$set": {
            "partner_id": payload.partner_id, "partner_attribution_model": "manual_review",
            "partner_attributed_at": ts, "updated_at": ts}})
    for pid in {payload.partner_id, conflict.get("claimed_by"), conflict.get("held_by")}:
        if pid:
            await pengine.refresh_stats(pid, org_id=org)
    await add_activity(entity_type="agent", entity_id=payload.partner_id, type="system",
                       body=f"Sengketa atribusi nomor {conflict.get('phone')} diputuskan untuk "
                            f"{partner['name']}: {payload.reason}",
                       actor=user.get("email"), org_id=org)
    await audit_log(user, "update", "partner_attribution", conflict_id,
                    {"decision": payload.partner_id, "reason": payload.reason})
    fresh = await db.partner_attribution_conflicts.find_one({"id": conflict_id}, {"_id": 0})
    return {"data": serialize_doc(fresh)}


# --------------------------------------------------------------- satu mitra
@router.get("/{partner_id}")
async def partner_overview(partner_id: str,
                           user: dict = Depends(require_permission("partners", "view"))):
    org = user.get("org_id", ORG_ID)
    try:
        data = await prep.overview(partner_id, org_id=org)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    ok, why = pengine.contract_active(data["partner"])
    data["contract_ok"] = ok
    data["contract_note"] = why
    data["toggles"] = await pengine.toggles(org)
    # Fase 43 — kesiapan webhook mitra. NILAI token tidak pernah dikirim ulang ke layar:
    # yang ditampilkan hanya "sudah ada / belum" + 4 karakter terakhir sebagai penanda,
    # supaya token tidak bocor lewat cache browser atau tangkapan layar.
    tok = (data["partner"] or {}).pop("webhook_token", None)
    data["webhook"] = {
        "enabled": bool(tok), "hint": f"…{tok[-4:]}" if tok else None,
        "created_at": (data["partner"] or {}).get("webhook_token_at"),
        "path": f"/api/webhooks/partner/{partner_id}", "header": "X-Partner-Token",
    }
    return {"data": serialize_doc(data)}


@router.put("/{partner_id}")
async def update_partner(partner_id: str, payload: PartnerUpdate,
                         user: dict = Depends(require_permission("partners", "update"))):
    org = user.get("org_id", ORG_ID)
    await _get_partner(partner_id, org)
    patch = payload.model_dump(exclude_none=True)
    if payload.contract is not None:
        patch["contract"] = payload.contract.model_dump()
    if patch.get("partner_kind"):
        patch["agent_type"] = KIND_TO_AGENT_TYPE.get(patch["partner_kind"], "lainnya")
    if patch.get("name"):
        dup = await db.agents.find_one({"org_id": org, "name": patch["name"],
                                       "id": {"$ne": partner_id}}, {"_id": 0, "id": 1})
        if dup:
            raise HTTPException(status_code=400,
                                detail=f"Mitra '{patch['name']}' sudah terdaftar.")
    if not patch:
        return {"data": serialize_doc(await _get_partner(partner_id, org))}
    patch["updated_at"] = now_iso()
    await db.agents.update_one({"id": partner_id, "org_id": org}, {"$set": patch})
    await audit_log(user, "update", "partners", partner_id, {"fields": sorted(patch)})
    return {"data": serialize_doc(await _get_partner(partner_id, org))}


@router.post("/{partner_id}/status")
async def set_partner_status(partner_id: str, payload: PartnerStatusUpdate,
                            user: dict = Depends(require_permission("partners", "update"))):
    """Ubah status mitra. `suspended/expired/blacklist` memblokir lead & fee BARU — tagihan
    yang sudah disetujui tetap menjadi utang (tidak boleh hilang karena status berubah)."""
    org = user.get("org_id", ORG_ID)
    partner = await _get_partner(partner_id, org)
    ts = now_iso()
    entry = {"at": ts, "by": user.get("email"), "from": partner.get("status"),
             "to": payload.status, "reason": payload.reason}
    await db.agents.update_one({"id": partner_id, "org_id": org}, {
        "$set": {"status": payload.status, "updated_at": ts,
                 "status_reason": payload.reason, "status_changed_at": ts},
        "$push": {"status_history": {"$each": [entry], "$slice": -50}}})
    await add_activity(entity_type="agent", entity_id=partner_id, type="system",
                       body=f"Status mitra {partner.get('name')}: "
                            f"{partner.get('status')} → {payload.status}. {payload.reason}",
                       actor=user.get("email"), org_id=org)
    await audit_log(user, "update", "partners", partner_id,
                    {"status": payload.status, "reason": payload.reason})
    return {"data": serialize_doc(await _get_partner(partner_id, org))}


@router.get("/{partner_id}/leads")
async def partner_leads(partner_id: str, skip: int = 0, limit: int = 50,
                        user: dict = Depends(require_permission("partners", "view"))):
    org = user.get("org_id", ORG_ID)
    await _get_partner(partner_id, org)
    skip, limit = parse_pagination(skip, limit)
    query = {"org_id": org, "partner_id": partner_id}
    total = await db.leads.count_documents(query)
    rows = await db.leads.find(query, {"_id": 0}).sort("created_at", -1) \
        .skip(skip).limit(limit).to_list(limit)
    import stage_clock as clock
    await clock.attach(rows, "lead", org_id=org)
    return {"data": serialize_doc(rows), "total": total}


@router.get("/{partner_id}/fees")
async def partner_fees(partner_id: str, status: str = None, skip: int = 0, limit: int = 50,
                       user: dict = Depends(require_permission("partners", "view"))):
    org = user.get("org_id", ORG_ID)
    await _get_partner(partner_id, org)
    skip, limit = parse_pagination(skip, limit)
    query = {"org_id": org, "agent_id": partner_id}
    lst.apply_in(query, "status", status)
    total = await db.marketing_fees.count_documents(query)
    rows = await db.marketing_fees.find(query, {"_id": 0}).sort("created_at", -1) \
        .skip(skip).limit(limit).to_list(limit)
    return {"data": serialize_doc(rows), "total": total}


@router.post("/{partner_id}/refresh-stats")
async def refresh_partner_stats(partner_id: str,
                               user: dict = Depends(require_permission("partners", "view"))):
    org = user.get("org_id", ORG_ID)
    await _get_partner(partner_id, org)
    stats = await pengine.refresh_stats(partner_id, org_id=org)
    return {"data": serialize_doc(stats)}


@router.post("/{partner_id}/webhook-token")
async def rotate_webhook_token(partner_id: str,
                               user: dict = Depends(require_permission("partners", "update"))):
    """Terbitkan/putar token webhook mitra (spec `docs/v2/25_PARTNER_SPEC.md` §4).

    Kenapa perlu: mitra aggregator & kantor broker mengirim lead dari sistem mereka sendiri.
    Sebelum ini satu-satunya cara adalah mengetik ulang lead secara manual — atribusi mitra
    jadi bergantung pada ingatan orang, dan setiap lead yang lupa ditandai berarti fee yang
    dipersengketakan. Token diberikan PER MITRA supaya sumber setiap lead bisa dibuktikan
    dan bisa dicabut tanpa mengganggu mitra lain. Nilai penuhnya dikembalikan SEKALI di sini;
    setelah itu layar hanya menampilkan 4 karakter terakhir.
    """
    org = user.get("org_id", ORG_ID)
    partner = await _get_partner(partner_id, org)
    token = secrets.token_urlsafe(24)
    ts = now_iso()
    await db.agents.update_one({"id": partner_id, "org_id": org}, {"$set": {
        "webhook_token": token, "webhook_token_at": ts, "webhook_token_by": user.get("email"),
        "updated_at": ts}})
    await add_activity(entity_type="agent", entity_id=partner_id, type="system",
                       body=f"Token webhook mitra {partner.get('name')} diterbitkan ulang "
                            "(token lama langsung tidak berlaku).",
                       actor=user.get("email"), org_id=org)
    await audit_log(user, "update", "partners", partner_id, {"webhook_token": "rotated"})
    return {"data": {"token": token, "path": f"/api/webhooks/partner/{partner_id}",
                     "header": "X-Partner-Token", "created_at": ts,
                     "note": ("Simpan sekarang — token penuh tidak ditampilkan lagi. Mitra "
                              "mengirim POST JSON berisi minimal `phone`, boleh disertai "
                              "`name`, `email`, `campaign`, `message`.")}}
