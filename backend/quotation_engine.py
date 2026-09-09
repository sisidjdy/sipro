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
                   scheme_id: str = None, discount_amount: int = 0, kpr: dict = None,
                   discount_scheme_id: str = None, promo_id: str = None,
                   coupon_code: str = None, lead_id: str = None,
                   booking_fee: int = None, allin_scheme_id: str = None) -> dict:
    """Hitung penawaran TANPA menyimpan — dipakai layar simulasi, penawaran, DAN reservasi.

    Fase 69: potongan TIDAK diketik. `discount_amount` > 0 ditolak; nilainya lahir dari
    `pricing_engine.compute_discounts` (skema diskon / promo / kupon yang dikonfigurasi).
    """
    import pricing_engine as pe
    if int(discount_amount or 0) > 0:
        raise ValueError("Diskon manual tidak diizinkan — pilih skema diskon, promo, atau "
                         "kupon yang dikonfigurasi di Pusat Konfigurasi › Harga & Promo.")
    unit = await _unit_or_error(org, unit_id)
    base_price = int(unit.get("price") or 0)
    lines = await addon_lines(org, unit, addons)
    addon_total = sum(x["amount"] for x in lines
                      if x["finance_treatment"] not in ("info",))
    # ADD-ON = komponen pembayaran TERPISAH: bukan bagian harga unit, tidak masuk termin,
    # tidak masuk simulasi KPR. `gross` di sini = harga unit saja.
    gross = base_price
    scheme = await _scheme(org, scheme_id)
    scheme_explicit = bool(scheme_id)  # dipilih sales (bukan bawaan) → mengunci jenis kontrak
    # Fase 88C: dasar hitung per SASARAN — DP = termin uang muka dari skema, booking fee dari
    # bawaan organisasi; komponen biaya all-in menyusul saat skema all-in dipilih (reservasi).
    pre_terms = fin.compute_scheme_items(scheme, gross, today_iso_date())
    dp_i = pe.dp_term_index(pre_terms)
    bases = {"price": gross,
             "dp": int(pre_terms[dp_i]["amount"]) if dp_i >= 0 else 0,
             "booking_fee": int(booking_fee if booking_fee is not None
                                else (await cfg.get("booking_fee.default_amount", org_id=org) or 0))}
    disc = await pe.compute_discounts(org, unit=unit, gross=gross,
                                      discount_scheme_id=discount_scheme_id,
                                      promo_id=promo_id, coupon_code=coupon_code,
                                      lead_id=lead_id, bases=bases)
    discount = int(disc["total"])
    net = gross - discount
    by_target = disc["by_target"]
    # Fase 88C: komponen biaya all-in dihitung dari harga BERSIH; potongan bersasaran komponen
    # dikurangkan dari komponennya oleh `attach_costs` (fungsi yang SAMA dipakai reservasi).
    costs = None
    if allin_scheme_id:
        import allin_engine as ae
        costs = await ae.resolve_scheme(org, allin_scheme_id, int(net), unit.get("project_id"),
                                        scheme=scheme.get("kind") or scheme.get("type"))
    # SATU KEBENARAN: termin dihitung oleh fungsi yang sama dengan pembuat AR.
    terms = pe.apply_component_discounts(
        fin.compute_scheme_items(scheme, gross - by_target["price"], today_iso_date()), by_target)
    booking_fee_net = max(0, bases["booking_fee"] - by_target["booking_fee"])
    config = await fin.get_finance_config(org)
    taxes = fin.compute_taxes(net, config)
    max_pct = float(await cfg.get("quotation.discount_max_pct_sales", org_id=org) or 0)
    discount_pct = round(discount / gross * 100, 2) if gross else 0

    def _pick(source):
        return next((x for x in disc["lines"] if x["source"] == source), None)
    calc = {
        "unit": {"id": unit["id"], "code": unit.get("code"), "type": unit.get("type"),
                 "project_id": unit.get("project_id"), "block": unit.get("block"),
                 "cluster_code": unit.get("cluster_code"), "status": unit.get("status")},
        "base_price": base_price, "addons": lines, "addon_total": addon_total,
        "addon_net_total": addon_total, "scheme_explicit": scheme_explicit,
        "gross_price": gross, "discount_amount": discount, "discount_pct": discount_pct,
        "discount_lines": disc["lines"], "discount_scheme": _pick("discount_scheme"),
        "promo": _pick("promo"), "coupon": _pick("coupon"), "coupon_code": disc["coupon_code"],
        "by_target": by_target, "bases": bases,
        "booking_fee_gross": bases["booking_fee"], "booking_fee_net": booking_fee_net,
        "booking_fee": booking_fee_net,
        "net_price": net, "taxes": taxes,
        "scheme": {"id": scheme.get("id"), "name": scheme.get("name"),
                   "type": scheme.get("kind") or scheme.get("type")},
        "terms": terms, "terms_total": sum(t["amount"] for t in terms),
        "kpr": kpr_estimate(net, kpr),
        "needs_discount_approval": (bool(discount) and discount_pct > max_pct)
        or disc["needs_approval"],
        "discount_limit_pct": max_pct,
        "as_of": today_iso_date(),
    }
    return attach_costs(calc, costs)


