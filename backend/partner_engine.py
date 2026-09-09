"""partner_engine.py — Fase 42: HAK FEE MITRA LAHIR DARI PERISTIWA NYATA.

Aturan yang dipegang (`docs/v2/25_PARTNER_SPEC.md` §5 & §8):
  1. Fee TIDAK boleh ada tanpa aturan yang berlaku (INV-09) — kalau tidak ada aturan, sistem
     MENOLAK dan mencatat alasannya, bukan memasang angka default.
  2. Fee tercipta saat PEMICU tercapai (reservasi/booking fee/PPJB/akad/AJB/pelunasan) —
     pemicunya adalah event yang sudah ada di `engine.HANDLERS`, bukan tombol manual.
  3. Satu mitra × satu deal × satu pemicu = satu tagihan fee (idempoten). Event `deal.ajb`
     dan `deal.sold` terbit bersamaan untuk deal yang sama; tanpa penjagaan ini mitra akan
     ditagihkan dua kali.
  4. Angka masuk lewat pintu `marketing_fees` yang SUDAH memegang invarian akuntansi
     (`2-1500 = Σ netto − terbayar`, jurnal idempoten) — modul ini tidak menyentuh jurnal.
  5. Semua keputusan (dipakai aturan mana, kenapa ditolak) disimpan pada dokumen fee &
     aktivitas, supaya bisa dipertanggungjawabkan ke mitra.
"""
import logging

import partner_fee as pfee
import sequences as seq
import settings_store as cfg
from core_utils import new_id, now_iso, today_iso_date
from db import db, ORG_ID
from p27_utils import rp

logger = logging.getLogger("sipro.partner_engine")

# Peristiwa NYATA yang sudah terbit di aplikasi → pemicu hak fee (SSOT `partner_fee_trigger`).
EVENT_TRIGGERS = {
    "deal.reserved": "spr_signed",
    "deal.booked": "booking_fee_verified",
    "deal.ppjb": "ppjb_signed",
    "deal.ajb": "ajb_signed",
    "deal.sold": "ajb_signed",
    "payment.paid_off": "full_payment",
    "kpr.akad": "akad_kredit",
}
TOGGLE_KEYS = ("partner.enabled", "partner.require_contract_active", "partner.auto_create_fee",
               "partner.fee_needs_approval", "partner.max_fee_pct_of_price",
               "partner.tax_pph21_rate", "partner.tax_pph23_rate",
               "partner.attribution_model", "partner.lead_dedup_window_days")
# Dasar fee yang tidak butuh deal (fee per lead) — dipakai untuk memutuskan kelayakan hitung.
LEAD_BASED = ("per_lead_qualified",)


async def toggles(org_id: str = ORG_ID) -> dict:
    return await cfg.get_many(TOGGLE_KEYS, org_id=org_id)


# ------------------------------------------------------------------ mitra & konteks
async def partner_of_deal(deal: dict, org_id: str = ORG_ID) -> dict:
    """Mitra pemilik deal: dari deal, kalau tidak ada dari lead-nya (atribusi tersimpan)."""
    pid = (deal or {}).get("partner_id")
    if not pid and (deal or {}).get("lead_id"):
        lead = await db.leads.find_one({"id": deal["lead_id"], "org_id": org_id},
                                       {"_id": 0, "partner_id": 1})
        pid = (lead or {}).get("partner_id")
    if not pid:
        return None
    return await db.agents.find_one({"id": pid, "org_id": org_id}, {"_id": 0})


def contract_active(partner: dict, at: str = None) -> tuple:
    """(aktif, alasan). Kontrak kedaluwarsa = mitra tidak boleh dapat fee baru (toggle)."""
    contract = (partner or {}).get("contract") or {}
    end = contract.get("end_date")
    today = (at or today_iso_date())[:10]
    if not contract.get("number"):
        return False, "Mitra belum punya nomor kontrak kerja sama."
    if contract.get("status") and contract["status"] not in ("active", "signed"):
        return False, f"Kontrak mitra berstatus {contract['status']}."
    if end and str(end)[:10] < today:
        return False, f"Kontrak mitra berakhir {str(end)[:10]}."
    return True, None


