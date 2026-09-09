"""SPR vs Tagihan Finance — pembanding angka per baris sebelum SPR ditandatangani.

SPR menyimpan `amounts_snapshot` (angka numerik saat terbit). Finance dibaca LANGSUNG dari
AR (termin unit + add-on) dan invoice biaya (INB). Selisih = SPR sudah basi (skema/harga
berubah setelah terbit) → terbitkan ulang, jangan ditandatangani.
"""
import contracts_engine as ce
import docgen
from db import db


def _terms(rows: list) -> list:
    return [{"label": t.get("label"), "amount": int(t.get("amount") or 0),
             "due_date": (str(t.get("due_date"))[:10] if t.get("due_date") else None)}
            for t in rows]


async def spr_amounts(org: str, contract: dict) -> dict:
    """Angka SPR numerik — sumber yang sama dengan `docgen.build_context`."""
    bd = await ce.build_breakdown(org, contract)
    plan = await ce.payment_plan(org, contract)
    if plan.get("state") != "ada":
        spec = await ce.scheme_terms_spec(org, contract.get("scheme"), contract)
        plan["rules_full"] = spec.get("items") or []
    unit_terms, addon_terms = docgen.split_terms(plan)
    costs = [{"code": r["code"], "label": r["label"], "amount": int(r.get("amount") or 0),
              "developer_borne": r.get("finance_treatment") == "developer_borne",
              "state": r.get("state")}
             for r in bd["rows"] if r.get("group") == "biaya" and r.get("state") != "not_applicable"]
    return {
        "unit_price": int(bd.get("gross_price") or 0),
        "promo_discount": int(bd.get("promo_discount") or 0),
        # Harga bersih UNIT saja (add-on kontrak dipisah) — sebanding dengan `ar_invoices.price`.
        "nett_price": int(bd.get("nett_price") or 0) - int(bd.get("addon_total") or 0),
        "booking_fee": int(bd.get("booking_fee") or 0),
        "dp_pct": docgen.dp_percent(unit_terms),
        "terms": _terms(unit_terms), "addons": _terms(addon_terms),
        "terms_total": sum(int(t.get("amount") or 0) for t in unit_terms),
        "addon_total": sum(int(t.get("amount") or 0) for t in addon_terms),
        "costs": costs,
        "costs_total": int(bd.get("costs_total") or 0),
        "total_bill": int(bd.get("total_bill") or 0),
        "terms_from_ar": plan.get("state") == "ada",
    }


async def finance_amounts(org: str, deal_id: str) -> dict:
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0}) or {}
    items = inv.get("items") or []
    unit = [i for i in items if i.get("basis") != "addon" and not i.get("addon_code")]
    addon = [i for i in items if i.get("basis") == "addon" or i.get("addon_code")]
    cis = await db.cost_invoices.find({"org_id": org, "deal_id": deal_id,
                                       "status": {"$ne": "void"}}, {"_id": 0}).to_list(20)
    costs = [{"code": it.get("code"), "label": it.get("name"), "amount": int(it.get("amount") or 0),
              "invoice_number": ci.get("number")} for ci in cis for it in (ci.get("items") or [])]
    deal = await db.deals.find_one({"id": deal_id, "org_id": org}, {"_id": 0}) or {}
    bd = inv.get("breakdown") or {}
    unit_total = sum(int(i.get("amount") or 0) for i in unit)
    addon_total = sum(int(i.get("amount") or 0) for i in addon)
    cost_total = sum(c["amount"] for c in costs)
    return {
        "exists": bool(inv), "invoice_id": inv.get("id"), "scheme_name": inv.get("scheme_name"),
        "nett_price": int(inv.get("price") or deal.get("price") or 0),
        "booking_fee": int(deal.get("booking_fee") or bd.get("booking_fee") or 0),
        "terms": _terms(unit), "addons": _terms(addon),
        "terms_total": unit_total, "addon_total": addon_total,
        "costs": costs, "costs_total": cost_total,
        "cost_invoice_numbers": [ci.get("number") for ci in cis],
        "total_bill": unit_total + addon_total + cost_total,
        "paid": int(inv.get("paid") or 0),
    }


def _row(key, label, spr, fin, kind="money"):
    return {"key": key, "label": label, "spr": spr, "finance": fin, "kind": kind,
            "match": (spr or 0) == (fin or 0) if kind == "money" else spr == fin}


