"""KONTRAK PEMBELI (Fase 53C) — komponen biaya, rencana bayar, tahap legal, sub-alur KPR.

## Kenapa berkas ini ada (cacat nyata, bukan penyempurnaan)

Sebelum Fase 53 rantai legal menempel pada `deals` dan hanya mengenal dua peristiwa:
`ppjb` lalu `ajb`. Padahal keputusan owner (D4, Dok 26 §1) menempatkan AJB/BAST di domain
**Pembeli**, dan pada skema KPR peristiwa yang menentukan adalah **akad kredit** — yang
sebelumnya tidak ada di data sama sekali. Akibat nyata:

  * `POST /deals/{id}/ajb` MENUNTUT PPJB dulu, sementara `POST /documents` (AJB) menuntut
    BAST dulu — dua aturan berbeda untuk satu peristiwa yang sama;
  * tidak ada tempat menyimpan SP3K, akad, dan pencairan, sehingga "sudah akad atau belum"
    hanya ada di kepala orang;
  * biaya-biaya transaksi (BPHTB, notaris, biaya bank, asuransi, promo) yang tercantum di
    dokumen owner tidak punya tempat, sehingga dokumen tidak mungkin dicetak dengan angka
    yang benar.

Kontrak di sini adalah SATU-SATUNYA sumber angka untuk dokumen (Dok 27 §5.1) dan penampung
tahap legal pembeli. Aturan yang dipegang:

1. **Biaya yang belum diketahui ditulis "belum diisi", bukan Rp 0.** Nol berarti "tidak ada
    biayanya" — pernyataan yang belum tentu benar dan langsung menular ke dokumen legal.
2. **Tidak ada rumus kedua untuk termin.** Rencana bayar dibaca dari AR (`ar_invoices`) yang
    dibuat `finance_engine.compute_scheme_items` — fungsi yang sama dengan yang menagih.
3. **Tahap legal punya GERBANG BUKTI.** Setiap tahap menyebutkan sebab (SSOT `legal_block`)
    bila belum boleh dimajukan; tombol tidak pernah "mati tanpa penjelasan".
4. **Deal lama tetap benar.** Setiap tahap legal juga menulis `deals.legal_stage/ppjb/ajb`
    supaya layar & gate yang sudah ada tidak mendadak berbohong.
"""
import logging

import finance_engine as fin
import kpr_engine as kprmod
import reference as ref
import sequences as seq
import settings_store as cfg
from core_utils import due_in, new_id, now_iso
from db import ORG_ID, db
from engine import add_activity, auto_create_task, dispatch_pending, emit

logger = logging.getLogger("sipro.contracts")

SCHEMES = ("cash_keras", "cash_bertahap", "kpr")
SCHEME_DOC = {"cash_keras": "SPR_CASH", "cash_bertahap": "SPR_CASH_STAGED", "kpr": "SPR_KPR"}
LEGAL_ORDER = ("ppjb", "akad_kredit", "pelunasan", "bast", "ajb", "sertifikat")
# Tahap KPR & mesinnya tinggal di `kpr_engine.py` (satu berkas satu tanggung jawab,
# dan berkas ini tetap di bawah batas ukuran yang dijaga gate kepatuhan).
# Komponen biaya yang diisi manual oleh Keuangan/Sales (bukan turunan add-on/unit).
COST_FIELDS = ("bphtb", "notary_fee", "bank_fee", "insurance", "pph_seller")
KPR_ONLY_COSTS = ("bank_fee", "insurance")


def _rp(v) -> str:
    return f"Rp {int(v or 0):,}".replace(",", ".")


def _addon_group(category: str) -> str:
    return {"kelebihan_tanah": "EXCESS_LAND", "posisi_unit": "HOOK_FEE"}.get(
        category or "", "ADDON_SPEC")


