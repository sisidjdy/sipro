"""PENAWARAN & SIMULASI HARGA (Fase 47C) — angka yang dijanjikan ke pembeli bisa direkonstruksi.

Cacat yang ditutup: tidak ada penawaran di sistem. Sales menghitung harga + add-on + termin
di luar aplikasi (kertas/WhatsApp/spreadsheet), sehingga:
  * angka yang dijanjikan ke calon pembeli tidak bisa dibuktikan ulang,
  * diskon diberikan tanpa jejak dan tanpa batas kewenangan,
  * saat berubah menjadi reservasi/SPR, tidak ada yang bisa membandingkan "yang dijanjikan"
    dengan "yang ditagihkan".

Aturan yang dipegang modul ini:

  1. **Tidak ada rumus kedua.** Termin penawaran dihitung dengan `finance_engine
     .compute_scheme_items` — fungsi yang SAMA dengan yang membuat AR saat deal jadi. Kalau
     rumusnya berbeda, pembeli akan menerima tagihan yang tidak sama dengan penawarannya.
  2. **Add-on dibaca dari master** (`addon_items`, Fase 39) beserta cara hitungnya
     (lump sum / per m² / per item / persen harga). Tidak ada harga add-on yang diketik bebas.
  3. **Simulasi KPR tidak pernah dikarang.** Bila tenor atau bunga belum diisi (dan tidak ada
     di konfigurasi), hasilnya `state="missing_data"` + daftar `missing[]` — BUKAN angka 0
     atau bunga tebakan. Bunga bank bukan urusan sistem untuk mengira-ngira.
  4. **Diskon punya batas kewenangan.** Di atas `quotation.discount_max_pct_sales`, penawaran
     wajib disetujui manajer; keputusan setuju/tolak beralasan dan berjejak.
  5. **Revisi = versi baru.** Penawaran lama menjadi `superseded` dan tetap bisa dibaca,
     karena "harga yang pernah dijanjikan" adalah bukti, bukan draf yang boleh ditimpa.
"""
import logging
from datetime import date, timedelta

import finance_engine as fin
import sequences as seq
import settings_store as cfg
from core_utils import new_id, now_iso, today_iso_date
from db import ORG_ID, db
from engine import add_activity, create_notification, emit
from reference_p47 import QUOTATION_LABEL

logger = logging.getLogger("sipro.quotation")
MIN_REASON = 5


def _label(state: str) -> str:
    return QUOTATION_LABEL.get(state, state)


def _round(v) -> int:
    return int(round(float(v or 0)))


async def _unit_or_error(org: str, unit_id: str) -> dict:
    unit = await db.units.find_one({"id": unit_id, "org_id": org}, {"_id": 0})
    if not unit:
        raise ValueError("Unit tidak ditemukan.")
    return unit


async def addon_lines(org: str, unit: dict, addons: list) -> list:
    """Baris add-on beserta cara hitungnya — semuanya dari master, bukan input bebas."""
    out = []
    for a in addons or []:
        code = str((a.get("code") if isinstance(a, dict) else a.code) or "").strip()
        qty = float((a.get("qty") if isinstance(a, dict) else a.qty) or 1)
        master = await db.addon_items.find_one({"org_id": org, "code": code}, {"_id": 0})
        if not master:
            raise ValueError(f"Add-on '{code}' tidak ada di master — daftarkan dulu di "
                             "Pusat Konfigurasi › Add-on.")
        if master.get("active") is False:
            raise ValueError(f"Add-on '{code}' sudah tidak aktif.")
        mode = master.get("pricing_mode") or "lump_sum"
        price = int(master.get("unit_price") or 0)
        if mode == "lump_sum":
            amount, formula = price, "nominal tetap"
        elif mode == "percent_of_price":
            amount = _round(int(unit.get("price") or 0) * price / 100)
            formula = f"{price}% × harga unit"
        else:  # per_m2 / per_item
            amount = _round(price * qty)
            formula = (f"{qty:g} {master.get('uom') or ''}".strip() + f" × Rp {price:,}") \
                .replace(",", ".")
        out.append({
            "code": master["code"], "name": master.get("name"), "qty": qty,
            "uom": master.get("uom"), "pricing_mode": mode, "unit_price": price,
            "amount": int(amount), "formula": formula,
            # `category` WAJIB dibawa (Fase 53): tanpa ini kontrak tidak bisa membedakan
            # "kelebihan tanah" (wajib SPKT & wajib lunas sebelum akad kredit) dari add-on
            # biasa, sehingga baris SPKT tidak pernah lahir dan gerbang akad tidak menahan
            # apa pun. Kategorinya sudah ada di master sejak Fase 39 — hanya tidak pernah
            # ikut tersimpan pada penawaran/deal.
            "category": master.get("category"),
            "gl_account": master.get("gl_account"),
            "finance_treatment": master.get("finance_treatment") or "revenue",
            "requires_document": master.get("requires_document"),
            "needs_approval_role": master.get("needs_approval_role"),
            "addon_id": master.get("id"),
        })
    return out


