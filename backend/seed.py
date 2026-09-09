"""Idempotent seed + index creation.

Seeds: 1 org (PT SIPRO Land), users per role (+ extra sales for RBAC scope test),
permission_settings matrix, a demo project + units, demo leads, sample
tasks/activities/notifications so the Work Hub shell is populated, plus Slice A
reference data (channel accounts [simulation], automation rule, document templates,
a demo WA conversation).
"""
import logging
import os

from db import db, ORG_ID, ORG_NAME
from core_utils import new_id, now_iso, due_in
from security import hash_password, verify_password
from rbac import DEFAULT_PERMISSIONS
from engine import add_activity, create_notification, compute_lead_score, recompute_project_progress, dispatch_pending
import finance_engine as fe
import gl_engine as gl
from seed_phase16 import seed_subcon_claims
from seed_phase17 import seed_inspections
from seed_phase18 import seed_material_requisitions
from seed_phase19 import seed_tax_setoran
from seed_phase22 import seed_omnichannel
from seed_indexes import ensure_indexes  # noqa: F401 — index dipisah (batas ukuran file)

logger = logging.getLogger("sipro.seed")

TEST_PASSWORD = "Sipro#2026"

# Akun super admin: email & sandi dari env (produksi). Tanpa env → nilai demo di bawah.
SUPERADMIN_EMAIL = os.environ.get("SUPERADMIN_EMAIL", "superadmin@sipro.co.id").lower()
SUPERADMIN_PASSWORD = os.environ.get("SUPERADMIN_PASSWORD", TEST_PASSWORD)
# Akun staf demo (owner/sales/finance/...) hanya dibuat bila SEED_DEMO_USERS=true.
SEED_DEMO_USERS = os.environ.get("SEED_DEMO_USERS", "false").lower() == "true"

SUPERADMIN_USER = {"name": "Super Admin", "email": SUPERADMIN_EMAIL, "role": "super_admin"}

DEMO_USERS = [
    {"name": "Budi Owner", "email": "owner@sipro.co.id", "role": "owner"},
    {"name": "Sinta Manajer", "email": "manager@sipro.co.id", "role": "sales_manager"},
    {"name": "Rani Marketing", "email": "marketing@sipro.co.id", "role": "marketing_admin"},
    {"name": "Andi Sales", "email": "sales@sipro.co.id", "role": "sales"},
    {"name": "Dewi Sales", "email": "sales2@sipro.co.id", "role": "sales"},
    {"name": "Fitri Finance", "email": "finance@sipro.co.id", "role": "finance"},
    {"name": "Joko PM", "email": "pm@sipro.co.id", "role": "project_manager"},
    {"name": "Eko Site", "email": "site@sipro.co.id", "role": "site_engineer"},
]

SEED_USERS = [SUPERADMIN_USER] + (DEMO_USERS if SEED_DEMO_USERS else [])


async def ensure_superadmin():
    """Idempoten: super admin selalu ada; sandi mengikuti SUPERADMIN_PASSWORD bila diubah."""
    ts = now_iso()
    existing = await db.users.find_one({"email": SUPERADMIN_EMAIL})
    if not existing:
        await db.users.insert_one({
            "id": new_id(), "org_id": ORG_ID, "name": "Super Admin", "email": SUPERADMIN_EMAIL,
            "role": "super_admin", "phone": None, "password_hash": hash_password(SUPERADMIN_PASSWORD),
            "is_active": True, "created_at": ts, "updated_at": ts})
        logger.info("Super admin dibuat: %s", SUPERADMIN_EMAIL)
        return
    if not verify_password(SUPERADMIN_PASSWORD, existing.get("password_hash", "")):
        await db.users.update_one({"email": SUPERADMIN_EMAIL}, {"$set": {
            "password_hash": hash_password(SUPERADMIN_PASSWORD), "is_active": True, "updated_at": ts}})
        logger.info("Sandi super admin disinkronkan dari SUPERADMIN_PASSWORD")

SPR_TEMPLATE = (
    "Pada hari ini {{date}}, telah dilakukan pemesanan unit properti dengan rincian berikut.\n\n"
    "Nama Pemesan : {{buyer_name}}\n"
    "No. Telepon : {{buyer_phone}}\n"
    "Proyek : {{project_name}}\n"
    "Unit : {{unit_code}} ({{unit_type}})\n"
    "Harga Unit : Rp {{price}}\n"
    "Booking Fee : Rp {{booking_fee}}\n"
    "Berlaku Hingga : {{reserved_until}}\n\n"
    "Pemesanan ini bersifat sementara (hold). Apabila melewati batas waktu di atas tanpa "
    "kelanjutan proses, pemesanan otomatis batal dan unit dilepas kembali.\n\n"
    "Sales : {{sales_name}}\n"
    "Penerbit : {{org_name}}\n"
)

PPJB_TEMPLATE = (
    "PERJANJIAN PENGIKATAN JUAL BELI (PPJB)\n\n"
    "Pada hari ini {{date}}, para pihak sepakat mengikatkan diri dalam jual beli unit berikut.\n\n"
    "Pembeli : {{buyer_name}}\n"
    "No. Telepon : {{buyer_phone}}\n"
    "Proyek : {{project_name}}\n"
    "Unit : {{unit_code}} ({{unit_type}})\n"
    "Harga : Rp {{price}}\n"
    "Tanggal : {{date}}\n\n"
    "Penjual : {{org_name}}\n"
)

AJB_TEMPLATE = (
    "AKTA JUAL BELI (AJB)\n\n"
    "Pada hari ini {{date}}, telah dilaksanakan jual beli unit properti yang telah diserahterimakan (BAST).\n\n"
    "Pembeli : {{buyer_name}}\n"
    "No. Telepon : {{buyer_phone}}\n"
    "Proyek : {{project_name}}\n"
    "Unit : {{unit_code}} ({{unit_type}})\n"
    "Harga : Rp {{price}}\n"
    "Tanggal Akta : {{date}}\n\n"
    "Dengan ditandatanganinya akta ini, hak atas unit beralih kepada Pembeli.\n\n"
    "Penjual : {{org_name}}\n"
)


