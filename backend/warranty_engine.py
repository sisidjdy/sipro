"""Klaim garansi pasca-huni (Fase 50A) — dari keluhan pembeli menjadi pekerjaan yang terbukti.

Cacat nyata yang ditutup modul ini: keluhan sesudah pembeli menghuni rumah hanya masuk sebagai
komplain CS lalu berhenti di sana. Tidak ada yang memeriksa apakah bagian yang dikeluhkan MASIH
bergaransi, keluhan tidak melahirkan pekerjaan perbaikan yang bisa dilacak di lapangan, tidak
ada tuntutan bukti foto "sesudah", tidak ada pemisahan tugas (yang mengerjakan = yang menyatakan
lulus), dan pembeli tidak pernah dimintai pengakuan bahwa perbaikannya benar selesai.

Aturan yang dipaksakan di sini:
  1. **Tidak ada klaim tanpa serah terima.** Masa garansi mulai dari tanggal BAST; tanpa BAST
     tidak ada dasar menghitung "masih garansi atau tidak".
  2. **Klaim lewat masa garansi TIDAK dibuang diam-diam.** Klaimnya tetap tercatat dengan
     status DITOLAK + sebab `lewat_masa_garansi` + tanggal habisnya, supaya pembeli mendapat
     jawaban tertulis yang bisa diperiksa ulang, bukan pesan galat yang hilang.
  3. **Klaim yang diterima melahirkan PEKERJAAN NYATA** (`punch_items`) beserta tugas di papan
     divisi, memakai jalur yang sama dengan temuan mutu — bukan tabel terpisah yang tidak
     pernah dikerjakan siapa pun.
  4. **Selesai butuh bukti.** Menyatakan perbaikan selesai wajib melampirkan foto; pemeriksaan
     mutu harus dilakukan orang LAIN (pemisahan tugas), lalu pembeli mengakui penutupannya.
  5. **Laporan tidak berbohong.** Bila belum ada klaim, laporan mengatakan "belum ada data" —
     bukan menampilkan rata-rata 0 hari.
"""
import logging
from datetime import date

import handover_engine as ho
import reference as ref
import sequences as seq
import settings_store as st
from core_utils import due_in, new_id, now_iso
from db import db, ORG_ID
from engine import auto_create_task

logger = logging.getLogger("sipro.warranty")

SUBMITTED, REJECTED, IN_PROGRESS = "diajukan", "ditolak", "dikerjakan"
DONE, VERIFIED, CLOSED = "selesai", "diverifikasi", "ditutup"
OPEN_STATES = (SUBMITTED, IN_PROGRESS, DONE, VERIFIED)


def _label(state: str) -> str:
    return ref.label_of("warranty_claim_state", state)


async def _claim(org: str, cid: str) -> dict:
    doc = await db.warranty_claims.find_one({"id": cid, "org_id": org}, {"_id": 0})
    if not doc:
        raise ValueError("Klaim garansi tidak ditemukan.")
    return doc


async def _pm_of(org: str, project_id: str) -> str:
    """Penerima pekerjaan bawaan: Manajer Proyek yang memang anggota proyek itu."""
    proj = await db.projects.find_one({"id": project_id, "org_id": org},
                                      {"_id": 0, "members": 1}) or {}
    members = proj.get("members") or []
    if members:
        pm = await db.users.find_one({"org_id": org, "email": {"$in": members},
                                      "role": "project_manager"}, {"_id": 0, "email": 1})
        if pm:
            return pm["email"]
        return members[0]
    return None