# ============================================================ rincian harga (breakdown)
async def build_breakdown(org: str, contract: dict) -> dict:
    """Susun `price_breakdown[]` — SATU BARIS PER KOMPONEN (permintaan owner).

    Tidak ada angka yang dihitung di dua tempat: harga unit dari `units`, add-on dari
    `deals.addons` (yang berasal dari master add-on lewat penawaran), biaya transaksi dari
    `contracts.costs` yang diisi manusia. Komponen yang belum diisi TIDAK menjadi 0.
    """
    scheme = contract.get("scheme")
    unit = await db.units.find_one({"id": contract.get("unit_id")}, {"_id": 0}) or {}
    deal = await db.deals.find_one({"id": contract.get("deal_id")}, {"_id": 0}) or {}
    costs = contract.get("costs") or {}
    rows = []

    def add(code, label, amount, *, group, treatment, state="filled", note=None, meta=None):
        rows.append({"code": code, "label": label, "group": group,
                     "finance_treatment": treatment,
                     "amount": (int(amount) if amount is not None else None),
                     "state": state,
                     "state_label": ref.label_of("component_fill_state", state),
                     "note": note, "meta": meta or {}})

    unit_price = int(deal.get("price") or unit.get("price") or 0)
    # `deals.price` pada deal hasil penawaran sudah NETTO (diskon dipotong); harga unit
    # murni dibaca dari master unit supaya diskon tidak hilang dari rincian.
    base_price = int(unit.get("price") or unit_price)
    add("UNIT_PRICE", "Harga unit", base_price, group="harga", treatment="revenue",
        note=f"Tipe {unit.get('type') or '-'} · unit {unit.get('code') or '-'}")

    addons = deal.get("addons") or []
    buckets = {}
    for a in addons:
        if (a.get("finance_treatment") or "revenue") == "info":
            continue
        kategori = a.get("category")
        if not kategori and a.get("code"):
            # PENYEMBUHAN baris lama: add-on yang disimpan SEBELUM Fase 53 tidak membawa
            # `category` (padahal masternya punya). Tanpa penyembuhan ini kelebihan tanah
            # pada deal lama akan dihitung sebagai add-on biasa — SPKT tidak pernah lahir
            # dan gerbang akad kredit tidak menahan apa pun.
            master = await db.addon_items.find_one(
                {"org_id": org, "code": a["code"]},
                {"_id": 0, "category": 1, "requires_document": 1})
            kategori = (master or {}).get("category")
            if not kategori and (master or {}).get("requires_document") == "SPKT":
                kategori = "kelebihan_tanah"
        key = _addon_group(kategori)
        b = buckets.setdefault(key, {"amount": 0, "items": []})
        b["amount"] += int(a.get("amount") or 0)
        b["items"].append({"code": a.get("code"), "name": a.get("name"),
                           "qty": a.get("qty"), "uom": a.get("uom"),
                           "unit_price": a.get("unit_price"),
                           "amount": int(a.get("amount") or 0),
                           "category": kategori})
    for code, label in (("ADDON_SPEC", "Spek tambahan (add-on)"),
                        ("EXCESS_LAND", "Kelebihan tanah"),
                        ("HOOK_FEE", "Biaya hook / posisi sudut")):
        if code in buckets:
            add(code, label, buckets[code]["amount"], group="tambahan", treatment="revenue",
                meta={"items": buckets[code]["items"]},
                note=("Wajib SPKT — estimasi sampai ada hasil ukur akhir."
                      if code == "EXCESS_LAND" else None))

    promo = costs.get("promo_discount")
    if promo is None:
        promo = int(deal.get("discount") or 0) or None
    add("PROMO_DISCOUNT", "Promo / potongan all-in", promo, group="potongan",
        treatment="discount", state="filled" if promo is not None else "empty")

    booking_fee = deal.get("booking_fee")
    if not booking_fee:
        booking_fee = int(await cfg.get("booking_fee.default_amount", org_id=org) or 0)
    add("BOOKING_FEE", "Booking fee", booking_fee, group="harga", treatment="deposit",
        note="Dibayar saat keep unit; dialihkan ke termin saat SPR sah.")

    for code, label, treatment in (("BPHTB", "BPHTB", "pass_through"),
                                   ("NOTARY_FEE", "Biaya notaris / akad", "pass_through"),
                                   ("BANK_FEE", "Biaya bank (provisi, admin, blokir, materai)",
                                    "pass_through"),
                                   ("INSURANCE", "Asuransi jiwa & kebakaran", "pass_through"),
                                   ("PPH_SELLER", "PPh penjual", "tax_out")):
        field = code.lower()
        if field in KPR_ONLY_COSTS and scheme != "kpr":
            add(code, label, None, group="biaya", treatment=treatment, state="not_applicable",
                note="Hanya berlaku pada skema KPR.")
            continue
        val = costs.get(field)
        add(code, label, val, group="biaya", treatment=treatment,
            state="filled" if val is not None else "empty",
            note=None if val is not None else "Belum diisi — bukan nol.")

    if scheme == "kpr":
        plafon = costs.get("plafon_kredit")
        add("PLAFON_KREDIT", "Plafon kredit bank", plafon, group="pembiayaan",
            treatment="info", state="filled" if plafon is not None else "empty",
            note="Informasi plafon KPR — bukan tagihan ke pembeli.")

    def amt(code):
        for r in rows:
            if r["code"] == code:
                return r["amount"]
        return None

    gross = sum(int(amt(c) or 0) for c in ("UNIT_PRICE", "ADDON_SPEC", "EXCESS_LAND",
                                          "HOOK_FEE"))
    nett = gross - int(amt("PROMO_DISCOUNT") or 0)
    cost_rows = [r for r in rows if r["group"] == "biaya"]
    empty = [r["code"] for r in cost_rows if r["state"] == "empty"]
    # LABEL manusia untuk daftar yang sama. `empty` (kode) tetap ada untuk mesin/uji, tetapi
    # apa pun yang DIBACA MANUSIA — spanduk "masih sementara" di layar, catatan total, dan
    # peringatan di panel dokumen — wajib memakai `empty_labels`. Temuan uji peramban Fase 56:
    # layar dan dokumen SPR yang ditandatangani pembeli sempat mencetak "NOTARY_FEE,
    # PPH_SELLER, BANK_FEE" apa adanya. Kode adalah bahasa mesin; pembeli tidak berutang
    # pengetahuan itu kepada kita.
    empty_labels = [r["label"] for r in cost_rows if r["state"] == "empty"]
    costs_total = sum(int(r["amount"] or 0) for r in cost_rows if r["state"] == "filled")
    plafon = amt("PLAFON_KREDIT")
    self_funding = None
    if scheme == "kpr" and plafon is not None:
        self_funding = max(0, nett - int(plafon))
    return {
        "rows": rows,
        "gross_price": gross,
        "promo_discount": int(amt("PROMO_DISCOUNT") or 0),
        "nett_price": nett,
        "costs_total": costs_total,
        "costs_incomplete": empty,
        "costs_incomplete_labels": empty_labels,
        "total_bill": nett + costs_total,
        "total_is_provisional": bool(empty),
        "booking_fee": int(amt("BOOKING_FEE") or 0),
        "plafon_kredit": plafon,
        "self_funding": self_funding,
        "excess_land": int(amt("EXCESS_LAND") or 0),
        "has_excess_land": amt("EXCESS_LAND") is not None and int(amt("EXCESS_LAND")) > 0,
        "note": ("Total masih SEMENTARA: " + ", ".join(empty_labels) + " belum diisi."
                 if empty_labels else None),
    }


