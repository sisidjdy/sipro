"""SPR vs Tagihan Finance — pembanding angka per baris sebelum SPR ditandatangani.

SPR menyimpan `amounts_snapshot` (angka numerik saat terbit). Finance dibaca LANGSUNG dari
AR (termin unit + add-on) dan invoice biaya (INB). Selisih = SPR sudah basi (skema/harga
berubah setelah terbit) → terbitkan ulang, jangan ditandatangani.
"""
import contracts_engine as ce
import docgen
from core_utils import new_id, now_iso
from db import ORG_NAME, db

ADENDUM_CODE = "ADENDUM_SPR"
# Rantai dokumen harga satu deal: SPR + adendumnya. Yang TERBARU adalah yang berlaku.
CHAIN_CODES = docgen.SPR_CODES + (ADENDUM_CODE,)


def _rp(v) -> str:
    return "—" if v is None else f"Rp {int(v):,}".replace(",", ".")


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
        "scheme_name": ((plan.get("scheme") or {}).get("name")) or contract.get("payment_scheme_name"),
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
        {"org_id": org, "deal_id": deal_id, "template_code": {"$in": list(CHAIN_CODES)}},
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
    legacy = await db.documents.count_documents({"org_id": org, "deal_id": deal_id, "template_code": "SPR"})
    signed = bool(doc and doc.get("status") == "signed")
    if not doc:
        state, verdict = "belum_terbit", ("SPR resmi belum diterbitkan — angka di kolom SPR adalah pratinjau "
                                          "dari kontrak & skema saat ini."
                                          + (f" ({legacy} SPR generik lama ada pada deal ini; bukan pembanding — "
                                             "terbitkan SPR resmi dari kontrak.)" if legacy else ""))
    elif not mismatches:
        state, verdict = "cocok", ("Semua baris SPR sama dengan tagihan Finance"
                                   + (" — aman ditandatangani." if not signed else "."))
    elif signed:
        state, verdict = "beda_sudah_ttd", (f"{len(mismatches)} baris BERBEDA padahal SPR sudah ditandatangani — "
                                            "adendum wajib (dibuat otomatis saat skema diganti); dokumen "
                                            "yang sudah ditandatangani tidak ditimpa.")
    else:
        state, verdict = "beda", (f"{len(mismatches)} baris BERBEDA — JANGAN tandatangani; terbitkan ulang SPR "
                                  "dari kontrak (angka Finance yang berlaku).")
    return {
        "state": state, "verdict": verdict, "all_match": not mismatches, "mismatch_count": len(mismatches),
        "provisional": provisional, "legacy_spr_count": legacy,
        "signed": signed, "spr_source": source,
        "contract": {"id": contract["id"], "scheme": contract.get("scheme"),
                     "payment_scheme_name": contract.get("payment_scheme_name")},
        "document": ({"id": doc["id"], "doc_number": doc.get("doc_number"), "title": doc.get("title"),
                      "template_code": doc.get("template_code"), "status": doc.get("status"),
                      "created_at": doc.get("created_at"), "has_snapshot": bool(doc.get("amounts_snapshot")),
                      "is_addendum": doc.get("template_code") == ADENDUM_CODE,
                      "parent_doc_number": doc.get("parent_doc_number")}
                     if doc else None),
        "older_documents": len(docs) - 1 if docs else 0,
        "spr": spr, "finance": fin, "rows": rows,
    }


async def sign_block_reason(org: str, doc: dict):
    """Alasan SPR TIDAK boleh ditandatangani (None bila boleh)."""
    if doc.get("template_code") not in CHAIN_CODES or not doc.get("amounts_snapshot"):
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


# ============================================================ adendum otomatis
ADENDUM_TEMPLATE_NAME = "Adendum SPR — Perubahan Skema Pembayaran"


async def ensure_addendum_template(org: str) -> None:
    """Template ADENDUM_SPR di master dokumen (agar tampil di filter/daftar). Idempoten."""
    ts = now_iso()
    await db.document_templates.update_one(
        {"org_id": org, "code": ADENDUM_CODE},
        {"$setOnInsert": {"id": new_id(), "org_id": org, "code": ADENDUM_CODE,
                          "name": ADENDUM_TEMPLATE_NAME, "scheme": None, "doc_code": "ADD-SPR",
                          "content": "(dibangkitkan otomatis — tabel selisih lama vs baru)",
                          "version": 1, "is_active": True, "generator": True,
                          "created_by": "system", "created_at": ts, "updated_at": ts}},
        upsert=True)


def _cell(row: dict, side: str) -> str:
    v = row.get(side)
    if row.get("kind") == "count":
        return f"{v if v is not None else '—'} termin"
    s = _rp(v)
    due = row.get(f"{side}_due")
    return f"{s} (jt {due})" if due else s