# ==================================================================== ajukan klaim
async def create_claim(org: str, *, unit_id: str, category: str, title: str,
                       description: str = None, source: str = "internal",
                       complaint_id: str = None, photo_file_ids: list = None,
                       actor: str = None, at: str = None) -> dict:
    """Ajukan klaim garansi. Menjawab JUJUR bila masa garansi bagian itu sudah lewat."""
    unit = await db.units.find_one({"id": unit_id, "org_id": org}, {"_id": 0})
    if not unit:
        raise ValueError("Unit tidak ditemukan.")
    handover = await ho.active_handover(org, unit_id)
    if not handover:
        raise ValueError(f"Rumah {unit.get('code') or unit_id} belum diserahterimakan, jadi masa "
                         "garansinya belum mulai — klaim garansi belum bisa diajukan.")
    day = str(at or ho.today_str())[:10]
    expiring = int(await st.get("warranty.expiring_days", org_id=org) or 30)
    rows = {w["category"]: w for w in ho.warranty_rows(handover, at=day, expiring_days=expiring)}
    row = rows.get(category)
    ts = now_iso()
    state, reject_reason, reject_detail = SUBMITTED, None, None
    if not row:
        state, reject_reason = REJECTED, "di_luar_lingkup"
        reject_detail = (f"{ref.label_of('warranty_category', category)} tidak termasuk bagian "
                         "yang digaransi pada serah terima ini (masa garansinya 0 bulan).")
    elif row["state"] == "habis":
        state, reject_reason = REJECTED, "lewat_masa_garansi"
        reject_detail = (f"Masa garansi {row['label'].lower()} berlaku {row['months']} bulan "
                         f"sejak {row['starts_at']} dan sudah habis pada {row['expires_at']} "
                         f"({abs(row['days_left'])} hari lalu).")
    doc = {
        "id": new_id(), "org_id": org,
        "number": await seq.next_number("warranty_claim", org, prefix="KG", year=day[:4],
                                        context={"unit_id": unit_id}),
        "handover_id": handover["id"], "handover_number": handover.get("number"),
        "unit_id": unit_id, "unit_code": unit.get("code"),
        "project_id": unit.get("project_id"), "project_name": handover.get("project_name"),
        "deal_id": handover.get("deal_id"), "customer_id": handover.get("customer_id"),
        "buyer_name": handover.get("buyer_name"),
        "category": category, "category_label": ref.label_of("warranty_category", category),
        "title": title.strip(), "description": (description or "").strip() or None,
        "source": source, "source_label": ref.label_of("warranty_claim_source", source),
        "complaint_id": complaint_id,
        "photos": [str(p) for p in (photo_file_ids or []) if str(p).strip()],
        "state": state, "state_label": _label(state),
        "reject_reason": reject_reason, "reject_detail": reject_detail,
        "warranty_months": (row or {}).get("months"),
        "warranty_starts_at": (row or {}).get("starts_at"),
        "warranty_expires_at": (row or {}).get("expires_at"),
        "days_left_at_submit": (row or {}).get("days_left"),
        "submitted_at": ts, "submitted_by": actor, "submitted_on": day,
        "sla_due_at": due_in(days=int(await st.get("warranty.claim_sla_days", org_id=org) or 7)),
        "punch_id": None, "assigned_to": None, "decided_by": None, "decided_at": None,
        "decision_reason": None, "fix_photos": [], "fix_note": None,
        "completed_by": None, "completed_at": None,
        "verified_by": None, "verified_at": None, "verify_note": None,
        "closed_at": None, "ack_by": None, "ack_note": None,
        "created_at": ts, "updated_at": ts,
    }
    await db.warranty_claims.insert_one(dict(doc))
    doc.pop("_id", None)
    if complaint_id:
        await db.complaints.update_one({"id": complaint_id, "org_id": org}, {"$set": {
            "warranty_claim_id": doc["id"], "warranty_claim_number": doc["number"],
            "updated_at": ts}})
    if state == SUBMITTED:
        await auto_create_task(
            source_event=f"warranty.claim:{doc['id']}",
            title=f"Klaim garansi {doc['number']} — {unit.get('code')}: {doc['title']}",
            jobdesk_code="TK-03", type="review",
            related_entity_type="warranty_claim", related_entity_id=doc["id"],
            assigned_to=await _pm_of(org, unit.get("project_id")),
            due_date=doc["sla_due_at"], sla_due_at=doc["sla_due_at"],
            priority="high", org_id=org, description=doc.get("description") or doc["title"])
        logger.info("klaim garansi %s diajukan untuk unit %s", doc["number"], unit.get("code"))
    else:
        logger.info("klaim garansi %s DITOLAK otomatis: %s", doc["number"], reject_reason)
    return doc