# ============================================================ skema → termin ([DOC])
async def scheme_terms_spec(org: str, scheme: str) -> dict:
    """Termin menurut dokumen owner, dibaca dari Pusat Konfigurasi (bukan angka mati).

    Dipakai untuk (a) membuat AR saat kontrak diaktifkan dan (b) menjelaskan aturan jatuh
    tempo di layar & dokumen. Jatuh tempo yang bergantung PERISTIWA (pembangunan 100%,
    akad) ditandai `event` supaya layar tidak berpura-pura tahu tanggal pastinya.
    """
    if scheme == "cash_keras":
        dp = float(await cfg.get("payment.cash.dp_pct", org_id=org) or 80)
        days = int(await cfg.get("payment.cash.payoff_days_after_completion", org_id=org) or 30)
        grace = int(await cfg.get("payment.cash.payoff_grace_days", org_id=org) or 7)
        return {"code": "cash_keras", "name": f"Cash keras (DP {dp:g}% + pelunasan)",
                "items": [
                    {"label": f"DP tahap pertama {dp:g}%", "basis": "percent", "value": dp,
                     "due_offset_days": 0, "due_rule": "sebelum pembangunan dimulai"},
                    {"label": f"Pelunasan {100 - dp:g}%", "basis": "percent",
                     "value": 100 - dp, "due_offset_days": 180,
                     "due_rule": (f"maks {days} hari sejak pemberitahuan pembangunan 100% "
                                  f"(perpanjangan {grace} hari)"), "event": True}]}
    if scheme == "cash_bertahap":
        dp = float(await cfg.get("payment.staged.dp_pct", org_id=org) or 80)
        n = int(await cfg.get("payment.staged.installment_count", org_id=org) or 6)
        day = int(await cfg.get("payment.staged.due_day", org_id=org) or 7)
        grace = int(await cfg.get("payment.staged.grace_day", org_id=org) or 20)
        sisa = 100 - dp
        items = [{"label": f"DP tahap pertama {dp:g}%", "basis": "percent", "value": dp,
                  "due_offset_days": 0, "due_rule": "sebelum pembangunan dimulai"}]
        for i in range(1, n + 1):
            items.append({"label": f"Cicilan {i}/{n}", "basis": "percent",
                          "value": round(sisa / n, 4), "due_offset_days": 30 * i,
                          "due_rule": (f"tanggal {day} tiap bulan · toleransi s/d "
                                       f"tanggal {grace}")})
        return {"code": "cash_bertahap",
                "name": f"Cash bertahap (DP {dp:g}% + {n}× cicilan)", "items": items}
    dp = float(await cfg.get("payment.kpr.dp_pct", org_id=org) or 0)
    items = []
    if dp > 0:
        items.append({"label": f"Uang muka (DP) {dp:g}%", "basis": "percent", "value": dp,
                      "due_offset_days": 0, "due_rule": "sebelum akad kredit"})
    items.append({"label": f"Pencairan KPR {100 - dp:g}%", "basis": "percent",
                  "value": 100 - dp, "due_offset_days": 45,
                  "due_rule": "setelah akad kredit (dana masuk dari bank)", "event": True})
    return {"code": "kpr", "name": f"KPR (DP {dp:g}% + pencairan bank)", "items": items}


