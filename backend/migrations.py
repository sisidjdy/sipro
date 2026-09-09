"""Migrasi idempoten hasil audit forensik. Dijalankan saat startup (lifespan).

1. KANONIKALISASI ENUM — menyatukan vocabulary yang tercecer:
   'Struktur'/'structural'/'struktur' -> 'struktur'; 'MEP'/'mep' -> 'mep';
   'Cerah berawan' -> 'cerah_berawan'; 'meta_lead_ads' -> 'meta_ads'; dst.
2. BACKFILL COUNTER — mengisi koleksi `counters` dari nomor dokumen yang sudah ada,
   supaya penomoran atomik yang baru tidak menabrak nomor lama.
3. RESYNC DENORMALISASI — memperbaiki field kopi yang basi (mis. commissions.unit_code).

Semua langkah aman dijalankan berulang kali.
"""
import logging
import re

import capi
import reference as ref
import sequences as seq
from core_utils import normalize_phone_e164, now_iso
from db import db, ORG_ID
from denorm import resync_all

logger = logging.getLogger("sipro.migrations")

# (koleksi, field, grup reference)
ENUM_FIELDS = [
    ("boq_items", "category", "work_category"),
    ("punch_items", "category", "work_category"),
    ("inspection_templates", "category", "inspection_category"),
    ("inspections", "category", "inspection_category"),
    ("subcontractors", "specialty", "subcon_specialty"),
    ("site_diaries", "weather", "weather"),
    ("leads", "source", "lead_source"),
    ("leads", "stage", "lead_stage"),
    ("leads", "score_band", "score_band"),
    ("channel_accounts", "channel", "channel_type"),
    ("conversion_events", "source", "lead_source"),
    ("lead_capture_events", "source", "lead_source"),
    ("complaints", "category", "complaint_category"),
    ("receipts", "method", "payment_method"),
    ("appointments", "type", "appointment_type"),
    ("materials", "uom", "uom"),
    ("boq_items", "uom", "uom"),
    ("tax_records", "type", "tax_type"),
    ("purchase_orders", "po_type", "po_type"),
    ("wa_templates", "category", "wa_template_category"),
    ("punch_items", "severity", "punch_severity"),
    ("tasks", "priority", "priority"),
    ("complaints", "priority", "priority"),
    ("permits", "type", "permit_type"),
    ("permits", "status", "permit_status"),
    # Ditambahkan setelah temuan sisa: status fase konstruksi memakai "pending"
    # (bukan "not_started") sehingga UI menampilkan nilai mentah tanpa label Indonesia.
    ("construction_phases", "status", "construction_status"),
    ("units", "status", "unit_status"),
    # Fase 28b — orientasi kavling sebelumnya teks bebas ("Utara"/"utara"/"UTARA")
    # sehingga tidak bisa difilter/diagregasi; kini terkontrol SSOT.
    ("units", "orientation", "unit_orientation"),
    ("projects", "status", "project_status"),
    ("units", "type", "unit_type"),
]

# (koleksi, field nomor, scope counter, lebar digit). Format: PREFIX/TAHUN/URUT
NUMBER_FIELDS = [
    ("journal_entries", "entry_no", "journal", 5),
    ("inspections", "inspection_number", "inspection", 4),
    ("spk", "spk_number", "spk", 4),
    ("purchase_orders", "po_number", "po", 4),
    ("grns", "grn_number", "grn", 4),
    ("progress_claims", "claim_number", "claim", 4),
    ("change_orders", "co_number", "change_order", 4),
    ("material_requisitions", "req_number", "requisition", 4),
    ("receipts", "receipt_no", "receipt", 4),
]

NUM_RE = re.compile(r"^(?P<prefix>[^/]+)/(?P<year>\d{4})/(?P<n>\d+)$")


