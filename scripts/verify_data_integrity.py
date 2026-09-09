#!/usr/bin/env python3
"""verify_data_integrity.py — SIPRO post-seed integrity gate (adopsi kn/KN3).

Menangkap kelas bug relasional/tipe yang lolos dari gate lain:
  1. org_id hilang di koleksi tenant (bocor multi-tenant)
  2. seed gap (koleksi inti yang dibaca app tapi KOSONG)
  3. integritas referensial (assigned_to->user, related_entity->entity, project_id->project)
  4. invarian tipe (uang IDR integer, tanggal ISO-8601)
  5. email user unik
Exit !=0 bila ada ERROR.
"""
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from pymongo import MongoClient
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

errors, warns = [], []


def err(m):
    errors.append(m)
    print(f"  [ERROR] {m}")


def warn(m):
    warns.append(m)
    print(f"  [WARN] {m}")


def ok(m):
    print(f"  [OK] {m}")


# Koleksi tenant yang WAJIB ber-org_id bila terisi.
SCOPED = ["users", "tasks", "leads", "projects", "units", "activities",
          "notifications", "audit_logs", "events", "deals", "reservations",
          "subcontractors", "spk", "boq_items", "purchase_orders", "grns",
          "accounts", "journal_entries", "appointments", "surveys", "commissions",
          "tax_records", "faktur_pajak", "progress_claims", "change_orders",
          "inspections", "inspection_templates", "material_requisitions",
          "build_templates", "build_schedules", "build_items"]
# Koleksi inti yang harus terisi setelah seed.
SEED_EXPECTED = ["orgs", "users", "permission_settings", "tasks", "leads",
                 "projects", "units", "notifications"]


def check_org_id():
    print("\nCHECK 1 — org_id di semua koleksi tenant")
    for c in SCOPED:
        n = db[c].count_documents({})
        if n == 0:
            continue
        missing = db[c].count_documents({"org_id": {"$exists": False}})
        err(f"{c}: {missing}/{n} dokumen tanpa org_id") if missing else ok(f"{c}: {n} dok, semua ber-org_id")


def check_seed_gap():
    print("\nCHECK 2 — seed gap (koleksi inti terisi)")
    for c in SEED_EXPECTED:
        n = db[c].count_documents({})
        err(f"koleksi inti '{c}' KOSONG setelah seed") if n == 0 else ok(f"{c}: {n}")


def check_referential():
    print("\nCHECK 3 — integritas referensial")
    emails = {u["email"] for u in db.users.find({}, {"email": 1})}
    ref = {
        "lead": {x["id"] for x in db.leads.find({}, {"id": 1})},
        "project": {x["id"] for x in db.projects.find({}, {"id": 1})},
        "unit": {x["id"] for x in db.units.find({}, {"id": 1})},
    }
    bad = [t["id"] for t in db.tasks.find({"assigned_to": {"$ne": None}}, {"id": 1, "assigned_to": 1})
           if t["assigned_to"] not in emails]
    err(f"tasks.assigned_to bukan user valid: {len(bad)}") if bad else ok("tasks.assigned_to -> user valid")

    bad = 0
    for t in db.tasks.find({"related_entity_type": {"$ne": None}}, {"related_entity_type": 1, "related_entity_id": 1}):
        et, eid = t.get("related_entity_type"), t.get("related_entity_id")
        if et in ref and eid not in ref[et]:
            bad += 1
    err(f"tasks.related_entity_id menggantung: {bad}") if bad else ok("tasks.related_entity -> entity valid")

    bad = [l["id"] for l in db.leads.find({"assigned_to": {"$ne": None}}, {"id": 1, "assigned_to": 1})
           if l["assigned_to"] not in emails]
    err(f"leads.assigned_to bukan user valid: {len(bad)}") if bad else ok("leads.assigned_to -> user valid")

    bad = [u["id"] for u in db.units.find({}, {"id": 1, "project_id": 1}) if u.get("project_id") not in ref["project"]]
    err(f"units.project_id menggantung: {len(bad)}") if bad else ok("units.project_id -> project valid")

    bad = [n["id"] for n in db.notifications.find({}, {"id": 1, "user_email": 1}) if n.get("user_email") not in emails]
    err(f"notifications.user_email bukan user valid: {len(bad)}") if bad else ok("notifications.user_email -> user valid")

    bad = 0
    for a in db.activities.find({"entity_type": {"$in": list(ref.keys())}}, {"entity_type": 1, "entity_id": 1}):
        if a["entity_id"] not in ref[a["entity_type"]]:
            bad += 1
    warn(f"activities dgn entity_id menggantung: {bad}") if bad else ok("activities -> entity valid")