async def ensure_payment_scheme(org: str, scheme: str) -> dict:
    """Simpan/segarkan skema AR untuk satu skema bayar, lalu kembalikan dokumennya.

    Skema disimpan di koleksi yang SAMA dengan skema AR lain (`payment_schemes`) supaya
    `finance_engine` tidak perlu tahu apa pun tentang Fase 53 — satu mesin termin.
    """
    spec = await scheme_terms_spec(org, scheme)
    doc = await db.payment_schemes.find_one({"org_id": org, "code": scheme}, {"_id": 0})
    ts = now_iso()
    if doc:
        await db.payment_schemes.update_one(
            {"id": doc["id"]},
            {"$set": {"name": spec["name"], "items": spec["items"], "updated_at": ts}})
        doc.update({"name": spec["name"], "items": spec["items"]})
        return doc
    doc = {"id": new_id(), "org_id": org, "code": scheme, "name": spec["name"],
           "items": spec["items"], "is_default": False, "source": "DOC",
           "created_by": "system", "created_at": ts, "updated_at": ts}
    await db.payment_schemes.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


# ============================================================ kontrak: buat & baca
async def ensure_contract(org: str, deal: dict, customer: dict, scheme: str,
                          actor: str) -> dict:
    """Buat kontrak bila belum ada (idempoten per deal). Tidak pernah menimpa yang ada."""
    existing = await db.contracts.find_one({"org_id": org, "deal_id": deal["id"]}, {"_id": 0})
    if existing:
        return existing
    ts = now_iso()
    unit = await db.units.find_one({"id": deal.get("unit_id")}, {"_id": 0}) or {}
    project = await db.projects.find_one({"id": deal.get("project_id")}, {"_id": 0}) or {}
    number = await seq.next_number("contract", org, prefix="KTR")
    doc = {
        "id": new_id(), "org_id": org, "number": number,
        "deal_id": deal["id"], "lead_id": deal.get("lead_id"),
        "customer_id": customer["id"], "customer_name": customer.get("name"),
        "unit_id": deal.get("unit_id"), "unit_code": unit.get("code"),
        "project_id": deal.get("project_id"), "project_name": project.get("name"),
        "scheme": scheme, "scheme_label": ref.label_of("payment_scheme", scheme),
        "state": "draft", "legal_stage": "belum",
        "costs": {}, "legal": {}, "legal_history": [],
        "assigned_to": deal.get("assigned_to"),
        "quotation_id": deal.get("quotation_id"),
        "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    await db.contracts.insert_one(dict(doc))
    doc.pop("_id", None)
    await db.deals.update_one({"id": deal["id"]}, {"$set": {
        "contract_id": doc["id"], "customer_id": customer["id"], "updated_at": ts}})
    await db.units.update_one({"id": deal.get("unit_id")}, {"$set": {
        "contract_id": doc["id"], "customer_id": customer["id"], "updated_at": ts}})
    await add_activity(entity_type="customer", entity_id=customer["id"], type="system",
                       body=(f"Kontrak {number} dibuat untuk unit {unit.get('code')} "
                             f"(skema {ref.label_of('payment_scheme', scheme)})."),
                       actor=actor, org_id=org)
    return doc


async def get_raw(org: str, contract_id: str) -> dict:
    c = await db.contracts.find_one({"id": contract_id, "org_id": org}, {"_id": 0})
    if not c:
        raise ValueError("Kontrak tidak ditemukan.")
    return c


async def payment_plan(org: str, contract: dict) -> dict:
    """Rencana bayar = AR yang benar-benar menagih + aturan jatuh tempo dari `[DOC]`.

    Bila AR belum ada (deal belum di-booking), dikatakan APA ADANYA beserta sebabnya —
    bukan tabel kosong yang terlihat seperti "tidak ada kewajiban".
    """
    spec = await scheme_terms_spec(org, contract.get("scheme"))
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": contract["deal_id"]},
                                       {"_id": 0})
    rules = [{"label": i["label"], "due_rule": i.get("due_rule"),
              "event_based": bool(i.get("event"))} for i in spec["items"]]
    if not inv:
        deal = await db.deals.find_one({"id": contract["deal_id"]},
                                       {"_id": 0, "status": 1}) or {}
        return {"state": "belum_ada", "rules": rules, "terms": [], "invoice": None,
                "reason": ("Jadwal tagihan belum dibuat. Tagihan lahir setelah reservasi "
                           "dikonfirmasi (booking) atau kontrak diaktifkan; status deal "
                           f"sekarang: {deal.get('status') or '-'}.")}
    terms = []
    for idx, it in enumerate(inv.get("items") or []):
        rule = spec["items"][idx] if idx < len(spec["items"]) else {}
        terms.append({**it, "no": idx + 1, "due_rule": rule.get("due_rule"),
                      "event_based": bool(rule.get("event"))})
    return {"state": "ada", "rules": rules, "terms": terms,
            "invoice": {"id": inv["id"], "total": inv.get("total"), "paid": inv.get("paid"),
                        "outstanding": inv.get("outstanding"), "status": inv.get("status"),
                        "scheme_name": inv.get("scheme_name")},
            "reason": None}