async def canonicalize_enums() -> dict:
    """Samakan nilai enum lama ke bentuk kanonik reference.GROUPS."""
    existing = set(await db.list_collection_names())
    changed = {}
    for coll, field, group in ENUM_FIELDS:
        if coll not in existing:
            continue
        for raw in await db[coll].distinct(field):
            if raw is None or not isinstance(raw, str):
                continue
            canon = ref.canonicalize(group, raw)
            if canon and canon != raw:
                res = await db[coll].update_many({field: raw}, {"$set": {field: canon}})
                if res.modified_count:
                    changed[f"{coll}.{field}: '{raw}'->'{canon}'"] = res.modified_count
    return changed


async def backfill_counters() -> dict:
    """Set counters >= nomor tertinggi yang sudah ada (per org + tahun)."""
    existing = set(await db.list_collection_names())
    out = {}
    for coll, field, scope, _w in NUMBER_FIELDS:
        if coll not in existing:
            continue
        rows = await db[coll].find({field: {"$ne": None}},
                                   {"_id": 0, "org_id": 1, field: 1}).to_list(20000)
        highest = {}
        for r in rows:
            m = NUM_RE.match(str(r.get(field) or ""))
            if not m:
                continue
            key = (r.get("org_id"), m.group("year"))
            highest[key] = max(highest.get(key, 0), int(m.group("n")))
        for (org, year), n in highest.items():
            await seq.ensure_at_least(scope, org, n, year)
            out[f"{scope}:{org}:{year}"] = n
    # dokumen legal (deals.ppjb.number / deals.ajb.number)
    if "deals" in existing:
        for kind in ("ppjb", "ajb"):
            rows = await db.deals.find({f"{kind}.number": {"$ne": None}},
                                       {"_id": 0, "org_id": 1, kind: 1}).to_list(20000)
            highest = {}
            for r in rows:
                m = NUM_RE.match(str((r.get(kind) or {}).get("number") or ""))
                if not m:
                    continue
                key = (r.get("org_id"), m.group("year"))
                highest[key] = max(highest.get(key, 0), int(m.group("n")))
            for (org, year), n in highest.items():
                await seq.ensure_at_least(f"legal:{kind}", org, n, year)
                out[f"legal:{kind}:{org}:{year}"] = n
    # dokumen per template (documents.doc_number = TEMPLATE/TAHUN/URUT)
    if "documents" in existing:
        rows = await db.documents.find({"doc_number": {"$ne": None}},
                                       {"_id": 0, "org_id": 1, "doc_number": 1,
                                        "template_code": 1}).to_list(20000)
        highest = {}
        for r in rows:
            m = NUM_RE.match(str(r.get("doc_number") or ""))
            if not m:
                continue
            key = (r.get("org_id"), r.get("template_code") or m.group("prefix"), m.group("year"))
            highest[key] = max(highest.get(key, 0), int(m.group("n")))
        for (org, tpl, year), n in highest.items():
            await seq.ensure_at_least(f"document:{tpl}", org, n, year)
            out[f"document:{tpl}:{org}:{year}"] = n
    # faktur pajak (kode.000-yy.00000001)
    if "faktur_pajak" in existing:
        rows = await db.faktur_pajak.find({"number": {"$ne": None}},
                                          {"_id": 0, "org_id": 1, "number": 1}).to_list(20000)
        highest = {}
        for r in rows:
            s = str(r.get("number") or "")
            tail = s.rsplit(".", 1)[-1]
            if tail.isdigit():
                key = r.get("org_id")
                highest[key] = max(highest.get(key, 0), int(tail))
        for org, n in highest.items():
            await seq.ensure_at_least("faktur", org, n)
            out[f"faktur:{org}"] = n
    return out


PHONE_FIELDS = [("leads", "phone"), ("customers", "phone"), ("portal_users", "phone"),
                ("conversations", "contact_phone"), ("broadcast_recipients", "phone"),
                ("users", "phone"), ("vendors", "phone")]
E164_ID_RE = re.compile(r"^\+62\d{8,13}$")


