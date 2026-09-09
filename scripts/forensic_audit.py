"""Forensic audit SIPRO — SSOT, duplikasi, integritas referensial, orphan collection, cacat form.

Read-only. Jalankan: python scripts/forensic_audit.py
Output: temuan bertingkat [CRITICAL] / [HIGH] / [MED] / [LOW] / [OK].
"""
import os
import re
import sys
import pathlib
import collections
from pymongo import MongoClient
from dotenv import load_dotenv

ROOT = pathlib.Path("/app")
load_dotenv(ROOT / "backend/.env")
client = MongoClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

FINDINGS = []


def add(sev, area, msg):
    FINDINGS.append((sev, area, msg))
    print(f"  [{sev}] {msg}")


def head(t):
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


# --------------------------------------------------------------------------
# A. Inventaris koleksi: DB vs kode vs endpoint tulis
# --------------------------------------------------------------------------
BACKEND = ROOT / "backend"
PY_FILES = [p for p in BACKEND.rglob("*.py") if "test" not in p.name and "seed" not in p.name]
SEED_FILES = [p for p in BACKEND.rglob("seed*.py")]
ROUTER_FILES = sorted((BACKEND / "routers").glob("*.py"))

WRITE_OPS = ("insert_one", "insert_many", "update_one", "update_many", "delete_one",
             "delete_many", "replace_one", "find_one_and_update", "bulk_write")

# Koleksi turunan/sistem: MEMANG ditulis engine (bukan form user). Bukan temuan.
DERIVED_BY_DESIGN = {
    "activities": "jejak kolaborasi dibuat sistem saat aksi terjadi",
    "build_bulk_runs": ("jejak operasi massal jadwal (Fase 34) ditulis "
                        "build_bulk.run_create/run_shift; dibaca GET /build/bulk/runs "
                        "(router memanggil build_bulk.runs) — kosong sampai operasi "
                        "massal pertama dijalankan"),
    "build_calibrations": ("jejak kalibrasi template (Fase 37) ditulis "
                           "build_calibration.apply/rollback lewat POST "
                           "/build/calibration/apply & /{id}/rollback; dibaca GET "
                           "/build/calibration/history & /candidates (router memanggil "
                           "build_calibration.history/candidates) — kosong sampai "
                           "kalibrasi pertama diterapkan"),
    "audit_logs": "jejak audit ditulis rbac.audit_log; dibaca GET /admin/audit-logs",
    "ar_invoices": "jadwal tagihan dibuat finance_engine dari skema pembayaran",
    "commissions": "dihitung finance_engine dari skema komisi",
    "contract_liabilities": "pendapatan diterima di muka (otomatis dari penerimaan)",
    "conversion_events": "feedback konversi ke platform iklan (capi.py)",
    "counters": "penomoran dokumen atomik (internal, sequences.py)",
    "events": "outbox event bus (internal)",
    "faktur_pajak": "diterbitkan lewat POST /tax/faktur",
    "file_blobs": "isi biner file (internal storage abstraction)",
    "files": "metadata file dibuat saat upload",
    "journal_entries": "jurnal otomatis gl_engine + jurnal manual POST /gl/journals",
    "lead_capture_events": "dedup log webhook capture",
    # Fase 50B — buku penanda antrean perangkat. Ini catatan MEKANIS (bukan data bisnis):
    # satu baris per `client_ref` supaya kiriman lapangan yang diulang tidak menjadi data
    # kedua (absensi ganda = upah ganda). Ditulis `offline_intake.begin/commit/rollback` dari
    # endpoint absensi, buku harian, punch list, klaim garansi & BAST. Sengaja TIDAK punya
    # endpoint baca: yang dibaca manusia adalah dokumen hasilnya (absensi/klaim/BAST) dan
    # antrean di perangkat; membuka buku penanda hanya menambah permukaan tanpa pembaca.
    # Keunikannya dijaga index `uq_offline_intake_ref`; dibuktikan gate 40 (Q6a/Q6b/Q6c).
    "offline_intake": ("buku penanda idempotensi antrean perangkat (Fase 50B) — ditulis "
                       "offline_intake.begin/commit; kosong sampai ada kiriman ber-client_ref"),
    # Fase 51B — riwayat pengingat WhatsApp otomatis. Satu baris per pengingat yang PERNAH
    # diputuskan (terkirim / simulasi / dilewati beserta sebabnya). Ditulis
    # `wa_reminder_engine.run/_record` lewat POST /reminders/run dan cron tick; dibaca
    # GET /reminders (riwayat) serta GET /reminders/candidates (dedup). Kosong sampai
    # pengingat pertama dijalankan — itu keadaan sah, bukan kolam data mati.
    "wa_reminders": ("riwayat pengingat WhatsApp otomatis (Fase 51B) — ditulis "
                     "wa_reminder_engine.run; dibaca GET /reminders; kosong sampai "
                     "pengingat pertama dijalankan"),
    "material_txns": "mutasi stok dari transaksi/opname",
    "messages": "pesan WhatsApp masuk/keluar",
    "notifications": "notifikasi sistem",
    "payments_out": "pembayaran AP; dibaca GET /finance/ap/payments",
    "portal_otps": "OTP portal (sementara, dihapus setelah verifikasi)",
    "receipts": "penerimaan pembayaran dari POST /finance/ar/receipts",
    "revenue_recognitions": "pengakuan pendapatan (PSAK 72) saat serah terima",
    "broadcast_recipients": "penerima broadcast",
    "build_weekly_reports": ("laporan mingguan (Fase 32) dibangkitkan penjadwal setiap Senin "
                             "dari jadwal nyata; dibaca GET /build/reports/weekly — tidak "
                             "boleh bisa dikarang manual, itulah nilai buktinya"),
    "construction_logs": "log progres & QC (bukti perubahan), dibaca GET /construction/project/{id}/logs",
    "permission_settings": "matriks RBAC; dibaca GET /admin/permissions (lewat rbac.get_matrix)",
    "finance_configs": "konfigurasi pajak/penagihan; dibaca GET /finance/config/*",
    "orgs": "tenant; dikelola /admin/orgs",
    "build_policies": ("kebijakan bukti kerja; dibaca GET /build/policy & diubah "
                       "PUT /build/policy (router memanggil build_policy.get/set_policy)"),
    "build_submit_claims": ("kunci idempotensi antrean offline (Fase 35, internal): ditulis "
                            "build_actions._claim_ref sebelum item disentuh, dihapus saat "
                            "pengajuan ditolak, sisanya dibersihkan TTL 7 hari. Tidak berisi "
                            "data yang perlu dibaca pengguna — jejak audit pengajuannya ada "
                            "di build_item_submissions (GET /build/items/{id})"),
    "wa_webhook_events": ("payload MENTAH webhook Meta (Fase 96) ditulis webhooks_router saat "
                          "event masuk, TTL 30 hari, dipakai forensik/replay — tidak ada layar "
                          "pembaca; ringkasannya tampil di Dashboard Pengiriman (GET /wa/stats). "
                          "Kosong sampai webhook pertama (mode simulasi)"),
}


