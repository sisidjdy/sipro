"""Hapus massal data OPERASIONAL per organisasi (konfigurasi & master sistem dipertahankan).

Tiga kelompok yang bisa dipilih: transaksi, proyek & konstruksi, mitra & rekening. Sesudah
dihapus, bendera `demo_seed_disabled` disimpan agar seed demo tidak dibuat ulang saat restart.
"""
import logging
import re

from db import db
from core_utils import now_iso

logger = logging.getLogger("sipro.data_mgmt.purge")

FLAG_KEY = "demo_seed_disabled"

GROUPS = {
    "transaksi": {
        "label": "Transaksi & operasional",
        "help": "Lead, pembeli, deal, kontrak, AR/AP, jurnal, kas, komisi, pajak, tugas, notifikasi, WA, dokumen, izin, anggaran.",
        "collections": [
            "leads", "customers", "deals", "contracts", "contract_liabilities", "quotations",
            "ar_invoices", "receipts", "ap_invoices", "payments_out", "journal_entries",
            "cash_vouchers", "cash_transfers", "cash_advances", "commissions", "cancellations",
            "payment_intakes", "financing_apps", "revenue_recognitions", "accounting_periods",
            "gl_year_closings", "fixed_assets", "asset_depreciations", "loans", "loan_payments",
            "marketing_fees", "partner_attribution_conflicts", "tax_records", "faktur_pajak",
            "withholding_docs", "bank_statements", "bank_transactions", "budget_items",
            "budget_manual_entries", "project_targets", "tasks", "activities", "notifications",
            "events", "appointments", "surveys", "conversations", "messages", "broadcasts",
            "broadcast_recipients", "complaints", "documents", "doc_shares", "doc_submissions",
            "wa_contacts", "wa_doc_shares", "wa_optouts", "wa_outbox", "wa_reminders",
            "wa_webhook_events", "campaigns", "ad_spend", "lead_capture_events",
            "conversion_events", "portal_users", "portal_otps", "offline_intake",
            "unit_handovers", "warranty_claims", "warning_letters", "metric_snapshots",
            "permits", "counters", "files", "file_blobs",
        ],
    },
    "proyek": {
        "label": "Proyek, unit & konstruksi",
        "help": "Proyek, cluster/blok, unit & tipe unit, site plan, jadwal & progres bangun, RAB/BOQ, SPK, termin, PO/GRN, material, inspeksi, tenaga kerja.",
        "collections": [
            "projects", "clusters", "blocks", "units", "unit_types", "site_plans", "rab_templates",
            "construction_phases", "construction_logs", "build_items", "build_schedules",
            "build_item_submissions", "build_submit_claims", "build_bulk_runs",
            "build_weekly_reports", "build_calibrations", "boq_items", "spk", "spk_scope_items",
            "spk_attachments", "progress_claims", "change_orders", "subcon_advances",
            "subcon_deductions", "subcon_retentions", "purchase_orders", "grns", "grn_returns",
            "material_requisitions", "material_transfers", "material_txns", "materials",
            "inspections", "punch_items", "site_diaries", "labor_attendance", "labor_payrolls",
            "workers", "vendor_assessments",
        ],
    },
    "mitra": {
        "label": "Mitra, vendor & rekening",
        "help": "Vendor & daftar harga, subkontraktor, agen/mitra, rekening bank & kas (beserta sub-akun GL-nya). Rekening default kosong dibuat ulang otomatis.",
        "collections": ["vendors", "vendor_prices", "subcontractors", "agents", "bank_accounts"],
    },
}

# Konfigurasi/master yang TIDAK PERNAH disentuh (informasi untuk pemakai).
KEEP = [
    "users", "orgs", "permission_settings", "settings", "accounts", "finance_configs",
    "payment_schemes", "commission_schemes", "discount_schemes", "allin_schemes",
    "kpr_disbursement_schemes", "cost_components", "price_components", "addon_items",
    "doc_requirements", "document_templates", "wa_templates", "wa_playbooks",
    "automation_rules", "channel_accounts", "jobdesk_templates", "inspection_templates",
    "build_templates", "build_policies", "build_work_calendars", "partner_fee_rules",
    "promos", "coupons", "notification_prefs", "migration_runs", "data_backups", "app_flags",
    "audit_logs",
]


def _filter(coll: str, org: str) -> dict:
    if coll == "file_blobs":
        return {"path": {"$regex": f"/{re.escape(org)}/"}}
    return {"org_id": org}


async def preview(org: str) -> dict:
    existing = set(await db.list_collection_names())
    out = {}
    for key, g in GROUPS.items():
        rows, total = [], 0
        for coll in g["collections"]:
            n = await db[coll].count_documents(_filter(coll, org)) if coll in existing else 0
            total += n
            if n:
                rows.append({"collection": coll, "count": n})
        out[key] = {"label": g["label"], "help": g["help"], "total": total, "rows": rows}
    flag = await db.app_flags.find_one({"key": FLAG_KEY, "org_id": org}, {"_id": 0})
    return {"groups": out, "keep": KEEP, "demo_seed_disabled": bool(flag and flag.get("value"))}


async def purge(org: str, groups: list, actor: str) -> dict:
    bad = [g for g in groups if g not in GROUPS]
    if bad or not groups:
        raise ValueError("Kelompok data tidak dikenal atau kosong.")
    existing = set(await db.list_collection_names())
    report, total = {}, 0
    for key in groups:
        for coll in GROUPS[key]["collections"]:
            if coll not in existing:
                continue
            n = (await db[coll].delete_many(_filter(coll, org))).deleted_count
            if n:
                report[coll] = n
                total += n
    if "mitra" in groups:
        n = (await db.accounts.delete_many({"org_id": org, "cash_account_id": {"$exists": True, "$ne": None}})).deleted_count
        if n:
            report["accounts (sub-akun rekening)"] = n
            total += n
    if "proyek" in groups or "transaksi" in groups:
        await db.units.update_many({"org_id": org}, {"$set": {
            "status": "available", "reserved_by_deal": None, "booked_by_deal": None,
            "payment_status": "none", "updated_at": now_iso()}})
    await db.app_flags.update_one({"key": FLAG_KEY, "org_id": org}, {"$set": {
        "key": FLAG_KEY, "org_id": org, "value": True, "updated_by": actor, "updated_at": now_iso()}},
        upsert=True)
    logger.warning("PURGE %s oleh %s (org %s): %s dokumen dari %s koleksi", groups, actor, org, total, len(report))
    return {"groups": groups, "deleted": total, "collections": report, "demo_seed_disabled": True}


async def demo_seed_allowed(org: str) -> bool:
    flag = await db.app_flags.find_one({"key": FLAG_KEY, "org_id": org}, {"_id": 0, "value": 1})
    return not (flag and flag.get("value"))