async def phone_health(org: str = None) -> dict:
    """Pratinjau (tanpa mengubah): nomor yang belum E.164 per koleksi + yang akan bentrok."""
    existing = set(await db.list_collection_names())
    out = []
    for coll, field in PHONE_FIELDS:
        if coll not in existing:
            continue
        q = {field: {"$type": "string", "$not": {"$regex": r"^\+62\d{8,13}$"}}}
        if org:
            q["org_id"] = org
        rows = await db[coll].find(q, {"_id": 0, "id": 1, "org_id": 1, field: 1, "name": 1,
                                       "contact_name": 1}).to_list(5000)
        fixable, unfixable, clashes = 0, [], []
        for r in rows:
            raw = r.get(field)
            if not raw:
                continue
            label = r.get("name") or r.get("contact_name")
            norm = normalize_phone_e164(raw)
            if not norm or norm == raw or not E164_ID_RE.match(norm):
                unfixable.append({"id": r.get("id"), "name": label, "phone": raw})
                continue
            other = await db[coll].find_one({"org_id": r.get("org_id"), field: norm,
                                             "id": {"$ne": r.get("id")}},
                                            {"_id": 0, "id": 1, "name": 1, "contact_name": 1})
            if other:
                clashes.append({"id": r.get("id"), "name": label, "phone": raw, "normalized": norm,
                                "clash_id": other.get("id"),
                                "clash_name": other.get("name") or other.get("contact_name")})
            else:
                fixable += 1
        out.append({"collection": coll, "field": field, "pending": fixable, "duplicate": len(clashes),
                    "invalid": len(unfixable), "invalid_samples": unfixable[:20],
                    "duplicate_samples": clashes[:20]})
    return {"rows": out, "total_pending": sum(r["pending"] for r in out),
            "total_duplicate": sum(r["duplicate"] for r in out),
            "total_invalid": sum(r["invalid"] for r in out)}


async def normalize_phones() -> dict:
    """Samakan format nomor telepon ke E.164 (+62...).

    Penting karena dedup lead & index unik memakai field ini: '08123', '628123' dan
    '+62 812-3' sebelumnya dianggap tiga nomor berbeda. Baris yang setelah normalisasi
    menjadi duplikat TIDAK diubah (dilaporkan lewat /api/master/data-health).
    """
    existing = set(await db.list_collection_names())
    out = {}
    for coll, field in PHONE_FIELDS:
        if coll not in existing:
            continue
        changed = skipped = 0
        rows = await db[coll].find({field: {"$type": "string"}},
                                   {"_id": 0, "id": 1, "org_id": 1, field: 1}).to_list(20000)
        for r in rows:
            raw = r.get(field)
            norm = normalize_phone_e164(raw)
            if not norm or norm == raw or not E164_ID_RE.match(norm):
                continue
            clash = await db[coll].find_one({"org_id": r.get("org_id"), field: norm,
                                             "id": {"$ne": r.get("id")}}, {"_id": 1})
            if clash:
                skipped += 1
                continue
            await db[coll].update_one({"id": r.get("id")}, {"$set": {field: norm}})
            changed += 1
        if changed or skipped:
            out[f"{coll}.{field}"] = {"normalized": changed, "skipped_duplicate": skipped}
    return out


async def sync_permission_matrix() -> list:
    """Tambahkan resource RBAC BARU ke matriks yang tersimpan di DB (idempoten).

    Masalah nyata yang diperbaiki: `permission_settings.rbac_matrix` adalah SSOT
    yang bisa diubah admin, dan `rbac.can()` memakainya alih-alih DEFAULT_PERMISSIONS.
    Akibatnya setiap resource baru dari rilis berikutnya (mis. Fase 27: `petty_cash`,
    `fixed_assets`, `loans`, `marketing_fee`) tidak pernah muncul di matriks database
    lama → seluruh peran non-owner mendapat 403 walau kode sudah mengizinkan.

    Hanya resource yang BELUM ADA yang ditambahkan; kustomisasi admin atas resource
    yang sudah ada tidak pernah ditimpa.
    """
    from rbac import DEFAULT_PERMISSIONS
    doc = await db.permission_settings.find_one({"key": "rbac_matrix"}, {"_id": 0})
    if not doc or not doc.get("matrix"):
        return []
    matrix = dict(doc["matrix"])
    added = [r for r in DEFAULT_PERMISSIONS if r not in matrix]
    if not added:
        return []
    for r in added:
        matrix[r] = DEFAULT_PERMISSIONS[r]
    await db.permission_settings.update_one(
        {"key": "rbac_matrix"},
        {"$set": {"matrix": matrix, "updated_at": now_iso(),
                  "updated_by": "migration:sync_permission_matrix"}})
    return added