async def closings(partner_id: str, *, org_id: str = ORG_ID, period: str = "monthly",
                   at: str = None) -> dict:
    """Jumlah & nilai closing mitra pada periode berjalan (dasar tier) — dari data nyata."""
    at = at or now_iso()
    start = None
    if period == "monthly":
        start = at[:7] + "-01"
    elif period == "quarterly":
        month = int(at[5:7])
        start = f"{at[:4]}-{3 * ((month - 1) // 3) + 1:02d}-01"
    leads = await db.leads.find({"org_id": org_id, "partner_id": partner_id},
                               {"_id": 0, "id": 1}).to_list(5000)
    lead_ids = [l["id"] for l in leads]
    query = {"org_id": org_id, "status": {"$in": ["booked", "completed"]},
             "$or": [{"partner_id": partner_id}, {"lead_id": {"$in": lead_ids}}]}
    if start:
        query["created_at"] = {"$gte": start}
    rows = await db.deals.find(query, {"_id": 0, "price": 1, "id": 1}).to_list(5000)
    return {"count": len(rows), "value": sum(int(r.get("price") or 0) for r in rows),
            "period": period, "since": start}


async def qualified_leads(partner_id: str, *, org_id: str = ORG_ID,
                          qualify_rule: str = "survey_attended") -> int:
    """Lead mitra yang LOLOS kualifikasi menurut bukti tercatat (bukan klaim mitra)."""
    base = {"org_id": org_id, "partner_id": partner_id}
    if qualify_rule == "contacted":
        return await db.leads.count_documents({**base, "first_contact_at": {"$ne": None}})
    if qualify_rule == "booking":
        return await db.leads.count_documents({**base, "stage": {"$in": ["booking", "won"]}})
    leads = await db.leads.find(base, {"_id": 0, "id": 1}).to_list(5000)
    ids = [l["id"] for l in leads]
    if not ids:
        return 0
    done = await db.appointments.distinct(
        "lead_id", {"org_id": org_id, "lead_id": {"$in": ids}, "status": "done"})
    return len(done)


async def context_for(deal: dict, partner: dict, rule: dict, trigger: str,
                      org_id: str = ORG_ID) -> dict:
    unit = None
    if (deal or {}).get("unit_id"):
        unit = await db.units.find_one({"id": deal["unit_id"], "org_id": org_id}, {"_id": 0})
    ctx = {"deal": deal, "unit": unit, "partner_id": (partner or {}).get("id"),
           "trigger": trigger, "at": now_iso(),
           "project_id": (deal or {}).get("project_id"),
           "cluster_id": (unit or {}).get("cluster_id"),
           "unit_type": (unit or {}).get("unit_type_code") or (unit or {}).get("type")}
    basis = (rule or {}).get("basis")
    if basis in ("tier_volume", "tier_value"):
        got = await closings((partner or {}).get("id"), org_id=org_id,
                            period=(rule.get("period") or "monthly"))
        ctx["closings_count"] = got["count"]
        ctx["closings_value"] = got["value"]
        ctx["closings"] = got
    if basis in LEAD_BASED or basis == "hybrid":
        ctx["qualified_leads"] = await qualified_leads(
            (partner or {}).get("id"), org_id=org_id,
            qualify_rule=(rule or {}).get("qualify_rule") or "survey_attended")
    return ctx