def collections_in(files, ops=None):
    """map collection -> set(file) yang memakai op tertentu (ops=None => semua op)."""
    out = collections.defaultdict(set)
    for f in files:
        src = f.read_text()
        for m in re.finditer(r"\bdb\.([a-z_][a-z_0-9]*)\.([a-z_]+)\(", src):
            coll, op = m.group(1), m.group(2)
            if ops and op not in ops:
                continue
            out[coll].add(f.name)
    return out


def _router_helper_modules():
    """Modul engine lokal yang DI-IMPORT router (satu tingkat).

    Dipakai untuk menjawab pertanyaan "apakah ada endpoint yang menampilkan koleksi ini?"
    secara jujur: sejak router dibatasi 800 baris, akses DB pindah ke modul engine
    (`masterplan.py`, `catalog.py`, `settings_store.py`, ...), jadi mencari `db.<coll>`
    HANYA di berkas router memberi jawaban yang salah.
    """
    local = {p.stem: p for p in BACKEND.glob("*.py")}
    found = {}
    for rf in ROUTER_FILES:
        # `^\s*` (bukan `^`): sebagian router meng-import modul engine DI DALAM fungsi
        # (mis. omnichannel_router memanggil `import wa_playbooks as wp` di dalam handler
        # untuk menghindari impor berputar). Tanpa toleransi indentasi, impor itu tak
        # terlihat dan koleksinya dilaporkan "tidak ada endpoint baca" secara salah.
        for mod in re.findall(r"^\s*(?:import|from)\s+([a-z_][a-z_0-9]*)",
                              rf.read_text(), re.M):
            if mod in local:
                found[mod] = local[mod]
    return sorted(found.values())


