"""MESIN HARGA — SKEMA DISKON, PROMO, KUPON (Fase 69).

Cacat yang ditutup: diskon penawaran diketik bebas (Rp berapa pun) dan reservasi langsung
tidak memakai mesin harga sama sekali. Kini:

  1. **Diskon tidak pernah diketik.** Nilainya lahir dari SKEMA DISKON yang dikonfigurasi
     (persen/nominal, batas maksimal, berlaku per proyek/tipe unit, periode). Skema boleh
     ditandai `requires_approval` → penawaran menunggu manajer.
  2. **Promo** adalah aturan potongan yang berlaku otomatis dipilih dari master; **kupon**
     adalah kode berperiode dengan KUOTA total & per pembeli, dan setiap pemakaian berjejak
     (`coupon_redemptions`) — dilepas kembali bila transaksinya batal.
  3. Satu fungsi `compute_discounts` dipakai penawaran DAN reservasi langsung, sehingga
     keduanya menghasilkan rincian yang sama.
"""
import logging

import settings_store as cfg
from core_utils import new_id, now_iso, today_iso_date
from db import ORG_ID, db

logger = logging.getLogger("sipro.pricing")

COLLECTIONS = {"discount_scheme": "discount_schemes", "promo": "promos", "coupon": "coupons"}
LABEL = {"discount_scheme": "Skema diskon", "promo": "Promo", "coupon": "Kupon"}


def _coll(kind: str):
    if kind not in COLLECTIONS:
        raise ValueError("Jenis aturan harga tidak dikenal.")
    return db[COLLECTIONS[kind]]


def _round(v) -> int:
    return int(round(float(v or 0)))


def _amount_of(rule: dict, gross: int) -> int:
    if rule.get("kind") == "percent":
        amt = _round(gross * float(rule.get("value") or 0) / 100)
    else:
        amt = _round(rule.get("value") or 0)
    cap = int(rule.get("max_amount") or 0)
    if cap and amt > cap:
        amt = cap
    return min(amt, int(gross))


def _in_window(rule: dict, today: str) -> bool:
    if rule.get("valid_from") and str(rule["valid_from"])[:10] > today:
        return False
    if rule.get("valid_until") and str(rule["valid_until"])[:10] < today:
        return False
    return True


def _applies_to_unit(rule: dict, unit: dict) -> bool:
    projects = rule.get("applies_project_ids") or []
    if projects and unit.get("project_id") not in projects:
        return False
    types = rule.get("applies_unit_types") or []
    if types and not ({unit.get("type"), unit.get("unit_type_code")} & set(types)):
        return False
    return True


def _check_usable(kind: str, rule: dict, unit: dict) -> None:
    label = LABEL[kind]
    if rule.get("active") is False:
        raise ValueError(f"{label} '{rule.get('code')}' sudah tidak aktif.")
    if not _in_window(rule, today_iso_date()):
        raise ValueError(f"{label} '{rule.get('code')}' di luar masa berlaku "
                         f"({rule.get('valid_from') or '…'} s/d {rule.get('valid_until') or '…'}).")
    if not _applies_to_unit(rule, unit):
        raise ValueError(f"{label} '{rule.get('code')}' tidak berlaku untuk unit "
                         f"{unit.get('code')} (proyek/tipe unit berbeda).")


def _target_of(rule: dict) -> str:
    return rule.get("target") or "price"


ALL_COST = "*"  # sasaran "semua komponen biaya pembeli" (promo "potongan all-in Rp X")


def target_label(rule: dict) -> str:
    """Label sasaran untuk layar & dokumen: 'Uang muka', 'Booking fee', 'BPHTB', …"""
    t = _target_of(rule)
    if t == "cost":
        if (rule.get("target_component") or "") == ALL_COST:
            return "seluruh biaya all-in pembeli"
        return f"komponen biaya {rule.get('target_component') or '?'}"
    return {"price": "harga jual", "dp": "uang muka / DP", "booking_fee": "booking fee"}[t]