def compare_rows(spr: dict, fin: dict) -> list:
    rows = [_row("nett_price", "Harga bersih unit (dasar termin)", spr.get("nett_price"), fin.get("nett_price")),
            _row("booking_fee", "Booking fee", spr.get("booking_fee"), fin.get("booking_fee"))]
    st, ft = spr.get("terms") or [], fin.get("terms") or []
    rows.append(_row("terms_count", "Jumlah termin unit", len(st), len(ft), kind="count"))
    for i in range(max(len(st), len(ft))):
        a, b = (st[i] if i < len(st) else {}), (ft[i] if i < len(ft) else {})
        label = f"Termin {i + 1} · {a.get('label') or b.get('label') or '-'}"
        r = _row(f"term_{i + 1}", label, a.get("amount"), b.get("amount"))
        r["spr_due"], r["finance_due"] = a.get("due_date"), b.get("due_date")
        r["label_match"] = (a.get("label") == b.get("label")) if a and b else False
        r["match"] = r["match"] and r["label_match"]
        rows.append(r)
    rows.append(_row("terms_total", "Total termin unit", spr.get("terms_total"), fin.get("terms_total")))
    if (spr.get("addons") or fin.get("addons")):
        sa = {x["label"]: x["amount"] for x in spr.get("addons") or []}
        fa = {x["label"]: x["amount"] for x in fin.get("addons") or []}
        for label in list(sa) + [k for k in fa if k not in sa]:
            rows.append(_row(f"addon_{label}", f"Add-on · {label}", sa.get(label), fa.get(label)))
        rows.append(_row("addon_total", "Total add-on (tagihan terpisah)", spr.get("addon_total"), fin.get("addon_total")))
    sc = {c["code"]: c for c in spr.get("costs") or []}
    fc = {c["code"]: c for c in fin.get("costs") or []}
    for code in list(sc) + [k for k in fc if k not in sc]:
        a, b = sc.get(code) or {}, fc.get(code) or {}
        if a.get("developer_borne") and not b:
            # Ditanggung developer: tercetak informatif di SPR, tidak ditagih ke pembeli.
            rows.append({"key": f"cost_{code}", "label": f"Biaya · {a.get('label')} (developer)",
                         "spr": a.get("amount"), "finance": 0, "kind": "money", "match": True,
                         "note": "ditanggung developer — tidak ditagih"})
            continue
        r = _row(f"cost_{code}", f"Biaya · {a.get('label') or b.get('label') or code}",
                 a.get("amount"), b.get("amount"))
        if a.get("state") == "empty" and not b:
            # Belum ditetapkan di kontrak & belum ditagih Finance: bukan selisih angka, tetapi
            # total SPR masih SEMENTARA — ditandai, tidak memblokir tanda tangan.
            r["match"], r["provisional"] = True, True
            r["note"] = "belum ditetapkan — belum ditagih (total SPR sementara)"
        rows.append(r)
    rows.append(_row("costs_total", "Total biaya pembeli", spr.get("costs_total"), fin.get("costs_total")))
    rows.append(_row("total_bill", "TOTAL dibayar pembeli", spr.get("total_bill"), fin.get("total_bill")))
    return rows


async def compare(org: str, deal_id: str) -> dict:
    contract = await db.contracts.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})
    docs = await db.documents.find(
        {"org_id": org, "deal_id": deal_id, "template_code": {"$in": list(docgen.SPR_CODES)}},
        {"_id": 0, "content": 0, "context_snapshot": 0}).sort("created_at", -1).to_list(10)
    doc = docs[0] if docs else None
    fin = await finance_amounts(org, deal_id)
    if not contract:
        return {"state": "tanpa_kontrak", "contract": None, "document": None, "finance": fin,
                "spr": None, "rows": [], "all_match": None,
                "reason": "Belum ada kontrak — SPR resmi lahir dari kontrak (Jadikan Pembeli dulu)."}
    if doc and doc.get("amounts_snapshot"):
        spr, source = doc["amounts_snapshot"], "snapshot"
    else:
        spr, source = await spr_amounts(org, contract), "live"
    rows = compare_rows(spr, fin)
    mismatches = [r for r in rows if not r["match"]]
    provisional = [r["label"] for r in rows if r.get("provisional")]
    signed = bool(doc and doc.get("status") == "signed")
    if not doc:
        state, verdict = "belum_terbit", ("SPR belum diterbitkan — angka di kolom SPR adalah pratinjau "
                                          "dari kontrak & skema saat ini.")
    elif not mismatches:
        state, verdict = "cocok", ("Semua baris SPR sama dengan tagihan Finance"
                                   + (" — aman ditandatangani." if not signed else "."))
    elif signed:
        state, verdict = "beda_sudah_ttd", (f"{len(mismatches)} baris BERBEDA padahal SPR sudah ditandatangani — "
                                            "terbitkan adendum, jangan menimpa dokumen.")
    else:
        state, verdict = "beda", (f"{len(mismatches)} baris BERBEDA — JANGAN tandatangani; terbitkan ulang SPR "
                                  "dari kontrak (angka Finance yang berlaku).")
    return {
        "state": state, "verdict": verdict, "all_match": not mismatches, "mismatch_count": len(mismatches),
        "provisional": provisional,
        "signed": signed, "spr_source": source,
        "contract": {"id": contract["id"], "scheme": contract.get("scheme"),
                     "payment_scheme_name": contract.get("payment_scheme_name")},
        "document": ({"id": doc["id"], "doc_number": doc.get("doc_number"), "title": doc.get("title"),
                      "template_code": doc.get("template_code"), "status": doc.get("status"),
                      "created_at": doc.get("created_at"), "has_snapshot": bool(doc.get("amounts_snapshot"))}
                     if doc else None),
        "older_documents": len(docs) - 1 if docs else 0,
        "spr": spr, "finance": fin, "rows": rows,
    }


async def sign_block_reason(org: str, doc: dict):
    """Alasan SPR TIDAK boleh ditandatangani (None bila boleh)."""
    if doc.get("template_code") not in docgen.SPR_CODES or not doc.get("amounts_snapshot"):
        return None
    fin = await finance_amounts(org, doc["deal_id"])
    if not fin["exists"]:
        return None
    bad = [r for r in compare_rows(doc["amounts_snapshot"], fin) if not r["match"]]
    if not bad:
        return None
    return (f"SPR {doc.get('doc_number')} berbeda dengan tagihan Finance pada {len(bad)} baris "
            f"({', '.join(r['label'] for r in bad[:3])}{'…' if len(bad) > 3 else ''}). "
            "Terbitkan ulang SPR dari kontrak sebelum ditandatangani.")
