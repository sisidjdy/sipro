"""WORK HUB v2 (Fase 29) — mesin pekerjaan berbasis DIVISI + JOBDESK.

Kenapa ada file ini? Sebelumnya `tasks` hanya koleksi datar: task lahir di 19 titik kode,
tanpa divisi, tanpa pemilik proses, tanpa bukti, tanpa verifikasi. Akibatnya Work Hub tidak
bisa dipakai supervisor untuk mengatur pekerjaan timnya.

Isi modul:
  * pemetaan pengguna → divisi & level (supervisor/staf)
  * konfigurasi jobdesk (katalog kode + override supervisor di koleksi `jobdesk_templates`)
  * pembuatan task dari jobdesk (idempoten via `source_event`)
  * dispatcher event → jobdesk, generator task BERULANG (harian/mingguan/bulanan)
  * sweeper yang mengubah kondisi nyata menjadi event (WA belum dijawab, survey H-1,
    survey lewat, AR jatuh tempo, lead diam)
  * verifikasi OTOMATIS (apa yang bisa diperiksa mesin) vs verifikasi SUPERVISOR
    (penilaian manusia, mis. pendampingan survey/akad)
  * agregasi papan divisi (beban kerja per staf, antrean verifikasi)
"""
import logging
from datetime import datetime, timezone

import jobdesk_catalog as cat
import reference_p29 as p29
from core_utils import due_in, new_id, now, now_iso, today_iso_date
from db import db, ORG_ID
from engine import add_activity, create_notification, emit
from rbac import has_role

logger = logging.getLogger("sipro.workhub")

OPEN_STATES = ["open", "in_progress", "snoozed", "submitted"]
ACTIVE_STATES = ["open", "in_progress", "snoozed"]


# ----------------------------- domain: divisi & level -----------------------------
def division_of(user: dict) -> str:
    """Divisi efektif seorang pengguna (field user menang atas default peran)."""
    if not user:
        return None
    role = user.get("role")
    from rbac import nav_role
    return user.get("division") or p29.ROLE_DIVISION.get(role) or p29.ROLE_DIVISION.get(nav_role(role) or "")


def level_of(user: dict) -> str:
    if not user:
        return None
    role = user.get("role")
    from rbac import nav_role
    return user.get("level") or p29.ROLE_LEVEL.get(role) or p29.ROLE_LEVEL.get(nav_role(role) or "") or "staff"


def is_owner_level(user: dict) -> bool:
    return level_of(user) == "owner"


def is_supervisor(user: dict) -> bool:
    return level_of(user) in ("supervisor", "owner")


async def division_members(org: str, division: str, *, level: str = None) -> list:
    """Anggota divisi (aktif). Level opsional: 'staff' atau 'supervisor'."""
    users = await db.users.find(
        {"org_id": org, "is_active": {"$ne": False}}, {"_id": 0, "password_hash": 0}).to_list(500)
    out = []
    for u in users:
        if division_of(u) != division:
            continue
        if level and level_of(u) != level:
            continue
        out.append(u)
    return out


async def user_by_email(org: str, email: str) -> dict:
    if not email:
        return None
    return await db.users.find_one({"org_id": org, "email": email},
                                  {"_id": 0, "password_hash": 0})


async def division_of_email(org: str, email: str) -> str:
    return division_of(await user_by_email(org, email))


# ----------------------------- konfigurasi jobdesk -----------------------------
async def ensure_jobdesk_templates(org: str = ORG_ID) -> int:
    """Sinkronkan katalog kode → koleksi `jobdesk_templates` (idempoten).

    Field yang boleh diubah supervisor (is_active/SLA/prioritas/aturan penerima/verifikasi)
    TIDAK ditimpa; metadata katalog (judul, divisi, sumber, tautan) selalu disegarkan agar
    perubahan kode ikut turun ke data.
    """
    made = 0
    for code in cat.BY_CODE:
        d = cat.defaults(code)
        existing = await db.jobdesk_templates.find_one({"org_id": org, "code": code}, {"_id": 0})
        meta = {k: d[k] for k in ("division", "title", "description", "source", "event",
                                  "type", "role_hint", "auto_check", "link", "native")}
        meta["updated_at"] = now_iso()
        if existing:
            await db.jobdesk_templates.update_one({"org_id": org, "code": code}, {"$set": meta})
            continue
        doc = {"id": new_id(), "org_id": org, **d, **meta,
               "created_at": now_iso(), "updated_at": now_iso()}
        await db.jobdesk_templates.insert_one(doc)
        made += 1
    return made