def audit_collections():
    head("A. INVENTARIS KOLEKSI — orphan, tidak bisa diinput, tidak terpakai")
    db_colls = set(db.list_collection_names())
    code_all = collections_in(PY_FILES)
    seed_all = collections_in(SEED_FILES)
    router_writes = collections_in(ROUTER_FILES, WRITE_OPS)
    engine_writes = collections_in([p for p in PY_FILES if p.parent == BACKEND], WRITE_OPS)
    # Koleksi yang dikelola user LEWAT helper (router memanggil fungsi engine, bukan db.<coll>)
    ENGINE_MANAGED = {
        "finance_configs": "PUT /finance/config/tax & /finance/config/collection -> finance_engine.set_config",
        # Fase 27 — router memanggil modul engine (bukan db.<coll> langsung), tetapi
        # SEMUA koleksi di bawah punya endpoint tulis nyata yang dipicu form pengguna.
        "cash_advances": "POST /petty-cash/advances (+approve/reject/cancel/disburse/settle) -> petty_cash.*",
        "fixed_assets": "POST /fixed-assets/assets & /assets/{id}/dispose -> fixed_assets.*",
        "asset_depreciations": "POST /fixed-assets/depreciation/run -> fixed_assets.run_depreciation",
        "loans": "POST /corp-financing/loans (+activate) -> loans.create_loan/activate_loan",
        "loan_payments": "POST /corp-financing/loans/{id}/pay -> loans.pay_installment",
        "agents": "POST & PUT /marketing/agents -> marketing_fee.create_agent/update_agent",
        "marketing_fees": "POST /marketing/fees (+approve/reject/pay) -> marketing_fee.*",
        # Fase 39 — fondasi data. Akses DB-nya ada di modul engine (masterplan.py,
        # catalog.py, doc_registry.py, settings_store.py) karena router harus tetap di
        # bawah batas 800 baris; endpoint tulisnya nyata & dipicu form pengguna:
        "clusters": "POST /masterplan/projects/{id}/clusters, PUT & DELETE /masterplan/clusters/{id} -> masterplan.*",
        "blocks": "POST /masterplan/clusters/{id}/blocks, PUT & DELETE /masterplan/blocks/{id} -> masterplan.*",
        "unit_types": "POST & PUT /catalog/unit-types -> catalog.create_unit_type/update_unit_type",
        "addon_items": "POST & PUT /catalog/addons -> catalog.create_addon/update_addon",
        "price_components": "POST & PUT /catalog/price-components -> catalog.create_component/update_component",
        "payment_scheme_templates": "POST & PUT /catalog/payment-schemes -> catalog.*",
        "doc_requirements": "POST & PUT /doc/requirements -> doc_registry.create_requirement/update_requirement",
        "doc_submissions": ("POST /doc/submissions (unggah dari checklist dokumen di layar "
                            "lead & pelanggan) + POST /doc/submissions/{id}/verify|reject "
                            "-> doc_registry.*"),
        "settings": "PUT /settings/{key}, POST /settings/bulk & /settings/{key}/reset -> settings_store.set_value/reset",
        # Fase 33/35/36 — endpoint tulis nyata yang aksesnya lewat modul engine.
        "spk_scope_items": ("POST /subcon/spk/{sid}/scope & DELETE /subcon/spk/{sid}/scope/{id} "
                            "-> opname.add_scope/remove_scope (lingkup SPK dipilih manusia)"),
        "build_item_submissions": ("POST /build/items/{id}/submit (Papan Mandor) -> "
                                   "build_actions.submit_item; dibaca GET /build/items/{id}"),
        "build_work_calendars": ("PUT /build/calendar/settings & POST /build/calendar/holidays "
                                 "(+/holidays/{day}/restore) -> build_calendar.* "
                                 "(master hari kerja & libur diatur admin)"),
        # Fase 77 — koleksi harga dinamis: pricing_router → pricing_engine `db[COLLECTIONS[kind]]`
        # (satu CRUD untuk discount-schemes/promos/coupons), jadi `db.<coll>.` tidak pernah tertulis.
        "discount_schemes": "POST/PUT/DELETE /pricing/discount-schemes -> pricing_engine.* (db[COLLECTIONS['discount_scheme']])",
        "promos": "POST/PUT/DELETE /pricing/promos -> pricing_engine.* (db[COLLECTIONS['promo']])",
        "coupons": "POST/PUT/DELETE /pricing/coupons -> pricing_engine.* (db[COLLECTIONS['coupon']])",
        # 2026-09 — tahapan progres proyek & tahapan survey (Pusat Konfigurasi), akses lewat modul engine.
        "phase_templates": ("POST/PUT/DELETE /construction/phase-templates & POST /construction/project/{id}/phases/apply "
                            "-> phase_templates.* (db[pt.COLL]); dibaca GET /construction/phase-templates"),
        "survey_stage_configs": "PUT /survey-stages -> survey_stages.save_config (db[COLL]); dibaca GET /survey-stages",
    }
    for c, why in ENGINE_MANAGED.items():
        router_writes.setdefault(c, set()).add(f"(via helper) {why}")
    READ_OPS = ("find", "find_one", "count_documents", "aggregate", "distinct")
    router_reads = collections_in(ROUTER_FILES, READ_OPS)
    for c in ("discount_schemes", "promos", "coupons", "phase_templates", "survey_stage_configs"):
        router_reads.setdefault(c, set()).add("(via helper) GET /pricing/{kind} & /pricing/options -> pricing_engine")
    # Fase 39b — atribusi BACA lewat modul engine yang di-import router.
    #
    # Dulu audit ini hanya melihat `db.<coll>.find(...)` DI DALAM berkas router, sehingga
    # koleksi yang dibaca lewat modul engine (pola wajib sejak router menyentuh batas 800
    # baris) dilaporkan "TIDAK ADA ENDPOINT BACA" walau datanya jelas tampil di layar.
    # Akibatnya 10 temuan palsu — dua di antaranya HIGH (`settings`, `doc_submissions`) —
    # menutupi temuan yang sungguhan. Sekarang: bila sebuah router meng-import modul lokal,
    # operasi baca di modul itu dihitung sebagai "ada endpoint baca", dan modulnya dicatat
    # supaya jejaknya bisa diperiksa manusia.
    for c, mods in collections_in(_router_helper_modules(), READ_OPS).items():
        router_reads.setdefault(c, set()).update(f"(via helper) {m}" for m in mods)

    known = set(code_all) | set(seed_all) | db_colls
    print(f"\nDB={len(db_colls)} koleksi | dirujuk kode={len(code_all)} | dirujuk seed={len(seed_all)}\n")

    for c in sorted(known):
        cnt = db[c].count_documents({}) if c in db_colls else None
        has_api_write = c in router_writes
        has_engine_write = c in engine_writes
        has_api_read = c in router_reads
        in_seed = c in seed_all
        flags = []
        if cnt is None:
            flags.append("BELUM ADA DI DB")
        elif cnt == 0:
            flags.append("KOSONG")
        if not has_api_write and not has_engine_write:
            flags.append("TIDAK BISA DIINPUT (tak ada endpoint/engine tulis)")
        elif not has_api_write and has_engine_write:
            flags.append("hanya ditulis engine/otomatis")
        if not has_api_read:
            flags.append("TIDAK ADA ENDPOINT BACA")
        if flags:
            if c in DERIVED_BY_DESIGN and "TIDAK BISA DIINPUT (tak ada endpoint/engine tulis)" not in flags:
                add("OK", "collections",
                    f"{c:26s} docs={str(cnt):>5} | by design: {DERIVED_BY_DESIGN[c]}")
                continue
            sev = "CRITICAL" if "TIDAK BISA DIINPUT (tak ada endpoint/engine tulis)" in flags else (
                "HIGH" if ("KOSONG" in flags and "TIDAK ADA ENDPOINT BACA" in flags) else "MED")
            add(sev, "collections",
                f"{c:26s} docs={str(cnt):>5} seed={'Y' if in_seed else 'N'} | " + "; ".join(flags))
    if not any(f[1] == "collections" for f in FINDINGS):
        add("OK", "collections", "semua koleksi punya jalur baca+tulis dan terisi")