def check_types():
    print("\nCHECK 4 — invarian tipe (uang integer, tanggal ISO)")
    badprice = [u["id"] for u in db.units.find({}, {"id": 1, "price": 1})
                if not isinstance(u.get("price"), int)]
    err(f"units.price bukan integer (uang harus IDR integer): {len(badprice)}") if badprice else ok("units.price integer (IDR)")

    bad = 0
    for c in ["tasks", "users", "leads", "notifications"]:
        for d in db[c].find({}, {"created_at": 1}).limit(50):
            try:
                datetime.fromisoformat(str(d.get("created_at")))
            except Exception:
                bad += 1
    err(f"created_at tidak ISO-8601: {bad}") if bad else ok("created_at ISO-8601")


def check_dup_email():
    print("\nCHECK 5 — email user unik")
    c = Counter(u["email"] for u in db.users.find({}, {"email": 1}))
    dups = [e for e, n in c.items() if n > 1]
    err(f"email ganda: {dups}") if dups else ok(f"{sum(c.values())} user, email unik")


def check_procurement():
    print("\nCHECK 6 — pilar pengadaan (BoQ + Subcon/SPK + PO/GRN/3-way)")
    projects = {x["id"] for x in db.projects.find({}, {"id": 1})}
    subs = {x["id"] for x in db.subcontractors.find({}, {"id": 1})}
    pos = {x["id"] for x in db.purchase_orders.find({}, {"id": 1})}

    if db.spk.count_documents({}):
        bad = [s["id"] for s in db.spk.find({}, {"id": 1, "subcontractor_id": 1}) if s.get("subcontractor_id") not in subs]
        err(f"spk.subcontractor_id menggantung: {len(bad)}") if bad else ok("spk.subcontractor_id -> subkontraktor valid")
        bad = [s["id"] for s in db.spk.find({}, {"id": 1, "project_id": 1}) if s.get("project_id") not in projects]
        err(f"spk.project_id menggantung: {len(bad)}") if bad else ok("spk.project_id -> project valid")

    if db.boq_items.count_documents({}):
        bad = [b["id"] for b in db.boq_items.find({}, {"id": 1, "project_id": 1}) if b.get("project_id") not in projects]
        err(f"boq_items.project_id menggantung: {len(bad)}") if bad else ok("boq_items.project_id -> project valid")
        badamt = [b["id"] for b in db.boq_items.find({}, {"id": 1, "amount": 1}) if not isinstance(b.get("amount"), int)]
        err(f"boq_items.amount bukan integer: {len(badamt)}") if badamt else ok("boq_items.amount integer (IDR)")

    if db.purchase_orders.count_documents({}):
        bad = [p["id"] for p in db.purchase_orders.find({}, {"id": 1, "project_id": 1}) if p.get("project_id") not in projects]
        err(f"purchase_orders.project_id menggantung: {len(bad)}") if bad else ok("purchase_orders.project_id -> project valid")
        badtot = [p["id"] for p in db.purchase_orders.find({}, {"id": 1, "total": 1}) if not isinstance(p.get("total"), int)]
        err(f"purchase_orders.total bukan integer: {len(badtot)}") if badtot else ok("purchase_orders.total integer (IDR)")

    if db.grns.count_documents({}):
        bad = [g["id"] for g in db.grns.find({}, {"id": 1, "po_id": 1}) if g.get("po_id") not in pos]
        err(f"grns.po_id menggantung: {len(bad)}") if bad else ok("grns.po_id -> PO valid")

    linked = list(db.ap_invoices.find({"po_id": {"$ne": None}}, {"id": 1, "po_id": 1}))
    if linked:
        bad = [b["id"] for b in linked if b.get("po_id") not in pos]
        err(f"ap_invoices.po_id menggantung: {len(bad)}") if bad else ok("ap_invoices.po_id -> PO valid (3-way)")