def attach_costs(calc: dict, costs: dict) -> dict:
    """Tempelkan snapshot biaya all-in ke hasil hitung: potongan bersasaran komponen
    dikurangkan dari komponennya, lalu SEMUA total turunan (by_target, potongan biaya, total
    dibayar pembeli, rincian komponen pembayaran) dihitung ulang dari satu tempat."""
    import pricing_engine as pe
    lines = calc["discount_lines"]
    if costs is not None and costs.get("components") is not None:
        pe.apply_cost_discounts(lines, costs["components"])
        comps = costs["components"]
        costs["buyer_total"] = sum(int(c.get("amount") or 0) for c in comps
                                   if c.get("treatment") != "developer_borne")
        costs["developer_total"] = sum(int(c.get("amount") or 0) for c in comps
                                       if c.get("treatment") == "developer_borne")
        costs["discount_total"] = sum(int(c.get("discount") or 0) for c in comps)
    calc["costs"] = costs
    return refresh_totals(calc)


def refresh_totals(calc: dict) -> dict:
    """Hitung ulang SEMUA total turunan dari komponen yang sudah ada (tanpa mengulang potongan
    komponen biaya) — dipanggil ulang bila add-on/potongan diubah setelah `attach_costs`."""
    import pricing_engine as pe
    lines = calc["discount_lines"]
    costs = calc.get("costs")
    calc["by_target"] = pe.split_by_target(lines)
    cost_discount = sum(int(x.get("amount") or 0) for x in lines if x.get("target") == "cost")
    addon_discount = sum(int(x.get("amount") or 0) for x in lines if x.get("target") == "addon")
    calc["cost_discount_amount"] = int(cost_discount)
    calc["addon_discount_amount"] = int(addon_discount)
    calc["addon_net_total"] = max(0, int(calc.get("addon_total") or 0) - int(addon_discount))
    calc["total_discount_amount"] = int(calc["discount_amount"]) + int(cost_discount) + int(addon_discount)
    # Total dibayar pembeli = harga bersih unit + add-on bersih + biaya all-in pembeli.
    calc["buyer_total"] = (int(calc["net_price"]) + int(calc["addon_net_total"])
                           + int((costs or {}).get("buyer_total") or 0))
    calc["payment_breakdown"] = build_payment_breakdown(calc)
    return calc