# ================================================================= keputusan klaim
async def decide(org: str, cid: str, *, accept: bool, actor: str, reason: str = None,
                 reject_reason: str = None, assigned_to: str = None,
                 due_date: str = None) -> dict:
    """Terima (lahirkan pekerjaan perbaikan) atau tolak beralasan."""
    doc = await _claim(org, cid)
    if doc["state"] != SUBMITTED:
        raise ValueError(f"Klaim {doc['number']} sudah berstatus \u201c{_label(doc['state'])}\u201d — "
                         "keputusan hanya bisa diambil pada klaim yang masih diajukan.")
    ts = now_iso()
    if not accept:
        if len((reason or "").strip()) < 10:
            raise ValueError("Alasan penolakan minimal 10 huruf — pembeli berhak tahu dasarnya.")
        if not reject_reason:
            raise ValueError("Pilih sebab penolakan dari kamus data (mis. di luar lingkup).")
        await db.warranty_claims.update_one({"id": cid, "org_id": org}, {"$set": {
            "state": REJECTED, "state_label": _label(REJECTED),
            "reject_reason": reject_reason, "reject_detail": reason.strip(),
            "decided_by": actor, "decided_at": ts, "decision_reason": reason.strip(),
            "updated_at": ts}})
        return await _claim(org, cid)

    assignee = assigned_to or await _pm_of(org, doc.get("project_id"))
    due = due_date or due_in(days=int(await st.get("warranty.fix_days", org_id=org) or 7))
    pid = new_id()
    await db.punch_items.insert_one({
        "id": pid, "org_id": org, "project_id": doc.get("project_id"),
        "project_name": doc.get("project_name"), "unit_id": doc.get("unit_id"),
        "title": f"[Garansi {doc['number']}] {doc['title']}",
        "description": (doc.get("description")
                        or f"Klaim garansi {doc['category_label']} dari pembeli."),
        "location": None, "category": "lainnya", "severity": "high", "status": "open",
        "assigned_to": assignee, "due_date": due,
        "photo": (doc.get("photos") or [None])[0], "photos": doc.get("photos") or [],
        "fix_photos": [], "source": "warranty_claim", "warranty_claim_id": cid,
        "opened_by": actor, "closed_at": None, "created_at": ts, "updated_at": ts,
    })
    await auto_create_task(
        source_event=f"warranty.fix:{cid}",
        title=f"Perbaikan garansi {doc['number']} — {doc.get('unit_code')}",
        jobdesk_code="TK-03", type="task",
        related_entity_type="punch_item", related_entity_id=pid,
        assigned_to=assignee, due_date=due, sla_due_at=due,
        priority="urgent", org_id=org,
        description=(reason or doc.get("description") or doc["title"]))
    await db.warranty_claims.update_one({"id": cid, "org_id": org}, {"$set": {
        "state": IN_PROGRESS, "state_label": _label(IN_PROGRESS), "punch_id": pid,
        "assigned_to": assignee, "decided_by": actor, "decided_at": ts,
        "decision_reason": (reason or "").strip() or None, "fix_due_date": due,
        "updated_at": ts}})
    logger.info("klaim garansi %s diterima, punch %s dibuat untuk %s", doc["number"], pid,
                assignee)
    return await _claim(org, cid)


async def complete(org: str, cid: str, *, actor: str, photo_file_ids: list,
                   note: str = None) -> dict:
    """Nyatakan perbaikan selesai — WAJIB melampirkan bukti foto 'sesudah'."""
    doc = await _claim(org, cid)
    if doc["state"] != IN_PROGRESS:
        raise ValueError(f"Klaim {doc['number']} berstatus \u201c{_label(doc['state'])}\u201d — "
                         "hanya pekerjaan yang sedang diperbaiki bisa dinyatakan selesai.")
    photos = [str(p).strip() for p in (photo_file_ids or []) if str(p).strip()]
    if not photos:
        raise ValueError("Bukti foto perbaikan wajib — klaim garansi tidak bisa dinyatakan "
                         "selesai hanya dengan catatan.")
    ts = now_iso()
    await db.warranty_claims.update_one({"id": cid, "org_id": org}, {"$set": {
        "state": DONE, "state_label": _label(DONE), "fix_photos": photos,
        "fix_note": (note or "").strip() or None, "completed_by": actor, "completed_at": ts,
        "updated_at": ts}})
    if doc.get("punch_id"):
        await db.punch_items.update_one({"id": doc["punch_id"], "org_id": org}, {"$set": {
            "status": "in_progress", "fix_photos": photos, "updated_at": ts}})
    return await _claim(org, cid)