def check_gl():
    print("\nCHECK 7 — General Ledger (double-entry)")
    if db.journal_entries.count_documents({}) == 0:
        ok("belum ada jurnal (lewati)")
        return
    codes = {a["code"] for a in db.accounts.find({}, {"code": 1})}
    unbalanced, dangling = [], []
    gd = gc = 0
    for je in db.journal_entries.find({}, {"id": 1, "total_debit": 1, "total_credit": 1, "lines": 1}):
        td = sum(int(l.get("debit", 0)) for l in je.get("lines", []))
        tc = sum(int(l.get("credit", 0)) for l in je.get("lines", []))
        gd += td
        gc += tc
        if td != tc or td != int(je.get("total_debit", 0)) or tc != int(je.get("total_credit", 0)):
            unbalanced.append(je["id"])
        for l in je.get("lines", []):
            if l.get("account_code") not in codes:
                dangling.append(je["id"])
    err(f"jurnal tidak seimbang: {len(unbalanced)}") if unbalanced else ok("semua jurnal seimbang (debit=kredit)")
    err(f"baris jurnal dengan akun tak dikenal: {len(dangling)}") if dangling else ok("semua baris jurnal -> akun valid")
    err(f"buku besar tidak seimbang total (Dr {gd} != Cr {gc})") if gd != gc else ok(f"neraca saldo seimbang (Rp {gd:,})")


def check_survey_appointment_commission():
    print("\nCHECK 8 — Appointment & Survey (EPIC 1.2) + Komisi (EPIC 1.6)")
    emails = {u["email"] for u in db.users.find({}, {"email": 1})}
    leads = {x["id"] for x in db.leads.find({}, {"id": 1})}
    deals = {x["id"] for x in db.deals.find({}, {"id": 1})}
    appts = {x["id"] for x in db.appointments.find({}, {"id": 1})}

    if db.appointments.count_documents({}):
        bad = [a["id"] for a in db.appointments.find({}, {"id": 1, "lead_id": 1}) if a.get("lead_id") not in leads]
        err(f"appointments.lead_id menggantung: {len(bad)}") if bad else ok("appointments.lead_id -> lead valid")
        bad = [a["id"] for a in db.appointments.find({"assigned_to": {"$ne": None}}, {"id": 1, "assigned_to": 1})
               if a.get("assigned_to") not in emails]
        err(f"appointments.assigned_to bukan user valid: {len(bad)}") if bad else ok("appointments.assigned_to -> user valid")

    if db.surveys.count_documents({}):
        bad = [s["id"] for s in db.surveys.find({}, {"id": 1, "lead_id": 1}) if s.get("lead_id") not in leads]
        err(f"surveys.lead_id menggantung: {len(bad)}") if bad else ok("surveys.lead_id -> lead valid")
        bad = [s["id"] for s in db.surveys.find({"appointment_id": {"$ne": None}}, {"id": 1, "appointment_id": 1})
               if s.get("appointment_id") not in appts]
        err(f"surveys.appointment_id menggantung: {len(bad)}") if bad else ok("surveys.appointment_id -> appointment valid")
        bad = [s["id"] for s in db.surveys.find({"assigned_to": {"$ne": None}}, {"id": 1, "assigned_to": 1})
               if s.get("assigned_to") not in emails]
        err(f"surveys.assigned_to bukan user valid: {len(bad)}") if bad else ok("surveys.assigned_to -> user valid")

    if db.commissions.count_documents({}):
        bad = [c["id"] for c in db.commissions.find({"deal_id": {"$ne": None}}, {"id": 1, "deal_id": 1})
               if c.get("deal_id") not in deals]
        err(f"commissions.deal_id menggantung: {len(bad)}") if bad else ok("commissions.deal_id -> deal valid")
        bad = [c["id"] for c in db.commissions.find({"assigned_to": {"$ne": None}}, {"id": 1, "assigned_to": 1})
               if c.get("assigned_to") not in emails]
        err(f"commissions.assigned_to bukan user valid: {len(bad)}") if bad else ok("commissions.assigned_to -> user valid")
        badamt = [c["id"] for c in db.commissions.find({}, {"id": 1, "amount": 1})
                  if not isinstance(c.get("amount"), int)]
        err(f"commissions.amount bukan integer: {len(badamt)}") if badamt else ok("commissions.amount integer (IDR)")