async def jobdesk(org: str, code: str) -> dict:
    """Konfigurasi efektif: default katalog + override tersimpan."""
    base = cat.defaults(code)
    row = await db.jobdesk_templates.find_one({"org_id": org, "code": code}, {"_id": 0})
    if row:
        for k, v in row.items():
            if v is not None and k in base:
                base[k] = v
        base["id"] = row.get("id")
    return base


async def jobdesks(org: str, division: str = None) -> list:
    out = []
    for code in cat.BY_CODE:
        jd = await jobdesk(org, code)
        if division and jd.get("division") != division:
            continue
        out.append(jd)
    out.sort(key=lambda j: j["code"])
    return out


# ----------------------------- penerima tugas -----------------------------
async def _least_loaded(org: str, candidates: list) -> str:
    best, best_n = None, None
    for u in candidates:
        n = await db.tasks.count_documents(
            {"org_id": org, "assigned_to": u["email"], "status": {"$in": ACTIVE_STATES}})
        if best_n is None or n < best_n:
            best, best_n = u["email"], n
    return best


async def resolve_assignees(org: str, jd: dict, *, record_owner: str = None) -> list:
    """Tentukan penerima tugas sesuai aturan jobdesk. Selalu kembalikan list email."""
    rule = jd.get("assignee_rule") or "round_robin"
    division = jd.get("division")
    if rule == "specific" and jd.get("assignee_email"):
        return [jd["assignee_email"]]
    if rule == "record_owner":
        if record_owner:
            return [record_owner]
        rule = "round_robin"  # fallback jujur: tidak ada pemilik → bagikan ke staf
    if rule == "supervisor":
        sup = await division_members(org, division, level="supervisor")
        return [sup[0]["email"]] if sup else []
    staff = await division_members(org, division, level="staff")
    if jd.get("role_hint"):
        typed = [u for u in staff if has_role(u, jd["role_hint"])]
        staff = typed or staff
    if not staff:
        sup = await division_members(org, division, level="supervisor")
        staff = sup
    if not staff:
        return []
    if rule == "all_staff":
        return [u["email"] for u in staff]
    return [await _least_loaded(org, staff)]


# ----------------------------- pembuatan task -----------------------------
def _sla_iso(hours: float) -> str:
    return due_in(minutes=int(round(float(hours or 24) * 60)))


async def create_task(org: str, jd: dict, *, source_event: str, assigned_to: str,
                      title: str = None, description: str = None,
                      entity_type: str = None, entity_id: str = None,
                      due_date: str = None, assigned_by: str = "system",
                      strict_once: bool = False, meta: dict = None,
                      link: str = None) -> dict:
    """Task v2 idempoten (satu `source_event` → satu task aktif).

    `strict_once=True` dipakai untuk task BERULANG: satu periode hanya boleh punya satu
    task walau task periode itu sudah diselesaikan (dulu task harian yang sudah selesai
    langsung dibuat ulang pada tick berikutnya di hari yang sama).
    """
    dedup = {"org_id": org, "source_event": source_event}
    if not strict_once:
        dedup["status"] = {"$in": OPEN_STATES}
    existing = await db.tasks.find_one(dedup, {"_id": 0, "id": 1})
    if existing:
        return None
    ts = now_iso()
    due = due_date or _sla_iso(jd.get("sla_hours"))
    verify = jd.get("verify_mode") or "none"
    doc = {
        "id": new_id(), "org_id": org, "title": title or jd.get("title"),
        "description": description or jd.get("description"),
        "type": jd.get("type", "todo"), "status": "open", "priority": jd.get("priority", "medium"),
        "division": jd.get("division"), "jobdesk_code": jd.get("code"),
        "related_entity_type": entity_type, "related_entity_id": entity_id,
        "assigned_to": assigned_to, "assigned_by": assigned_by,
        "due_date": due, "sla_due_at": due, "sla_breached": False,
        "source_event": source_event, "auto_generated": assigned_by == "system",
        "proof_kind": jd.get("proof_kind", "note"), "verify_mode": verify,
        "review": "none", "proof": [], "outcome": None,
        "link": link or jd.get("link"), "meta": meta or {},
        "created_by": assigned_by, "created_at": ts, "updated_at": ts,
    }
    import stage_clock as clock
    doc.update(await clock.patch_for("task", doc.get("status", "open"), org_id=org, at=ts))
    await db.tasks.insert_one(dict(doc))
    doc.pop("_id", None)
    if assigned_to:
        await create_notification(
            user_email=assigned_to, title=f"Tugas baru: {doc['title']}",
            body=f"Jatuh tempo {str(due)[:16].replace('T', ' ')} · {jd.get('code')}",
            type="task", related_entity_type=entity_type, related_entity_id=entity_id, org_id=org)
    return doc