def _base_of(rule: dict, bases: dict) -> int:
    """Dasar hitung persen = nilai komponen sasaran (harga, DP, booking fee, atau biaya)."""
    t = _target_of(rule)
    key = f"cost:{rule.get('target_component')}" if t == "cost" else t
    v = bases.get(key)
    return int(v) if v is not None else 0


def _line(kind: str, rule: dict, gross: int, bases: dict = None) -> dict:
    bases = bases if bases is not None else {"price": gross}
    base = _base_of(rule, bases)
    target = _target_of(rule)
    known = (f"cost:{rule.get('target_component')}" if target == "cost" else target) in bases
    amt = _amount_of(rule, base) if known else 0
    return {
        "source": kind, "source_label": LABEL[kind], "rule_id": rule["id"],
        "code": rule.get("code"), "name": rule.get("name"), "kind": rule.get("kind"),
        "value": rule.get("value"), "max_amount": rule.get("max_amount") or 0,
        "target": target, "target_component": rule.get("target_component"),
        "target_label": target_label(rule), "base": base, "pending": not known,
        "amount": amt, "pct": round(amt / base * 100, 2) if base else 0,
        "requires_approval": bool(rule.get("requires_approval")),
        "formula": (f"{rule.get('value'):g}% × {target_label(rule)}" if rule.get("kind") == "percent"
                    else "nominal tetap") + (f", maks Rp {int(rule.get('max_amount')):,}"
                                              .replace(",", ".") if rule.get("max_amount") else "")
                   + (f" — dipotong dari {target_label(rule)}" if target != "price" else ""),
    }


# ------------------------------------------------------------------ CRUD
async def listing(kind: str, org: str = ORG_ID, active: bool = None) -> list:
    q = {"org_id": org}
    if active is not None:
        q["active"] = active
    rows = await _coll(kind).find(q, {"_id": 0}).sort("code", 1).to_list(500)
    today = today_iso_date()
    for r in rows:
        r["in_window"] = _in_window(r, today)
        if kind == "coupon":
            quota = int(r.get("quota_total") or 0)
            r["remaining"] = (quota - int(r.get("used_count") or 0)) if quota else None
    return rows


async def create(kind: str, payload: dict, actor: str, org: str = ORG_ID) -> dict:
    coll = _coll(kind)
    code = payload["code"]
    if await coll.find_one({"org_id": org, "code": code}, {"_id": 1}):
        raise ValueError(f"{LABEL[kind]} dengan kode '{code}' sudah ada.")
    if payload.get("valid_from") and payload.get("valid_until") \
            and payload["valid_from"] > payload["valid_until"]:
        raise ValueError("Tanggal mulai tidak boleh melewati tanggal selesai.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, **payload, "created_by": actor,
           "created_at": ts, "updated_at": ts}
    if kind == "coupon":
        doc.setdefault("used_count", 0)
    await coll.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def update(kind: str, rule_id: str, patch: dict, actor: str, org: str = ORG_ID) -> dict:
    patch = {k: v for k, v in patch.items() if v is not None}
    if not patch:
        raise ValueError("Tidak ada perubahan.")
    if patch.get("kind") == "percent" and float(patch.get("value") or 0) > 100:
        raise ValueError("Persen potongan maksimal 100.")
    if "target" in patch or "target_component" in patch:
        cur = await get_rule(kind, rule_id, org)
        merged = {**cur, **patch}
        if merged.get("target") == "cost" and not (merged.get("target_component") or "").strip():
            raise ValueError("Sasaran 'komponen biaya' wajib menyebut kode komponennya.")
        if merged.get("target") != "cost":
            patch["target_component"] = None
    patch.update({"updated_at": now_iso(), "updated_by": actor})
    res = await _coll(kind).update_one({"id": rule_id, "org_id": org}, {"$set": patch})
    if not res.matched_count:
        raise LookupError(f"{LABEL[kind]} tidak ditemukan.")
    return await _coll(kind).find_one({"id": rule_id}, {"_id": 0})


async def get_rule(kind: str, rule_id: str, org: str = ORG_ID) -> dict:
    r = await _coll(kind).find_one({"id": rule_id, "org_id": org}, {"_id": 0})
    if not r:
        raise ValueError(f"{LABEL[kind]} tidak ditemukan.")
    return r