def build_payment_breakdown(calc: dict) -> dict:
    """SATU daftar komponen pembayaran pembeli — harga unit, add-on, potongan harga, harga
    bersih, komponen biaya (kotor − potongan = bersih), total dibayar pembeli, booking fee.
    Dipakai layar simulasi/reservasi, snapshot deal, dan piutang di Finance."""
    rows = []

    def add(code, label, amount, group, **extra):
        rows.append({"code": code, "label": label, "amount": int(amount or 0), "group": group, **extra})

    unit = calc.get("unit") or {}
    add("UNIT_PRICE", f"Harga unit {unit.get('code') or ''}".strip(), calc.get("base_price"), "harga",
        hint=unit.get("type"))
    for x in calc.get("discount_lines") or []:
        if x.get("target") in ("cost", "addon"):
            continue
        add(f"DISC:{x.get('code')}", f"Potongan · {x.get('name') or x.get('code')}",
            -int(x.get("amount") or 0), "potongan",
            hint=f"{x.get('source_label')} · dipotong dari {x.get('target_label')}",
            pending=bool(x.get("pending")))
    add("NET_PRICE", "Harga bersih unit — dasar termin / KPR", calc.get("net_price"), "subtotal",
        kpr_base=True)
    addon_rows = [a for a in calc.get("addons") or [] if (a.get("finance_treatment") or "revenue") != "info"]
    for a in addon_rows:
        add(f"ADDON:{a.get('code')}", f"Add-on · {a.get('name') or a.get('code')}", a.get("amount"),
            "tambahan", hint=f"{a.get('formula')} · tagihan terpisah, tidak masuk KPR", kpr_excluded=True)
    for x in calc.get("discount_lines") or []:
        if x.get("target") != "addon":
            continue
        add(f"ADDONDISC:{x.get('code')}", f"Potongan · {x.get('name') or x.get('code')}",
            -int(x.get("amount") or 0), "potongan", hint=f"{x.get('source_label')} · dipotong dari add-on")
    addon_net = int(calc.get("addon_net_total") if calc.get("addon_net_total") is not None
                    else calc.get("addon_total") or 0)
    if addon_rows:
        add("ADDON_TOTAL", "Total add-on (tagihan terpisah, bukan dasar KPR)", addon_net, "subtotal",
            kpr_excluded=True)
    costs = calc.get("costs") or {}
    buyer_costs = dev_costs = 0
    for c in costs.get("components") or []:
        dev = c.get("treatment") == "developer_borne"
        gross = int(c.get("amount") or 0) + int(c.get("discount") or 0)
        add(f"COST:{c.get('code')}", c.get("name") or c.get("code"), gross, "biaya",
            developer_borne=dev, hint=str(c.get("formula") or "").split(" − potongan")[0]
            + (" · ditanggung developer" if dev else ""))
        if int(c.get("discount") or 0):
            names = ", ".join(d.get("name") or d.get("code") or "" for d in c.get("discount_lines") or [])
            add(f"COSTDISC:{c.get('code')}", f"Potongan · {names or 'promo'} ({c.get('name') or c.get('code')})",
                -int(c["discount"]), "potongan_biaya", developer_borne=dev,
                hint=f"dipotong dari komponen biaya {c.get('name') or c.get('code')}")
        if dev:
            dev_costs += int(c.get("amount") or 0)
        else:
            buyer_costs += int(c.get("amount") or 0)
    pending = [x for x in calc.get("discount_lines") or [] if x.get("pending")]
    for x in pending:
        add(f"DISC:{x.get('code')}", f"Potongan · {x.get('name') or x.get('code')} (menunggu skema all-in)", 0,
            "potongan_biaya", pending=True, hint=x.get("note") or "pilih skema all-in yang memuat komponennya")
    if costs.get("components") is not None:
        add("COST_TOTAL", f"Total biaya ditagih ke pembeli · {costs.get('scheme_name') or 'all-in'}",
            buyer_costs, "subtotal", hint=(f"ditanggung developer Rp {dev_costs:,}".replace(",", ".")
                                          if dev_costs else None))
    net = int(calc.get("net_price") or 0)
    total = net + addon_net + buyer_costs
    bf = int(calc.get("booking_fee") if calc.get("booking_fee") is not None else calc.get("booking_fee_net") or 0)
    add("TOTAL", "Total dibayar pembeli", total, "total",
        hint="harga bersih unit + add-on + biaya all-in pembeli setelah potongan")
    add("BOOKING_FEE", "Booking fee (dibayar saat keep unit, dialihkan ke termin)", bf, "deposit")
    add("AFTER_BOOKING_FEE", "Sisa yang ditagih setelah booking fee", total - bf, "total")
    return {"rows": rows, "base_price": int(calc.get("base_price") or 0),
            "addon_total": int(calc.get("addon_total") or 0), "addon_net_total": addon_net,
            "price_discount": int(calc.get("discount_amount") or 0),
            "cost_discount": int(calc.get("cost_discount_amount") or 0),
            "addon_discount": int(calc.get("addon_discount_amount") or 0),
            "total_discount": int(calc.get("total_discount_amount") or 0),
            "net_price": net, "kpr_base": net, "buyer_costs": buyer_costs,
            "developer_costs": dev_costs, "total": total, "booking_fee": bf,
            "remaining_after_booking_fee": total - bf,
            "has_costs": costs.get("components") is not None, "pending": bool(pending)}