async def spawn(org: str, code: str, *, source_event: str, record_owner: str = None,
                title: str = None, description: str = None, entity_type: str = None,
                entity_id: str = None, due_date: str = None, assignee_override: str = None,
                assigned_by: str = "system", strict_once: bool = False,
                meta: dict = None, link: str = None) -> list:
    """Buat task dari sebuah kode jobdesk untuk semua penerima yang cocok."""
    jd = await jobdesk(org, code)
    if not jd.get("is_active", True):
        return []
    if assignee_override:
        emails = [assignee_override]
    else:
        emails = await resolve_assignees(org, jd, record_owner=record_owner)
    made = []
    for email in emails:
        se = source_event if len(emails) == 1 else f"{source_event}:{email}"
        t = await create_task(org, jd, source_event=se, assigned_to=email, title=title,
                              description=description, entity_type=entity_type,
                              entity_id=entity_id, due_date=due_date,
                              assigned_by=assigned_by, strict_once=strict_once, meta=meta,
                              link=link)
        if t:
            made.append(t)
    return made


# ----------------------------- dispatcher event → jobdesk -----------------------------
async def _record_owner_for(ev: dict) -> str:
    """Pemilik data terkait event (untuk aturan penerima `record_owner`)."""
    et, eid = ev.get("entity_type"), ev.get("entity_id")
    org = ev.get("org_id", ORG_ID)
    if not eid:
        return None
    if et == "lead":
        row = await db.leads.find_one({"id": eid}, {"_id": 0, "assigned_to": 1})
        return (row or {}).get("assigned_to")
    if et == "deal":
        row = await db.deals.find_one({"id": eid}, {"_id": 0, "assigned_to": 1})
        return (row or {}).get("assigned_to")
    if et == "conversation":
        row = await db.conversations.find_one({"id": eid}, {"_id": 0, "owner": 1})
        return (row or {}).get("owner")
    if et == "customer":
        row = await db.customers.find_one({"id": eid}, {"_id": 0, "assigned_to": 1})
        return (row or {}).get("assigned_to")
    if et == "punch_item":
        row = await db.punch_items.find_one({"id": eid}, {"_id": 0, "assigned_to": 1})
        return (row or {}).get("assigned_to")
    if et == "appointment":
        row = await db.appointments.find_one({"id": eid}, {"_id": 0, "assigned_to": 1})
        return (row or {}).get("assigned_to")
    if et == "project":
        proj = await db.projects.find_one({"id": eid}, {"_id": 0, "members": 1})
        members = (proj or {}).get("members") or []
        for m in members:
            u = await user_by_email(org, m)
            if u and has_role(u, "project_manager"):
                return m
        return members[0] if members else None
    return None


async def dispatch_jobdesk_event(ev: dict) -> int:
    """Handler Event Bus generik: setiap event yang punya jobdesk melahirkan task.

    Jobdesk ber-`native=True` sudah dibuatkan task oleh kode modulnya sendiri; di sini
    hanya DILENGKAPI (divisi/jobdesk/bukti) supaya muncul di papan divisi yang benar.
    """
    codes = cat.EVENT_CODES.get(ev.get("type")) or []
    if not codes:
        return 0
    org = ev.get("org_id", ORG_ID)
    owner = await _record_owner_for(ev)
    made = 0
    for code in codes:
        jd = await jobdesk(org, code)
        if not jd.get("is_active", True):
            continue
        if jd.get("native"):
            await _enrich_native_tasks(org, jd, ev)
            continue
        label = (ev.get("data") or {}).get("label")
        rows = await spawn(org, code, source_event=f"{ev['type']}:{ev['entity_id']}:{code}",
                           record_owner=owner, entity_type=ev.get("entity_type"),
                           entity_id=ev.get("entity_id"),
                           title=f"{jd['title']}{f' — {label}' if label else ''}")
        made += len(rows)
    return made