async def _excess_land_paid(org: str, contract: dict, breakdown: dict) -> bool:
    """Kelebihan tanah lunas? `[DOC]`: wajib lunas SEBELUM akad kredit.

    Dibaca dari uang yang benar-benar masuk (AR terbayar ≥ nilai kelebihan tanah). Tidak
    ada penanda manual "sudah lunas" — penanda seperti itu bisa dicentang tanpa uang.
    """
    if not breakdown.get("has_excess_land"):
        return True
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": contract["deal_id"]},
                                       {"_id": 0, "paid": 1})
    return int((inv or {}).get("paid") or 0) >= int(breakdown.get("excess_land") or 0)


async def _spkt_exists(org: str, contract: dict) -> bool:
    n = await db.documents.count_documents({"org_id": org, "deal_id": contract["deal_id"],
                                           "template_code": "SPKT"})
    return n > 0


async def legal_gates(org: str, contract: dict, breakdown: dict = None) -> dict:
    """Untuk setiap tahap legal: boleh dimajukan atau tidak, beserta SEBABnya (SSOT)."""
    bd = breakdown or await build_breakdown(org, contract)
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": contract["deal_id"]},
                                       {"_id": 0})
    scheme = contract.get("scheme")
    legal = contract.get("legal") or {}
    kpr = await kprmod.kpr_of(org, contract)
    handover = await db.unit_handovers.find_one(
        {"org_id": org, "unit_id": contract.get("unit_id"),
         "state": {"$nin": ["dibatalkan"]}}, {"_id": 0})
    paid = int((inv or {}).get("paid") or 0)
    dp_amount = int(((inv or {}).get("items") or [{}])[0].get("amount") or 0) if inv else 0
    out = {}

    def gate(stage, blocks):
        out[stage] = {
            "stage": stage, "label": ref.label_of("contract_legal_stage", stage),
            "done": bool(legal.get(stage)),
            "ok": not blocks,
            "blocks": [{"code": c, "label": ref.label_of("legal_block", c), "detail": d}
                       for c, d in blocks],
        }

    # --- PPJB: DP/termin pertama harus benar-benar masuk.
    b = []
    if not inv:
        b.append(("dp_belum_bayar", "Jadwal tagihan belum ada — booking dulu."))
    elif paid < dp_amount or paid <= 0:
        b.append(("dp_belum_bayar",
                  f"DP {_rp(dp_amount)} belum terbayar (baru {_rp(paid)} diterima)."))
    gate("ppjb", b)

    # --- Akad kredit: hanya KPR, wajib SP3K + kelebihan tanah lunas `[DOC]`.
    b = []
    if scheme != "kpr":
        b.append(("bukan_kpr", "Akad kredit hanya ada pada skema KPR."))
    else:
        app = kpr.get("application") or {}
        sp3k = app.get("sp3k") or {}
        if not (sp3k.get("file_id") and int(app.get("approved_plafon") or 0) > 0):
            b.append(("sp3k_belum",
                      "SP3K bank belum tercatat lengkap (butuh berkas SP3K + plafon "
                      "disetujui)."))
        if bd.get("has_excess_land"):
            if not await _spkt_exists(org, contract):
                b.append(("spkt_belum_ada",
                          "Ada kelebihan tanah tetapi SPKT belum diterbitkan."))
            if not await _excess_land_paid(org, contract, bd):
                b.append(("kelebihan_tanah_belum_lunas",
                          f"Kelebihan tanah {_rp(bd.get('excess_land'))} wajib lunas "
                          "sebelum akad kredit."))
    gate("akad_kredit", b)

    # --- Pelunasan: dikonfirmasi dari uang yang masuk, bukan dari klik.
    b = []
    if not inv:
        b.append(("belum_lunas", "Jadwal tagihan belum ada."))
    elif int(inv.get("outstanding") or 0) > 0:
        b.append(("belum_lunas",
                  f"Sisa kewajiban {_rp(inv.get('outstanding'))} belum dibayar."))
    gate("pelunasan", b)

    # --- BAST: serah terima kunci hanya setelah lunas (mesin serah terima yang menilai).
    b = []
    if not handover:
        b.append(("bast_belum",
                  "Serah terima (BAST) belum diterbitkan di menu Serah Terima & Garansi."))
    gate("bast", b)

    # --- AJB: KPR -> setelah akad; tunai -> setelah pelunasan & BAST.
    b = []
    if not legal.get("ppjb"):
        b.append(("urutan_salah", "PPJB belum ditandatangani."))
    if scheme == "kpr":
        if not legal.get("akad_kredit"):
            b.append(("akad_belum", "Pada skema KPR, AJB menyusul akad kredit."))
    else:
        if inv and int(inv.get("outstanding") or 0) > 0:
            b.append(("belum_lunas", "Skema tunai: AJB setelah pelunasan."))
        if not handover:
            b.append(("bast_belum", "Skema tunai: AJB setelah serah terima (BAST)."))
    gate("ajb", b)

    # --- Sertifikat (SHGB).
    b = []
    if not legal.get("ajb"):
        b.append(("urutan_salah", "AJB belum ditandatangani."))
    gate("sertifikat", b)
    return out