async def create(org: str = ORG_ID, *, lead_id: str, unit_id: str, addons: list = None,
                 scheme_id: str = None, discount_amount: int = 0, kpr: dict = None,
                 valid_days: int = None, note: str = None, discount_reason: str = None,
                 actor: str = "system", version_of: dict = None,
                 discount_scheme_id: str = None, promo_id: str = None,
                 coupon_code: str = None) -> dict:
    """Simpan penawaran (versi 1 atau revisi). Diskon di atas kewenangan → minta persetujuan."""
    lead = await db.leads.find_one({"id": lead_id, "org_id": org}, {"_id": 0})
    if not lead:
        raise ValueError("Lead tidak ditemukan.")
    calc = await simulate(org, unit_id=unit_id, addons=addons, scheme_id=scheme_id,
                          discount_amount=discount_amount, kpr=kpr,
                          discount_scheme_id=discount_scheme_id, promo_id=promo_id,
                          coupon_code=coupon_code, lead_id=lead_id)
    if calc["needs_discount_approval"] and not (discount_reason or "").strip():
        raise ValueError("Diskon melebihi kewenangan sales — tulis alasan/dasar diskon "
                         "agar manajer bisa memutuskan.")
    days = int(valid_days or await cfg.get("quotation.validity_days", org_id=org) or 7)
    ts = now_iso()
    state = "awaiting_approval" if calc["needs_discount_approval"] else "draft"
    doc = {
        "id": new_id(), "org_id": org,
        "no": (version_of or {}).get("no") or await seq.next_number("quotation", org,
                                                                    prefix="PNW",
                                                                    context={"unit_id": unit_id}),
        "version": int((version_of or {}).get("version") or 0) + 1,
        "parent_id": (version_of or {}).get("id"),
        "lead_id": lead_id, "lead_name": lead.get("name"), "lead_phone": lead.get("phone"),
        "unit_id": unit_id, "unit_code": calc["unit"]["code"],
        "project_id": calc["unit"]["project_id"],
        "addons": calc["addons"], "base_price": calc["base_price"],
        "addon_total": calc["addon_total"], "addon_net_total": calc.get("addon_net_total"),
        "gross_price": calc["gross_price"],
        "discount_amount": calc["discount_amount"], "discount_pct": calc["discount_pct"],
        "discount_lines": calc["discount_lines"], "discount_scheme": calc["discount_scheme"],
        "promo": calc["promo"], "coupon": calc["coupon"], "coupon_code": calc["coupon_code"],
        "discount_reason": (discount_reason or "").strip() or None,
        "net_price": calc["net_price"], "scheme": calc["scheme"], "terms": calc["terms"],
        "scheme_explicit": bool(calc.get("scheme_explicit")),
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


def pricing_snapshot(calc: dict) -> dict:
    """Rincian harga yang DISIMPAN pada deal — angka yang dijanjikan bisa direkonstruksi."""
    keys = ("base_price", "addon_total", "addon_net_total", "addon_discount_amount",
            "gross_price", "discount_amount", "discount_pct",
            "discount_lines", "discount_scheme", "promo", "coupon", "coupon_code", "net_price",
            "scheme", "terms", "terms_total", "taxes", "kpr", "as_of", "discount_limit_pct",
            "by_target", "bases", "booking_fee_gross", "booking_fee_net", "booking_fee",
            "cost_discount_amount", "total_discount_amount", "buyer_total", "payment_breakdown")
    return {k: calc.get(k) for k in keys}


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
    import pricing_engine as pe
    if q.get("coupon_code"):
        # Kuota kupon dicek ULANG saat konversi — penawaran hanya memvalidasi, tidak memakai.
        await pe.validate_coupon(org, q["coupon_code"], unit=unit, lead_id=lead["id"])
    deal = await sr.reserve(
        org, lead=lead, unit=unit, actor=actor, notes=note,
        extra={"price": int(q["net_price"]), "discount": int(q.get("discount_amount") or 0),
               "quotation_id": q["id"], "quotation_no": q.get("no"),
               "addons": q.get("addons") or [],
               "scheme_id": (q.get("scheme") or {}).get("id"),
               "scheme_explicit": bool(q.get("scheme_explicit")),
               "pricing": pricing_snapshot(q)})
    if q.get("coupon_code"):
        await pe.redeem_coupon(org, q["coupon_code"], unit=unit, lead=lead, ref_type="deal",
                               ref_id=deal["id"], amount=int((q.get("coupon") or {})
                                                             .get("amount") or 0), actor=actor)
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