async def _enrich_native_tasks(org: str, jd: dict, ev: dict) -> int:
    """Lengkapi task yang dibuat modul lama agar punya identitas jobdesk v2."""
    q = {"org_id": org, "related_entity_id": ev.get("entity_id"),
         "status": {"$in": OPEN_STATES}, "jobdesk_code": {"$in": [None, ""]}}
    upd = {"jobdesk_code": jd["code"], "division": jd["division"],
           "proof_kind": jd.get("proof_kind", "note"), "verify_mode": jd.get("verify_mode", "none"),
           "link": jd.get("link"), "updated_at": now_iso()}
    res = await db.tasks.update_many(q, {"$set": upd})
    return res.modified_count


# ----------------------------- task berulang -----------------------------
def period_key(recurrence: str, ref_dt: datetime = None) -> str:
    d = (ref_dt or now()).astimezone(timezone.utc)
    if recurrence == "daily":
        return d.date().isoformat()
    if recurrence == "weekly":
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    return f"{d.year}-{d.month:02d}"


def _period_due(recurrence: str) -> str:
    return due_in(days=1) if recurrence == "daily" else (
        due_in(days=3) if recurrence == "weekly" else due_in(days=7))


async def recurring_tick(org: str = None) -> int:
    """Buat task berulang untuk periode berjalan (idempoten via period_key)."""
    orgs = [org] if org else await db.users.distinct("org_id")
    made = 0
    for o in orgs:
        for code in cat.RECURRING:
            jd = await jobdesk(o, code)
            if not jd.get("is_active", True):
                continue
            rec = jd.get("recurrence") or "daily"
            pk = period_key(rec)
            rows = await spawn(
                o, code, source_event=f"jobdesk:{code}:{pk}", strict_once=True,
                due_date=_period_due(rec), entity_type="jobdesk", entity_id=code,
                title=f"{jd['title']} · {pk}", meta={"period": pk, "recurrence": rec})
            made += len(rows)
    return made


# ----------------------------- sweeper: kondisi nyata → event -----------------------------
async def workhub_sweeper() -> dict:
    """Ubah kondisi nyata menjadi event supaya Work Hub tidak "buta"."""
    out = {"conversation.unanswered": 0, "appointment.due_soon": 0,
           "appointment.passed": 0, "lead.followup_due": 0, "ar.overdue": 0}
    now_s = now_iso()
    # 1) WA masuk belum dibalas > 2 jam
    cutoff = due_in(hours=-2)
    convs = await db.conversations.find(
        {"last_direction": "in", "last_message_at": {"$ne": None, "$lt": cutoff}},
        {"_id": 0, "id": 1, "org_id": 1, "contact_name": 1, "unanswered_task_at": 1}).to_list(300)
    for c in convs:
        if c.get("unanswered_task_at") and c["unanswered_task_at"] > due_in(hours=-12):
            continue
        await emit("conversation.unanswered", "conversation", c["id"],
                   {"label": c.get("contact_name")}, org_id=c.get("org_id", ORG_ID))
        await db.conversations.update_one({"id": c["id"]},
                                          {"$set": {"unanswered_task_at": now_s}})
        out["conversation.unanswered"] += 1
    # 2) Appointment H-1 & 3) appointment sudah lewat tapi belum dicatat hasilnya
    appts = await db.appointments.find(
        {"status": "scheduled", "scheduled_at": {"$ne": None}},
        {"_id": 0, "id": 1, "org_id": 1, "title": 1, "scheduled_at": 1, "lead_name": 1}).to_list(500)
    soon = due_in(days=1)
    for a in appts:
        at = a.get("scheduled_at")
        label = a.get("lead_name") or a.get("title")
        if at < now_s:
            await emit("appointment.passed", "appointment", a["id"], {"label": label},
                       org_id=a.get("org_id", ORG_ID))
            out["appointment.passed"] += 1
        elif at <= soon:
            await emit("appointment.due_soon", "appointment", a["id"], {"label": label},
                       org_id=a.get("org_id", ORG_ID))
            out["appointment.due_soon"] += 1
    # 4) Lead nurturing diam >= 3 hari
    stale = due_in(days=-3)
    leads = await db.leads.find(
        {"stage": {"$in": ["nurturing", "appointment"]}, "updated_at": {"$lt": stale}},
        {"_id": 0, "id": 1, "org_id": 1, "name": 1}).to_list(300)
    for l in leads:
        await emit("lead.followup_due", "lead", l["id"], {"label": l.get("name")},
                   org_id=l.get("org_id", ORG_ID))
        out["lead.followup_due"] += 1
    # 4b) Lead sangat lama tanpa aktivitas -> DAUR ULANG (jujur: pipeline tidak digantung)
    import lead_lifecycle as lc
    dead = due_in(days=-14)
    cold = await db.leads.find(
        {"stage": {"$in": ["acquisition", "nurturing"]}, "updated_at": {"$lt": dead}},
        {"_id": 0}).to_list(200)
    for l in cold:
        await lc.record(l, "recycle", actor="system", reason="no_response",
                        source="sweeper:no_activity_14d")
        out["lead.recycled"] = out.get("lead.recycled", 0) + 1

    # 5) AR jatuh tempo belum lunas
    ars = await db.ar_invoices.find(
        {"status": {"$in": ["pending", "partial", "overdue"]}, "due_date": {"$lt": now_s}},
        {"_id": 0, "id": 1, "org_id": 1, "customer_name": 1, "unit_code": 1}).to_list(300)
    for r in ars:
        await emit("ar.overdue", "ar_invoice", r["id"],
                   {"label": r.get("customer_name") or r.get("unit_code")},
                   org_id=r.get("org_id", ORG_ID))
        out["ar.overdue"] += 1
    return out


