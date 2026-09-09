"""Riwayat dokumen terbit per lead/customer (Fase 91).

Satu tampilan untuk semua dokumen yang DIGENERATE sistem sepanjang perjalanan transaksi
(Booking → SPR → Tagihan & Kwitansi → Pajak & Biaya → Legal → BAST), lengkap dengan
aksi cepat penerbitan dan ALASAN jelas bila belum bisa diterbitkan."""
import contracts_engine as ce
import docgen
import reference as ref
from db import db, ORG_ID


def _rp(v) -> str:
    return "Rp " + f"{int(v or 0):,}".replace(",", ".")


def _doc(kind, label, number, status, at, actor, pdf=None, href=None, amount=None, note=None):
    return {"kind": kind, "label": label, "number": number, "status": status, "issued_at": at,
            "actor": actor or "sistem", "pdf_url": pdf, "href": href, "amount": amount, "note": note}


def _action(key, label, enabled, reason=None, href=None, method=None, endpoint=None, body=None):
    return {"key": key, "label": label, "enabled": bool(enabled), "reason": reason,
            "href": href, "method": method, "endpoint": endpoint, "body": body}


async def _deals_for(org: str, entity_type: str, entity_id: str) -> list:
    if entity_type == "lead":
        return await db.deals.find({"org_id": org, "lead_id": entity_id}, {"_id": 0}).to_list(50)
    cust = await db.customers.find_one({"id": entity_id, "org_id": org}, {"_id": 0}) or {}
    ors = [{"customer_id": entity_id}]
    if cust.get("lead_id"):
        ors.append({"lead_id": cust["lead_id"]})
    if cust.get("deal_id"):
        ors.append({"id": cust["deal_id"]})
    return await db.deals.find({"org_id": org, "$or": ors}, {"_id": 0}).to_list(50)