def check_tax():
    print("\nCHECK 9 — Perpajakan (EPIC 3.3): tax_records + Faktur Pajak")
    deals = {x["id"] for x in db.deals.find({}, {"id": 1})}
    valid_types = ("ppn", "pph", "bphtb", "ppn_masukan")
    if db.tax_records.count_documents({}):
        badamt = [r["id"] for r in db.tax_records.find({}, {"id": 1, "amount": 1})
                  if not isinstance(r.get("amount"), int)]
        err(f"tax_records.amount bukan integer: {len(badamt)}") if badamt else ok("tax_records.amount integer (IDR)")
        bad = [r["id"] for r in db.tax_records.find({"deal_id": {"$ne": None}}, {"id": 1, "deal_id": 1})
               if r.get("deal_id") not in deals]
        err(f"tax_records.deal_id menggantung: {len(bad)}") if bad else ok("tax_records.deal_id -> deal valid")
        badtype = [r["id"] for r in db.tax_records.find({}, {"id": 1, "type": 1})
                   if r.get("type") not in valid_types]
        err(f"tax_records.type tak dikenal: {len(badtype)}") if badtype else ok("tax_records.type valid (ppn/pph/bphtb)")

    if db.faktur_pajak.count_documents({}):
        bad = [f["id"] for f in db.faktur_pajak.find({"deal_id": {"$ne": None}}, {"id": 1, "deal_id": 1})
               if f.get("deal_id") not in deals]
        err(f"faktur_pajak.deal_id menggantung: {len(bad)}") if bad else ok("faktur_pajak.deal_id -> deal valid")
        badamt = [f["id"] for f in db.faktur_pajak.find({}, {"id": 1, "dpp": 1, "ppn": 1})
                  if not (isinstance(f.get("dpp"), int) and isinstance(f.get("ppn"), int))]
        err(f"faktur_pajak dpp/ppn bukan integer: {len(badamt)}") if badamt else ok("faktur_pajak.dpp/ppn integer (IDR)")
        badc = []
        for f in db.faktur_pajak.find({}, {"id": 1, "dpp": 1, "ppn": 1, "ppn_rate": 1}):
            exp = round(int(f.get("dpp", 0)) * float(f.get("ppn_rate", 0)) / 100)
            if int(f.get("ppn", 0)) != exp:
                badc.append(f["id"])
        err(f"faktur_pajak PPN != DPP×rate: {len(badc)}") if badc else ok("faktur_pajak PPN konsisten (DPP×rate)")
        dups = [f["number"] for f in db.faktur_pajak.find({}, {"number": 1})]
        err("nomor faktur pajak ganda") if len(dups) != len(set(dups)) else ok("nomor faktur pajak unik")