# ----------------------------- verifikasi -----------------------------
async def auto_verify(task: dict) -> tuple:
    """Periksa bukti secara OTOMATIS bila memungkinkan.

    Kembalikan (ok, pesan). `ok=False` berarti sistem belum melihat bukti di data —
    tugas dikembalikan ke staf dengan alasan yang jelas (bukan asal ditolak).
    """
    code = task.get("jobdesk_code")
    check = (cat.BY_CODE.get(code) or {}).get("auto_check")
    if not check:
        return True, "Tidak ada pemeriksaan otomatis untuk jobdesk ini."
    org = task.get("org_id", ORG_ID)
    eid = task.get("related_entity_id")
    if check == "lead_contacted":
        lead = await db.leads.find_one({"id": eid}, {"_id": 0, "first_contact_at": 1})
        ok = bool((lead or {}).get("first_contact_at"))
        return ok, "Kontak pertama tercatat." if ok else "Belum ada catatan kontak pertama pada lead."
    if check == "conversation_replied":
        conv = await db.conversations.find_one({"id": eid}, {"_id": 0, "last_direction": 1})
        if not conv:
            return bool(task.get("proof")), "Tidak ada percakapan terkait; memakai bukti manual."
        ok = conv.get("last_direction") == "out"
        return ok, "Pesan balasan terkirim." if ok else "Percakapan masih menunggu balasan Anda."
    if check == "lead_activity_recent":
        n = await db.activities.count_documents(
            {"org_id": org, "entity_type": "lead", "entity_id": eid,
             "created_at": {"$gte": due_in(days=-1)}})
        return n > 0, "Ada aktivitas follow-up 24 jam terakhir." if n else "Belum ada aktivitas follow-up."
    if check in ("document_spr", "document_ppjb"):
        want = "spr" if check.endswith("spr") else "ppjb"
        n = await db.documents.count_documents(
            {"org_id": org, "type": want, "related_entity_id": eid})
        return n > 0, f"Dokumen {want.upper()} ditemukan." if n else f"Dokumen {want.upper()} belum dibuat."
    if check == "customer_kyc":
        c = await db.customers.find_one({"id": eid}, {"_id": 0, "nik": 1, "npwp": 1})
        ok = bool((c or {}).get("nik"))
        return ok, "NIK pembeli sudah terisi." if ok else "NIK pembeli masih kosong."
    if check == "complaint_closed":
        c = await db.complaints.find_one({"id": eid}, {"_id": 0, "status": 1})
        ok = (c or {}).get("status") in ("resolved", "closed")
        return ok, "Komplain sudah selesai." if ok else "Komplain belum berstatus selesai."
    if check == "punch_fixed":
        p = await db.punch_items.find_one({"id": eid}, {"_id": 0, "fix_photos": 1, "status": 1})
        ok = bool((p or {}).get("fix_photos"))
        return ok, "Foto bukti perbaikan sudah ada." if ok else "Belum ada foto bukti perbaikan."
    if check == "diary_today":
        n = await db.site_diaries.count_documents(
            {"org_id": org, "actor": task.get("assigned_to"), "log_date": {"$gte": today_iso_date()}})
        return n > 0, "Buku harian hari ini sudah diisi." if n else "Buku harian hari ini belum ada."
    if check == "progress_updated":
        n = await db.construction_phases.count_documents(
            {"org_id": org, "updated_at": {"$gte": due_in(days=-7)}})
        return n > 0, "Ada pembaruan progres 7 hari terakhir." if n else "Belum ada pembaruan progres minggu ini."
    if check == "inspection_finalized":
        n = await db.inspections.count_documents(
            {"org_id": org, "status": {"$in": ["passed", "failed"]},
             "updated_at": {"$gte": due_in(days=-7)}})
        return n > 0, "Ada inspeksi QC difinalisasi." if n else "Belum ada inspeksi QC difinalisasi minggu ini."
    if check == "wa_template_exists":
        n = await db.wa_templates.count_documents({"org_id": org, "status": "approved"})
        return n > 0, "Template WA tersedia." if n else "Belum ada template WA yang disetujui."
    if check == "broadcast_recent":
        n = await db.broadcasts.count_documents({"org_id": org, "created_at": {"$gte": due_in(days=-7)}})
        return n > 0, "Ada blasting 7 hari terakhir." if n else "Belum ada blasting minggu ini."
    if check == "depreciation_posted":
        pk = period_key("monthly")
        n = await db.asset_depreciations.count_documents({"org_id": org, "period": {"$regex": f"^{pk}"}})
        return n > 0, "Penyusutan periode ini sudah diposting." if n else "Penyusutan periode ini belum diposting."
    if check == "ar_followed_up":
        n = await db.activities.count_documents(
            {"org_id": org, "entity_id": eid, "created_at": {"$gte": due_in(days=-2)}})
        return (n > 0 or bool(task.get("proof"))), (
            "Ada catatan penagihan." if n else "Belum ada catatan penagihan; lampirkan bukti.")
    return True, "Pemeriksaan otomatis tidak dikenal — dianggap lolos."