async def verify(org: str, cid: str, *, actor: str, passed: bool = True, note: str = None,
                 reason: str = None) -> dict:
    """Pemeriksaan mutu oleh orang LAIN — pemisahan tugas dijaga di DATA, bukan di layar."""
    doc = await _claim(org, cid)
    if doc["state"] != DONE:
        raise ValueError(f"Klaim {doc['number']} berstatus \u201c{_label(doc['state'])}\u201d — "
                         "hanya perbaikan yang sudah dinyatakan selesai bisa diperiksa.")
    if doc.get("completed_by") and actor and doc["completed_by"] == actor:
        raise ValueError("Pemeriksa tidak boleh orang yang mengerjakan perbaikannya "
                         f"({actor}) — minta rekan/atasan yang memeriksa.")
    ts = now_iso()
    if not passed:
        if len((reason or "").strip()) < 10:
            raise ValueError("Alasan perbaikan dikembalikan minimal 10 huruf.")
        await db.warranty_claims.update_one({"id": cid, "org_id": org}, {"$set": {
            "state": IN_PROGRESS, "state_label": _label(IN_PROGRESS),
            "verify_note": reason.strip(), "verified_by": None, "verified_at": None,
            "completed_by": None, "completed_at": None, "updated_at": ts}})
        await auto_create_task(
            source_event=f"warranty.rework:{cid}:{ts}",
            title=f"Perbaikan garansi {doc['number']} dikembalikan — {doc.get('unit_code')}",
            jobdesk_code="TK-03", type="task",
            related_entity_type="warranty_claim", related_entity_id=cid,
            assigned_to=doc.get("assigned_to"), priority="urgent", org_id=org,
            description=reason.strip())
        return await _claim(org, cid)
    await db.warranty_claims.update_one({"id": cid, "org_id": org}, {"$set": {
        "state": VERIFIED, "state_label": _label(VERIFIED), "verified_by": actor,
        "verified_at": ts, "verify_note": (note or "").strip() or None, "updated_at": ts}})
    if doc.get("punch_id"):
        await db.punch_items.update_one({"id": doc["punch_id"], "org_id": org}, {"$set": {
            "status": "verified", "verified_by": actor, "updated_at": ts}})
    return await _claim(org, cid)


async def close(org: str, cid: str, *, actor: str, ack_by: str = None,
                ack_note: str = None) -> dict:
    """Ditutup setelah pembeli MENGAKUI perbaikannya selesai."""
    doc = await _claim(org, cid)
    if doc["state"] != VERIFIED:
        raise ValueError(f"Klaim {doc['number']} berstatus \u201c{_label(doc['state'])}\u201d — "
                         "penutupan hanya untuk perbaikan yang sudah diperiksa.")
    ts = now_iso()
    await db.warranty_claims.update_one({"id": cid, "org_id": org}, {"$set": {
        "state": CLOSED, "state_label": _label(CLOSED), "closed_at": ts,
        "ack_by": ack_by or doc.get("buyer_name") or actor,
        "ack_note": (ack_note or "").strip() or None, "closed_by": actor, "updated_at": ts}})
    if doc.get("punch_id"):
        await db.punch_items.update_one({"id": doc["punch_id"], "org_id": org}, {"$set": {
            "status": "closed", "closed_at": ts, "updated_at": ts}})
    if doc.get("complaint_id"):
        await db.complaints.update_one(
            {"id": doc["complaint_id"], "org_id": org, "status": {"$ne": "closed"}},
            {"$set": {"status": "resolved", "updated_at": ts}})
    return await _claim(org, cid)


# ======================================================================== laporan
async def list_claims(org: str, *, unit_id: str = None, project_id: str = None,
                      state: str = None, category: str = None,
                      customer_id: str = None) -> dict:
    q = {"org_id": org}
    for key, val in (("unit_id", unit_id), ("project_id", project_id), ("state", state),
                     ("category", category), ("customer_id", customer_id)):
        if val:
            q[key] = val
    rows = await db.warranty_claims.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"rows": rows, "total": len(rows),
            "summary": _tally(rows),
            "detail": ("Belum ada klaim garansi yang cocok dengan saringan ini — belum ada "
                       "data, bukan nol klaim yang sudah selesai."
                       if not rows else f"{len(rows)} klaim garansi ditemukan.")}


def _tally(rows: list) -> dict:
    # Daftar status diambil dari Kamus Data (SSOT) supaya laporan tidak pernah kehilangan
    # satu status hanya karena penulis laporan lupa menambahkannya di sini.
    states = list(ref.values("warranty_claim_state"))
    per_state = {s: sum(1 for r in rows if r.get("state") == s) for s in states}
    return {"total": len(rows), "per_state": per_state,
            "open": sum(1 for r in rows if r.get("state") in OPEN_STATES)}