# --------------------------------------------------------------------------
# B. Duplikasi koleksi (dua tempat menyimpan konsep sama)
# --------------------------------------------------------------------------
# Pasangan koleksi yang MIRIP tapi sudah diverifikasi punya peran berbeda (bukan SSOT ganda).
VERIFIED_DISTINCT = {
    ("construction_logs", "site_diaries"):
        "construction_logs = log perubahan progres/QC (bukti audit per aksi); "
        "site_diaries = buku harian lapangan harian (cuaca, tenaga kerja, kendala)",
    ("faktur_pajak", "tax_records"):
        "faktur_pajak = dokumen Faktur Pajak keluaran bernomor; "
        "tax_records = catatan kewajiban PPN/PPh/BPHTB per deal",
    ("revenue_recognitions", "contract_liabilities"):
        "revenue_recognitions = pendapatan diakui saat serah terima; "
        "contract_liabilities = uang muka yang belum jadi pendapatan",
    ("payments_out", "ap_invoices"):
        "payments_out = kas keluar per pembayaran; ap_invoices = tagihan (header + retensi)",
    ("receipts", "ar_invoices"):
        "receipts = penerimaan kas; ar_invoices = jadwal tagihan pembeli",
    ("file_blobs", "files"):
        "file_blobs = isi biner (fallback storage); files = metadata + kepemilikan",
}
OVERLAP_CANDIDATES = [(a, b, why) for (a, b), why in VERIFIED_DISTINCT.items()]


def audit_overlap():
    head("B. DUPLIKASI / SSOT GANDA ANTAR KOLEKSI")
    db_colls = set(db.list_collection_names())
    for a, b, label in OVERLAP_CANDIDATES:
        ca = db[a].count_documents({}) if a in db_colls else 0
        cb = db[b].count_documents({}) if b in db_colls else 0
        refs_a = len(collections_in(PY_FILES).get(a, set()))
        refs_b = len(collections_in(PY_FILES).get(b, set()))
        has_write = bool(collections_in(PY_FILES, WRITE_OPS).get(a))
        if refs_a and not has_write:
            add("HIGH", "overlap", f"'{a}' dirujuk {refs_a} file tapi TIDAK PUNYA jalur tulis -> koleksi mati")
        else:
            add("OK", "overlap", f"'{a}'({ca}) vs '{b}'({cb}) — peran berbeda: {label}")


# --------------------------------------------------------------------------
# C. Integritas referensial (FK menggantung)
# --------------------------------------------------------------------------
FK_MAP = {
    "project_id": ("projects", "id"),
    "unit_id": ("units", "id"),
    "lead_id": ("leads", "id"),
    "deal_id": ("deals", "id"),
    "customer_id": ("customers", "id"),
    "spk_id": ("spk", "id"),
    "subcontractor_id": ("subcontractors", "id"),
    "phase_id": ("construction_phases", "id"),
    "po_id": ("purchase_orders", "id"),
    "boq_item_id": ("boq_items", "id"),
    "material_id": ("materials", "id"),
    "conversation_id": ("conversations", "id"),
    "broadcast_id": ("broadcasts", "id"),
    "appointment_id": ("appointments", "id"),
    "bill_id": ("ap_invoices", "id"),
    "ap_bill_id": ("ap_invoices", "id"),
    "org_id": ("orgs", "id"),
}
USER_FIELDS = ("assigned_to", "created_by", "approved_by", "requested_by", "issued_by",
               "posted_by", "uploaded_by", "opened_by", "received_by", "finalized_by",
               "rejected_by", "user_email", "owner", "actor")