# ----------------------------- papan divisi -----------------------------
def bucket(tasks: list) -> dict:
    now_s, today = now_iso(), today_iso_date()
    out = {"overdue": [], "today": [], "upcoming": [], "waiting": [], "review": []}
    for t in tasks:
        if t.get("status") == "submitted":
            out["review"].append(t)
            continue
        if t.get("status") == "snoozed":
            out["waiting"].append(t)
            continue
        due = t.get("due_date")
        if not due:
            out["upcoming"].append(t)
        elif due < now_s:
            out["overdue"].append(t)
        elif str(due)[:10] == today:
            out["today"].append(t)
        else:
            out["upcoming"].append(t)
    return out


async def division_board(org: str, division: str) -> dict:
    """Ringkasan pekerjaan satu divisi: beban kerja per staf + antrean verifikasi."""
    tasks = await db.tasks.find(
        {"org_id": org, "division": division, "status": {"$in": OPEN_STATES}},
        {"_id": 0}).sort("due_date", 1).to_list(1000)
    members = await division_members(org, division)
    now_s = now_iso()
    per_member = []
    for m in members:
        mine = [t for t in tasks if t.get("assigned_to") == m["email"]]
        per_member.append({
            "email": m["email"], "name": m.get("name"), "role": m.get("role"),
            "level": level_of(m), "open": len(mine),
            "overdue": sum(1 for t in mine if (t.get("due_date") or "9") < now_s),
            "submitted": sum(1 for t in mine if t.get("status") == "submitted"),
            "sla_breached": sum(1 for t in mine if t.get("sla_breached")),
        })
    per_member.sort(key=lambda r: (-r["overdue"], -r["open"], r["name"] or ""))
    unassigned = [t for t in tasks if not t.get("assigned_to")]
    return {
        "division": division, "division_label": p29.DIVISION_LABEL.get(division, division),
        "totals": {
            "open": len(tasks),
            "overdue": sum(1 for t in tasks if (t.get("due_date") or "9") < now_s),
            "review": sum(1 for t in tasks if t.get("status") == "submitted"),
            "unassigned": len(unassigned),
            "staff": len([m for m in members if level_of(m) == "staff"]),
        },
        "members": per_member,
        "review_queue": [t for t in tasks if t.get("status") == "submitted"][:50],
        "unassigned": unassigned[:50],
    }


async def notify_supervisor(org: str, division: str, *, title: str, body: str,
                            entity_type: str = None, entity_id: str = None):
    sup = await division_members(org, division, level="supervisor")
    for s in sup:
        await create_notification(user_email=s["email"], title=title, body=body, type="task",
                                  related_entity_type=entity_type, related_entity_id=entity_id,
                                  org_id=org)


async def log_task_activity(task: dict, body: str, actor: str):
    et, eid = task.get("related_entity_type"), task.get("related_entity_id")
    if et and eid and et != "jobdesk":
        await add_activity(entity_type=et, entity_id=eid, type="system", body=body,
                           actor=actor, org_id=task.get("org_id", ORG_ID))