async def migrate_workhub_tasks() -> dict:
    """Fase 29 — rapikan koleksi `tasks` warisan.

    1. Status `completed` (di luar SSOT `task_status`) → `done`.
    2. Tugas tanpa `division` diberi divisi dari penerimanya, supaya muncul di papan
       divisi yang benar (dulu semua task tidak bertuan sehingga supervisor tak melihatnya).
    3. Field baru siklus kerja (`review`, `proof`, `proof_kind`, `verify_mode`) diisi
       nilai aman untuk data lama.
    """
    import reference_p29 as p29
    out = {}
    res = await db.tasks.update_many({"status": "completed"},
                                     {"$set": {"status": "done", "review": "approved"}})
    if res.modified_count:
        out["status_done"] = res.modified_count
    res = await db.tasks.update_many(
        {"$or": [{"review": {"$exists": False}}, {"proof": {"$exists": False}}]},
        {"$set": {"review": "none", "proof": [], "proof_kind": "none", "verify_mode": "none"}})
    if res.modified_count:
        out["workflow_fields"] = res.modified_count
    users = await db.users.find({}, {"_id": 0, "email": 1, "role": 1, "division": 1}).to_list(500)
    div_of = {u["email"]: (u.get("division") or p29.ROLE_DIVISION.get(u.get("role")))
              for u in users}
    tagged = 0
    for email, div in div_of.items():
        if not div:
            continue
        res = await db.tasks.update_many(
            {"assigned_to": email, "division": {"$in": [None, ""]}}, {"$set": {"division": div}})
        tagged += res.modified_count
    if tagged:
        out["division_tagged"] = tagged
    return out


async def honest_capi_status() -> dict:
    """Fase 43 — baris event konversi mode SIMULASI tidak boleh berstatus 'Terkirim'.

    Sebelum fase ini setiap baris `conversion_events` ditulis `status="sent"` walau tidak ada
    satu pun paket yang keluar (kredensial platform belum ada). Layar audit CAPI karena itu
    menampilkan "Terkirim" untuk event yang tidak pernah dikirim ke mana pun \u2014 tepat jenis
    angka yang membuat orang berhenti percaya pada laporan. Idempoten.
    """
    if "conversion_events" not in set(await db.list_collection_names()):
        return {}
    res = await db.conversion_events.update_many(
        {"transport": "simulation", "status": "sent"}, {"$set": {
            "status": "simulated",
            "message": ("Mode simulasi: event dicatat lengkap dan siap dikirim begitu "
                        "kredensial platform diisi.")}})
    return {"conversion_events.status sent->simulated": res.modified_count} \
        if res.modified_count else {}