def check_subcon_claims():
    print("\nCHECK 10 — Progress Claim (Termin) & Change Order (EPIC 2.3)")
    spks = {x["id"] for x in db.spk.find({}, {"id": 1})}
    bills = {x["id"] for x in db.ap_invoices.find({}, {"id": 1})}
    claim_status = ("submitted", "verified", "approved", "rejected")
    if db.progress_claims.count_documents({}):
        bad = [c["id"] for c in db.progress_claims.find({}, {"id": 1, "spk_id": 1}) if c.get("spk_id") not in spks]
        err(f"progress_claims.spk_id menggantung: {len(bad)}") if bad else ok("progress_claims.spk_id -> spk valid")
        badamt = [c["id"] for c in db.progress_claims.find({}, {"id": 1, "gross": 1, "gross_est": 1, "retention_held": 1})
                  if not (isinstance(c.get("gross"), int) and isinstance(c.get("gross_est"), int)
                          and isinstance(c.get("retention_held"), int))]
        err(f"progress_claims nilai bukan integer: {len(badamt)}") if badamt else ok("progress_claims gross/retensi integer (IDR)")
        badpct = [c["id"] for c in db.progress_claims.find({}, {"id": 1, "prev_pct": 1, "claimed_pct": 1})
                  if not (0 <= int(c.get("prev_pct", 0)) <= 100 and 0 < int(c.get("claimed_pct", 0)) <= 100)]
        err(f"progress_claims persen di luar 0-100: {len(badpct)}") if badpct else ok("progress_claims persen valid (0-100)")
        badst = [c["id"] for c in db.progress_claims.find({}, {"id": 1, "status": 1}) if c.get("status") not in claim_status]
        err(f"progress_claims.status tak dikenal: {len(badst)}") if badst else ok("progress_claims.status valid")
        badbill = [c["id"] for c in db.progress_claims.find({"status": "approved"}, {"id": 1, "ap_bill_id": 1})
                   if c.get("ap_bill_id") not in bills]
        err(f"progress_claims approved tanpa AP bill valid: {len(badbill)}") if badbill else ok("progress_claims approved -> ap_bill valid")

    if db.change_orders.count_documents({}):
        bad = [c["id"] for c in db.change_orders.find({}, {"id": 1, "spk_id": 1}) if c.get("spk_id") not in spks]
        err(f"change_orders.spk_id menggantung: {len(bad)}") if bad else ok("change_orders.spk_id -> spk valid")
        badamt = [c["id"] for c in db.change_orders.find({}, {"id": 1, "value_delta": 1})
                  if not isinstance(c.get("value_delta"), int)]
        err(f"change_orders.value_delta bukan integer: {len(badamt)}") if badamt else ok("change_orders.value_delta integer (IDR)")
        badst = [c["id"] for c in db.change_orders.find({}, {"id": 1, "status": 1})
                 if c.get("status") not in ("draft", "approved", "rejected")]
        err(f"change_orders.status tak dikenal: {len(badst)}") if badst else ok("change_orders.status valid")


def check_inspections():
    print("\nCHECK 11 — QC / Inspeksi (EPIC 2.4)")
    projects = {x["id"] for x in db.projects.find({}, {"id": 1})}
    valid_res = ("pending", "pass", "fail", "na")
    if db.inspections.count_documents({}):
        bad = [i["id"] for i in db.inspections.find({}, {"id": 1, "project_id": 1}) if i.get("project_id") not in projects]
        err(f"inspections.project_id menggantung: {len(bad)}") if bad else ok("inspections.project_id -> project valid")
        badst = [i["id"] for i in db.inspections.find({}, {"id": 1, "status": 1})
                 if i.get("status") not in ("in_progress", "passed", "failed")]
        err(f"inspections.status tak dikenal: {len(badst)}") if badst else ok("inspections.status valid")
        badres = []
        badcount = []
        for i in db.inspections.find({}, {"id": 1, "items": 1, "fail_count": 1, "pass_count": 1}):
            items = i.get("items", [])
            if any((it.get("result") or "pending") not in valid_res for it in items):
                badres.append(i["id"])
            fc = sum(1 for it in items if it.get("result") == "fail")
            pc = sum(1 for it in items if it.get("result") == "pass")
            if int(i.get("fail_count", 0)) != fc or int(i.get("pass_count", 0)) != pc:
                badcount.append(i["id"])
        err(f"inspections item result tak valid: {len(badres)}") if badres else ok("inspections item result valid (pending/pass/fail/na)")
        err(f"inspections count tidak konsisten: {len(badcount)}") if badcount else ok("inspections pass/fail_count konsisten dgn items")
        badfp = [i["id"] for i in db.inspections.find({"status": "failed"}, {"id": 1, "fail_count": 1})
                 if int(i.get("fail_count", 0)) == 0]
        err(f"inspections FAILED tanpa item gagal: {len(badfp)}") if badfp else ok("inspections FAILED memiliki >=1 item gagal")
    if db.inspection_templates.count_documents({}):
        badt = [t.get("code") for t in db.inspection_templates.find({}, {"code": 1, "items": 1}) if not t.get("items")]
        err(f"inspection_templates tanpa item: {len(badt)}") if badt else ok("inspection_templates punya item")