def addendum_content(*, number: str, spr: dict, contract: dict, customer: dict, unit: dict,
                     project: dict, old_scheme: str, new_scheme: str, reason: str,
                     diff: list, new_total: int) -> str:
    """Naskah adendum: baris 'Label : Nilai' dirender sebagai tabel oleh pdf_utils."""
    lines = [
        f"Nomor adendum : {number}",
        f"Mengubah SPR : {spr.get('doc_number')} (ditandatangani {str(spr.get('first_signed_at') or spr.get('updated_at') or '')[:10]})",
        f"Pembeli : {customer.get('name') or '—'}",
        f"Unit : {unit.get('code') or '—'}{(' — ' + project['name']) if project.get('name') else ''}",
        f"Skema pembayaran lama : {old_scheme or '—'}",
        f"Skema pembayaran baru : {new_scheme or '—'}",
        f"Alasan perubahan : {reason or '—'}",
        "",
        "Para pihak sepakat mengubah ketentuan pembayaran dalam SPR tersebut sebagai berikut "
        "(angka LAMA → BARU):",
        "",
    ]
    for r in diff:
        lines.append(f"{r['label']} : {_cell(r, 'spr')}  →  {_cell(r, 'finance')}")
    lines += [
        "",
        f"Total kewajiban pembeli setelah adendum : {_rp(new_total)}",
        "",
        "Ketentuan lain dalam SPR yang tidak diubah oleh adendum ini tetap berlaku sepenuhnya. "
        "Adendum ini merupakan satu kesatuan yang tidak terpisahkan dari SPR di atas dan mulai "
        "berlaku sejak ditandatangani kedua pihak.",
        f"Tanggal dokumen : {now_iso()[:10]}",
        f"Penerbit : {project.get('developer_name') or ORG_NAME}",
    ]
    return "\n".join(lines)


async def ensure_addendum(org: str, deal_id: str, actor: str, reason: str):
    """Skema/angka berubah SETELAH SPR ditandatangani → adendum (draft) dengan tabel selisih.

    Dokumen yang ditandatangani tidak pernah ditimpa. Idempoten: adendum draft yang belum
    ditandatangani diperbarui isinya (tidak lahir adendum kembar); bila tak ada selisih → None.
    """
    contract = await db.contracts.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})
    if not contract:
        return None
    chain = await db.documents.find(
        {"org_id": org, "deal_id": deal_id, "template_code": {"$in": list(CHAIN_CODES)}},
        {"_id": 0, "content": 0, "context_snapshot": 0}).sort("created_at", -1).to_list(20)
    signed = next((d for d in chain if d.get("status") == "signed" and d.get("amounts_snapshot")), None)
    if not signed:
        return None
    fin = await finance_amounts(org, deal_id)
    if not fin["exists"]:
        return None
    diff = [r for r in compare_rows(signed["amounts_snapshot"], fin) if not r["match"]]
    latest = chain[0]
    draft = latest if (latest.get("template_code") == ADENDUM_CODE
                       and latest.get("status") != "signed") else None
    if not diff:
        if draft:
            # Angka kembali sama dengan SPR yang ditandatangani → adendum draft tidak relevan.
            await db.documents.delete_one({"id": draft["id"]})
            from engine import add_activity
            await add_activity(entity_type="deal", entity_id=deal_id, type="document",
                               body=f"Adendum draft {draft.get('doc_number')} dibatalkan otomatis: angka "
                                    f"kembali sama dengan SPR {signed.get('doc_number')}.",
                               actor=actor, org_id=org)
        return None
    await ensure_addendum_template(org)
    tpl = await db.document_templates.find_one({"org_id": org, "code": ADENDUM_CODE}, {"_id": 0})
    project = await db.projects.find_one({"id": contract.get("project_id")}, {"_id": 0}) or {}
    unit = await db.units.find_one({"id": contract.get("unit_id")}, {"_id": 0, "code": 1}) or {}
    cust = await db.customers.find_one({"id": contract.get("customer_id")}, {"_id": 0, "name": 1}) or {}
    old_scheme = ((signed.get("amounts_snapshot") or {}).get("scheme_name")
                  or (signed.get("context_snapshot") or {}).get("scheme_name")
                  or ((signed.get("payment_scheme_name_at_issue")) or "skema pada SPR"))
    new_snapshot = await spr_amounts(org, contract)
    new_snapshot["scheme_name"] = contract.get("payment_scheme_name") or fin.get("scheme_name")
    number = draft["doc_number"] if draft else await docgen.next_doc_number(org, ADENDUM_CODE, project)
    content = addendum_content(number=number, spr=signed, contract=contract, customer=cust, unit=unit,
                               project=project, old_scheme=old_scheme, new_scheme=new_snapshot["scheme_name"],
                               reason=reason, diff=diff, new_total=fin["total_bill"])
    ts = now_iso()
    fields = {
        "content": content, "amounts_snapshot": new_snapshot, "diff_rows": diff,
        "parent_document_id": signed["id"], "parent_doc_number": signed.get("doc_number"),
        "reason": reason, "updated_at": ts,
    }
    if draft:
        await db.documents.update_one({"id": draft["id"]}, {"$set": fields})
        doc = await db.documents.find_one({"id": draft["id"]}, {"_id": 0})
        created = False
    else:
        doc = {
            "id": new_id(), "org_id": org, "template_id": (tpl or {}).get("id"),
            "template_code": ADENDUM_CODE, "template_version": int((tpl or {}).get("version") or 1),
            "doc_number": number, "title": f"Adendum SPR {signed.get('doc_number')}",
            "deal_id": deal_id, "contract_id": contract["id"], "lead_id": contract.get("lead_id"),
            "customer_id": contract.get("customer_id"), "unit_id": contract.get("unit_id"),
            "assigned_to": contract.get("assigned_to"), "status": "draft", "signatures": [],
            "auto_generated": True, "created_by": actor, "created_at": ts, **fields,
        }
        await db.documents.insert_one(dict(doc))
        doc.pop("_id", None)
        created = True
    from engine import add_activity
    await add_activity(entity_type="deal", entity_id=deal_id, type="document",
                       body=(f"Adendum {number} {'dibuat' if created else 'diperbarui'} otomatis: "
                             f"{len(diff)} angka SPR {signed.get('doc_number')} berubah ({reason})."),
                       actor=actor, org_id=org)
    return {"document": doc, "created": created, "diff_count": len(diff)}