async def _scheme(org: str, scheme_id: str = None) -> dict:
    if scheme_id:
        s = await db.payment_schemes.find_one({"id": scheme_id, "org_id": org}, {"_id": 0})
        if not s:
            raise ValueError("Skema pembayaran tidak ditemukan.")
        return s
    return await fin.get_default_payment_scheme(org)


def kpr_estimate(price_after_discount: int, kpr: dict) -> dict:
    """Angsuran KPR anuitas — atau pengakuan jujur bahwa datanya belum ada.

    Rumus: `A = P × i / (1 − (1+i)^-n)` dengan `i` bunga bulanan efektif. TIDAK ada bunga
    bawaan: bank yang menentukan, bukan aplikasi. Karena itu tenor/bunga yang kosong
    menghasilkan `missing_data` + daftar apa yang kurang, bukan angka 0 yang menyesatkan.
    """
    kpr = kpr or {}
    tenor = int(kpr.get("tenor_months") or 0)
    rate = float(kpr.get("annual_rate_pct") or 0)
    dp_pct = kpr.get("dp_pct")
    missing = []
    if tenor <= 0:
        missing.append("tenor_bulan")
    if rate <= 0:
        missing.append("bunga_tahunan")
    if dp_pct is None:
        missing.append("persen_dp")
    if missing:
        return {"state": "missing_data", "missing": missing, "monthly_installment": None,
                "loan_amount": None, "dp_amount": None, "total_interest": None,
                "note": ("Simulasi KPR belum bisa dihitung: " + ", ".join(missing).replace("_", " ")
                         + " belum diisi. Angka bunga/tenor harus dari bank — sistem tidak "
                           "boleh mengarang.")}
    dp = _round(price_after_discount * float(dp_pct) / 100)
    loan = max(0, int(price_after_discount) - dp)
    i = rate / 100 / 12
    monthly = _round(loan * i / (1 - (1 + i) ** (-tenor))) if loan and i else 0
    return {"state": "complete", "missing": [], "tenor_months": tenor,
            "annual_rate_pct": rate, "dp_pct": float(dp_pct), "dp_amount": dp,
            "loan_amount": loan, "monthly_installment": monthly,
            "total_payment": monthly * tenor,
            "total_interest": max(0, monthly * tenor - loan),
            "note": ("Estimasi anuitas dari tenor & bunga yang DIINPUT — keputusan akhir "
                     "tetap milik bank (hasil SP3K).")}


async def simulate(org: str = ORG_ID, *, unit_id: str, addons: list = None,
                   scheme_id: str = None, discount_amount: int = 0, kpr: dict = None) -> dict:
    """Hitung penawaran TANPA menyimpan — dipakai layar simulasi & saat membuat penawaran."""
    unit = await _unit_or_error(org, unit_id)
    base_price = int(unit.get("price") or 0)
    lines = await addon_lines(org, unit, addons)
    addon_total = sum(x["amount"] for x in lines
                      if x["finance_treatment"] not in ("info",))
    discount = int(discount_amount or 0)
    gross = base_price + addon_total
    if discount > gross:
        raise ValueError(f"Diskon Rp {discount:,} melebihi total harga Rp {gross:,}."
                         .replace(",", "."))
    net = gross - discount
    scheme = await _scheme(org, scheme_id)
    # SATU KEBENARAN: termin dihitung oleh fungsi yang sama dengan pembuat AR.
    terms = fin.compute_scheme_items(scheme, net, today_iso_date())
    config = await fin.get_finance_config(org)
    taxes = fin.compute_taxes(net, config)
    max_pct = float(await cfg.get("quotation.discount_max_pct_sales", org_id=org) or 0)
    discount_pct = round(discount / gross * 100, 2) if gross else 0
    return {
        "unit": {"id": unit["id"], "code": unit.get("code"), "type": unit.get("type"),
                 "project_id": unit.get("project_id"), "block": unit.get("block"),
                 "cluster_code": unit.get("cluster_code"), "status": unit.get("status")},
        "base_price": base_price, "addons": lines, "addon_total": addon_total,
        "gross_price": gross, "discount_amount": discount, "discount_pct": discount_pct,
        "net_price": net, "taxes": taxes,
        "scheme": {"id": scheme.get("id"), "name": scheme.get("name"),
                   "type": scheme.get("type")},
        "terms": terms, "terms_total": sum(t["amount"] for t in terms),
        "kpr": kpr_estimate(net, kpr),
        "needs_discount_approval": bool(discount) and discount_pct > max_pct,
        "discount_limit_pct": max_pct,
        "as_of": today_iso_date(),
    }