def check_material_requisitions():
    print("\nCHECK 12 — Material Requisition + Anggaran RAB (EPIC 2.6)")
    projects = {x["id"] for x in db.projects.find({}, {"id": 1})}
    materials = {x["id"] for x in db.materials.find({}, {"id": 1})}
    boq = {x["id"] for x in db.boq_items.find({}, {"id": 1})}
    valid_status = ("submitted", "approved", "partially_issued", "issued", "rejected")
    if db.material_requisitions.count_documents({}):
        bad = [r["id"] for r in db.material_requisitions.find({}, {"id": 1, "project_id": 1})
               if r.get("project_id") not in projects]
        err(f"material_requisitions.project_id menggantung: {len(bad)}") if bad else ok("material_requisitions.project_id -> project valid")
        badst = [r["id"] for r in db.material_requisitions.find({}, {"id": 1, "status": 1})
                 if r.get("status") not in valid_status]
        err(f"material_requisitions.status tak dikenal: {len(badst)}") if badst else ok("material_requisitions.status valid")
        baditem, badissue = [], []
        for r in db.material_requisitions.find({}, {"id": 1, "items": 1}):
            for it in r.get("items", []):
                if it.get("material_id") not in materials or not isinstance(it.get("qty_requested"), (int, float)):
                    baditem.append(r["id"])
                    break
                if float(it.get("qty_issued", 0)) > float(it.get("qty_requested", 0)) + 1e-6:
                    badissue.append(r["id"])
                    break
        err(f"material_requisitions item material/qty invalid: {len(baditem)}") if baditem else ok("material_requisitions item -> material valid & qty numerik")
        err(f"material_requisitions qty_issued > qty_requested: {len(badissue)}") if badissue else ok("material_requisitions qty_issued <= qty_requested")
    # Anggaran: boq_item_id valid bila di-set; budget_qty numerik
    if db.materials.count_documents({"boq_item_id": {"$ne": None}}):
        bad = [m["id"] for m in db.materials.find({"boq_item_id": {"$ne": None}}, {"id": 1, "boq_item_id": 1})
               if m.get("boq_item_id") not in boq]
        err(f"materials.boq_item_id menggantung: {len(bad)}") if bad else ok("materials.boq_item_id -> BoQ valid")
    badbq = [m["id"] for m in db.materials.find({"budget_qty": {"$exists": True}}, {"id": 1, "budget_qty": 1})
             if not isinstance(m.get("budget_qty"), (int, float))]
    err(f"materials.budget_qty bukan numerik: {len(badbq)}") if badbq else ok("materials.budget_qty numerik")