async def seed_if_empty():
    existing = await db.orgs.find_one({"id": ORG_ID})
    if existing:
        return False
    ts = now_iso()
    await db.orgs.insert_one({"id": ORG_ID, "name": ORG_NAME, "status": "active", "created_at": ts})
    # EPIC M4 — 2nd (empty) demo tenant so multi-tenant switching is demonstrable & isolated.
    if SEED_DEMO_USERS:
        await db.orgs.insert_one({"id": "org-nusa", "name": "PT Nusa Properti Sejahtera",
                                  "status": "active", "created_at": ts})
        await db.users.update_one({"email": "owner@nusaproperti.co.id"}, {"$setOnInsert": {
            "id": new_id(), "org_id": "org-nusa", "name": "Hendra Wijaya (Owner Nusa)",
            "email": "owner@nusaproperti.co.id", "role": "owner", "phone": None,
            "password_hash": hash_password(TEST_PASSWORD), "is_active": True,
            "created_at": ts, "updated_at": ts}}, upsert=True)

    # Users
    await ensure_superadmin()
    for u in DEMO_USERS if SEED_DEMO_USERS else []:
        await db.users.update_one(
            {"email": u["email"]},
            {"$setOnInsert": {
                "id": new_id(), "org_id": ORG_ID, "name": u["name"], "email": u["email"],
                "role": u["role"], "phone": None, "password_hash": hash_password(TEST_PASSWORD),
                "is_active": True, "created_at": ts, "updated_at": ts,
            }}, upsert=True,
        )

    # Permission matrix (SSOT copy of defaults, admin-overridable)
    await db.permission_settings.update_one(
        {"key": "rbac_matrix"},
        {"$set": {"key": "rbac_matrix", "matrix": DEFAULT_PERMISSIONS, "updated_at": ts,
                  "updated_by": "seed"}}, upsert=True,
    )

    # Channel accounts + automation rules + WA templates (EPIC 1.7) are seeded by
    # seed_omnichannel() below, after demo leads/conversations exist.

    # Document templates
    await db.document_templates.insert_many([
        {"id": new_id(), "org_id": ORG_ID, "code": "SPR", "name": "Surat Pemesanan Rumah (SPR)",
         "content": SPR_TEMPLATE, "is_active": True, "created_at": ts},
        {"id": new_id(), "org_id": ORG_ID, "code": "PPJB", "name": "Perjanjian Pengikatan Jual Beli (PPJB)",
         "content": PPJB_TEMPLATE, "is_active": True, "created_at": ts},
        {"id": new_id(), "org_id": ORG_ID, "code": "AJB", "name": "Akta Jual Beli (AJB)",
         "content": AJB_TEMPLATE, "is_active": True, "created_at": ts},
    ])

    # Demo project + units (for Project Home + Slice B)
    project_id = new_id()
    await db.projects.insert_one({
        "id": project_id, "org_id": ORG_ID, "name": "Cluster Asri Blok A", "code": "CAA",
        "location": "Bogor, Jawa Barat", "status": "active",
        "members": ["pm@sipro.co.id", "site@sipro.co.id"], "created_at": ts, "updated_at": ts,
    })
    for i in range(1, 7):
        uid = new_id()
        if i == 1:
            first_unit_id = uid
        await db.units.insert_one({
            "id": uid, "org_id": ORG_ID, "project_id": project_id,
            "code": f"A-{i:02d}", "type": "Tipe 45/90", "price": 850_000_000,
            "status": "available", "construction_status": "not_started",
            "construction_progress": 0, "payment_status": "none",
            "reserved_by_deal": None, "booked_by_deal": None,
            "created_at": ts, "updated_at": ts,
        })

    # Construction phases (weighted) for Slice B + Kurva-S baseline.
    # `work_category` = kategori DEFAULT_PHASES → progres fase disinkronkan dari jadwal unit.
    from phase_templates import DEFAULT_PHASES
    category_of = {n: c for n, _w, _p, c in DEFAULT_PHASES}
    phases = [
        ("Persiapan Lahan", 10, 100, 100, "done", 1),
        ("Pondasi", 20, 100, 80, "in_progress", 2),
        ("Struktur", 30, 60, 40, "in_progress", 3),
        ("Dinding & Atap", 20, 20, 0, "not_started", 4),
        ("MEP (Listrik/Air)", 10, 0, 0, "not_started", 5),
        ("Finishing", 10, 0, 0, "not_started", 6),
    ]
    for name, weight, planned, progress, status, order in phases:
        await db.construction_phases.insert_one({
            "id": new_id(), "org_id": ORG_ID, "project_id": project_id, "name": name,
            "weight": weight, "planned_pct": planned, "progress": progress, "status": status,
            "work_category": category_of.get(name),
            "order": order, "created_at": ts, "updated_at": ts,
        })
    await recompute_project_progress(project_id, ORG_ID)

    # Site diary (buku harian) + Punch list (daftar cacat) — EPIC 2.8
    await db.site_diaries.insert_many([
        {"id": new_id(), "org_id": ORG_ID, "project_id": project_id, "project_name": "Cluster Asri Blok A",
         "log_date": due_in(days=-1), "weather": "cerah_berawan", "workforce": 24,
         "work_description": "Pengecoran kolom lantai 2 Blok A, area grid A1-A4.",
         "materials": "Semen 40 sak, besi D13 1.2 ton", "equipment": "1 concrete mixer, 1 vibrator",
         "obstacles": "Hujan sore ~1 jam, pekerjaan sempat berhenti.", "photo": None,
         "actor": "site@sipro.co.id", "created_at": ts},
        {"id": new_id(), "org_id": ORG_ID, "project_id": project_id, "project_name": "Cluster Asri Blok A",
         "log_date": ts, "weather": "cerah", "workforce": 28,
         "work_description": "Pemasangan bekisting balok lantai 2 & pembesian pelat.",
         "materials": "Plywood 30 lembar, kawat bendrat", "equipment": "Scaffolding, bar cutter",
         "obstacles": None, "photo": None, "actor": "site@sipro.co.id", "created_at": ts},
    ])
    await db.punch_items.insert_many([
        {"id": new_id(), "org_id": ORG_ID, "project_id": project_id, "project_name": "Cluster Asri Blok A",
         "unit_id": None, "title": "Retak rambut plafon", "description": "Retak rambut pada plafon gypsum ruang tamu.",
         "location": "Unit A-01 · Ruang Tamu", "category": "finishing", "severity": "medium", "status": "open",
         "assigned_to": "site@sipro.co.id", "due_date": due_in(days=3), "photo": None,
         "opened_by": "pm@sipro.co.id", "closed_at": None, "created_at": ts, "updated_at": ts},
        {"id": new_id(), "org_id": ORG_ID, "project_id": project_id, "project_name": "Cluster Asri Blok A",
         "unit_id": None, "title": "Rembesan pipa wastafel", "description": "Terdapat rembesan pada sambungan pipa wastafel kamar mandi.",
         "location": "Unit A-01 · Kamar Mandi", "category": "mep", "severity": "high", "status": "in_progress",
         "assigned_to": "site@sipro.co.id", "due_date": due_in(days=2), "photo": None,
         "opened_by": "pm@sipro.co.id", "closed_at": None, "created_at": due_in(hours=-30), "updated_at": ts},
        {"id": new_id(), "org_id": ORG_ID, "project_id": project_id, "project_name": "Cluster Asri Blok A",
         "unit_id": None, "title": "Cat dinding belang", "description": "Warna cat dinding belang, sudah dilakukan pengecatan ulang.",
         "location": "Unit A-01 · Kamar Utama", "category": "finishing", "severity": "low", "status": "closed",
         "assigned_to": "site@sipro.co.id", "due_date": due_in(days=-2), "photo": None,
         "opened_by": "pm@sipro.co.id", "closed_at": ts, "created_at": due_in(hours=-72), "updated_at": ts},
    ])

    # Materials + opening GRN transactions
    materials = [
        ("SMN", "Semen Portland", "sak", 500),
        ("BSI", "Besi Beton D10", "batang", 300),
        ("PSR", "Pasir Beton", "m3", 120),
        ("BTA", "Bata Merah", "pcs", 20000),
    ]
    material_ids = {}
    for code, mname, uom, qty_in in materials:
        mid = new_id()
        material_ids[code] = {"id": mid, "uom": uom, "name": mname}
        await db.materials.insert_one({
            "id": mid, "org_id": ORG_ID, "project_id": project_id, "code": code,
            "name": mname, "uom": uom, "created_at": ts, "created_by": "seed"})
        await db.material_txns.insert_one({
            "id": new_id(), "org_id": ORG_ID, "project_id": project_id, "material_id": mid,
            "type": "in", "qty": qty_in, "note": "Penerimaan awal (GRN)", "ref": "GRN-0001",
            "actor": "site@sipro.co.id", "created_at": ts})

    # Demo leads assigned to sales (with heuristic score)
    lead1 = new_id()
    lead2 = new_id()
    lead_docs = [
        {"id": lead1, "org_id": ORG_ID, "name": "Ibu Dewi Kartika", "phone": "+628121111111",
         "email": None, "source": "walk_in", "campaign": None, "stage": "acquisition",
         "assigned_to": "sales@sipro.co.id", "interest_unit_type": "Tipe 45/90", "notes": None,
         "first_contact_at": None, "response_time_minutes": None,
         "created_at": ts, "updated_at": ts, "created_by": "seed"},
        {"id": lead2, "org_id": ORG_ID, "name": "Bapak Rudi Hartono", "phone": "+628122222222",
         "email": None, "source": "meta_ads", "campaign": "cluster-a-meta", "stage": "nurturing",
         "assigned_to": "sales@sipro.co.id", "interest_unit_type": "Tipe 45/90", "notes": "Tertarik unit Tipe 45/90.",
         "first_contact_at": ts, "response_time_minutes": 4,
         "created_at": ts, "updated_at": ts, "created_by": "seed"},
    ]
    for ld in lead_docs:
        ld.update(compute_lead_score(ld))
        await db.leads.insert_one(ld)

    # Demo WA conversation for lead2 (simulation)
    conv_id = new_id()
    await db.conversations.insert_one({
        "id": conv_id, "org_id": ORG_ID, "channel": "whatsapp", "contact_phone": "+628122222222",
        "contact_name": "Bapak Rudi Hartono", "lead_id": lead2, "owner": "sales@sipro.co.id",
        "status": "active", "mode": "simulation", "unread": 0, "last_message_at": ts,
        "window_expires_at": due_in(hours=24), "created_at": ts, "updated_at": ts,
    })
    await db.messages.insert_many([
        {"id": new_id(), "org_id": ORG_ID, "conversation_id": conv_id, "direction": "in",
         "body": "Halo, saya tertarik unit Tipe 45 di Cluster Asri. Boleh info harga?",
         "sender": "contact", "created_at": ts},
        {"id": new_id(), "org_id": ORG_ID, "conversation_id": conv_id, "direction": "out",
         "body": "Halo Pak Rudi, terima kasih. Harga unit Tipe 45 mulai Rp 850 juta. Boleh saya jadwalkan survey?",
         "sender": "sales@sipro.co.id", "created_at": ts},
    ])

    # EPIC 1.7 omnichannel seed (channels, WA templates, automation rules, attribution,
    # stale/unanswered demo conversation) — needs lead2 + conv_id to exist.
    await seed_omnichannel(ORG_ID, ts, {"lead2": lead2, "conv_id": conv_id})

    # Sample tasks so Work Hub is not blank
    tasks = [
        {"assigned_to": "sales@sipro.co.id", "title": "Hubungi lead baru: Ibu Dewi Kartika",
         "type": "contact", "priority": "urgent", "due_date": due_in(minutes=-30),
         "sla_due_at": due_in(minutes=-30), "related_entity_type": "lead", "related_entity_id": lead1},
        {"assigned_to": "sales@sipro.co.id", "title": "Follow-up: Bapak Rudi Hartono",
         "type": "follow_up", "priority": "high", "due_date": due_in(hours=3),
         "related_entity_type": "lead", "related_entity_id": lead2},
        {"assigned_to": "sales@sipro.co.id", "title": "Siapkan materi presentasi unit A-03",
         "type": "todo", "priority": "medium", "due_date": due_in(days=2)},
        {"assigned_to": "manager@sipro.co.id", "title": "Review distribusi lead minggu ini",
         "type": "review", "priority": "medium", "due_date": due_in(hours=5)},
        {"assigned_to": "finance@sipro.co.id", "title": "Rekap penerimaan kas hari ini",
         "type": "todo", "priority": "high", "due_date": due_in(hours=2)},
        {"assigned_to": "pm@sipro.co.id", "title": "Cek progres konstruksi Blok A",
         "type": "todo", "priority": "medium", "due_date": due_in(hours=6),
         "related_entity_type": "project", "related_entity_id": project_id},
    ]
    for t in tasks:
        doc = {
            "id": new_id(), "org_id": ORG_ID, "status": "open", "sla_breached": False,
            "source_event": None, "auto_generated": False, "outcome": None,
            "description": None, "created_by": "seed", "created_at": ts, "updated_at": ts,
            "sla_due_at": t.get("sla_due_at"), "related_entity_type": t.get("related_entity_type"),
            "related_entity_id": t.get("related_entity_id"),
        }
        doc.update({k: t[k] for k in ("assigned_to", "title", "type", "priority", "due_date")})
        await db.tasks.insert_one(doc)

    # ----------------------------- Phase 14 seed: Appointment & Survey (EPIC 1.2) -----------------------------
    appt_done_id, appt_today_id, appt_upcoming_id = new_id(), new_id(), new_id()
    await db.appointments.insert_many([
        {"id": appt_done_id, "org_id": ORG_ID, "lead_id": lead2, "lead_name": "Bapak Rudi Hartono",
         "title": "Survey lokasi & unit A-01",
         "scheduled_at": due_in(days=-1, hours=2), "type": "survey", "location": "Cluster Asri Blok A",
         "notes": "Kunjungan pertama, tinjau kavling & lingkungan.", "status": "done",
         "assigned_to": "sales@sipro.co.id", "created_by": "seed",
         "created_at": due_in(days=-3), "updated_at": due_in(days=-1)},
        {"id": appt_today_id, "org_id": ORG_ID, "lead_id": lead1, "lead_name": "Ibu Dewi Kartika",
         "title": "Presentasi unit & tanda tangan SPR",
         "scheduled_at": due_in(hours=3), "type": "meeting", "location": "Kantor pemasaran Cluster Asri",
         "notes": "Bawa brosur Tipe 45 & simulasi KPR.", "status": "scheduled",
         "assigned_to": "sales@sipro.co.id", "created_by": "seed",
         "created_at": ts, "updated_at": ts},
        {"id": appt_upcoming_id, "org_id": ORG_ID, "lead_id": lead2, "lead_name": "Bapak Rudi Hartono",
         "title": "Survey lanjutan (cek finishing)",
         "scheduled_at": due_in(days=2, hours=1), "type": "survey", "location": "Cluster Asri Blok A",
         "notes": None, "status": "scheduled", "assigned_to": "sales@sipro.co.id", "created_by": "seed",
         "created_at": ts, "updated_at": ts},
    ])

    # Survey selesai (terikat appointment lalu) — checklist terisi + hasil + foto demo.
    survey_done_id = new_id()
    await db.surveys.insert_one({
        "id": survey_done_id, "org_id": ORG_ID, "lead_id": lead2, "lead_name": "Bapak Rudi Hartono",
        "appointment_id": appt_done_id, "location": "Cluster Asri Blok A",
        "notes": "Kavling kering, akses jalan bagus.", "summary": "Lokasi sangat layak; calon serius.",
        "assigned_to": "sales@sipro.co.id", "status": "completed", "result": "recommended",
        "photo_count": 1, "checklist": [
            {"key": "akses_jalan", "label": "Akses jalan menuju lokasi", "status": "ok", "note": "Aspal 6m"},
            {"key": "kondisi_tanah", "label": "Kondisi tanah & kontur", "status": "ok", "note": "Datar"},
            {"key": "batas_kavling", "label": "Batas kavling & patok jelas", "status": "ok", "note": None},
            {"key": "listrik", "label": "Ketersediaan listrik", "status": "ok", "note": "PLN tersedia"},
            {"key": "air", "label": "Ketersediaan air / PDAM", "status": "issue", "note": "PDAM belum, pakai sumur bor"},
            {"key": "drainase", "label": "Saluran drainase", "status": "ok", "note": None},
            {"key": "lingkungan", "label": "Lingkungan & keamanan sekitar", "status": "ok", "note": "One gate system"}],
        "created_by": "sales@sipro.co.id", "created_at": due_in(days=-1, hours=2),
        "updated_at": due_in(days=-1, hours=3), "completed_at": due_in(days=-1, hours=3)})
    # Foto survey demo (PNG 1x1) via mongo provider (tanpa network saat seed).
    import base64 as _b64
    _png = _b64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    survey_fid = new_id()
    survey_path = f"sipro/{ORG_ID}/survey/{survey_done_id}/{survey_fid}.png"
    await db.file_blobs.insert_one({
        "path": survey_path, "data_b64": _b64.b64encode(_png).decode(),
        "content_type": "image/png", "size": len(_png)})
    await db.files.insert_one({
        "id": survey_fid, "org_id": ORG_ID, "storage_path": survey_path, "provider": "mongo",
        "original_filename": "kavling-blok-a.png", "content_type": "image/png", "size": len(_png),
        "owner_type": "survey", "owner_id": survey_done_id, "doc_type": "survey_photo",
        "uploaded_by": "sales@sipro.co.id", "is_deleted": False, "created_at": due_in(days=-1, hours=3)})

    # Survey berjalan (belum selesai) untuk lead1 — checklist default.
    await db.surveys.insert_one({
        "id": new_id(), "org_id": ORG_ID, "lead_id": lead1, "lead_name": "Ibu Dewi Kartika",
        "appointment_id": None, "location": "Cluster Asri Blok A", "notes": None, "summary": None,
        "assigned_to": "sales@sipro.co.id", "status": "in_progress", "result": None, "photo_count": 0,
        "checklist": [
            {"key": "akses_jalan", "label": "Akses jalan menuju lokasi", "status": "na", "note": None},
            {"key": "kondisi_tanah", "label": "Kondisi tanah & kontur", "status": "na", "note": None},
            {"key": "batas_kavling", "label": "Batas kavling & patok jelas", "status": "na", "note": None},
            {"key": "listrik", "label": "Ketersediaan listrik", "status": "na", "note": None},
            {"key": "air", "label": "Ketersediaan air / PDAM", "status": "na", "note": None},
            {"key": "drainase", "label": "Saluran drainase", "status": "na", "note": None},
            {"key": "lingkungan", "label": "Lingkungan & keamanan sekitar", "status": "na", "note": None}],
        "created_by": "sales@sipro.co.id", "created_at": ts, "updated_at": ts, "completed_at": None})

    # ----------------------------- Slice Finance seed -----------------------------
    # Tax config (configurable defaults; wajib dikonfirmasi penasihat pajak saat go-live).
    await db.finance_configs.update_one(
        {"org_id": ORG_ID, "key": "finance_config"},
        {"$set": {"key": "finance_config", "org_id": ORG_ID, "ppn_rate": 12.0,
                  "bphtb_rate": 5.0, "pph_rate": 2.5, "npoptkp": 80_000_000, "updated_at": ts}},
        upsert=True)

    # Collection config (denda keterlambatan + masa tenggang) untuk EPIC 3.5.
    await db.finance_configs.update_one(
        {"org_id": ORG_ID, "key": "collection_config"},
        {"$set": {"key": "collection_config", "org_id": ORG_ID,
                  "denda_rate_pct_month": 2.0, "grace_days": 7, "updated_at": ts}},
        upsert=True)

    # Payment schemes (multi-scheme AR): default + alternatif.
    await db.payment_schemes.insert_many([
        {"id": new_id(), "org_id": ORG_ID, "name": "Standar KPR (DP 20%)", "is_default": True,
         "created_by": "seed", "created_at": ts, "items": [
             {"label": "DP 20%", "basis": "percent", "value": 20, "due_offset_days": 0},
             {"label": "Termin I 25%", "basis": "percent", "value": 25, "due_offset_days": 60},
             {"label": "Termin II 25%", "basis": "percent", "value": 25, "due_offset_days": 120},
             {"label": "Pelunasan / KPR 30%", "basis": "percent", "value": 30, "due_offset_days": 180}]},
        {"id": new_id(), "org_id": ORG_ID, "name": "Cash Bertahap (3x)", "is_default": False,
         "created_by": "seed", "created_at": ts, "items": [
             {"label": "DP 30%", "basis": "percent", "value": 30, "due_offset_days": 0},
             {"label": "Termin 40%", "basis": "percent", "value": 40, "due_offset_days": 45},
             {"label": "Pelunasan 30%", "basis": "percent", "value": 30, "due_offset_days": 90}]},
    ])

    # Commission scheme (tiered / bracket-based).
    await db.commission_schemes.insert_one({
        "id": new_id(), "org_id": ORG_ID, "name": "Komisi Sales Bertingkat", "basis": "price",
        "trigger": "booked", "is_default": True, "created_by": "seed", "created_at": ts, "tiers": [
            {"min_amount": 0, "max_amount": 500_000_000, "rate_pct": 2.0},
            {"min_amount": 500_000_001, "max_amount": 1_000_000_000, "rate_pct": 2.5},
            {"min_amount": 1_000_000_001, "max_amount": None, "rate_pct": 3.0}]})

    # Demo booked deal (unit A-01) -> AR schedule + 1 receipt (DP) + commission + demo AP bill.
    demo_deal_id = new_id()
    await db.deals.insert_one({
        "id": demo_deal_id, "org_id": ORG_ID, "lead_id": lead1, "unit_id": first_unit_id,
        "project_id": project_id, "assigned_to": "sales@sipro.co.id", "status": "booked",
        "price": 850_000_000, "booking_fee": 5_000_000, "reserved_at": ts,
        "reserved_until": due_in(days=7), "booked_at": ts, "notes": "Demo finance",
        "created_by": "seed", "created_at": ts, "updated_at": ts})
    await db.units.update_one({"id": first_unit_id}, {"$set": {
        "status": "booked", "booked_by_deal": demo_deal_id, "payment_status": "booking_fee",
        "updated_at": ts}})
    if lead_docs and lead_docs[0]["id"] == lead1:
        await db.leads.update_one({"id": lead1}, {"$set": {"stage": "booking", "updated_at": ts}})
    demo_deal = await db.deals.find_one({"id": demo_deal_id}, {"_id": 0})
    await fe.create_ar_for_deal(demo_deal, org_id=ORG_ID)
    await fe.apply_receipt(demo_deal_id, 170_000_000, "transfer", "Pembayaran DP 20%",
                           "finance@sipro.co.id", ORG_ID)
    await fe.create_commission_for_deal(demo_deal, org_id=ORG_ID, trigger="booked")
    # Phase 14 (EPIC 1.6): komisi demo tambahan agar breakdown menampilkan approved & paid.
    comm_approved_id, comm_paid_id = new_id(), new_id()
    await db.commissions.insert_many([
        {"id": comm_approved_id, "org_id": ORG_ID, "deal_id": demo_deal_id, "unit_id": first_unit_id,
         "unit_code": "A-01", "scheme_id": None, "scheme_name": "Komisi Sales Bertingkat",
         "assigned_to": "sales@sipro.co.id", "basis": "price", "base": 680_000_000, "rate_pct": 2.5,
         "amount": 17_000_000, "trigger": "booked", "status": "approved",
         "approved_by": "finance@sipro.co.id", "approved_at": due_in(days=-2), "paid_by": None,
         "paid_at": None, "created_at": due_in(days=-5), "updated_at": due_in(days=-2)},
        {"id": comm_paid_id, "org_id": ORG_ID, "deal_id": demo_deal_id, "unit_id": first_unit_id,
         "unit_code": "A-01", "scheme_id": None, "scheme_name": "Komisi Sales Bertingkat",
         "assigned_to": "sales@sipro.co.id", "basis": "price", "base": 1_020_000_000, "rate_pct": 2.5,
         "amount": 25_500_000, "trigger": "booked", "status": "paid",
         "approved_by": "finance@sipro.co.id", "approved_at": due_in(days=-10),
         "paid_by": "finance@sipro.co.id", "paid_at": due_in(days=-6),
         "created_at": due_in(days=-12), "updated_at": due_in(days=-6)},
    ])
    await fe.create_ap_bill("CV Bangun Jaya", project_id, 200_000_000, 5, due_in(days=30),
                            "Termin pondasi Blok A", "finance@sipro.co.id", ORG_ID)

    # Demo: backdate satu termin belum-terbayar agar Collections & Cash-Flow punya data menunggak.
    demo_inv = await db.ar_invoices.find_one({"org_id": ORG_ID, "deal_id": demo_deal_id}, {"_id": 0})
    if demo_inv:
        inv_items = demo_inv["items"]
        for it in inv_items:
            if it.get("status") != "paid":  # termin belum lunas pertama
                it["due_date"] = due_in(days=-25)  # 25 hari lewat jatuh tempo
                break
        await db.ar_invoices.update_one({"id": demo_inv["id"]}, {"$set": {"items": inv_items, "updated_at": ts}})

    # ----------------------------- EPIC 1.5 seed: Customer (KYC) + Financing (KPR) -----------------------------
    cust_id = new_id()
    await db.customers.insert_one({
        "id": cust_id, "org_id": ORG_ID, "name": "Ibu Dewi Kartika",
        "phone": "+628121111111", "email": "dewi.kartika@example.com",
        "nik": "3201234567890001", "npwp": "09.123.456.7-011.000",
        "address": "Jl. Melati No. 12, Bogor, Jawa Barat", "occupation": "Wiraswasta",
        "monthly_income": 25_000_000, "spouse_name": "Bapak Andi Kartika",
        "spouse_nik": "3201234567890002", "heir_name": "Rara Kartika", "heir_relation": "Anak",
        "lead_id": lead1, "kyc_status": "submitted", "notes": "Customer demo (KPR).",
        "kyc_files": [], "created_by": "seed", "created_at": ts, "updated_at": ts,
    })
    # Demo KYC file via mongo provider (no network during seed).
    kyc_fid = new_id()
    kyc_path = f"sipro/{ORG_ID}/kyc/{cust_id}/{kyc_fid}.txt"
    kyc_text = "DEMO KTP - Ibu Dewi Kartika - NIK 3201234567890001"
    await db.file_blobs.insert_one({
        "path": kyc_path, "data_b64": _b64.b64encode(kyc_text.encode()).decode(),
        "content_type": "text/plain", "size": len(kyc_text)})
    await db.files.insert_one({
        "id": kyc_fid, "org_id": ORG_ID, "storage_path": kyc_path, "provider": "mongo",
        "original_filename": "ktp-dewi.txt", "content_type": "text/plain", "size": len(kyc_text),
        "owner_type": "customer", "owner_id": cust_id, "doc_type": "ktp",
        "uploaded_by": "seed", "is_deleted": False, "created_at": ts})
    await db.customers.update_one({"id": cust_id}, {"$push": {"kyc_files": {
        "file_id": kyc_fid, "doc_type": "ktp", "original_filename": "ktp-dewi.txt", "uploaded_at": ts}}})

    # Financing (KPR) app for the demo deal — approved after SLIK clear (demo).
    await db.financing_apps.insert_one({
        "id": new_id(), "org_id": ORG_ID, "deal_id": demo_deal_id, "customer_id": cust_id,
        "unit_id": first_unit_id, "bank_name": "Bank Negara Griya", "plafon": 680_000_000,
        "dp_amount": 170_000_000, "tenor_months": 180, "interest_rate_pct": 8.5,
        "status": "approved", "slik_status": "clear", "slik_note": "Riwayat kredit lancar (demo).",
        "disbursements": [], "disbursed_total": 0, "assigned_to": "sales@sipro.co.id",
        "created_by": "seed", "created_at": ts, "updated_at": ts})

    # ----------------------------- EPIC M1 seed: Portal user + demo documents -----------------------------
    await db.portal_users.insert_one({
        "id": new_id(), "org_id": ORG_ID, "customer_id": cust_id, "name": "Ibu Dewi Kartika",
        "phone": "+628121111111", "email": "dewi.kartika@example.com",
        "is_active": True, "created_at": ts, "last_login_at": None})

    # Two demo legal documents for the buyer's deal so the portal has content.
    def _doc(code, title, status, sigs):
        return {
            "id": new_id(), "org_id": ORG_ID, "template_id": None, "template_code": code,
            "doc_number": f"{code}/{ts[:4]}/0001", "title": title, "deal_id": demo_deal_id,
            "lead_id": lead1, "unit_id": first_unit_id, "assigned_to": "sales@sipro.co.id",
            "content": (f"{title}\n\nPembeli : Ibu Dewi Kartika\nUnit : A-01 (Tipe 45/90)\n"
                        f"Harga : Rp 850.000.000\nTanggal : {ts[:10]}\n\nPenjual : PT SIPRO Land\n"),
            "status": status, "signatures": sigs,
            "created_by": "seed", "created_at": ts, "updated_at": ts,
            "finalized_at": ts if status in ("finalized", "signed") else None,
            "first_signed_at": ts if status == "signed" else None,
        }
    await db.documents.insert_many([
        _doc("SPR", "Surat Pemesanan Rumah (SPR)", "signed",
             [{"role": "Pembeli", "name": "Ibu Dewi Kartika", "signed_at": ts},
              {"role": "Penjual", "name": "Fitri Finance", "signed_at": ts}]),
        _doc("PPJB", "Perjanjian Pengikatan Jual Beli (PPJB)", "finalized", []),
    ])

    # Sample complaints (resolved + open + an SLA-breached one) so the staff CS
    # dashboard (Phase 9) and the portal complaints list both have content.
    await db.complaints.insert_many([
        {"id": new_id(), "org_id": ORG_ID, "customer_id": cust_id, "customer_name": "Ibu Dewi Kartika",
         "deal_id": demo_deal_id, "unit_code": "A-01", "category": "konstruksi",
         "subject": "Permintaan update progres", "message": "Mohon info progres pembangunan terbaru.",
         "status": "resolved", "priority": "low", "assigned_to": "sales@sipro.co.id",
         "sla_due_at": ts, "resolved_at": ts,
         "responses": [{"by": "sales@sipro.co.id", "message": "Progres 38%, sesuai jadwal.",
                        "at": ts, "staff": True}],
         "created_at": due_in(hours=-72), "updated_at": ts},
        {"id": new_id(), "org_id": ORG_ID, "customer_id": cust_id, "customer_name": "Ibu Dewi Kartika",
         "deal_id": demo_deal_id, "unit_code": "A-01", "category": "pembayaran",
         "subject": "Konfirmasi pembayaran DP", "message": "Apakah pembayaran DP saya sudah diterima?",
         "status": "open", "priority": "medium", "assigned_to": "sales@sipro.co.id",
         "sla_due_at": due_in(hours=40), "responses": [],
         "created_at": due_in(hours=-6), "updated_at": due_in(hours=-6)},
        {"id": new_id(), "org_id": ORG_ID, "customer_id": cust_id, "customer_name": "Ibu Dewi Kartika",
         "deal_id": demo_deal_id, "unit_code": "A-01", "category": "konstruksi",
         "subject": "Keretakan dinding minor", "message": "Ada retak rambut di dinding kamar, mohon dicek.",
         "status": "in_progress", "priority": "high", "assigned_to": "sales@sipro.co.id",
         "sla_due_at": due_in(hours=-6),
         "responses": [{"by": "sales@sipro.co.id", "message": "Tim QC akan meninjau minggu ini.",
                        "at": due_in(hours=-30), "staff": True}],
         "created_at": due_in(hours=-54), "updated_at": due_in(hours=-30)},
    ])

    # Permits / legal-document tracker (EPIC 2.7): mix of approved / in-progress / overdue.
    permit_rows = [
        ("KRK", "Keterangan Rencana Kota", "Dinas Tata Ruang", "approved", due_in(days=-120), "KRK/2025/0102"),
        ("IMB", "Izin Mendirikan Bangunan (PBG)", "DPMPTSP", "approved", due_in(days=-30), "IMB/2026/0456"),
        ("PBG", "Persetujuan Bangunan Gedung", "DPMPTSP", "submitted", due_in(days=10), "PBG/2026/0789"),
        ("SLF", "Sertifikat Laik Fungsi", "Dinas PU", "not_started", due_in(days=90), None),
        ("AMDAL", "Dokumen Lingkungan (UKL-UPL)", "DLH Kabupaten", "in_progress", due_in(days=-5), None),
    ]
    for ptype, pname, authority, status, deadline, ref in permit_rows:
        await db.permits.insert_one({
            "id": new_id(), "org_id": ORG_ID, "project_id": project_id,
            "project_name": "Cluster Asri Blok A", "type": ptype, "name": pname,
            "authority": authority, "reference_no": ref, "status": status, "deadline": deadline,
            "reminder_days": 14,
            "submitted_at": ts if status in ("submitted", "approved") else None,
            "approved_at": ts if status == "approved" else None,
            "notes": None, "created_by": "seed", "created_at": ts, "updated_at": ts})

    # ----------------------------- Phase 12 seed: Procurement pillar -----------------------------
    year = ts[:4]
    # Fase 48B: penilaian 3-way pindah ke `procurement_extra.evaluate_bill` (menahan, bukan
    # sekadar menandai). Seed memakai fungsi yang sama agar data demo tidak pernah memakai
    # aturan lama yang sudah dihapus.
    from procurement_extra import evaluate_bill as _run_3way
    # Subcontractors
    sub1_id, sub2_id = new_id(), new_id()
    await db.subcontractors.insert_many([
        {"id": sub1_id, "org_id": ORG_ID, "code": "SUB-01", "name": "CV Bangun Jaya",
         "specialty": "struktur", "phone": "+628130000001", "email": "cs@bangunjaya.co.id",
         "npwp": "01.234.567.8-011.000", "address": "Bogor, Jawa Barat", "pic_name": "Bapak Slamet",
         "rating": 4.5, "is_active": True, "notes": None, "created_by": "seed",
         "created_at": ts, "updated_at": ts},
        {"id": sub2_id, "org_id": ORG_ID, "code": "SUB-02", "name": "PT Instalasi Prima",
         "specialty": "mep", "phone": "+628130000002", "email": "info@instalasiprima.co.id",
         "npwp": "02.345.678.9-011.000", "address": "Depok, Jawa Barat", "pic_name": "Ibu Rina",
         "rating": 4.2, "is_active": True, "notes": None, "created_by": "seed",
         "created_at": ts, "updated_at": ts},
    ])
    # SPK (work orders)
    spk1_id, spk2_id = new_id(), new_id()
    await db.spk.insert_many([
        {"id": spk1_id, "org_id": ORG_ID, "spk_number": f"SPK/{year}/0001",
         "subcontractor_id": sub1_id, "subcontractor_name": "CV Bangun Jaya",
         "project_id": project_id, "project_name": "Cluster Asri Blok A",
         "title": "Pekerjaan Struktur Blok A", "scope": "Kolom, balok, pelat lantai 1-2.",
         "contract_value": 300_000_000, "retention_pct": 5.0, "start_date": due_in(days=-40),
         "end_date": due_in(days=50), "status": "active", "progress_pct": 40, "notes": None,
         "created_by": "pm@sipro.co.id", "created_at": ts, "updated_at": ts},
        {"id": spk2_id, "org_id": ORG_ID, "spk_number": f"SPK/{year}/0002",
         "subcontractor_id": sub2_id, "subcontractor_name": "PT Instalasi Prima",
         "project_id": project_id, "project_name": "Cluster Asri Blok A",
         "title": "Instalasi MEP Blok A", "scope": "Instalasi listrik, plumbing, titik lampu.",
         "contract_value": 150_000_000, "retention_pct": 5.0, "start_date": due_in(days=10),
         "end_date": due_in(days=90), "status": "draft", "progress_pct": 0, "notes": None,
         "created_by": "pm@sipro.co.id", "created_at": ts, "updated_at": ts},
    ])
    # Progress Claim (Termin) + Change Order demo — EPIC 2.3 (modul terpisah agar seed ramping).
    await seed_subcon_claims(spk1_id, sub1_id, project_id, year, ts, due_in(days=21))
    await seed_inspections(project_id, ts)
    boq_rows = [
        ("PREP-01", "persiapan", "Pembersihan & pematokan lahan", "m2", 500, 50_000),
        ("STR-01", "struktur", "Beton K-300 kolom & balok", "m3", 120, 1_200_000),
        ("STR-02", "struktur", "Pembesian D13", "kg", 8000, 15_000),
        ("ARS-01", "arsitektur", "Pasangan bata & plesteran", "m2", 900, 120_000),
        ("MEP-01", "mep", "Instalasi listrik & titik lampu", "titik", 60, 350_000),
        ("FIN-01", "finishing", "Pengecatan dinding", "m2", 1200, 45_000),
    ]
    for code, cat, desc, uom, qty, price in boq_rows:
        await db.boq_items.insert_one({
            "id": new_id(), "org_id": ORG_ID, "project_id": project_id,
            "project_name": "Cluster Asri Blok A", "cost_code": code, "category": cat,
            "description": desc, "uom": uom, "quantity": float(qty), "unit_price": int(price),
            "amount": int(qty * price), "notes": None, "created_by": "pm@sipro.co.id",
            "created_at": ts, "updated_at": ts})
    await seed_material_requisitions(project_id, material_ids, ts)

    # Purchase Order 1 (material) — approved, fully received via GRN, matched bill.
    po1_id = new_id()
    smn, bsi = material_ids["SMN"], material_ids["BSI"]
    po1_items = [
        {"description": smn["name"], "material_id": smn["id"], "boq_item_id": None, "uom": smn["uom"],
         "qty": 200.0, "unit_price": 65_000, "amount": 13_000_000, "received_qty": 200.0},
        {"description": bsi["name"], "material_id": bsi["id"], "boq_item_id": None, "uom": bsi["uom"],
         "qty": 100.0, "unit_price": 120_000, "amount": 12_000_000, "received_qty": 100.0},
    ]
    await db.purchase_orders.insert_one({
        "id": po1_id, "org_id": ORG_ID, "po_number": f"PO/{year}/0001", "project_id": project_id,
        "project_name": "Cluster Asri Blok A", "po_type": "material", "vendor": "TB Sumber Bangunan",
        "subcontractor_id": None, "subcontractor_name": None, "spk_id": None, "items": po1_items,
        "subtotal": 25_000_000, "total": 25_000_000, "status": "received",
        "received_value": 25_000_000, "billed_value": 25_000_000, "high_value": False,
        "due_date": due_in(days=30), "note": "Material struktur tahap 1",
        "approved_by": "finance@sipro.co.id", "approved_at": ts,
        "created_by": "pm@sipro.co.id", "created_at": due_in(hours=-48), "updated_at": ts})
    # GRN for PO1 (full receipt) + material stock in
    await db.grns.insert_one({
        "id": new_id(), "org_id": ORG_ID, "grn_number": f"GRN/{year}/0001", "po_id": po1_id,
        "po_number": f"PO/{year}/0001", "project_id": project_id, "vendor": "TB Sumber Bangunan",
        "items": [
            {"po_item_index": 0, "description": smn["name"], "material_id": smn["id"], "uom": smn["uom"],
             "qty_received": 200.0, "unit_price": 65_000, "amount": 13_000_000},
            {"po_item_index": 1, "description": bsi["name"], "material_id": bsi["id"], "uom": bsi["uom"],
             "qty_received": 100.0, "unit_price": 120_000, "amount": 12_000_000}],
        "received_value": 25_000_000, "note": "Penerimaan penuh", "received_by": "site@sipro.co.id",
        "created_at": due_in(hours=-40)})
    for mkey, q in (("SMN", 200), ("BSI", 100)):
        await db.material_txns.insert_one({
            "id": new_id(), "org_id": ORG_ID, "project_id": project_id, "material_id": material_ids[mkey]["id"],
            "type": "in", "qty": q, "note": f"Penerimaan PO/{year}/0001", "ref": f"GRN/{year}/0001",
            "actor": "site@sipro.co.id", "created_at": due_in(hours=-40)})
    match1 = _run_3way({"total": 25_000_000, "received_value": 25_000_000, "billed_value": 0}, 25_000_000, 25_000_000)
    bill1 = await fe.create_ap_bill("TB Sumber Bangunan", project_id, 25_000_000, 0, due_in(days=30),
                                    f"Tagihan PO/{year}/0001", "pm@sipro.co.id", ORG_ID)
    await db.ap_invoices.update_one({"id": bill1["id"]}, {"$set": {
        "po_id": po1_id, "po_number": f"PO/{year}/0001", "grn_id": None, "match_status": "matched",
        "match_detail": match1, "requires_senior_approval": False, "updated_at": ts}})

    # Purchase Order 2 (subcon, SPK1) — approved; a bill WITHOUT goods receipt gets FLAGGED (3-way).
    po2_id = new_id()
    await db.purchase_orders.insert_one({
        "id": po2_id, "org_id": ORG_ID, "po_number": f"PO/{year}/0002", "project_id": project_id,
        "project_name": "Cluster Asri Blok A", "po_type": "subcon", "vendor": "CV Bangun Jaya",
        "subcontractor_id": sub1_id, "subcontractor_name": "CV Bangun Jaya", "spk_id": spk1_id,
        "items": [{"description": "Termin 1 pekerjaan struktur", "material_id": None, "boq_item_id": None,
                   "uom": "ls", "qty": 1.0, "unit_price": 150_000_000, "amount": 150_000_000, "received_qty": 0.0}],
        "subtotal": 150_000_000, "total": 150_000_000, "status": "approved",
        "received_value": 0, "billed_value": 80_000_000, "high_value": False,
        "due_date": due_in(days=30), "note": "Termin struktur (kait SPK/0001)",
        "approved_by": "owner@sipro.co.id", "approved_at": ts,
        "created_by": "pm@sipro.co.id", "created_at": due_in(hours=-20), "updated_at": ts})
    match2 = _run_3way({"total": 150_000_000, "received_value": 0, "billed_value": 0}, 80_000_000, 0)
    bill2 = await fe.create_ap_bill("CV Bangun Jaya", project_id, 80_000_000, 5, due_in(days=30),
                                    f"Termin 1 struktur (tanpa GRN) PO/{year}/0002", "pm@sipro.co.id", ORG_ID)
    await db.ap_invoices.update_one({"id": bill2["id"]}, {"$set": {
        "po_id": po2_id, "po_number": f"PO/{year}/0002", "grn_id": None, "subcontractor_id": sub1_id,
        "spk_id": spk1_id, "match_status": "flagged", "match_detail": match2,
        "requires_senior_approval": True, "updated_at": ts}})
    await db.tasks.insert_one({
        "id": new_id(), "org_id": ORG_ID, "title": f"Tinjau tagihan mencurigakan — PO/{year}/0002",
        "description": "; ".join(match2["reasons"]), "type": "review", "status": "open",
        "priority": "urgent", "related_entity_type": "ap_bill", "related_entity_id": bill2["id"],
        "assigned_to": "finance@sipro.co.id", "due_date": due_in(days=1), "sla_due_at": due_in(days=1),
        "sla_breached": False, "source_event": f"3way.flagged:{bill2['id']}", "auto_generated": True,
        "outcome": None, "created_by": "system", "created_at": ts, "updated_at": ts})

    # ----------------------------- Phase 13 seed: GL / Buku Besar -----------------------------
    # Approve + pay the matched material bill (PO/0001 fully received) -> realistic AP->GL chain.
    await fe.approve_ap_bill(bill1["id"], "finance@sipro.co.id", ORG_ID)
    await fe.pay_ap_bill(bill1["id"], 25_000_000, "Pelunasan material PO/0001", "finance@sipro.co.id", ORG_ID)
    # Chart of accounts + opening balances (posisi awal periode).
    await gl.ensure_coa(ORG_ID)
    await gl.post_journal(
        ORG_ID, "Saldo awal periode",
        [{"account_code": "1-1200", "debit": 2_000_000_000, "credit": 0},
         {"account_code": "1-1400", "debit": 300_000_000, "credit": 0},
         {"account_code": "1-1600", "debit": 700_000_000, "credit": 0},
         {"account_code": "3-1100", "debit": 0, "credit": 3_000_000_000}],
        source_type="opening", source_event="opening:seed", posted_by="seed", auto=False)
    # Phase 14: jurnal komisi demo (akrual approved + pembayaran paid) agar GL konsisten.
    await gl.post_journal(
        ORG_ID, "Akrual komisi — sales@sipro.co.id (A-02)",
        [{"account_code": "6-1100", "debit": 17_000_000, "credit": 0},
         {"account_code": "2-1600", "debit": 0, "credit": 17_000_000}],
        source_type="commission", source_id=comm_approved_id,
        source_event="seed:comm_accrual:A02", posted_by="seed", auto=False)
    await gl.post_journal(
        ORG_ID, "Akrual komisi — sales@sipro.co.id (A-03)",
        [{"account_code": "6-1100", "debit": 25_500_000, "credit": 0},
         {"account_code": "2-1600", "debit": 0, "credit": 25_500_000}],
        source_type="commission", source_id=comm_paid_id,
        source_event="seed:comm_accrual:A03", posted_by="seed", auto=False)
    await gl.post_journal(
        ORG_ID, "Pembayaran komisi sales (A-03)",
        [{"account_code": "2-1600", "debit": 25_500_000, "credit": 0},
         {"account_code": "1-1200", "debit": 0, "credit": 25_500_000}],
        source_type="commission", source_id=comm_paid_id,
        source_event="seed:comm_pay:A03", posted_by="seed", auto=False)
    # Activities on lead + welcome notifications
    await add_activity(entity_type="lead", entity_id=lead1, type="system",
                       body="Lead dibuat dari walk-in dan di-assign ke Andi Sales.", actor="system")
    await add_activity(entity_type="lead", entity_id=lead2, type="comment",
                       body="Sudah dihubungi, tertarik unit Tipe 45. Jadwalkan survey.",
                       actor="sales@sipro.co.id")
    for u in SEED_USERS:
        await create_notification(user_email=u["email"], title="Selamat datang di SIPRO",
                                  body="Buka 'Hari Saya' untuk melihat tugas & prioritas Anda.",
                                  type="info")

    # Dispatch outbox now so subledger events post to the GL immediately (idempotent).
    await dispatch_pending()
    await seed_tax_setoran(ORG_ID, ts)
    logger.info("Seed complete: org=%s users=%d", ORG_NAME, len(SEED_USERS))
    return True