async def create(org: str = ORG_ID, *, lead_id: str, unit_id: str, addons: list = None,
                 scheme_id: str = None, discount_amount: int = 0, kpr: dict = None,
                 valid_days: int = None, note: str = None, discount_reason: str = None,
                 actor: str = "system", version_of: dict = None) -> dict:
    """Simpan penawaran (versi 1 atau revisi). Diskon di atas kewenangan → minta persetujuan."""
    lead = await db.leads.find_one({"id": lead_id, "org_id": org}, {"_id": 0})
    if not lead:
        raise ValueError("Lead tidak ditemukan.")
    calc = await simulate(org, unit_id=unit_id, addons=addons, scheme_id=scheme_id,
                          discount_amount=discount_amount, kpr=kpr)
    if calc["needs_discount_approval"] and not (discount_reason or "").strip():
        raise ValueError("Diskon melebihi kewenangan sales — tulis alasan/dasar diskon "
                         "agar manajer bisa memutuskan.")
    days = int(valid_days or await cfg.get("quotation.validity_days", org_id=org) or 7)
    ts = now_iso()
    state = "awaiting_approval" if calc["needs_discount_approval"] else "draft"
    doc = {
        "id": new_id(), "org_id": org,
        "no": (version_of or {}).get("no") or await seq.next_number("quotation", org,
                                                                    prefix="PNW"),
        "version": int((version_of or {}).get("version") or 0) + 1,
        "parent_id": (version_of or {}).get("id"),
        "lead_id": lead_id, "lead_name": lead.get("name"), "lead_phone": lead.get("phone"),
        "unit_id": unit_id, "unit_code": calc["unit"]["code"],
        "project_id": calc["unit"]["project_id"],
        "addons": calc["addons"], "base_price": calc["base_price"],
        "addon_total": calc["addon_total"], "gross_price": calc["gross_price"],
        "discount_amount": calc["discount_amount"], "discount_pct": calc["discount_pct"],
        "discount_reason": (discount_reason or "").strip() or None,
        "net_price": calc["net_price"], "scheme": calc["scheme"], "terms": calc["terms"],
        "taxes": calc["taxes"], "kpr": calc["kpr"],
        "needs_discount_approval": calc["needs_discount_approval"],
        "discount_limit_pct": calc["discount_limit_pct"],
        "state": state, "state_label": _label(state),
        "valid_days": days,
        "valid_until": (date.fromisoformat(today_iso_date()) + timedelta(days=days)).isoformat(),
        "note": note, "approved_by": None, "approved_at": None, "decision_reason": None,
        "sent_at": None, "sent_channel": None, "sent_status": None,
        "converted_deal_id": None, "converted_at": None,
        "created_by": actor, "created_at": ts, "updated_at": ts,
        "history": [{"at": ts, "by": actor, "action": "create", "state": state}],
    }
    await db.quotations.insert_one(dict(doc))
    doc.pop("_id", None)
    if version_of:
        await db.quotations.update_one({"id": version_of["id"]}, {"$set": {
            "state": "superseded", "state_label": _label("superseded"),
            "superseded_by": doc["id"], "updated_at": ts}})
    await add_activity(entity_type="lead", entity_id=lead_id, type="sales", actor=actor,
                       org_id=org,
                       body=(f"Penawaran {doc['no']} v{doc['version']} dibuat untuk unit "
                             f"{doc['unit_code']} — Rp {doc['net_price']:,}"
                             + (" (menunggu persetujuan diskon)"
                                if state == "awaiting_approval" else "")).replace(",", "."))
    if state == "awaiting_approval":
        for mgr in await db.users.find({"org_id": org,
                                        "role": {"$in": ["sales_manager", "owner"]}},
                                       {"_id": 0, "email": 1}).to_list(20):
            await create_notification(
                user_email=mgr.get("email"), org_id=org, type="sales",
                title="Persetujuan diskon penawaran",
                body=(f"{doc['no']} unit {doc['unit_code']}: diskon Rp "
                      f"{doc['discount_amount']:,} ({doc['discount_pct']}%) melebihi batas "
                      f"{doc['discount_limit_pct']}%.").replace(",", "."),
                related_entity_type="quotation", related_entity_id=doc["id"])
    await emit("quotation.created", "lead", lead_id,
              {"quotation_id": doc["id"], "net_price": doc["net_price"]}, org_id=org)
    return doc