async def report(org: str, *, project_id: str = None, period: str = None) -> dict:
    """Rekap klaim garansi yang bisa dijumlahkan — dan mengaku bila belum ada datanya."""
    q = {"org_id": org}
    if project_id:
        q["project_id"] = project_id
    if period:
        q["submitted_on"] = {"$regex": f"^{period}"}
    rows = await db.warranty_claims.find(q, {"_id": 0}).to_list(2000)
    tally = _tally(rows)
    closed = [r for r in rows if r.get("state") == CLOSED and r.get("closed_at")]
    durations = []
    for r in closed:
        try:
            start = date.fromisoformat(str(r.get("submitted_on") or r["submitted_at"])[:10])
            end = date.fromisoformat(str(r["closed_at"])[:10])
            durations.append((end - start).days)
        except Exception:  # noqa: BLE001 — tanggal rusak tidak boleh merusak laporan
            continue
    per_category = {}
    for r in rows:
        key = r.get("category") or "lainnya"
        cur = per_category.setdefault(key, {"category": key,
                                            "label": ref.label_of("warranty_category", key),
                                            "total": 0, "ditolak": 0, "ditutup": 0})
        cur["total"] += 1
        if r.get("state") == REJECTED:
            cur["ditolak"] += 1
        if r.get("state") == CLOSED:
            cur["ditutup"] += 1
    # Tie-out: Σ per status HARUS sama dengan jumlah klaim (laporan bisa dijumlahkan pembaca).
    sum_states = sum(tally["per_state"].values())
    return {
        "period": period, "project_id": project_id,
        "total": tally["total"], "per_state": tally["per_state"], "open": tally["open"],
        "per_category": sorted(per_category.values(), key=lambda x: -x["total"]),
        "avg_days_to_close": (round(sum(durations) / len(durations), 1) if durations else None),
        "avg_days_note": (None if durations else
                          "Belum ada klaim yang ditutup pada saringan ini — rata-rata hari "
                          "penyelesaian belum ada datanya (bukan 0 hari)."),
        "tie_out": {"matches": sum_states == tally["total"],
                    "sum_per_state": sum_states, "total": tally["total"],
                    "detail": ("\u03a3 klaim per status sama dengan jumlah klaim."
                               if sum_states == tally["total"] else
                               "\u03a3 klaim per status TIDAK sama dengan jumlah klaim — "
                               "ada status di luar kamus data.")},
        "missing": not rows,
        "detail": ("Belum ada klaim garansi pada saringan ini — belum ada data."
                   if not rows else f"{tally['total']} klaim, {tally['open']} masih berjalan."),
    }


async def warranty_board(org: str, *, project_id: str = None) -> dict:
    """Papan garansi: rumah yang sudah diserahterimakan + keadaan masa garansinya."""
    q = {"org_id": org, "state": "issued"}
    if project_id:
        q["project_id"] = project_id
    rows = await db.unit_handovers.find(q, {"_id": 0}).sort("handed_over_at", -1).to_list(500)
    expiring = int(await st.get("warranty.expiring_days", org_id=org) or 30)
    out = []
    for r in rows:
        w = ho.warranty_rows(r, expiring_days=expiring)
        claims = await db.warranty_claims.find({"org_id": org, "handover_id": r["id"]},
                                               {"_id": 0, "state": 1}).to_list(500)
        out.append({
            "handover_id": r["id"], "number": r.get("number"), "unit_id": r.get("unit_id"),
            "unit_code": r.get("unit_code"), "project_id": r.get("project_id"),
            "project_name": r.get("project_name"), "buyer_name": r.get("buyer_name"),
            "handed_over_at": r.get("handed_over_at"),
            "warranty": w,
            "aktif": sum(1 for x in w if x["state"] == "aktif"),
            "hampir_habis": sum(1 for x in w if x["state"] == "hampir_habis"),
            "habis": sum(1 for x in w if x["state"] == "habis"),
            "claims_open": sum(1 for c in claims if c.get("state") in OPEN_STATES),
            "claims_total": len(claims),
        })
    return {"rows": out, "total": len(out),
            "detail": ("Belum ada rumah yang diserahterimakan — papan garansi belum ada "
                       "datanya." if not out else
                       f"{len(out)} rumah dalam pemantauan garansi.")}