# ------------------------------------------------------------------ hitung + buat fee
async def compute(deal: dict, trigger: str, *, org_id: str = ORG_ID, partner: dict = None,
                  cfgs: dict = None) -> dict:
    """Hitung angka fee TANPA menyimpan — dipakai pratinjau UI & pembuatan otomatis.

    Mengembalikan {ok, reason, partner, rule, gross, share, tax, amounts, ctx}.
    """
    cfgs = cfgs or await toggles(org_id)
    if not cfgs.get("partner.enabled"):
        return {"ok": False, "reason": "Modul mitra dimatikan di Pusat Konfigurasi "
                                      "(`partner.enabled`)."}
    partner = partner or await partner_of_deal(deal, org_id)
    if not partner:
        return {"ok": False, "reason": "Deal ini tidak berasal dari mitra (tidak ada "
                                      "`partner_id` pada deal maupun lead-nya)."}
    if partner.get("status") != "active":
        return {"ok": False, "reason": f"Mitra {partner.get('name')} berstatus "
                                      f"{partner.get('status')} — fee baru ditolak.",
                "partner": partner}
    if cfgs.get("partner.require_contract_active"):
        okc, why = contract_active(partner)
        if not okc:
            return {"ok": False, "reason": f"{why} Aktifkan kontrak atau matikan "
                                          "`partner.require_contract_active`.",
                    "partner": partner}
    rules = await pfee.list_rules(org_id=org_id, partner_id=partner["id"])
    probe = {"partner_id": partner["id"], "trigger": trigger, "at": now_iso(),
             "project_id": (deal or {}).get("project_id")}
    rule, why = pfee.select(rules, probe)
    if not rule:
        return {"ok": False, "reason": why, "partner": partner}
    ctx = await context_for(deal, partner, rule, trigger, org_id)
    rule, why = pfee.select(rules, ctx)          # pilih ulang dengan cakupan LENGKAP (unit/cluster)
    if not rule:
        return {"ok": False, "reason": why, "partner": partner}
    try:
        evaluated = pfee.evaluate(rule, ctx)
    except ValueError as exc:
        return {"ok": False, "reason": str(exc), "partner": partner, "rule": rule}
    share = pfee.split_pct(rule, trigger)
    gross_share = int(round(evaluated["gross"] * share / 100.0))
    if gross_share <= 0:
        return {"ok": False, "reason": f"Porsi fee pada pemicu '{trigger}' 0% — tidak ada yang "
                                      "jatuh tempo sekarang.", "partner": partner, "rule": rule}
    rates = {"pph21": cfgs.get("partner.tax_pph21_rate"),
             "pph23": cfgs.get("partner.tax_pph23_rate")}
    try:
        tax = pfee.tax_of(gross_share, rule, partner, rates)
    except ValueError as exc:
        return {"ok": False, "reason": str(exc), "partner": partner, "rule": rule}
    price = int((deal or {}).get("price") or 0)
    guard = float(cfgs.get("partner.max_fee_pct_of_price") or 0)
    fee_pct_of_price = round(tax["expense"] * 100.0 / price, 3) if price else None
    needs_owner = bool(guard and fee_pct_of_price and fee_pct_of_price > guard)
    return {
        "ok": True, "partner": partner, "rule": rule, "trigger": trigger,
        "gross_full": evaluated["gross"], "share_pct": share, "gross": gross_share,
        "tax": tax, "detail": evaluated["detail"], "ctx": {k: v for k, v in ctx.items()
                                                          if k not in ("deal", "unit")},
        "fee_pct_of_price": fee_pct_of_price, "guard_pct": guard,
        "needs_owner_approval": needs_owner,
        "amounts": {"expense": tax["expense"], "pph": tax["pph_amount"],
                    "payout": tax["payout"]},
    }


def _compat_basis(basis: str) -> str:
    """Kosakata lama `scheme_basis` (percent|fixed) tetap terisi supaya daftar & laporan
    Marketing Fee lama tidak buta terhadap fee mitra otomatis."""
    return "percent" if basis in ("percent_price", "tier_volume", "tier_value") else "fixed"