async def _deal_history(org: str, deal: dict, entity_type: str, entity_id: str) -> dict:
    did = deal["id"]
    unit_code = deal.get("unit_code") or "-"
    contract = await db.contracts.find_one({"org_id": org, "deal_id": did}, {"_id": 0})
    ar = await db.ar_invoices.find_one({"org_id": org, "deal_id": did}, {"_id": 0})
    receipts = await db.receipts.find({"org_id": org, "deal_id": did}, {"_id": 0}).sort("created_at", 1).to_list(200)
    documents = await db.documents.find({"org_id": org, "deal_id": did}, {"_id": 0, "content": 0, "context_snapshot": 0}).sort("created_at", 1).to_list(100)
    fakturs = await db.faktur_pajak.find({"org_id": org, "deal_id": did}, {"_id": 0}).sort("created_at", 1).to_list(20)
    handovers = await db.unit_handovers.find({"org_id": org, "$or": [{"deal_id": did}, {"unit_id": deal.get("unit_id")}]}, {"_id": 0}).to_list(10)
    refunds = await db.receipts.find({"org_id": org, "deal_id": did, "kind": "booking_fee_refund"}, {"_id": 0}).to_list(10)
    cost_invoices, cost_receipts = [], []
    if contract:
        cost_invoices = await db.cost_invoices.find({"org_id": org, "contract_id": contract["id"]}, {"_id": 0}).to_list(50)
        cost_receipts = await db.cost_receipts.find({"org_id": org, "contract_id": contract["id"]}, {"_id": 0}).to_list(100)

    profile_href = f"/leads/{entity_id}" if entity_type == "lead" else f"/customers/{entity_id}"
    ar_href = f"/finance?tab=receivables&sub=ar&q={unit_code}"
    stages = []

    # 1. Booking
    docs, actions = [], []
    bf_inv = await db.booking_fee_invoices.find_one({"org_id": org, "deal_id": did}, {"_id": 0})
    if bf_inv:
        docs.append(_doc("booking_invoice", "Invoice booking fee", bf_inv.get("number"), bf_inv.get("status"),
                         bf_inv.get("created_at"), bf_inv.get("created_by"),
                         pdf=f"/booking-fee/deals/{did}/invoice/pdf", amount=bf_inv.get("amount"),
                         note=f"Terbayar {_rp(bf_inv.get('paid'))} · sisa {_rp(bf_inv.get('outstanding'))}"))
    elif deal.get("booking_fee"):
        docs.append(_doc("booking_fee", "Booking fee (tercatat di reservasi)", None, deal.get("status"),
                         deal.get("booked_at") or deal.get("reserved_at"), deal.get("created_by"),
                         amount=deal.get("booking_fee"), note="Tanpa invoice terpisah — dibuat sebelum modul tagihan booking fee."))
    for r in refunds:
        docs.append(_doc("booking_refund", "Bukti refund booking fee", r.get("number"), r.get("status"), r.get("created_at"),
                         r.get("created_by"), pdf=f"/booking-fee/deals/{did}/refunds/{r['id']}/pdf", amount=r.get("amount")))
    if deal.get("status") == "cancelled":
        actions.append(_action("booking", "Deal dibatalkan", False, "Deal ini sudah dibatalkan; tidak ada dokumen baru yang bisa terbit."))
    elif not deal.get("booking_fee"):
        actions.append(_action("booking", "Terbitkan invoice booking fee", False,
                               "Booking fee belum ditetapkan pada reservasi ini.", href=f"{profile_href}?tab=unit"))
    stages.append({"key": "booking", "label": "Booking & Reservasi",
                   "description": "Unit dipesan; invoice booking fee terbit otomatis dari reservasi.",
                   "state": "done" if deal.get("status") in ("booked", "won", "sold") else ("blocked" if deal.get("status") == "cancelled" else "active"),
                   "docs": docs, "actions": actions})

    # 2. SPR / dokumen owner
    docs, actions = [], []
    for d in documents:
        docs.append(_doc("document", d.get("title") or d.get("template_code"), d.get("doc_number"), d.get("status"),
                         d.get("created_at"), d.get("created_by"), pdf=f"/documents/{d['id']}/pdf", href=f"/documents?q={d.get('doc_number') or ''}"))
    if not contract:
        actions.append(_action("spr", "Terbitkan SPR", False,
                               "Deal belum dikonversi menjadi kontrak. Konversi dulu dari tab Unit & SPR (lead) atau Customer & Kontrak.",
                               href=f"{profile_href}?tab=unit" if entity_type == "lead" else f"{profile_href}?tab=kontrak53"))
    else:
        for a in await docgen.applicable(org, contract):
            if a["existing"] and a["can_generate"]:
                reason = f"Sudah terbit {a['existing']}× — terbitkan ulang hanya bila ada revisi."
            elif a["existing"]:
                reason = (f"Sudah terbit {a['existing']}×. Terbit ulang terhalang: "
                          + " ".join(b["detail"] for b in a["blocks"]))
            else:
                reason = " ".join(b["detail"] for b in a["blocks"]) or None
            actions.append(_action(f"gen:{a['code']}", f"Terbitkan {a['name']}", a["can_generate"], reason,
                                   method="POST", endpoint=f"/contracts/{contract['id']}/documents",
                                   body={"template_code": a["code"]}))
    stages.append({"key": "spr", "label": "SPR & Dokumen Owner",
                   "description": "Surat Pesanan Rumah dan dokumen pendamping dari template owner; angka murni dari kontrak.",
                   "state": "done" if documents else ("active" if contract else "locked"),
                   "docs": docs, "actions": actions})

    # 3. Tagihan & kwitansi
    docs, actions = [], []
    if ar:
        docs.append(_doc("ar_invoice", "Invoice / jadwal tagihan", None, ar.get("status"), ar.get("created_at"), ar.get("created_by"),
                         pdf=f"/finance/ar/{did}/invoice/pdf", href=ar_href, amount=ar.get("total"),
                         note=f"Terbayar {_rp(ar.get('paid'))} · sisa {_rp(ar.get('outstanding'))}"))
        for r in receipts:
            labels = ", ".join(a.get("label", "") for a in (r.get("allocations") or []))
            docs.append(_doc("receipt", "Kwitansi pembayaran", r.get("receipt_no"), "issued", r.get("created_at"), r.get("actor"),
                             pdf=f"/finance/ar/receipts/{r['id']}/pdf", amount=r.get("amount"), note=labels or r.get("note")))
        if int(ar.get("outstanding") or 0) > 0:
            actions.append(_action("receipt", "Terima pembayaran (kwitansi)", True, None, href=ar_href))
        else:
            actions.append(_action("receipt", "Terima pembayaran", False, "Seluruh tagihan sudah lunas.", href=ar_href))
    else:
        actions.append(_action("ar", "Buat jadwal tagihan", False,
                               "Jadwal AR dibuat otomatis saat unit di-booking (bayar booking fee).", href=f"{profile_href}?tab=unit"))
    stages.append({"key": "billing", "label": "Tagihan & Kwitansi",
                   "description": "Invoice termin dan kwitansi setiap penerimaan pembayaran.",
                   "state": "done" if ar and int(ar.get("outstanding") or 0) == 0 else ("active" if ar else "locked"),
                   "docs": docs, "actions": actions})

    # 4. Pajak & biaya all-in
    docs, actions = [], []
    for f in fakturs:
        docs.append(_doc("faktur", "Faktur pajak keluaran", f.get("number"), f.get("status"), f.get("issued_at") or f.get("created_at"),
                         f.get("issued_by"), pdf=f"/tax/faktur/{f['id']}/pdf", href="/tax", amount=(f.get("dpp") or 0) + (f.get("ppn") or 0)))
    for ci in cost_invoices:
        docs.append(_doc("cost_invoice", f"Invoice biaya {ci.get('component_label') or ci.get('component') or 'all-in'}", ci.get("number"),
                         ci.get("status"), ci.get("created_at"), ci.get("created_by"), pdf=f"/cost-invoices/{ci['id']}/pdf", amount=ci.get("amount")))
    for cr in cost_receipts:
        docs.append(_doc("cost_receipt", "Kwitansi biaya all-in", cr.get("number"), "issued", cr.get("created_at"), cr.get("created_by"),
                         pdf=f"/cost-receipts/{cr['id']}/pdf", amount=cr.get("amount")))
    active_faktur = any(f.get("status") in (None, "issued") for f in fakturs)
    if active_faktur:
        actions.append(_action("faktur", "Terbitkan faktur pajak", False, "Faktur pajak aktif sudah terbit untuk deal ini.", href="/tax"))
    elif not ar:
        actions.append(_action("faktur", "Terbitkan faktur pajak", False, "Belum ada tagihan AR — faktur dibuat dari nilai tagihan.", href="/tax"))
    else:
        actions.append(_action("faktur", "Terbitkan faktur pajak", True, None, href="/tax"))
    if contract:
        costs = (contract.get("costs") or {})
        if not costs:
            actions.append(_action("cost", "Terbitkan invoice biaya (BPHTB/notaris)", False,
                                   "Komponen biaya all-in belum diisi pada kontrak.", href=f"/customers/{contract.get('customer_id')}?tab=kontrak53" if contract.get("customer_id") else None))
        else:
            actions.append(_action("cost", "Terbitkan invoice biaya (BPHTB/notaris)", True, None,
                                   href=f"/customers/{contract.get('customer_id')}?tab=kontrak53" if contract.get("customer_id") else None))
    stages.append({"key": "tax", "label": "Pajak & Biaya All-in",
                   "description": "Faktur pajak keluaran serta invoice/kwitansi komponen biaya (BPHTB, notaris, dll.).",
                   "state": "done" if fakturs else ("active" if ar else "locked"), "docs": docs, "actions": actions})

    # 5. Legal
    docs, actions = [], []
    legal = (contract or {}).get("legal") or {}
    for st in ce.LEGAL_ORDER:
        v = legal.get(st)
        if v:
            docs.append(_doc("legal", ref.label_of("legal_stage", st), (v.get("number") if isinstance(v, dict) else None),
                             "done", (v.get("at") or v.get("date")) if isinstance(v, dict) else None,
                             (v.get("by") if isinstance(v, dict) else None)))
    next_stage = next((s for s in ce.LEGAL_ORDER if not legal.get(s)), None)
    if not contract:
        actions.append(_action("legal", "Catat tahap legal", False, "Belum ada kontrak.", href=None))
    elif next_stage:
        actions.append(_action("legal", f"Catat {ref.label_of('legal_stage', next_stage)}", True, None,
                               href=f"/customers/{contract.get('customer_id')}?tab=kontrak53" if contract.get("customer_id") else profile_href))
    stages.append({"key": "legal", "label": "Legal (PPJB / Akad / AJB)",
                   "description": "Tahapan legal kontrak; tiap tahap dicatat berurutan.",
                   "state": "done" if contract and not next_stage else ("active" if legal else "locked"),
                   "docs": docs, "actions": actions})

    # 6. BAST
    docs, actions = [], []
    for h in handovers:
        docs.append(_doc("bast", "Berita Acara Serah Terima (BAST)", h.get("number"), h.get("status"), h.get("created_at"),
                         h.get("issued_by"), pdf=f"/handover/{h['id']}/pdf", href=f"/units/{h.get('unit_id')}"))
    sisa = int((ar or {}).get("outstanding") or 0)
    if handovers:
        actions.append(_action("bast", "Terbitkan BAST", False, "BAST sudah terbit untuk unit ini.", href=f"/units/{deal.get('unit_id')}"))
    elif not ar:
        actions.append(_action("bast", "Terbitkan BAST", False, "Belum ada tagihan — BAST menunggu transaksi berjalan.", href=None))
    elif sisa > 0:
        actions.append(_action("bast", "Terbitkan BAST", False,
                               f"Sisa tagihan {_rp(sisa)} belum lunas — BAST hanya bisa diterbitkan setelah pelunasan.", href=ar_href))
    else:
        actions.append(_action("bast", "Terbitkan BAST", True, None, href=f"/units/{deal.get('unit_id')}"))
    stages.append({"key": "bast", "label": "Serah Terima (BAST)",
                   "description": "Berita acara serah terima kunci; memicu pengakuan pendapatan.",
                   "state": "done" if handovers else ("active" if ar and sisa == 0 else "locked"),
                   "docs": docs, "actions": actions})

    total_docs = sum(len(s["docs"]) for s in stages)
    return {"deal_id": did, "unit_code": unit_code, "deal_status": deal.get("status"),
            "project_id": deal.get("project_id"), "contract_id": (contract or {}).get("id"),
            "contract_number": (contract or {}).get("number"), "total_docs": total_docs, "stages": stages}


async def history(org: str, entity_type: str, entity_id: str) -> dict:
    import wa_docs
    out = await _history(org, entity_type, entity_id)
    out["wa_send"] = await wa_docs.eligibility(org, entity_type, entity_id)
    out["wa_shares"] = await wa_docs.shares(org, entity_type, entity_id)
    return out


async def _history(org: str, entity_type: str, entity_id: str) -> dict:
    org = org or ORG_ID
    deals = await _deals_for(org, entity_type, entity_id)
    deals.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    items = [await _deal_history(org, d, entity_type, entity_id) for d in deals]
    return {"entity_type": entity_type, "entity_id": entity_id, "deals": items,
            "total_docs": sum(i["total_docs"] for i in items)}