def audit_referential():
    head("C. INTEGRITAS REFERENSIAL (FK menggantung)")
    db_colls = sorted(db.list_collection_names())
    ids_cache = {}

    def parent_ids(coll, field):
        key = (coll, field)
        if key not in ids_cache:
            ids_cache[key] = {d[field] for d in db[coll].find({}, {field: 1, "_id": 0}) if d.get(field)}
        return ids_cache[key]

    user_emails = {u["email"] for u in db.users.find({}, {"email": 1, "_id": 0})}
    bad = 0
    for c in db_colls:
        for doc in db[c].find({}, {"_id": 0}):
            for fld, (pc, pf) in FK_MAP.items():
                v = doc.get(fld)
                if not v or pc not in db_colls:
                    continue
                if v not in parent_ids(pc, pf):
                    add("CRITICAL", "referential",
                        f"{c}.{doc.get('id', '?')} -> {fld}={v} tidak ada di {pc}")
                    bad += 1
            for uf in USER_FIELDS:
                v = doc.get(uf)
                if isinstance(v, str) and "@" in v and v not in user_emails:
                    add("HIGH", "referential", f"{c}.{doc.get('id', '?')} -> {uf}={v} bukan user terdaftar")
                    bad += 1
    if not bad:
        add("OK", "referential", "tidak ada FK menggantung di seluruh koleksi")


# --------------------------------------------------------------------------
# D. Denormalisasi basi (SSOT conflict nyata)
# --------------------------------------------------------------------------
DENORM = [
    # (koleksi anak, field kopi, field fk, koleksi master, field master)
    ("units", None, None, None, None),  # placeholder dihapus di loop
]
DENORM = [
    ("deals", "unit_code", "unit_id", "units", "code"),
    ("ar_invoices", "unit_code", "unit_id", "units", "code"),
    ("commissions", "unit_code", "unit_id", "units", "code"),
    ("complaints", "unit_code", "unit_id", "units", "code"),
    ("ar_invoices", "lead_name", "lead_id", "leads", "name"),
    ("appointments", "lead_name", "lead_id", "leads", "name"),
    ("surveys", "lead_name", "lead_id", "leads", "name"),
    ("boq_items", "project_name", "project_id", "projects", "name"),
    ("permits", "project_name", "project_id", "projects", "name"),
    ("punch_items", "project_name", "project_id", "projects", "name"),
    ("site_diaries", "project_name", "project_id", "projects", "name"),
    ("spk", "project_name", "project_id", "projects", "name"),
    ("progress_claims", "project_name", "project_id", "projects", "name"),
    ("change_orders", "project_name", "project_id", "projects", "name"),
    ("purchase_orders", "project_name", "project_id", "projects", "name"),
    ("material_requisitions", "project_name", "project_id", "projects", "name"),
    ("inspections", "project_name", "project_id", "projects", "name"),
    ("spk", "subcontractor_name", "subcontractor_id", "subcontractors", "name"),
    ("progress_claims", "subcontractor_name", "subcontractor_id", "subcontractors", "name"),
    ("change_orders", "subcontractor_name", "subcontractor_id", "subcontractors", "name"),
    ("purchase_orders", "subcontractor_name", "subcontractor_id", "subcontractors", "name"),
    ("progress_claims", "spk_number", "spk_id", "spk", "spk_number"),
    ("change_orders", "spk_number", "spk_id", "spk", "spk_number"),
    ("grns", "po_number", "po_id", "purchase_orders", "po_number"),
    ("material_requisitions", "phase_name", "phase_id", "construction_phases", "name"),
    ("commissions", "scheme_name", "scheme_id", "commission_schemes", "name"),
    ("ar_invoices", "scheme_name", "scheme_id", "payment_schemes", "name"),
    ("complaints", "customer_name", "customer_id", "customers", "name"),
]