async def create_fee_for_trigger(deal: dict, trigger: str, *, actor: str = "system",
                                 org_id: str = ORG_ID, manual: bool = False) -> dict:
    """Buat tagihan fee mitra untuk satu pemicu (idempoten). {created, reason, fee}."""
    if trigger not in pfee.TRIGGERS:
        raise ValueError(f"Pemicu hak fee tidak dikenal: {trigger}")
    cfgs = await toggles(org_id)
    if not manual and not cfgs.get("partner.auto_create_fee"):
        return {"created": False, "reason": "Pembuatan fee otomatis dimatikan "
                                           "(`partner.auto_create_fee`)."}
    calc = await compute(deal, trigger, org_id=org_id, cfgs=cfgs)
    if not calc.get("ok"):
        logger.info("Fee mitra tidak dibuat untuk deal %s (%s): %s",
                    (deal or {}).get("id"), trigger, calc.get("reason"))
        return {"created": False, "reason": calc.get("reason"),
                "partner_id": (calc.get("partner") or {}).get("id")}
    partner, rule, tax = calc["partner"], calc["rule"], calc["tax"]
    existing = await db.marketing_fees.find_one(
        {"org_id": org_id, "agent_id": partner["id"], "deal_id": deal["id"],
         "trigger": trigger, "status": {"$in": mfee_open_statuses()}}, {"_id": 0})
    if existing:
        return {"created": False, "reason": f"Fee untuk pemicu ini sudah ada ({existing['no']}).",
                "fee": existing}
    ts = now_iso()
    no = await seq.next_number("marketing_fee", org_id, prefix="MF", width=4,
                               context={"project_id": deal.get("project_id")})
    doc = {
        "id": new_id(), "org_id": org_id, "no": no, "status": "submitted",
        "agent_id": partner["id"], "agent_name": partner.get("name"),
        "agent_type": partner.get("agent_type") or "lainnya",
        "partner_id": partner["id"], "partner_kind": partner.get("partner_kind"),
        "deal_id": deal["id"], "unit_code": deal.get("unit_code"),
        "project_id": deal.get("project_id"), "deal_price": int(deal.get("price") or 0),
        "lead_id": deal.get("lead_id"),
        "basis": _compat_basis(rule["basis"]), "rule_basis": rule["basis"],
        "rule_id": rule["id"], "rule_code": rule.get("code"), "rule_name": rule.get("name"),
        "value": float(rule.get("value") or 0), "trigger": trigger,
        "share_pct": calc["share_pct"], "gross_full": calc["gross_full"],
        "amount_gross": tax["expense"], "pph_type": tax["pph_type"],
        "pph_pct": tax["pph_pct"], "pph_amount": tax["pph_amount"],
        "amount_net": tax["payout"], "gross_up": tax["gross_up"], "paid_amount": 0,
        "calc": {"detail": calc["detail"], "context": calc["ctx"],
                 "fee_pct_of_price": calc["fee_pct_of_price"]},
        "needs_owner_approval": calc["needs_owner_approval"],
        "guard_pct": calc["guard_pct"], "source": "manual" if manual else "auto",
        "note": (f"Otomatis dari aturan {rule.get('code')} saat pemicu "
                 f"{trigger} tercapai.") if not manual else None,
        "requested_by": actor, "approved_by": None, "approved_at": None,
        "rejected_by": None, "rejected_at": None, "reject_reason": None, "paid_at": None,
        "journal_ids": [], "created_at": ts, "updated_at": ts,
    }
    await db.marketing_fees.insert_one(dict(doc))
    doc.pop("_id", None)
    from engine import add_activity
    from finance_engine import notify_finance
    body = (f"Fee mitra {no} untuk {partner.get('name')} terbit otomatis {rp(tax['expense'])} "
            f"(aturan {rule.get('code')}, pemicu {trigger}, porsi {calc['share_pct']}%).")
    await add_activity(entity_type="marketing_fee", entity_id=doc["id"], type="system",
                       body=body, actor=actor, org_id=org_id)
    await add_activity(entity_type="agent", entity_id=partner["id"], type="system",
                       body=body, actor=actor, org_id=org_id)
    await notify_finance(org_id, "Tagihan fee mitra baru",
                         f"{partner.get('name')} — {rp(tax['expense'])} atas unit "
                         f"{deal.get('unit_code') or '-'} menunggu persetujuan.",
                         "approval", "marketing_fee", doc["id"])
    if not cfgs.get("partner.fee_needs_approval") and not calc["needs_owner_approval"]:
        import marketing_fee as mfee
        doc = await mfee.approve_fee(doc["id"], actor="system",
                                     note="Disetujui otomatis (`partner.fee_needs_approval` mati).",
                                     org_id=org_id)
    await refresh_stats(partner["id"], org_id=org_id)
    return {"created": True, "fee": doc, "rule": rule,
            "reason": None if not calc["needs_owner_approval"] else
            (f"Fee {calc['fee_pct_of_price']}% dari harga melewati pagar wajar "
             f"{calc['guard_pct']}% — butuh persetujuan owner.")}


def mfee_open_statuses() -> list:
    import marketing_fee as mfee
    return list(mfee.OPEN_STATUSES)


# ------------------------------------------------------------------ event bus
async def on_event(ev: dict):
    """Handler event bus — dipasang ke `engine.HANDLERS` (lihat `register()`)."""
    trigger = EVENT_TRIGGERS.get(ev.get("type"))
    if not trigger:
        return
    org = ev.get("org_id", ORG_ID)
    deal = None
    if ev.get("entity_type") == "deal":
        deal = await db.deals.find_one({"id": ev["entity_id"]}, {"_id": 0})
    else:
        data = ev.get("data") or {}
        deal_id = data.get("deal_id")
        if not deal_id and data.get("invoice_id"):
            inv = await db.ar_invoices.find_one({"id": data["invoice_id"]},
                                               {"_id": 0, "deal_id": 1})
            deal_id = (inv or {}).get("deal_id")
        if deal_id:
            deal = await db.deals.find_one({"id": deal_id}, {"_id": 0})
    if not deal:
        return
    result = await create_fee_for_trigger(deal, trigger, actor="system", org_id=org)
    if not result.get("created") and result.get("reason"):
        logger.debug("fee mitra dilewati (%s): %s", ev.get("type"), result["reason"])


def register():
    """Pasang handler pada event yang SUDAH terbit di aplikasi (tanpa event karangan)."""
    import engine
    for etype in EVENT_TRIGGERS:
        engine.HANDLERS.setdefault(etype, [])
        if on_event not in engine.HANDLERS[etype]:
            engine.HANDLERS[etype].append(on_event)
    return sorted(EVENT_TRIGGERS)