async def capi_event_identity() -> dict:
    """Fase 44 — baris `conversion_events` warisan dilengkapi `event_id` + `user_data` hash.

    Kenapa migrasi, bukan hanya perbaikan seed: basis data yang SUDAH berjalan (termasuk
    demo yang dipakai orang) menyimpan baris event dari sebelum CAPI V2. Baris tanpa
    `event_id` punya dua akibat nyata:

      1. **Tidak bisa di-dedup.** Meta/Google membuang event kembar berdasarkan `event_id`.
         Baris tanpa ID akan dihitung sebagai konversi BARU setiap kali dikirim ulang —
         ROAS di layar naik tanpa ada penjualan baru.
      2. **Tidak bisa dikirim** saat kredensial dinyalakan tanpa menyusun ulang payload,
         karena `user_data` (hash telepon/email) juga tidak ada.

    `event_id` dihitung dengan fungsi yang SAMA seperti jalur runtime
    (`capi.event_id_for`), jadi peristiwa bisnis yang sama tidak akan pernah punya dua ID.
    Idempoten: hanya menyentuh baris yang field-nya kosong.
    """
    if "conversion_events" not in set(await db.list_collection_names()):
        return {}
    rows = await db.conversion_events.find(
        {"$or": [{"event_id": None}, {"event_id": {"$exists": False}}]},
        {"_id": 0, "id": 1, "org_id": 1, "event_name": 1, "lead_id": 1, "deal_id": 1,
         "user_data": 1}).to_list(20000)
    fixed, hashed, collision = 0, 0, 0
    for row in rows:
        event_id = capi.event_id_for(org_id=row.get("org_id") or ORG_ID,
                                     event_name=row.get("event_name") or "Lead",
                                     lead_id=row.get("lead_id"), deal_id=row.get("deal_id"))
        # Bila peristiwa yang sama SUDAH punya baris ber-`event_id` (mis. runtime menulisnya
        # setelah baris warisan), baris warisan itu adalah duplikat: index unik akan menolak
        # ID yang sama. Barisnya dihapus, bukan dipaksa masuk — menyimpan dua baris untuk
        # satu peristiwa berarti laporan konversi menghitungnya dua kali.
        twin = await db.conversion_events.find_one(
            {"org_id": row.get("org_id") or ORG_ID, "event_id": event_id},
            {"_id": 0, "id": 1})
        if twin and twin.get("id") != row.get("id"):
            await db.conversion_events.delete_one({"id": row["id"]})
            collision += 1
            continue
        patch = {"event_id": event_id}
        if not (row.get("user_data") or {}):
            lead = await db.leads.find_one({"id": row.get("lead_id")},
                                           {"_id": 0, "phone": 1, "email": 1}) or {}
            ud = capi.user_data_for(lead)
            if ud:
                patch["user_data"] = ud
                hashed += 1
        await db.conversion_events.update_one({"id": row["id"]}, {"$set": patch})
        fixed += 1
    out = {}
    if fixed:
        out["conversion_events.event_id terisi"] = fixed
    if hashed:
        out["conversion_events.user_data di-hash"] = hashed
    if collision:
        out["conversion_events duplikat warisan dibuang"] = collision
    return out


async def reminder_recipient_identity() -> dict:
    """Fase 51B — pindahkan id LEAD yang salah tersimpan di `wa_reminders.customer_id`.

    Cacat aslinya: pencari penerima memakai lead sebagai cadangan bila rumah belum punya
    pelanggan, tetapi id-nya ditulis ke `customer_id`. Akibat nyatanya bukan kosmetik:

      1. Setiap sambungan `wa_reminders.customer_id → customers` diam-diam tidak menemukan
         apa pun, jadi riwayat pengingat tidak bisa dijejaki ke pemiliknya.
      2. Audit forensik melaporkannya sebagai **FK yatim (CRITICAL)** — dan itu benar:
         id itu memang tidak ada di `customers`.

    Migrasi ini memindahkan id ke `lead_id`, mengisi `recipient_type`, dan hanya menyentuh
    baris yang memang salah (idempoten). Baris yang id-nya tidak ada di leads MAUPUN
    customers dibiarkan apa adanya tetapi ditandai `recipient_type=None` — kita tidak
    mengarang pemilik untuk data yang sumbernya sudah hilang.
    """
    if "wa_reminders" not in set(await db.list_collection_names()):
        return {}
    rows = await db.wa_reminders.find(
        {"customer_id": {"$ne": None}},
        {"_id": 0, "id": 1, "org_id": 1, "customer_id": 1,
         "recipient_type": 1}).to_list(20000)
    ke_lead, ditandai, tak_dikenal = 0, 0, 0
    for row in rows:
        cid = row["customer_id"]
        if await db.customers.count_documents({"id": cid}, limit=1):
            if not row.get("recipient_type"):
                await db.wa_reminders.update_one(
                    {"id": row["id"]},
                    {"$set": {"recipient_type": "customer",
                              "recipient_type_label": ref.label_of("reminder_recipient",
                                                                   "customer")}})
                ditandai += 1
            continue
        if await db.leads.count_documents({"id": cid}, limit=1):
            await db.wa_reminders.update_one(
                {"id": row["id"]},
                {"$set": {"lead_id": cid, "customer_id": None, "recipient_type": "lead",
                          "recipient_type_label": ref.label_of("reminder_recipient", "lead")}})
            ke_lead += 1
            continue
        tak_dikenal += 1
    out = {}
    if ke_lead:
        out["wa_reminders id lead dipindah dari customer_id"] = ke_lead
    if ditandai:
        out["wa_reminders recipient_type diisi"] = ditandai
    if tak_dikenal:
        out["wa_reminders penerima tidak dikenal (dibiarkan, perlu ditinjau)"] = tak_dikenal
    return out