# ------------------------------------------------------------------ kupon
async def _customer_uses(org: str, coupon_id: str, lead_id: str) -> int:
    if not lead_id:
        return 0
    return await db.coupon_redemptions.count_documents(
        {"org_id": org, "coupon_id": coupon_id, "lead_id": lead_id, "state": "used"})


async def validate_coupon(org: str, code: str, *, unit: dict, lead_id: str = None) -> dict:
    """Kupon yang boleh dipakai SEKARANG — atau alasan jelas kenapa tidak."""
    code = (code or "").strip().upper()
    c = await db.coupons.find_one({"org_id": org, "code": code}, {"_id": 0})
    if not c:
        raise ValueError(f"Kupon '{code}' tidak ditemukan.")
    _check_usable("coupon", c, unit)
    quota = int(c.get("quota_total") or 0)
    used = int(c.get("used_count") or 0)
    if quota and used >= quota:
        raise ValueError(f"Kuota kupon '{code}' sudah habis ({used}/{quota}).")
    per = int(c.get("quota_per_customer") or 0)
    if per and lead_id and await _customer_uses(org, c["id"], lead_id) >= per:
        raise ValueError(f"Kupon '{code}' sudah dipakai pembeli ini sebanyak batasnya ({per}×).")
    return c


async def redeem_coupon(org: str, coupon_code: str, *, unit: dict, lead: dict, ref_type: str,
                        ref_id: str, amount: int, actor: str) -> dict:
    """Pakai kupon SECARA ATOMIK (kuota tidak bisa terlampaui oleh dua transaksi bersamaan)."""
    c = await validate_coupon(org, coupon_code, unit=unit, lead_id=lead.get("id"))
    quota = int(c.get("quota_total") or 0)
    cond = {"id": c["id"], "org_id": org}
    if quota:
        cond["used_count"] = {"$lt": quota}
    hit = await db.coupons.find_one_and_update(cond, {"$inc": {"used_count": 1},
                                                      "$set": {"updated_at": now_iso()}})
    if hit is None:
        raise ValueError(f"Kuota kupon '{c['code']}' habis tepat sebelum transaksi ini.")
    red = {"id": new_id(), "org_id": org, "coupon_id": c["id"], "coupon_code": c["code"],
           "lead_id": lead.get("id"), "lead_name": lead.get("name"),
           "unit_id": unit.get("id"), "unit_code": unit.get("code"),
           "ref_type": ref_type, "ref_id": ref_id, "amount": int(amount or 0),
           "state": "used", "used_at": now_iso(), "used_by": actor, "released_at": None}
    await db.coupon_redemptions.insert_one(dict(red))
    red.pop("_id", None)
    return red


async def release_coupon(org: str, *, ref_type: str, ref_id: str, actor: str) -> int:
    """Transaksi batal → kupon dilepas & kuota dikembalikan (berjejak, tidak dihapus)."""
    n = 0
    async for r in db.coupon_redemptions.find({"org_id": org, "ref_type": ref_type,
                                               "ref_id": ref_id, "state": "used"}):
        await db.coupon_redemptions.update_one({"id": r["id"]}, {"$set": {
            "state": "released", "released_at": now_iso(), "released_by": actor}})
        await db.coupons.update_one({"id": r["coupon_id"], "used_count": {"$gt": 0}},
                                    {"$inc": {"used_count": -1}})
        n += 1
    return n


async def redemptions(org: str, coupon_id: str) -> list:
    return await db.coupon_redemptions.find({"org_id": org, "coupon_id": coupon_id},
                                            {"_id": 0}).sort("used_at", -1).to_list(500)


def dp_term_index(items: list) -> int:
    """Termin 'uang muka': label mengandung DP/uang muka, kalau tidak ada → termin pertama."""
    for i, t in enumerate(items):
        lbl = str(t.get("label") or "").lower()
        if "dp" in lbl.split() or "uang muka" in lbl or lbl.startswith("dp"):
            return i
    return 0 if items else -1