async def enrich(org: str, contract: dict) -> dict:
    """Kontrak + semua yang dibutuhkan layar: rincian, rencana bayar, legal, KPR, dokumen."""
    bd = await build_breakdown(org, contract)
    plan = await payment_plan(org, contract)
    gates = await legal_gates(org, contract, bd)
    kpr = await kprmod.kpr_of(org, contract)
    docs = await db.documents.find(
        {"org_id": org, "deal_id": contract["deal_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    customer = await db.customers.find_one({"id": contract.get("customer_id")},
                                          {"_id": 0, "name": 1, "phone": 1, "nik": 1}) or {}
    deal = await db.deals.find_one({"id": contract["deal_id"]}, {"_id": 0}) or {}
    shgb_months = int(await cfg.get("legal.shgb_months_after_ajb", org_id=org) or 6)
    return {**contract, "breakdown": bd, "payment_plan": plan, "gates": gates, "kpr": kpr,
            "documents": docs, "customer": customer,
            "deal": {"id": deal.get("id"), "status": deal.get("status"),
                     "unit_code": deal.get("unit_code"),
                     "booking_fee": deal.get("booking_fee"),
                     "reserved_until": deal.get("reserved_until"),
                     "quotation_no": deal.get("quotation_no")},
            "legal_order": [s for s in LEGAL_ORDER
                            if s != "akad_kredit" or contract.get("scheme") == "kpr"],
            "shgb_months_after_ajb": shgb_months,
            "doc_template_for_scheme": SCHEME_DOC.get(contract.get("scheme"))}


# ============================================================ perubahan kontrak
async def set_costs(org: str, contract_id: str, payload: dict, actor: str) -> dict:
    """Isi/ubah komponen biaya. `None` DIABAIKAN (tidak menghapus nilai yang sudah ada);
    kirim -1 untuk mengosongkan kembali menjadi "belum diisi"."""
    c = await get_raw(org, contract_id)
    if c.get("state") == "cancelled":
        raise ValueError("Kontrak sudah dibatalkan.")
    costs = dict(c.get("costs") or {})
    changed = []
    for k in (*COST_FIELDS, "promo_discount", "plafon_kredit", "dp_percent"):
        v = payload.get(k)
        if v is None:
            continue
        if isinstance(v, (int, float)) and v < 0:
            costs.pop(k, None)
            changed.append(f"{k}=dikosongkan")
            continue
        costs[k] = int(v) if k != "dp_percent" else float(v)
        changed.append(f"{k}={costs[k]}")
    ts = now_iso()
    await db.contracts.update_one({"id": contract_id}, {"$set": {
        "costs": costs, "updated_at": ts, "costs_updated_by": actor,
        "costs_updated_at": ts}})
    if changed:
        await add_activity(entity_type="customer", entity_id=c.get("customer_id"),
                           type="system", actor=actor, org_id=org,
                           body=(f"Komponen biaya kontrak {c.get('number')} diperbarui: "
                                 + ", ".join(changed)))
    return await get_raw(org, contract_id)


async def set_scheme(org: str, contract_id: str, scheme: str, actor: str,
                     reason: str = None) -> dict:
    if scheme not in SCHEMES:
        raise ValueError(f"Skema '{scheme}' tidak dikenal.")
    c = await get_raw(org, contract_id)
    if c.get("scheme") == scheme:
        return c
    if c.get("legal") or {}:
        if any((c.get("legal") or {}).get(s) for s in LEGAL_ORDER):
            raise ValueError("Skema tidak bisa diubah setelah ada tahap legal — terbitkan "
                             "adendum/kontrak baru.")
    ts = now_iso()
    await db.contracts.update_one({"id": contract_id}, {"$set": {
        "scheme": scheme, "scheme_label": ref.label_of("payment_scheme", scheme),
        "updated_at": ts},
        "$push": {"scheme_history": {"from": c.get("scheme"), "to": scheme, "at": ts,
                                     "by": actor, "reason": reason}}})
    await add_activity(entity_type="customer", entity_id=c.get("customer_id"),
                       type="system", actor=actor, org_id=org,
                       body=(f"Skema kontrak {c.get('number')} diubah menjadi "
                             f"{ref.label_of('payment_scheme', scheme)}"
                             + (f" — {reason}" if reason else ".")))
    return await get_raw(org, contract_id)


async def activate(org: str, contract_id: str, actor: str) -> dict:
    """Aktifkan kontrak: termin AR dibuat/disegarkan dari skema `[DOC]` kontrak ini.

    Kenapa AR dibuat ulang: saat deal di-booking, AR lahir dari skema BAWAAN keuangan
    ("Standar KPR (DP 20%)") — bukan skema kontrak. Sesudah kontrak punya skema resmi,
    tagihan harus mengikuti dokumen yang ditandatangani pembeli, bukan bawaan sistem.
    """
    c = await get_raw(org, contract_id)
    deal = await db.deals.find_one({"id": c["deal_id"]}, {"_id": 0})
    if not deal:
        raise ValueError("Deal kontrak ini tidak ditemukan.")
    if deal.get("status") not in ("booked", "completed"):
        raise ValueError("Kontrak hanya bisa diaktifkan setelah reservasi dikonfirmasi "
                         "(booking).")
    scheme_doc = await ensure_payment_scheme(org, c.get("scheme"))
    inv = await fin.create_ar_for_deal(deal, scheme_id=scheme_doc["id"], org_id=org,
                                       replace=True, actor=actor)
    ts = now_iso()
    await db.contracts.update_one({"id": contract_id}, {"$set": {
        "state": "active", "activated_at": ts, "activated_by": actor,
        "ar_invoice_id": inv.get("id"), "payment_scheme_id": scheme_doc["id"],
        "updated_at": ts}})
    await add_activity(entity_type="customer", entity_id=c.get("customer_id"),
                       type="system", actor=actor, org_id=org,
                       body=(f"Kontrak {c.get('number')} diaktifkan — termin mengikuti "
                             f"skema {scheme_doc.get('name')} (total "
                             f"{_rp(inv.get('total'))})."))
    return await get_raw(org, contract_id)


# ============================================================ tahap legal
async def legal_advance(org: str, contract_id: str, stage: str, payload: dict,
                        actor: str) -> dict:
    """Majukan satu tahap legal setelah gerbang buktinya lulus. Menulis jejak + cermin deal."""
    if stage not in LEGAL_ORDER:
        raise ValueError(f"Tahap legal '{stage}' tidak dikenal.")
    c = await get_raw(org, contract_id)
    if (c.get("legal") or {}).get(stage):
        raise ValueError(f"Tahap {ref.label_of('contract_legal_stage', stage)} sudah "
                         "tercatat untuk kontrak ini.")
    gates = await legal_gates(org, c)
    g = gates.get(stage) or {}
    if not g.get("ok"):
        sebab = " ".join(b["detail"] for b in g.get("blocks", []))
        raise ValueError(f"Belum bisa dimajukan ke {g.get('label')}. {sebab}".strip())
    ts = now_iso()
    number = payload.get("number")
    if stage in ("ppjb", "ajb") and not number:
        number = await seq.next_number(f"legal:{stage}", org, prefix=stage.upper())
    entry = {"stage": stage, "label": ref.label_of("contract_legal_stage", stage),
             "number": number, "date": payload.get("date") or ts[:10],
             "notary": payload.get("notary"), "place": payload.get("place"),
             "file_id": payload.get("file_id"), "note": payload.get("note"),
             "at": ts, "by": actor}
    await db.contracts.update_one({"id": contract_id}, {
        "$set": {f"legal.{stage}": entry, "legal_stage": stage, "updated_at": ts},
        "$push": {"legal_history": entry}})
    # ---- cermin ke `deals` supaya layar & gate lama tetap menyatakan hal yang sama ----
    deal_set = {"updated_at": ts}
    if stage == "ppjb":
        deal_set.update({"legal_stage": "ppjb", "ppjb": {
            "number": number, "signed_date": entry["date"], "signed_by": c.get("customer_name"),
            "note": entry["note"], "created_at": ts}})
        await auto_create_task(
            source_event=f"contract.ajb:{contract_id}",
            title=f"Jadwalkan AJB / akad: {c.get('customer_name')} · unit {c.get('unit_code')}",
            type="follow_up", related_entity_type="contract", related_entity_id=contract_id,
            assigned_to=c.get("assigned_to"), due_date=due_in(days=14), priority="medium",
            org_id=org)
    if stage == "ajb":
        deal_set.update({"legal_stage": "ajb", "status": "completed", "sold_at": ts,
                         "ajb": {"number": number, "notary": entry["notary"],
                                 "signed_date": entry["date"],
                                 "buyer": c.get("customer_name"), "note": entry["note"],
                                 "created_at": ts}})
        await db.units.update_one({"id": c.get("unit_id"), "org_id": org}, {"$set": {
            "status": "sold", "sold_at": ts, "sold_by_deal": c["deal_id"],
            "updated_at": ts}})
        await db.contracts.update_one({"id": contract_id},
                                      {"$set": {"state": "completed"}})
        await emit("deal.ajb", "deal", c["deal_id"],
                   {"unit_id": c.get("unit_id"), "number": number}, org_id=org)
        await emit("deal.sold", "deal", c["deal_id"], {"unit_id": c.get("unit_id")},
                   org_id=org)
        await dispatch_pending()
    await db.deals.update_one({"id": c["deal_id"]}, {"$set": deal_set})
    await add_activity(entity_type="customer", entity_id=c.get("customer_id"), type="system",
                       actor=actor, org_id=org,
                       body=(f"{entry['label']}" + (f" {number}" if number else "")
                             + f" tercatat untuk unit {c.get('unit_code')}."))
    return await get_raw(org, contract_id)


# ============================================================ daftar
async def listing(org: str = ORG_ID, *, customer_id: str = None, deal_id: str = None,
                  scheme: str = None, state: str = None, legal_stage: str = None,
                  q: str = None, skip: int = 0, limit: int = 50) -> dict:
    query = {"org_id": org}
    if customer_id:
        query["customer_id"] = customer_id
    if deal_id:
        query["deal_id"] = deal_id
    if scheme:
        query["scheme"] = scheme
    if state:
        query["state"] = state
    if legal_stage:
        query["legal_stage"] = legal_stage
    if q:
        query["$or"] = [{"number": {"$regex": q, "$options": "i"}},
                        {"customer_name": {"$regex": q, "$options": "i"}},
                        {"unit_code": {"$regex": q, "$options": "i"}}]
    total = await db.contracts.count_documents(query)
    rows = await (db.contracts.find(query, {"_id": 0})
                  .sort("created_at", -1).skip(int(skip)).limit(int(limit))
                  .to_list(int(limit)))
    for r in rows:
        inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": r["deal_id"]},
                                           {"_id": 0, "total": 1, "paid": 1,
                                            "outstanding": 1, "status": 1})
        r["ar"] = inv
    counts = {}
    for st in ("draft", "active", "completed", "cancelled"):
        counts[st] = await db.contracts.count_documents({"org_id": org, "state": st})
    return {"data": rows, "total": total, "counts": counts}