# ------------------------------------------------------------------ atribusi lead
async def attribute(*, partner_id: str, phone: str, org_id: str = ORG_ID,
                    lead_id: str = None) -> dict:
    """Tentukan mitra yang berhak atas lead ini (dedup + model atribusi).

    Lead yang sama dikirim dua mitra adalah kejadian nyata di bisnis agen. Kalau tidak
    diputuskan dengan aturan, dua mitra akan menagih fee atas satu pembeli.
    """
    cfgs = await cfg.get_many(["partner.attribution_model", "partner.lead_dedup_window_days"],
                             org_id=org_id)
    model = cfgs.get("partner.attribution_model") or "first_touch"
    window = int(cfgs.get("partner.lead_dedup_window_days") or 30)
    from datetime import timedelta

    from core_utils import now
    since = (now() - timedelta(days=window)).isoformat()
    query = {"org_id": org_id, "phone": phone, "partner_id": {"$ne": None},
             "created_at": {"$gte": since}}
    if lead_id:
        query["id"] = {"$ne": lead_id}
    prior = await db.leads.find(query, {"_id": 0, "id": 1, "partner_id": 1, "created_at": 1}) \
        .sort("created_at", 1).to_list(20)
    if not prior or prior[0].get("partner_id") == partner_id:
        return {"partner_id": partner_id, "model": model, "conflict": None}
    first = prior[0]
    conflict = {
        "id": new_id(), "org_id": org_id, "phone": phone, "lead_id": lead_id,
        "claimed_by": partner_id, "held_by": first.get("partner_id"),
        "first_lead_id": first.get("id"), "first_seen_at": first.get("created_at"),
        "model": model, "window_days": window,
        "status": "pending_review" if model == "manual_review" else "resolved",
        "created_at": now_iso(),
    }
    if model == "last_touch":
        conflict["decision"] = partner_id
        effective = partner_id
    elif model == "manual_review":
        conflict["decision"] = None
        effective = first.get("partner_id")
    else:
        conflict["decision"] = first.get("partner_id")
        effective = first.get("partner_id")
    await db.partner_attribution_conflicts.insert_one(dict(conflict))
    conflict.pop("_id", None)
    return {"partner_id": effective, "model": model, "conflict": conflict}


# ------------------------------------------------------------------ statistik mitra
async def refresh_stats(partner_id: str, *, org_id: str = ORG_ID) -> dict:
    """Denormalisasi angka mitra (dihitung dari data, bukan dijumlah manual di UI)."""
    base = {"org_id": org_id, "partner_id": partner_id}
    leads = await db.leads.find(base, {"_id": 0, "id": 1, "stage": 1, "created_at": 1,
                                       "first_contact_at": 1}).to_list(5000)
    lead_ids = [l["id"] for l in leads]
    deals = await db.deals.find(
        {"org_id": org_id, "$or": [{"partner_id": partner_id},
                                   {"lead_id": {"$in": lead_ids}}]},
        {"_id": 0, "status": 1, "price": 1}).to_list(5000)
    fees = await db.marketing_fees.find(
        {"org_id": org_id, "agent_id": partner_id}, {"_id": 0, "status": 1, "amount_net": 1,
                                                     "paid_amount": 1}).to_list(5000)
    approved = [f for f in fees if f.get("status") in ("approved", "paid")]
    stats = {
        "leads": len(leads),
        "contacted": sum(1 for l in leads if l.get("first_contact_at")),
        "qualified": sum(1 for l in leads if l.get("stage") in
                         ("appointment", "booking", "won")),
        "booked": sum(1 for d in deals if d.get("status") in ("booked", "completed")),
        "won": sum(1 for l in leads if l.get("stage") == "won"),
        "revenue": sum(int(d.get("price") or 0) for d in deals
                       if d.get("status") in ("booked", "completed")),
        "fee_submitted": sum(1 for f in fees if f.get("status") == "submitted"),
        "fee_total": sum(int(f.get("amount_net") or 0) for f in approved),
        "fee_paid": sum(int(f.get("paid_amount") or 0) for f in approved),
        "last_lead_at": max([l.get("created_at") for l in leads], default=None),
        "refreshed_at": now_iso(),
    }
    stats["fee_outstanding"] = stats["fee_total"] - stats["fee_paid"]
    await db.agents.update_one({"id": partner_id, "org_id": org_id},
                              {"$set": {"stats": stats, "fee_total": stats["fee_total"],
                                        "fee_paid": stats["fee_paid"],
                                        "deals_count": stats["booked"],
                                        "updated_at": now_iso()}})
    return stats