async def get(org: str, quotation_id: str) -> dict:
    q = await db.quotations.find_one({"id": quotation_id, "org_id": org}, {"_id": 0})
    if not q:
        raise ValueError("Penawaran tidak ditemukan.")
    return _with_expiry(q)


def _with_expiry(q: dict) -> dict:
    """Masa berlaku dihitung saat dibaca — supaya tidak ada penawaran 'abadi' karena lupa tick."""
    if q.get("state") in ("draft", "awaiting_approval", "approved", "sent") \
            and str(q.get("valid_until") or "") < today_iso_date():
        q = {**q, "state": "expired", "state_label": _label("expired"), "expired_derived": True}
    return q


async def decide_discount(org: str, quotation_id: str, actor: str, approve: bool,
                          reason: str) -> dict:
    """Manajer menyetujui/menolak diskon — wajib beralasan (jejak kewenangan)."""
    if len((reason or "").strip()) < MIN_REASON:
        raise ValueError(f"Alasan keputusan minimal {MIN_REASON} huruf.")
    q = await get(org, quotation_id)
    if q["state"] != "awaiting_approval":
        raise ValueError(f"Penawaran ini berstatus {q.get('state_label')} — tidak sedang "
                         "menunggu persetujuan diskon.")
    state = "approved" if approve else "rejected"
    ts = now_iso()
    await db.quotations.update_one({"id": quotation_id}, {"$set": {
        "state": state, "state_label": _label(state), "approved_by": actor,
        "approved_at": ts, "decision_reason": reason.strip(), "updated_at": ts},
        "$push": {"history": {"at": ts, "by": actor,
                              "action": ("approve_discount" if approve
                                         else "reject_discount"),
                              "reason": reason.strip(), "state": state}}})
    await add_activity(entity_type="lead", entity_id=q["lead_id"], type="sales", actor=actor,
                       org_id=org,
                       body=(f"Diskon penawaran {q['no']} {'DISETUJUI' if approve else 'DITOLAK'}"
                             f" — {reason.strip()}"))
    await create_notification(
        user_email=q.get("created_by"), org_id=org, type="sales",
        title=f"Diskon penawaran {q['no']} {'disetujui' if approve else 'ditolak'}",
        body=reason.strip(), related_entity_type="quotation", related_entity_id=quotation_id)
    return await get(org, quotation_id)


async def mark_sent(org: str, quotation_id: str, actor: str, channel: str = "whatsapp",
                    note: str = None) -> dict:
    """Kirim penawaran. Kanal WhatsApp berjalan MODE SIMULASI bila kredensial belum ada —
    statusnya ditulis apa adanya (`simulated`), tidak pernah diklaim "terkirim"."""
    q = await get(org, quotation_id)
    if q["state"] not in ("draft", "approved", "sent"):
        raise ValueError(f"Penawaran berstatus {q.get('state_label')} tidak bisa dikirim.")
    if q.get("needs_discount_approval") and q["state"] == "draft":
        raise ValueError("Diskon belum disetujui manajer — penawaran belum boleh dikirim.")
    from notifications import send_whatsapp
    text = (f"Penawaran {q['no']} unit {q['unit_code']}: harga Rp {q['net_price']:,}"
            .replace(",", ".") + f" · berlaku s/d {q['valid_until']}.")
    res = await send_whatsapp(q.get("lead_phone"), text) if q.get("lead_phone") else \
        {"status": "skipped", "reason": "lead tanpa nomor telepon"}
    ts = now_iso()
    await db.quotations.update_one({"id": quotation_id}, {"$set": {
        "state": "sent", "state_label": _label("sent"), "sent_at": ts,
        "sent_channel": channel, "sent_status": res.get("status"), "updated_at": ts},
        "$push": {"history": {"at": ts, "by": actor, "action": "send",
                              "channel": channel, "result": res.get("status"),
                              "note": note}}})
    return {"quotation": await get(org, quotation_id), "delivery": res}