def check_phase27():
    print("\nCHECK 13 — Kas Bon / Aset Tetap / Pembiayaan / Marketing Fee (Fase 27)")
    projects = {x["id"] for x in db.projects.find({}, {"id": 1})}
    deals = {x["id"] for x in db.deals.find({}, {"id": 1})}
    users = {x["email"] for x in db.users.find({}, {"email": 1})}
    money_int = []

    if db.cash_advances.count_documents({}):
        bad_pic, bad_proj = [], []
        for a in db.cash_advances.find({}, {"_id": 0}):
            if a.get("requested_by") not in users:
                bad_pic.append(a["id"])
            if a.get("project_id") and a["project_id"] not in projects:
                bad_proj.append(a["id"])
            for f in ("amount_requested", "disbursed_amount", "expense_total",
                      "returned_amount", "reimburse_amount"):
                if not isinstance(a.get(f, 0), int):
                    money_int.append(f"cash_advances.{f}")
        err(f"cash_advances.requested_by bukan user: {len(bad_pic)}") if bad_pic \
            else ok("cash_advances.requested_by -> user valid")
        err(f"cash_advances.project_id menggantung: {len(bad_proj)}") if bad_proj \
            else ok("cash_advances.project_id -> proyek valid")

    if db.fixed_assets.count_documents({}):
        bad_proj, bad_bill = [], []
        for a in db.fixed_assets.find({}, {"_id": 0}):
            if a.get("project_id") and a["project_id"] not in projects:
                bad_proj.append(a["id"])
            if a.get("ap_bill_id") and not db.ap_invoices.count_documents({"id": a["ap_bill_id"]}):
                bad_bill.append(a["id"])
            for f in ("cost", "salvage_value", "accumulated_depreciation", "book_value"):
                if not isinstance(a.get(f, 0), int):
                    money_int.append(f"fixed_assets.{f}")
        err(f"fixed_assets.project_id menggantung: {len(bad_proj)}") if bad_proj \
            else ok("fixed_assets.project_id -> proyek valid")
        err(f"fixed_assets.ap_bill_id menggantung: {len(bad_bill)}") if bad_bill \
            else ok("fixed_assets.ap_bill_id -> tagihan AP valid")
        assets = {a["id"] for a in db.fixed_assets.find({}, {"id": 1})}
        orphan = [d["id"] for d in db.asset_depreciations.find({}, {"id": 1, "asset_id": 1})
                  if d.get("asset_id") not in assets]
        err(f"asset_depreciations.asset_id menggantung: {len(orphan)}") if orphan \
            else ok("asset_depreciations.asset_id -> aset valid")
        dupes = []
        seen = set()
        for d in db.asset_depreciations.find({}, {"asset_id": 1, "period": 1}):
            key = (d.get("asset_id"), d.get("period"))
            if key in seen:
                dupes.append(key)
            seen.add(key)
        err(f"asset_depreciations ganda per (aset, periode): {len(dupes)}") if dupes \
            else ok("asset_depreciations unik per (aset, periode) — idempotensi terjaga")

    if db.loans.count_documents({}):
        loans = {l["id"] for l in db.loans.find({}, {"id": 1})}
        orphan = [p["id"] for p in db.loan_payments.find({}, {"id": 1, "loan_id": 1})
                  if p.get("loan_id") not in loans]
        err(f"loan_payments.loan_id menggantung: {len(orphan)}") if orphan \
            else ok("loan_payments.loan_id -> fasilitas valid")
        badsched = []
        for l in db.loans.find({}, {"_id": 0}):
            for f in ("principal", "provision_fee", "paid_principal", "paid_interest",
                      "outstanding_principal"):
                if not isinstance(l.get(f, 0), int):
                    money_int.append(f"loans.{f}")
            for r in l.get("schedule") or []:
                if not all(isinstance(r.get(k, 0), int) for k in
                           ("principal", "interest", "total", "paid_total")):
                    badsched.append(l["id"])
                    break
        err(f"loans.schedule nominal bukan integer: {len(badsched)}") if badsched \
            else ok("loans.schedule nominal integer (rupiah utuh)")

    if db.marketing_fees.count_documents({}):
        agents = {a["id"] for a in db.agents.find({}, {"id": 1})}
        bad_agent = [f["id"] for f in db.marketing_fees.find({}, {"id": 1, "agent_id": 1})
                     if f.get("agent_id") not in agents]
        bad_deal = [f["id"] for f in db.marketing_fees.find({}, {"id": 1, "deal_id": 1})
                    if f.get("deal_id") not in deals]
        err(f"marketing_fees.agent_id menggantung: {len(bad_agent)}") if bad_agent \
            else ok("marketing_fees.agent_id -> agen valid")
        err(f"marketing_fees.deal_id menggantung: {len(bad_deal)}") if bad_deal \
            else ok("marketing_fees.deal_id -> deal valid")
        dupes = []
        seen = set()
        for f in db.marketing_fees.find({"status": {"$in": ["submitted", "approved", "paid"]}},
                                        {"agent_id": 1, "deal_id": 1, "trigger": 1}):
            key = (f.get("agent_id"), f.get("deal_id"), f.get("trigger"))
            if key in seen:
                dupes.append(key)
            seen.add(key)
        err(f"marketing_fees ganda aktif per (agen, deal, pemicu): {len(dupes)}") if dupes \
            else ok("marketing_fees tidak ganda per (agen, deal, pemicu)")
        for f in db.marketing_fees.find({}, {"_id": 0}):
            for fld in ("amount_gross", "pph_amount", "amount_net", "paid_amount"):
                if not isinstance(f.get(fld, 0), int):
                    money_int.append(f"marketing_fees.{fld}")

    if money_int:
        err(f"nominal Fase 27 bukan integer: {sorted(set(money_int))}")
    else:
        ok("semua nominal Fase 27 integer (tanpa pecahan sen)")