def apply_component_discounts(items: list, comp: dict) -> list:
    """Fase 88C: potongan bersasaran DP/booking fee dikurangkan dari termin uang muka —
    jumlah termin tetap = harga bersih, tetapi potongannya TERLIHAT pada komponen yang dijanjikan."""
    amt = int((comp or {}).get("dp") or 0) + int((comp or {}).get("booking_fee") or 0)
    if not items or amt <= 0:
        return items
    i = dp_term_index(items)
    cut = min(amt, int(items[i]["amount"]))
    items[i]["amount"] = int(items[i]["amount"]) - cut
    items[i]["discount"] = cut
    items[i]["label_note"] = f"setelah potongan Rp {cut:,}".replace(",", ".")
    rest = amt - cut
    for t in items[i + 1:]:
        if rest <= 0:
            break
        c = min(rest, int(t["amount"]))
        t["amount"] = int(t["amount"]) - c
        t["discount"] = c
        rest -= c
    return items


# ------------------------------------------------------------------ hitung potongan
async def compute_discounts(org: str, *, unit: dict, gross: int, discount_scheme_id: str = None,
                            promo_id: str = None, coupon_code: str = None,
                            lead_id: str = None, bases: dict = None) -> dict:
    """Rincian potongan dari ATURAN, bukan angka ketikan. Dipakai penawaran & reservasi.

    Fase 88C: setiap aturan punya SASARAN. `bases` = nilai komponen yang boleh dipotong
    (`price`, `dp`, `booking_fee`, `cost:<KODE>`); komponen yang belum diketahui (biaya
    all-in sebelum skema dipilih) menghasilkan baris `pending` dan dihitung ulang oleh
    `apply_cost_discounts` saat komponennya sudah ada.
    """
    bases = {"price": int(gross), **(bases or {})}
    lines = []
    if discount_scheme_id:
        s = await get_rule("discount_scheme", discount_scheme_id, org)
        _check_usable("discount_scheme", s, unit)
        lines.append(_line("discount_scheme", s, gross, bases))
    if promo_id:
        p = await get_rule("promo", promo_id, org)
        _check_usable("promo", p, unit)
        lines.append(_line("promo", p, gross, bases))
    if coupon_code:
        stack = await cfg.get("pricing.allow_stack_promo_coupon", org_id=org)
        if promo_id and stack is False:
            raise ValueError("Promo dan kupon tidak boleh digabung (aturan organisasi).")
        promo_rule = next((x for x in lines if x["source"] == "promo"), None)
        c = await validate_coupon(org, coupon_code, unit=unit, lead_id=lead_id)
        if promo_rule and promo_rule.get("code") and promo_id:
            p = await get_rule("promo", promo_id, org)
            if p.get("stackable") is False:
                raise ValueError(f"Promo '{p.get('code')}' tidak bisa digabung dengan kupon.")
        lines.append({**_line("coupon", c, gross, bases), "coupon_code": c["code"]})
    by_target = split_by_target(lines)
    price_total = by_target["price"] + by_target["dp"] + by_target["booking_fee"]
    if price_total > gross:
        raise ValueError(f"Total potongan Rp {price_total:,} melebihi harga Rp {gross:,}."
                         .replace(",", "."))
    if by_target["dp"] > int(bases.get("dp") or 0) and "dp" in bases:
        raise ValueError("Potongan uang muka melebihi nilai uang mukanya sendiri.")
    if by_target["booking_fee"] > int(bases.get("booking_fee") or 0) and "booking_fee" in bases \
            and by_target["booking_fee"]:
        raise ValueError("Potongan booking fee melebihi nilai booking fee.")
    return {"lines": lines, "total": int(price_total), "by_target": by_target,
            "needs_approval": any(x["requires_approval"] for x in lines),
            "coupon_code": (coupon_code or "").strip().upper() or None}