async def convert(org: str, quotation_id: str, actor: str, note: str = None) -> dict:
    """Ubah penawaran menjadi RESERVASI (deal) memakai jalur reservasi yang sudah ada.

    Penawaran tidak menciptakan aturan reservasi sendiri (batas unit aktif per lead, status
    unit, dsb.) — semuanya tetap milik `deals_router`/engine reservasi. Yang ditambahkan di
    sini hanya JEJAK: deal menyimpan `quotation_id` sehingga "yang dijanjikan" bisa
    dibandingkan dengan "yang ditagihkan".
    """
    q = await get(org, quotation_id)
    if q["state"] == "converted":
        raise ValueError("Penawaran ini sudah menjadi reservasi.")
    if q["state"] == "expired":
        raise ValueError("Penawaran sudah kedaluwarsa — buat revisi lebih dulu.")
    if q.get("needs_discount_approval") and q["state"] not in ("approved", "sent"):
        raise ValueError("Diskon belum disetujui manajer — penawaran belum bisa dikonversi.")
    unit = await _unit_or_error(org, q["unit_id"])
    if unit.get("status") != "available":
        raise ValueError(f"Unit {unit.get('code')} berstatus {unit.get('status')} — "
                         "tidak bisa direservasi dari penawaran ini.")
    ts = now_iso()
    lead = await db.leads.find_one({"id": q["lead_id"], "org_id": org}, {"_id": 0})
    if not lead:
        raise ValueError("Lead penawaran ini tidak ditemukan.")
    # SATU JALUR RESERVASI (Fase 53A). Dulu di sini deal dibuat sendiri dengan bentuk LAIN
    # (`stage="reserved", status="active"`, tanpa `reserved_until`/booking fee/ikatan unit),
    # sehingga deal hasil penawaran DITOLAK saat mau di-booking ("Deal harus berstatus
    # 'reserved'") — AR tidak pernah lahir dan tahap lead mandek. Sekarang reservasi dibuat
    # oleh mesin yang sama dengan tombol "Buat Reservasi", dan penawaran hanya MENAMBAH
    # jejak (nomor penawaran, add-on, diskon, harga netto yang dijanjikan).
    import sales_reserve as sr
    deal = await sr.reserve(
        org, lead=lead, unit=unit, actor=actor, notes=note,
        extra={"price": int(q["net_price"]), "discount": int(q.get("discount_amount") or 0),
               "quotation_id": q["id"], "quotation_no": q.get("no"),
               "addons": q.get("addons") or [],
               "scheme_id": (q.get("scheme") or {}).get("id")})
    await db.quotations.update_one({"id": quotation_id}, {"$set": {
        "state": "converted", "state_label": _label("converted"),
        "converted_deal_id": deal["id"], "converted_at": ts, "updated_at": ts},
        "$push": {"history": {"at": ts, "by": actor, "action": "convert",
                              "deal_id": deal["id"]}}})
    await add_activity(entity_type="lead", entity_id=q["lead_id"], type="sales", actor=actor,
                       org_id=org,
                       body=(f"Penawaran {q['no']} dikonversi menjadi reservasi unit "
                             f"{q['unit_code']}."))
    await emit("quotation.converted", "deal", deal["id"],
              {"quotation_id": q["id"], "net_price": q["net_price"]}, org_id=org)
    return {"deal": deal, "quotation": await get(org, quotation_id)}


async def listing(org: str = ORG_ID, *, lead_id: str = None, state: str = None,
                  unit_id: str = None, owner_email: str = None, skip: int = 0,
                  limit: int = 50) -> dict:
    q = {"org_id": org}
    if lead_id:
        q["lead_id"] = lead_id
    if unit_id:
        q["unit_id"] = unit_id
    if state:
        q["state"] = state
    if owner_email:
        q["created_by"] = owner_email
    total = await db.quotations.count_documents(q)
    rows = await db.quotations.find(q, {"_id": 0}).sort("created_at", -1) \
        .skip(skip).limit(limit).to_list(limit)
    rows = [_with_expiry(r) for r in rows]
    # Ringkasan WAJIB memakai saringan yang sama dengan barisnya (kecuali `state`, karena
    # ringkasan justru dipecah per status). Dulu ringkasan menghitung SELURUH organisasi:
    # di layar Lead 360 angkanya menyebut penawaran lead lain, dan bagi sales (yang barisnya
    # dibatasi row-scope) angka itu MEMBOCORKAN pekerjaan sales lain — dua-duanya membuat
    # layar dan data berbeda pendapat.
    base = {k: v for k, v in q.items() if k != "state"}
    summary = {s: 0 for s in QUOTATION_LABEL}
    for r in await db.quotations.find(base, {"_id": 0, "state": 1,
                                             "valid_until": 1,
                                             "net_price": 1}).to_list(2000):
        st = _with_expiry(r)["state"]
        summary[st] = summary.get(st, 0) + 1
    return {"data": rows, "total": total, "summary": summary}