def check_build_schedules():
    print("\nCHECK 14 — Jadwal pembangunan per unit (Fase 31)")
    if not db.build_schedules.count_documents({}):
        warn("build_schedules kosong (belum ada unit yang dijadwalkan)")
        return
    units = {u["id"]: u for u in db.units.find({}, {"id": 1, "construction_progress": 1,
                                                    "project_id": 1})}
    ok_states = ("blocked", "ready", "in_progress", "submitted", "rework", "done")
    dangling, dupes, mismatch, weightbad = [], [], [], []
    seen_units = Counter()
    for s in db.build_schedules.find({}, {"_id": 0}):
        seen_units[s.get("unit_id")] += 1
        if s.get("unit_id") not in units:
            dangling.append(s["id"])
            continue
        items = list(db.build_items.find({"schedule_id": s["id"]}, {"_id": 0}))
        total = sum(float(i.get("weight") or 0) for i in items) or 1
        done = sum(float(i.get("weight") or 0) for i in items if i.get("status") == "done")
        want = round(done / total * 100, 1)
        if abs(float(s.get("progress") or 0) - want) > 0.2:
            mismatch.append(f"{s.get('unit_code')}: {s.get('progress')} != {want}")
        if abs(total - 100) > 0.5:
            weightbad.append(f"{s.get('unit_code')}: bobot {round(total, 2)}%")
        u = units[s["unit_id"]]
        if int(u.get("construction_progress") or 0) != int(round(float(s.get("progress") or 0))):
            mismatch.append(f"unit {s.get('unit_code')} progres tidak sinkron: "
                            f"{u.get('construction_progress')} vs {s.get('progress')}")
    dupes = [k for k, v in seen_units.items() if v > 1]
    err(f"build_schedules.unit_id menggantung: {len(dangling)}") if dangling \
        else ok("build_schedules.unit_id -> unit valid")
    err(f"unit punya lebih dari satu jadwal: {len(dupes)}") if dupes \
        else ok("satu unit tepat satu jadwal pembangunan")
    err(f"progres tidak sama dengan Σ bobot item terverifikasi: {mismatch[:3]}") if mismatch \
        else ok("progres unit = Σ bobot item terverifikasi (tidak bisa diketik manual)")
    warn(f"total bobot template != 100%: {weightbad[:3]}") if weightbad \
        else ok("total bobot item per jadwal = 100%")
    badst = [i["id"] for i in db.build_items.find({}, {"id": 1, "status": 1})
             if i.get("status") not in ok_states]
    err(f"build_items.status tak dikenal: {len(badst)}") if badst \
        else ok("build_items.status sesuai SSOT")
    # Gerbang mutu: item DONE tidak boleh tanpa bukti & verifikator; verifikator != pengaju
    noproof = [i.get("step_code") for i in db.build_items.find(
        {"status": "done"}, {"step_code": 1, "evidence": 1, "min_photos": 1, "verified_by": 1})
        if int(i.get("min_photos") or 0) > 0 and not (i.get("evidence") or [])]
    err(f"item selesai TANPA bukti: {len(noproof)}") if noproof \
        else ok("setiap item selesai punya bukti (bila bukti diwajibkan)")
    selfver = [i.get("step_code") for i in db.build_items.find(
        {"status": "done"}, {"step_code": 1, "submitted_by": 1, "verified_by": 1})
        if i.get("verified_by") and i.get("submitted_by")
        and i["verified_by"] == i["submitted_by"] and i["verified_by"] != "seed"]
    err(f"item diverifikasi oleh pengajunya sendiri: {len(selfver)}") if selfver \
        else ok("pemisahan tugas terjaga (pengaju != verifikator)")
    # Ikatan unit -> lead/deal (cacat D-F)
    unbound = [u.get("id") for u in db.units.find(
        {"$or": [{"booked_by_deal": {"$nin": [None, ""]}}, {"sold_by_deal": {"$nin": [None, ""]}}]},
        {"id": 1, "lead_id": 1, "deal_id": 1}) if not (u.get("lead_id") and u.get("deal_id"))]
    err(f"unit terjual tanpa ikatan lead/deal: {len(unbound)}") if unbound \
        else ok("unit reserved/booked/sold terikat deal & lead")


def main():
    check_org_id()
    check_seed_gap()
    check_referential()
    check_types()
    check_dup_email()
    check_procurement()
    check_gl()
    check_survey_appointment_commission()
    check_tax()
    check_subcon_claims()
    check_inspections()
    check_material_requisitions()
    check_phase27()
    check_build_schedules()
    print("-" * 50)
    if errors:
        print(f"DATA INTEGRITY FAILED: {len(errors)} error, {len(warns)} warn")
        sys.exit(1)
    print(f"DATA INTEGRITY PASSED ({len(warns)} warn)")


if __name__ == "__main__":
    main()