def audit_denorm():
    head("D. DENORMALISASI BASI — copy nama/kode vs master (SSOT conflict)")
    db_colls = set(db.list_collection_names())
    stale = 0
    pairs = 0
    for child, copyf, fk, master, mf in DENORM:
        if child not in db_colls or master not in db_colls:
            continue
        mmap = {d["id"]: d.get(mf) for d in db[master].find({}, {"id": 1, mf: 1, "_id": 0})}
        for doc in db[child].find({fk: {"$ne": None}}, {"_id": 0}):
            pairs += 1
            want = mmap.get(doc.get(fk))
            got = doc.get(copyf)
            if want is not None and got is not None and want != got:
                add("HIGH", "denorm",
                    f"{child}.{doc.get('id')}: {copyf}='{got}' TIDAK SAMA dengan {master}.{mf}='{want}'")
                stale += 1
    print(f"\n  ({pairs} pasangan denormalisasi diperiksa)")
    if not stale:
        add("OK", "denorm", "tidak ada copy nama/kode yang basi SAAT INI (risiko tetap ada jika master di-rename)")

    # Deteksi endpoint rename master TANPA cascade
    head("D2. RENAME MASTER TANPA CASCADE (bom waktu SSOT)")
    masters = {
        "projects": ("projects_router.py", "project_name"),
        "subcontractors": ("subcon_router.py", "subcontractor_name"),
        "units": ("deals_router.py", "unit_code"),
        "commission_schemes": ("finance_config_router.py", "scheme_name"),
        "payment_schemes": ("finance_config_router.py", "scheme_name"),
        "construction_phases": ("construction_router.py", "phase_name"),
        "leads": ("leads_router.py", "lead_name"),
        "customers": ("customers_router.py", "customer_name"),
    }
    # Field sumber yang memang tidak bisa diubah lewat endpoint mana pun -> tidak butuh cascade.
    IMMUTABLE_SOURCE = {"units": "code (unit code tidak dapat diubah, hanya tipe/harga)"}
    for master, (rf, copyf) in masters.items():
        if master in IMMUTABLE_SOURCE:
            add("OK", "denorm-cascade", f"{master}: {IMMUTABLE_SOURCE[master]} -> cascade tidak diperlukan")
            continue
        f = BACKEND / "routers" / rf
        if not f.exists():
            continue
        src = f.read_text()
        # PUT route bisa memakai path alias (mis. commission_schemes -> /config/commission-schemes)
        alias = master.replace("_", "-")
        has_update = bool(re.search(rf"db\.{master}\.update_one", src)) or \
            bool(re.search(rf"db\[coll\]\.update_one", src) and re.search(rf"@router\.put\([^)]*{alias}", src))
        # cascade bisa langsung (update_many) ATAU lewat helper SSOT denorm.cascade_master_change
        cascades = ("cascade_master_change" in src) or \
            bool(re.search(rf"update_many\(\s*\{{[^}}]*\}},\s*\{{\"\$set\":\s*\{{\"{copyf}\"", src))
        if has_update and not cascades:
            add("HIGH", "denorm-cascade",
                f"{master}: ada endpoint update/rename tapi TIDAK ada cascade ke '{copyf}' di koleksi anak")
        elif not has_update:
            add("MED", "denorm-cascade",
                f"{master}: TIDAK ADA endpoint update (master data tak bisa dikoreksi setelah dibuat)")


# --------------------------------------------------------------------------
# E. Duplikasi baris (natural key ganda)
# --------------------------------------------------------------------------
NATURAL_KEYS = {
    "users": ["email"], "orgs": ["id"], "projects": ["org_id", "code"],
    "units": ["org_id", "project_id", "code"], "accounts": ["org_id", "code"],
    "materials": ["org_id", "project_id", "code"], "subcontractors": ["org_id", "code"],
    "wa_templates": ["org_id", "code"], "document_templates": ["org_id", "code"],
    "inspection_templates": ["org_id", "code"], "channel_accounts": ["org_id", "code"],
    "spk": ["org_id", "spk_number"], "purchase_orders": ["org_id", "po_number"],
    "grns": ["org_id", "grn_number"], "progress_claims": ["org_id", "claim_number"],
    "change_orders": ["org_id", "co_number"], "inspections": ["org_id", "inspection_number"],
    "material_requisitions": ["org_id", "req_number"], "journal_entries": ["org_id", "entry_no"],
    "documents": ["org_id", "doc_number"], "leads": ["org_id", "phone"],
    "customers": ["org_id", "nik"], "portal_users": ["org_id", "phone"],
    "finance_configs": ["org_id", "key"], "boq_items": ["org_id", "project_id", "cost_code"],
    "construction_phases": ["org_id", "project_id", "name"],
    "commission_schemes": ["org_id", "name"], "payment_schemes": ["org_id", "name"],
}


def audit_duplicates():
    head("E. DUPLIKASI BARIS (natural key ganda) + index unik")
    db_colls = set(db.list_collection_names())
    dups = 0
    for coll, keys in NATURAL_KEYS.items():
        if coll not in db_colls:
            continue
        group = {"$group": {"_id": {k: f"${k}" for k in keys}, "n": {"$sum": 1},
                            "ids": {"$push": "$id"}}}
        for r in db[coll].aggregate([group, {"$match": {"n": {"$gt": 1}}}]):
            if all(v is None for v in r["_id"].values()):
                continue
            add("HIGH", "duplicate", f"{coll}: {r['_id']} muncul {r['n']}x -> ids={r['ids'][:4]}")
            dups += 1
        # index unik?
        idx = db[coll].index_information()
        has_unique = any(v.get("unique") and [f[0] for f in v["key"]] == keys for v in idx.values())
        if not has_unique:
            add("MED", "duplicate-index",
                f"{coll}: natural key {keys} TIDAK dilindungi unique index -> duplikat bisa masuk")
    # id duplikat global
    for coll in sorted(db_colls):
        agg = list(db[coll].aggregate([{"$group": {"_id": "$id", "n": {"$sum": 1}}},
                                       {"$match": {"n": {"$gt": 1}, "_id": {"$ne": None}}},
                                       {"$limit": 3}]))
        for r in agg:
            add("CRITICAL", "duplicate", f"{coll}: id='{r['_id']}' duplikat {r['n']}x")
            dups += 1
    if not dups:
        add("OK", "duplicate", "tidak ada baris duplikat pada natural key yang diperiksa")