def split_by_target(lines: list) -> dict:
    """Jumlah potongan per sasaran: price/dp/booking_fee mengurangi kewajiban harga;
    `cost` per komponen (kunci `cost:<KODE>`) mengurangi tagihan biaya itu."""
    out = {"price": 0, "dp": 0, "booking_fee": 0, "addon": 0}
    for x in lines:
        t = x.get("target") or "price"
        if t == "cost":
            k = f"cost:{x.get('target_component')}"
            out[k] = out.get(k, 0) + int(x.get("amount") or 0)
        else:
            out[t] += int(x.get("amount") or 0)
    return out


def apply_cost_discounts(lines: list, components: list) -> list:
    """Hitung baris bersasaran komponen biaya terhadap snapshot komponen all-in, lalu
    kurangi nilai komponennya (jejak `discount` tersimpan pada komponen — bukan diam-diam)."""
    by_code = {c["code"]: c for c in components or []}
    for x in lines:
        if x.get("target") != "cost":
            continue
        if (x.get("target_component") or "") == ALL_COST:
            _apply_all_cost_discount(x, components or [])
            continue
        comp = by_code.get(x.get("target_component"))
        if not comp:
            x.update({"amount": 0, "pending": True,
                      "note": f"Komponen {x.get('target_component')} tidak ada pada skema all-in ini."})
            continue
        base = int(comp.get("amount") or 0)
        rule = {"kind": x["kind"], "value": x["value"], "max_amount": x.get("max_amount")}
        amt = _amount_of(rule, base)
        x.update({"base": base, "amount": amt, "pending": False,
                  "pct": round(amt / base * 100, 2) if base else 0})
        if x.get("kind") != "percent" and amt < int(x.get("value") or 0):
            x["note"] = (f"Nominal Rp {int(x['value']):,} dibatasi nilai komponen "
                         f"{comp.get('name') or comp['code']} Rp {base:,}").replace(",", ".")
        comp["amount"] = base - amt
        comp["discount"] = int(comp.get("discount") or 0) + amt
        comp.setdefault("discount_lines", []).append(
            {"code": x.get("code"), "name": x.get("name"), "amount": amt, "source": x["source"]})
        comp["formula"] = f"{comp.get('formula') or base} − potongan {x.get('code')} Rp {amt:,}".replace(",", ".")
    return lines


def _apply_all_cost_discount(x: dict, components: list) -> None:
    """Sasaran SEMUA: potongan dihitung dari total biaya PEMBELI lalu dibagi berurutan ke
    komponen (BPHTB → notaris → bank → …) sampai nominal habis; jejak per komponen tersimpan."""
    buyer = [c for c in components if c.get("treatment") != "developer_borne"]
    base = sum(int(c.get("amount") or 0) for c in buyer)
    if not buyer or base <= 0:
        x.update({"amount": 0, "pending": True,
                  "note": "Skema all-in ini tidak punya komponen biaya yang ditagih ke pembeli."})
        return
    rule = {"kind": x["kind"], "value": x["value"], "max_amount": x.get("max_amount")}
    total = _amount_of(rule, base)
    rest = total
    for c in buyer:
        if rest <= 0:
            break
        cur = int(c.get("amount") or 0)
        cut = min(rest, cur)
        if cut <= 0:
            continue
        c["amount"] = cur - cut
        c["discount"] = int(c.get("discount") or 0) + cut
        c.setdefault("discount_lines", []).append(
            {"code": x.get("code"), "name": x.get("name"), "amount": cut, "source": x["source"]})
        c["formula"] = f"{c.get('formula') or cur} − potongan {x.get('code')} Rp {cut:,}".replace(",", ".")
        rest -= cut
    x.update({"base": base, "amount": total, "pending": False,
              "pct": round(total / base * 100, 2) if base else 0})
    if x.get("kind") != "percent" and total < int(x.get("value") or 0):
        x["note"] = (f"Nominal Rp {int(x['value']):,} dibatasi total biaya pembeli Rp {base:,}").replace(",", ".")