async def receipt_numbers() -> dict:
    """Beri NOMOR pada kwitansi warisan yang lahir tanpa nomor.

    Cacat aslinya: `finance_engine` membuat baris `receipts` tanpa `receipt_no` sama sekali.
    Selama kwitansi hanya dibaca staf di layar hal itu lolos, tetapi Fase 51C membuat PEMBELI
    bisa mengunduh PDF-nya — dan dokumen itu memakai UUID sebagai "nomor kwitansi". Kwitansi
    tanpa nomor urut bukan bukti yang bisa diaudit (dan tidak bisa dirujuk saat sengketa).

    Nomor diberikan URUT TANGGAL supaya urutan nomor mengikuti urutan kejadian, memakai
    counter yang sama dengan jalur runtime (`sequences`) sehingga tidak akan bertabrakan
    dengan kwitansi baru. Idempoten: hanya baris tanpa nomor yang disentuh.
    """
    if "receipts" not in set(await db.list_collection_names()):
        return {}
    rows = await db.receipts.find(
        {"$or": [{"receipt_no": None}, {"receipt_no": {"$exists": False}}]},
        {"_id": 0, "id": 1, "org_id": 1, "created_at": 1}).to_list(20000)
    if not rows:
        return {}
    rows.sort(key=lambda r: str(r.get("created_at") or ""))
    diberi = 0
    for row in rows:
        org = row.get("org_id") or ORG_ID
        tahun = str(row.get("created_at") or "")[:4] or None
        nomor = await seq.next_number("receipt", org, prefix="KWT", year=tahun)
        await db.receipts.update_one({"id": row["id"]}, {"$set": {"receipt_no": nomor}})
        diberi += 1
    return {"receipts.receipt_no diberi nomor": diberi}


async def run_migrations() -> dict:
    """Semua migrasi (idempoten). Dipanggil di lifespan setelah ensure_indexes."""
    enums = await canonicalize_enums()
    phones = await normalize_phones()
    counters = await backfill_counters()
    denorm = await resync_all()
    perms = await sync_permission_matrix()
    workhub = await migrate_workhub_tasks()
    capi_status = await honest_capi_status()
    capi_identity = await capi_event_identity()
    reminder_ident = await reminder_recipient_identity()
    receipt_nos = await receipt_numbers()
    if receipt_nos:
        logger.info("Migrasi nomor kwitansi (Fase 51C): %s", receipt_nos)
    if reminder_ident:
        logger.info("Migrasi identitas penerima pengingat (Fase 51B): %s", reminder_ident)
    if capi_identity:
        logger.info("Migrasi identitas event CAPI (Fase 44): %s", capi_identity)
    if capi_status:
        logger.info("Migrasi status CAPI (Fase 43): %s", capi_status)
    if enums:
        logger.info("Migrasi enum: %s", enums)
    if denorm:
        logger.info("Migrasi denormalisasi (field kopi basi diperbaiki): %s", denorm)
    if counters:
        logger.info("Counter nomor dokumen di-backfill: %s entri", len(counters))
    if phones:
        logger.info("Migrasi nomor telepon (E.164): %s", phones)
    if perms:
        logger.info("Resource RBAC baru ditambahkan ke matriks tersimpan: %s", perms)
    if workhub:
        logger.info("Migrasi Work Hub (Fase 29): %s", workhub)
    return {"enums": enums, "phones": phones, "counters": counters, "denorm": denorm,
            "permissions": perms, "workhub": workhub, "capi_status": capi_status}