# --------------------------------------------------------------------------
# F. Master data: bisa dikelola dari UI?
# --------------------------------------------------------------------------
MASTER_COLLS = ["accounts", "payment_schemes", "commission_schemes", "wa_templates",
                "document_templates", "inspection_templates", "channel_accounts",
                "finance_configs", "subcontractors", "materials", "construction_phases",
                "projects", "units", "automation_rules", "users", "orgs", "boq_items"]


def audit_master_ui():
    head("F. MASTER DATA — CRUD backend vs form di frontend")
    FE = ROOT / "frontend/src"
    fe_src = "\n".join(p.read_text() for p in FE.rglob("*.js"))
    router_writes = collections_in(ROUTER_FILES, WRITE_OPS)
    routes = []
    for f in ROUTER_FILES:
        src = f.read_text()
        pm = re.search(r'prefix\s*=\s*["\']([^"\']+)', src)
        prefix = pm.group(1) if pm else ""
        for mm in re.finditer(r'@router\.(get|post|put|delete)\(\s*["\']([^"\']*)["\']', src):
            routes.append((f.name, mm.group(1).upper(), prefix + mm.group(2)))
    SOFT_DELETE_OK = {
        "users": "dinonaktifkan lewat PUT is_active",
        "orgs": "status tenant lewat PUT",
        "subcontractors": "is_active lewat PUT",
        "projects": "status 'archived' lewat PUT",
        "accounts": "is_active lewat PUT (hard delete dilarang: jejak jurnal)",
        "materials": "is_active lewat PUT (ditolak bila ada transaksi stok)",
        "boq_items": "punya DELETE",
        "automation_rules": "punya DELETE",
        "finance_configs": "konfigurasi tunggal per org (tidak dihapus)",
    }
    ENGINE_MANAGED_UI = {"finance_configs"}
    for coll in MASTER_COLLS:
        files = router_writes.get(coll, set())
        if coll in ENGINE_MANAGED_UI:
            add("OK", "master-crud", f"{coll:22s} -> dikelola lewat endpoint config (helper engine)")
            continue
        methods = {m for (fn, m, p) in routes if fn in files}
        can_create = "POST" in methods
        can_update = "PUT" in methods
        can_delete = "DELETE" in methods
        missing = []
        if not can_create:
            missing.append("tanpa CREATE")
        if not can_update:
            missing.append("tanpa UPDATE")
        if not can_delete and coll not in SOFT_DELETE_OK:
            missing.append("tanpa DELETE/arsip")
        # apakah FE punya form create untuk koleksi ini? cari pola api.post ke prefix terkait
        if missing:
            sev = "HIGH" if "tanpa CREATE" in missing else "MED"
            add(sev, "master-crud", f"{coll:22s} -> " + ", ".join(missing) +
                f" (router: {sorted(files) or 'tidak ada'})")
    print()


# --------------------------------------------------------------------------
# G. Cacat form frontend: free-text padahal harus dropdown dari tabel
# --------------------------------------------------------------------------
REF_HINTS = {
    "project_id": "projects", "unit_id": "units", "lead_id": "leads", "deal_id": "deals",
    "customer_id": "customers", "spk_id": "spk", "subcontractor_id": "subcontractors",
    "phase_id": "construction_phases", "po_id": "purchase_orders", "material_id": "materials",
    "boq_item_id": "boq_items", "template_id": "templates", "template_code": "templates",
    "scheme_id": "schemes", "assigned_to": "users", "vendor": "subcontractors/vendors",
    "account_code": "accounts", "uom": "enum satuan",
    "category": "enum kategori", "severity": "enum", "priority": "enum", "status": "enum",
    "type": "enum", "channel": "enum", "method": "enum", "basis": "enum", "trigger": "enum",
    "authority": "master instansi", "specialty": "enum bidang",
}


def audit_forms():
    head("G. CACAT FORM FRONTEND — input bebas padahal harus dropdown/relasi")
    print("  catatan: 'cost_code' RAB memang input bebas (BoQ adalah master kode biaya,\n"
          "  keunikannya dijaga unique index per proyek).")
    FE = ROOT / "frontend/src"
    issues = 0
    for page in sorted(list((FE / "pages").rglob("*.js")) + list((FE / "components").rglob("*.js"))):
        src = page.read_text()
        # kumpulkan field yang dirender sebagai <Input .../> lewat binding form state
        inputs = set()
        for m in re.finditer(r"<Input\b[^>]*?(?:value|placeholder)=\{?[^>]*?\}?[^>]*?>", src, re.S):
            frag = m.group(0)
            for mm in re.finditer(r"(?:\[|\.)([a-z_][a-z_0-9]*)(?:\]|\b)\s*(?:\}|\)|,)", frag):
                inputs.add(mm.group(1))
            for mm in re.finditer(r'name=["\']([a-z_][a-z_0-9]*)["\']', frag):
                inputs.add(mm.group(1))
        selects = set(re.findall(r"<(?:Select|select)\b", src))
        has_select = bool(selects)
        for fld in sorted(inputs):
            if fld in REF_HINTS:
                # cek apakah field yang sama juga punya Select di file
                sel_ctx = re.search(rf"<Select[^>]*?(?:value|onValueChange)[^>]*?{fld}\b", src, re.S)
                if not sel_ctx:
                    add("HIGH", "form",
                        f"{page.relative_to(FE)}: field '{fld}' pakai <Input> teks bebas — "
                        f"seharusnya dropdown dari {REF_HINTS[fld]}")
                    issues += 1
        if re.search(r"<Input\b", src) and not has_select and re.search(r"_id\b", src):
            pass
    if not issues:
        add("OK", "form", "tidak ditemukan input bebas untuk field relasi/enum")


