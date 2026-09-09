#!/usr/bin/env python3
"""_dump_vocab.py — bantu pemetaan SSOT: cetak nilai distinct field enum di DB."""
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

TARGETS = {
    "appointments": ["status", "type"],
    "activities": ["type"],
    "messages": ["direction"],
    "automation_rules": ["trigger_event"],
    "surveys": ["result"],
    "tax_records": ["status", "type"],
    "inspections": ["status"],
    "organizations": ["status"],
    "documents": ["status", "template_code"],
    "deals": ["status", "legal_stage"],
    "ar_invoices": ["status"],
    "ap_invoices": ["status"],
    "commissions": ["status", "trigger", "basis"],
    "units": ["status", "payment_status"],
    "requisitions": ["status"],
    "progress_claims": ["status"],
    "purchase_orders": ["status", "type"],
    "grns": ["status"],
    "spks": ["status"],
    "punch_items": ["status"],
    "material_txns": ["type"],
    "financing_apps": ["status", "slik_status", "bank_name"],
    "permits": ["status", "type"],
    "complaints": ["status", "category"],
    "tasks": ["status", "type", "priority"],
    "leads": ["stage", "source", "score_band"],
    "change_orders": ["status"],
    "broadcasts": ["status"],
    "conversations": ["channel", "status"],
    "notifications": ["type"],
    "site_plan_layouts": ["status"],
    "accounting_periods": ["status"],
    "receipts": ["method"],
    "boq_items": ["category", "uom"],
    "qc_records": ["result"],
}

for coll, fields in TARGETS.items():
    names = db.list_collection_names()
    if coll not in names:
        continue
    for f in fields:
        try:
            vals = db[coll].distinct(f)
        except Exception as e:  # noqa: BLE001
            vals = [f"ERR {e}"]
        vals = [v for v in vals if v is not None]
        if vals:
            print(f"{coll}.{f}: {sorted(map(str, vals))}")