async def options_for_unit(org: str, unit: dict, lead_id: str = None) -> dict:
    """Aturan yang BOLEH dipilih untuk unit ini (aktif, dalam periode, cocok proyek/tipe)."""
    today = today_iso_date()
    out = {}
    for kind in ("discount_scheme", "promo"):
        rows = await _coll(kind).find({"org_id": org, "active": True}, {"_id": 0}).sort(
            "code", 1).to_list(200)
        out[kind + "s"] = [
            {**r, "target": r.get("target") or "price", "target_label": target_label(r),
             "preview_amount": _amount_of(r, int(unit.get("price") or 0))
             if (r.get("target") or "price") == "price" else None}
            for r in rows if _in_window(r, today) and _applies_to_unit(r, unit)]
    out["discount_limit_pct"] = float(
        await cfg.get("quotation.discount_max_pct_sales", org_id=org) or 0)
    return out


# ------------------------------------------------------------------ seed demo
async def seed_defaults(org: str = ORG_ID) -> dict:
    """Contoh aturan awal supaya layar tidak kosong. Idempoten per kode."""
    ts = now_iso()
    added = 0
    demo = [
        ("discount_scheme", {"code": "DISC-CASH", "name": "Diskon pembayaran tunai keras",
                             "kind": "percent", "value": 2, "max_amount": 0,
                             "requires_approval": False,
                             "note": "Contoh DEMO — potongan 2% untuk cash keras."}),
        ("discount_scheme", {"code": "DISC-MGR", "name": "Diskon khusus persetujuan manajer",
                             "kind": "percent", "value": 5, "max_amount": 50_000_000,
                             "requires_approval": True,
                             "note": "Contoh DEMO — wajib persetujuan manajer."}),
        ("promo", {"code": "PROMO-LAUNCH", "name": "Promo peluncuran (all-in)",
                   "kind": "amount", "value": 2_000_000, "max_amount": 0, "stackable": True,
                   "note": "Contoh DEMO — potongan all-in Rp2.000.000."}),
        ("promo", {"code": "PROMO-DP", "name": "Promo potongan uang muka", "kind": "amount",
                   "value": 5_000_000, "max_amount": 0, "stackable": True, "target": "dp",
                   "note": "Contoh DEMO — Rp5.000.000 dipotong dari termin uang muka (bukan harga)."}),
        ("promo", {"code": "PROMO-BF", "name": "Promo booking fee ringan", "kind": "percent",
                   "value": 50, "max_amount": 0, "stackable": True, "target": "booking_fee",
                   "note": "Contoh DEMO — booking fee dipotong 50%."}),
        ("promo", {"code": "PROMO-BPHTB", "name": "Promo bebas BPHTB 100%", "kind": "percent",
                   "value": 100, "max_amount": 0, "stackable": True, "target": "cost",
                   "target_component": "BPHTB",
                   "note": "Contoh DEMO — komponen biaya BPHTB dipotong penuh."}),
        ("promo", {"code": "PROMO-ALLIN27", "name": "Promo subsidi BPHTB Rp27 juta", "kind": "amount",
                   "value": 27_000_000, "max_amount": 0, "stackable": True, "target": "cost",
                   "target_component": "BPHTB",
                   "note": "Contoh DEMO — Rp27.000.000 dipotong dari komponen biaya BPHTB (bukan harga unit)."}),
        ("coupon", {"code": "SIPRO2026", "name": "Kupon pameran 2026", "kind": "amount",
                    "value": 5_000_000, "max_amount": 0, "quota_total": 50,
                    "quota_per_customer": 1, "used_count": 0,
                    "valid_until": f"{today_iso_date()[:4]}-12-31",
                    "note": "Contoh DEMO — kuota 50, 1× per pembeli."}),
    ]
    for kind, doc in demo:
        coll = _coll(kind)
        if await coll.find_one({"org_id": org, "code": doc["code"]}, {"_id": 1}):
            continue
        await coll.insert_one({"id": new_id(), "org_id": org, "active": True,
                               "applies_project_ids": [], "applies_unit_types": [],
                               "target": "price", "target_component": None,
                               "valid_from": None, "valid_until": None, "created_by": "seed",
                               "created_at": ts, "updated_at": ts, **doc})
        added += 1
    if added:
        logger.info("Mesin harga: %s aturan contoh ditambahkan", added)
    return {"pricing_rules": added}