# --------------------------------------------------------------------------
# H. BAHAN UJI GATE/POC YANG BOCOR KE LAYAR MANUSIA
# --------------------------------------------------------------------------
# Aturan repo sejak Fase 46: "bahan uji gate/POC dibuat & DIBUANG otomatis; bila terlihat di
# layar berarti ada run yang mati di tengah." Aturan itu tidak pernah dijaga oleh apa pun —
# jadi `verify_partner.py` bisa bertahun-tahun meninggalkan lead "Gate 42 Lead Mitra",
# mengunci rumah nyata `A-03` menjadi `booked` oleh transaksi hantu, dan menerbitkan fee
# Rp 17 juta yang ikut terhitung di analitik mitra — semuanya HIJAU di 40 gate.
#
# Pemeriksaan ini menutup lubang itu: data berpenanda uji yang masih ada di koleksi yang
# DIPAJANG ke pengguna = temuan HIGH, dan rujukan menggantung unit → deal yang sudah tidak
# ada = CRITICAL (rumah tidak bisa dijual karena dipegang transaksi yang tidak eksis).
TEST_NAME_RE = re.compile(r"^\s*(gate\s*\d*|uji|poc|test|dummy|coba)\b", re.I)
TEST_CODE_RE = re.compile(r"^(GATE|POC|G39|G40|G41|G42)[-\d]", re.I)
# Koleksi yang benar-benar dilihat manusia di layar harian.
HUMAN_FACING = {
    "leads": ("name",), "customers": ("name",), "agents": ("name",),
    "units": ("code",), "projects": ("name",), "vendors": ("name",),
    "subcontractors": ("name",), "workers": ("name",), "materials": ("name",),
}
TEST_TAGS = ("gate42", "gate47", "gate48", "gate49", "gate50", "poc_tag")


def audit_test_material():
    head("H. BAHAN UJI GATE/POC YANG BOCOR KE LAYAR")
    bocor = 0
    db_colls = set(db.list_collection_names())
    for coll, fields in HUMAN_FACING.items():
        if coll not in db_colls:
            continue
        for doc in db[coll].find({}, {"_id": 0, "id": 1, **{f: 1 for f in fields}}):
            teks = " ".join(str(doc.get(f) or "") for f in fields)
            bertanda = any(doc.get(t) for t in TEST_TAGS)
            if bertanda or TEST_NAME_RE.match(teks) or TEST_CODE_RE.match(teks.strip()):
                add("HIGH", "test-material",
                    f"{coll}: '{teks.strip()}' tampak bahan uji tetapi masih ada di data "
                    f"yang dipajang ke pengguna (id={doc.get('id')})")
                bocor += 1
    # Rujukan menggantung: rumah dipegang transaksi yang sudah dibuang.
    if {"units", "deals"} <= db_colls:
        hidup = {d["id"] for d in db.deals.find({}, {"_id": 0, "id": 1})}
        for u in db.units.find({}, {"_id": 0, "code": 1, "reserved_by_deal": 1,
                                    "booked_by_deal": 1, "sold_by_deal": 1}):
            for k in ("reserved_by_deal", "booked_by_deal", "sold_by_deal"):
                if u.get(k) and u[k] not in hidup:
                    add("CRITICAL", "test-material",
                        f"units '{u.get('code')}': {k} menunjuk deal {u[k]} yang TIDAK ADA — "
                        "rumah terkunci oleh transaksi hantu (sisa run gate/POC yang mati)")
                    bocor += 1
    if not bocor:
        add("OK", "test-material",
            "tidak ada bahan uji gate/POC yang tertinggal di koleksi yang dilihat pengguna")


def main():
    audit_collections()
    audit_overlap()
    audit_referential()
    audit_denorm()
    audit_duplicates()
    audit_master_ui()
    audit_forms()
    audit_test_material()

    head("RINGKASAN")
    by = collections.Counter(f[0] for f in FINDINGS)
    for sev in ("CRITICAL", "HIGH", "MED", "LOW", "OK"):
        if by.get(sev):
            print(f"  {sev:9s}: {by[sev]}")
    crit = by.get("CRITICAL", 0) + by.get("HIGH", 0)
    print(f"\n  Total temuan perlu tindakan (CRITICAL+HIGH): {crit}")
    print("-" * 50)
    client.close()
    if crit:
        print(f"FORENSIC AUDIT FAILED: {crit} temuan CRITICAL/HIGH")
        return 1
    print("FORENSIC AUDIT PASSED: SSOT konsisten, tidak ada duplikasi/FK yatim/cacat form")
    return 0


if __name__ == "__main__":
    sys.exit(main())
