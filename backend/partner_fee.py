"""partner_fee.py — Fase 42: MESIN ATURAN FEE MITRA (murni, teruji tanpa server).

Mengapa mesin ini dipisah dari `marketing_fee.py`:
  * `marketing_fee.py` sudah benar untuk PENGAJUAN MANUAL (satu deal, satu persen/nominal)
    dan memegang invarian akuntansi (`2-1500 = Σ netto − terbayar`, jurnal idempoten).
    Itu TIDAK diubah — modul ini hanya menghitung ANGKA yang kemudian masuk lewat pintu
    yang sama, sehingga invarian lama tetap berlaku.
  * Keputusan pemilik D5 (`docs/v2/25_PARTNER_SPEC.md` §3): SEMUA skema fee harus tersedia —
    persen harga, nominal per transaksi, nominal per tipe unit, berjenjang per jumlah,
    berjenjang per nilai, per lead terkualifikasi, dan gabungan. Kalau skema dipilih diam-diam
    saat aturan bentrok, mitra bisa ditagihkan angka yang bukan haknya; karena itu
    `select()` MENOLAK dengan pesan jelas ketika dua aturan sama spesifik.

Semua fungsi hitung di sini MURNI (tanpa I/O) supaya bisa diuji angka demi angka.
"""
import logging

import sequences as seq
from core_utils import new_id, now_iso
from db import db, ORG_ID

logger = logging.getLogger("sipro.partner_fee")

BASES = ("percent_price", "fixed_per_deal", "fixed_per_unit_type", "tier_volume",
         "tier_value", "per_lead_qualified", "hybrid")
PRICE_BASES = ("gross", "nett", "after_discount")
TRIGGERS = ("booking_fee_verified", "spr_signed", "ppjb_signed", "akad_kredit",
            "ajb_signed", "full_payment")
TAX_TYPES = ("pph21", "pph23", "none")
TIER_MODES = ("percent", "fixed")
PERIODS = ("monthly", "quarterly", "project")
STATUSES = ("active", "inactive")
SCOPE_KEYS = ("project_id", "cluster_id", "unit_type")


# --------------------------------------------------------------- dasar harga
def price_of(deal: dict, price_base: str = "gross") -> tuple:
    """(nominal, penjelasan). Penjelasan ikut disimpan supaya angka fee bisa dipertanggungkan."""
    deal = deal or {}
    gross = int(deal.get("price") or 0)
    discount = int(deal.get("discount") or deal.get("discount_amount") or 0)
    after = max(0, gross - discount)
    if price_base == "gross":
        return gross, "harga jual unit"
    if price_base == "after_discount":
        return after, f"harga jual − diskon ({discount:,})".replace(",", ".")
    nett = deal.get("nett_price")
    if nett is None:
        return after, ("harga jual − diskon (deal belum menyimpan `nett_price`, "
                       "jadi dasar nett memakai harga setelah diskon)")
    return int(nett), "harga nett tersimpan pada deal"


def _num(value, field="nilai") -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} harus berupa angka.")


def _tier_pick(tiers: list, amount: float) -> dict:
    for tier in tiers or []:
        low = _num(tier.get("min") or 0, "batas bawah tier")
        raw_max = tier.get("max")
        high = None if raw_max in (None, "") else _num(raw_max, "batas atas tier")
        if amount >= low and (high is None or amount <= high):
            return tier
    return None


# --------------------------------------------------------------- perhitungan
def evaluate(rule: dict, ctx: dict) -> dict:
    """Hitung fee BRUTO satu aturan. `ctx` = {deal, unit, closings_count, closings_value,
    qualified_leads}. Melempar ValueError bila data yang dibutuhkan aturan tidak ada —
    lebih baik menolak daripada mengarang angka."""
    basis = rule.get("basis")
    if basis not in BASES:
        raise ValueError(f"Dasar fee tidak dikenal: {basis}")
    ctx = ctx or {}
    deal = ctx.get("deal") or {}
    unit = ctx.get("unit") or {}
    detail = {"basis": basis}

    if basis == "percent_price":
        base_amount, note = price_of(deal, rule.get("price_base") or "gross")
        pct = _num(rule.get("value"), "persentase fee")
        if base_amount <= 0:
            raise ValueError("Harga deal belum terisi — fee persen tidak bisa dihitung.")
        gross = round(base_amount * pct / 100.0)
        detail.update({"price_base": rule.get("price_base") or "gross", "base_amount": base_amount,
                       "base_note": note, "percent": pct})
    elif basis == "fixed_per_deal":
        gross = int(_num(rule.get("value"), "nominal fee"))
        detail.update({"amount": gross})
    elif basis == "fixed_per_unit_type":
        table = rule.get("by_unit_type") or {}
        code = unit.get("unit_type_code") or unit.get("type") or deal.get("unit_type")
        if not code:
            raise ValueError("Tipe unit tidak diketahui — aturan per tipe unit tidak bisa dipakai.")
        if str(code) not in {str(k) for k in table}:
            raise ValueError(f"Tipe unit '{code}' belum punya nominal fee pada aturan ini.")
        gross = int(_num(table.get(str(code), table.get(code)), f"nominal fee tipe {code}"))
        detail.update({"unit_type": str(code), "amount": gross})
    elif basis in ("tier_volume", "tier_value"):
        measure = (ctx.get("closings_count") if basis == "tier_volume"
                   else ctx.get("closings_value"))
        if measure is None:
            raise ValueError("Jumlah/nilai closing periode belum dihitung — tier tidak bisa dipilih.")
        tier = _tier_pick(rule.get("tiers"), float(measure))
        if not tier:
            raise ValueError(f"Tidak ada tier yang mencakup nilai {measure} pada aturan ini.")
        mode = tier.get("mode") or "percent"
        if mode not in TIER_MODES:
            raise ValueError(f"Mode tier tidak dikenal: {mode}")
        if mode == "percent":
            base_amount, note = price_of(deal, rule.get("price_base") or "gross")
            if base_amount <= 0:
                raise ValueError("Harga deal belum terisi — tier persen tidak bisa dihitung.")
            gross = round(base_amount * _num(tier.get("value"), "nilai tier") / 100.0)
            detail.update({"base_amount": base_amount, "base_note": note})
        else:
            gross = int(_num(tier.get("value"), "nilai tier"))
        detail.update({"measure": float(measure), "period": rule.get("period") or "monthly",
                       "tier": {k: tier.get(k) for k in ("min", "max", "value", "mode")}})
    elif basis == "per_lead_qualified":
        leads = ctx.get("qualified_leads")
        if leads is None:
            raise ValueError("Jumlah lead terkualifikasi belum dihitung.")
        per = _num(rule.get("value"), "nominal per lead")
        gross = int(round(per * int(leads)))
        detail.update({"qualified_leads": int(leads), "per_lead": per,
                       "qualify_rule": rule.get("qualify_rule") or "survey_attended"})
    else:  # hybrid
        components = rule.get("components") or []
        if not components:
            raise ValueError("Aturan gabungan wajib punya komponen.")
        gross = 0
        parts = []
        for comp in components:
            if comp.get("basis") == "hybrid":
                raise ValueError("Komponen gabungan tidak boleh berisi gabungan lagi.")
                # (dibatasi satu tingkat supaya angka fee selalu bisa dijelaskan)
            sub = evaluate({**comp, "price_base": comp.get("price_base") or rule.get("price_base")},
                           ctx)
            gross += sub["gross"]
            parts.append({"basis": comp.get("basis"), "gross": sub["gross"],
                          "detail": sub["detail"]})
        detail.update({"components": parts})

    gross = int(gross)
    if gross <= 0:
        raise ValueError("Hasil perhitungan fee harus lebih dari 0.")
    return {"gross": gross, "detail": detail}


def tax_of(gross: int, rule: dict, partner: dict, rates: dict) -> dict:
    """PPh mitra. `gross_up=True` = mitra menerima utuh, pajak ditanggung perusahaan.

    Keluaran menjaga persamaan yang dipakai jurnal `marketing_fee.approve_fee`:
        beban (amount_gross) = netto (amount_net) + PPh (pph_amount)
    """
    tax = rule.get("tax") or {}
    kind = tax.get("pph_type")
    if not kind:
        kind = "pph23" if (partner or {}).get("entity_type") == "company" else "pph21"
    if kind not in TAX_TYPES:
        raise ValueError(f"Jenis PPh tidak dikenal: {kind}")
    if kind == "none":
        return {"pph_type": "none", "pph_pct": 0.0, "pph_amount": 0, "expense": int(gross),
                "payout": int(gross), "gross_up": False}
    rate = tax.get("rate")
    if rate in (None, ""):
        rate = (rates or {}).get(kind)
    rate = _num(rate if rate not in (None, "") else 0, "tarif PPh")
    if rate < 0 or rate >= 100:
        raise ValueError("Tarif PPh harus 0–99,99%.")
    if tax.get("gross_up"):
        expense = int(round(int(gross) / (1 - rate / 100.0)))
        pph = expense - int(gross)
        payout = int(gross)
    else:
        expense = int(gross)
        pph = int(round(int(gross) * rate / 100.0))
        payout = expense - pph
    return {"pph_type": kind, "pph_pct": rate, "pph_amount": pph, "expense": expense,
            "payout": payout, "gross_up": bool(tax.get("gross_up"))}


def split_pct(rule: dict, trigger: str) -> float:
    """Porsi (%) yang jatuh tempo pada pemicu ini. Tanpa `splits` = 100% di pemicu utama."""
    splits = rule.get("splits") or []
    if not splits:
        return 100.0 if (not rule.get("trigger") or rule.get("trigger") == trigger) else 0.0
    for part in splits:
        if part.get("trigger") == trigger:
            return float(part.get("pct") or 0)
    return 0.0


# --------------------------------------------------------------- validasi aturan
def validate_rule(rule: dict) -> dict:
    """Tolak aturan yang tidak bisa dieksekusi SEBELUM tersimpan (bukan saat menagih)."""
    basis = rule.get("basis")
    if basis not in BASES:
        raise ValueError(f"Dasar fee tidak dikenal: {basis}. Pilihan: {', '.join(BASES)}")
    if (rule.get("price_base") or "gross") not in PRICE_BASES:
        raise ValueError(f"Dasar harga tidak dikenal: {rule.get('price_base')}")
    if (rule.get("status") or "active") not in STATUSES:
        raise ValueError("Status aturan hanya boleh active/inactive.")
    if basis in ("percent_price",):
        pct = _num(rule.get("value"), "persentase fee")
        if not 0 < pct <= 100:
            raise ValueError("Persentase fee harus di antara 0 dan 100.")
    if basis in ("fixed_per_deal", "per_lead_qualified"):
        if _num(rule.get("value"), "nominal fee") <= 0:
            raise ValueError("Nominal fee harus lebih dari 0.")
    if basis == "fixed_per_unit_type":
        table = rule.get("by_unit_type") or {}
        if not table:
            raise ValueError("Aturan per tipe unit wajib mengisi nominal minimal satu tipe.")
        for code, amount in table.items():
            if _num(amount, f"nominal tipe {code}") <= 0:
                raise ValueError(f"Nominal fee tipe {code} harus lebih dari 0.")
    if basis in ("tier_volume", "tier_value"):
        tiers = rule.get("tiers") or []
        if len(tiers) < 2:
            raise ValueError("Aturan berjenjang wajib punya minimal 2 tingkat.")
        if (rule.get("period") or "monthly") not in PERIODS:
            raise ValueError(f"Periode tier tidak dikenal: {rule.get('period')}")
        prev_high = None
        for tier in tiers:
            low = _num(tier.get("min") or 0, "batas bawah tier")
            raw_max = tier.get("max")
            high = None if raw_max in (None, "") else _num(raw_max, "batas atas tier")
            if (tier.get("mode") or "percent") not in TIER_MODES:
                raise ValueError(f"Mode tier tidak dikenal: {tier.get('mode')}")
            if _num(tier.get("value"), "nilai tier") <= 0:
                raise ValueError("Nilai tiap tingkat harus lebih dari 0.")
            if high is not None and high <= low:
                raise ValueError("Batas atas tier harus lebih besar dari batas bawahnya.")
            if prev_high is None and low > 0 and tiers.index(tier) == 0:
                raise ValueError("Tingkat pertama harus dimulai dari 0 agar tidak ada celah.")
            if prev_high is not None:
                if low <= prev_high:
                    raise ValueError("Tingkat fee tumpang tindih — batas bawah harus di atas "
                                     "batas atas tingkat sebelumnya.")
                if low > prev_high + 1:
                    raise ValueError("Ada celah antar tingkat fee — nilai di celah itu tidak "
                                     "akan dapat fee.")
            prev_high = high
            if high is None:
                break
    if basis == "hybrid":
        components = rule.get("components") or []
        if not 1 < len(components) <= 4:
            raise ValueError("Aturan gabungan berisi 2–4 komponen.")
        for comp in components:
            validate_rule({**comp, "trigger": rule.get("trigger"), "splits": []})
    trigger = rule.get("trigger")
    if trigger and trigger not in TRIGGERS:
        raise ValueError(f"Pemicu hak fee tidak dikenal: {trigger}")
    splits = rule.get("splits") or []
    if splits:
        seen = set()
        total = 0.0
        for part in splits:
            trg = part.get("trigger")
            if trg not in TRIGGERS:
                raise ValueError(f"Pemicu pembayaran bertahap tidak dikenal: {trg}")
            if trg in seen:
                raise ValueError(f"Pemicu '{trg}' ditulis dua kali pada pembayaran bertahap.")
            seen.add(trg)
            pct = _num(part.get("pct"), "porsi pembayaran")
            if pct <= 0:
                raise ValueError("Porsi pembayaran bertahap harus lebih dari 0%.")
            total += pct
        if round(total, 4) != 100:
            raise ValueError(f"Total porsi pembayaran bertahap harus 100% (sekarang {total}%).")
    elif not trigger:
        raise ValueError("Aturan wajib punya pemicu hak fee atau daftar pembayaran bertahap.")
    tax = rule.get("tax") or {}
    if tax:
        if (tax.get("pph_type") or "pph21") not in TAX_TYPES:
            raise ValueError(f"Jenis PPh tidak dikenal: {tax.get('pph_type')}")
        if tax.get("rate") not in (None, ""):
            rate = _num(tax.get("rate"), "tarif PPh")
            if not 0 <= rate < 100:
                raise ValueError("Tarif PPh harus 0–99,99%.")
    scope = rule.get("scope") or {}
    unknown = [k for k in scope if k not in SCOPE_KEYS]
    if unknown:
        raise ValueError(f"Cakupan aturan hanya boleh {', '.join(SCOPE_KEYS)} "
                         f"(ditemukan: {', '.join(unknown)}).")
    vf, vt = rule.get("valid_from"), rule.get("valid_to")
    if vf and vt and str(vt) < str(vf):
        raise ValueError("Masa berlaku selesai tidak boleh lebih awal dari mulai.")
    return rule


# --------------------------------------------------------------- pemilihan aturan
def specificity(rule: dict) -> int:
    """Semakin spesifik semakin menang: mitra > tipe unit > cluster > proyek."""
    scope = rule.get("scope") or {}
    return ((8 if rule.get("partner_id") else 0) + (4 if scope.get("unit_type") else 0)
            + (2 if scope.get("cluster_id") else 0) + (1 if scope.get("project_id") else 0))


def applicable(rule: dict, ctx: dict) -> bool:
    ctx = ctx or {}
    if (rule.get("status") or "active") != "active":
        return False
    at = str(ctx.get("at") or now_iso())[:10]
    if rule.get("valid_from") and at < str(rule["valid_from"])[:10]:
        return False
    if rule.get("valid_to") and at > str(rule["valid_to"])[:10]:
        return False
    if rule.get("partner_id") and rule["partner_id"] != ctx.get("partner_id"):
        return False
    scope = rule.get("scope") or {}
    for key in SCOPE_KEYS:
        want = scope.get(key)
        if want and str(want) != str(ctx.get(key) or ""):
            return False
    if ctx.get("trigger") and split_pct(rule, ctx["trigger"]) <= 0:
        return False
    return True


def select(rules: list, ctx: dict) -> tuple:
    """(aturan, alasan_penolakan). Seri spesifik = DITOLAK, tidak dipilih diam-diam."""
    candidates = [r for r in (rules or []) if applicable(r, ctx)]
    if not candidates:
        return None, ("Tidak ada aturan fee yang berlaku untuk mitra/proyek/tipe unit ini pada "
                      f"pemicu '{(ctx or {}).get('trigger')}'. Buat aturan fee dulu "
                      "(INV-09: tidak ada fee tanpa aturan).")
    best = max(specificity(r) for r in candidates)
    top = [r for r in candidates if specificity(r) == best]
    if len(top) > 1:
        codes = ", ".join(sorted(str(r.get("code") or r.get("id")) for r in top))
        return None, (f"Aturan fee bentrok — {codes} sama-sama berlaku dan sama spesifik. "
                      "Persempit cakupan (proyek/cluster/tipe unit) atau atur masa berlaku "
                      "salah satunya.")
    return top[0], None


# --------------------------------------------------------------- penyimpanan aturan
async def list_rules(*, org_id: str = ORG_ID, partner_id: str = None, status: str = None,
                     limit: int = 500) -> list:
    query = {"org_id": org_id}
    if partner_id:
        query["$or"] = [{"partner_id": partner_id}, {"partner_id": None}]
    if status:
        query["status"] = status
    return await db.partner_fee_rules.find(query, {"_id": 0}).sort("created_at", -1) \
        .to_list(limit)


async def get_rule(rule_id: str, org_id: str = ORG_ID) -> dict:
    doc = await db.partner_fee_rules.find_one({"id": rule_id, "org_id": org_id}, {"_id": 0})
    if not doc:
        raise ValueError("Aturan fee tidak ditemukan.")
    return doc


async def create_rule(payload: dict, *, actor: str, org_id: str = ORG_ID) -> dict:
    rule = validate_rule(dict(payload))
    if rule.get("partner_id"):
        partner = await db.agents.find_one({"id": rule["partner_id"], "org_id": org_id},
                                          {"_id": 0, "id": 1})
        if not partner:
            raise ValueError("Mitra pada aturan ini tidak ditemukan.")
    ts = now_iso()
    code = await seq.next_number("partner_fee_rule", org_id, prefix="PFR", width=4)
    doc = {
        "id": new_id(), "org_id": org_id, "code": code,
        "name": rule.get("name") or f"Aturan fee {code}",
        "partner_id": rule.get("partner_id"), "basis": rule["basis"],
        "value": float(rule.get("value") or 0), "price_base": rule.get("price_base") or "gross",
        "by_unit_type": rule.get("by_unit_type") or {}, "tiers": rule.get("tiers") or [],
        "period": rule.get("period") or "monthly", "qualify_rule": rule.get("qualify_rule"),
        "components": rule.get("components") or [], "trigger": rule.get("trigger"),
        "splits": rule.get("splits") or [], "tax": rule.get("tax") or {},
        "scope": rule.get("scope") or {}, "valid_from": rule.get("valid_from"),
        "valid_to": rule.get("valid_to"), "status": rule.get("status") or "active",
        "note": rule.get("note"), "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    await db.partner_fee_rules.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def update_rule(rule_id: str, patch: dict, *, actor: str, org_id: str = ORG_ID) -> dict:
    current = await get_rule(rule_id, org_id)
    merged = {**current, **{k: v for k, v in (patch or {}).items() if v is not None}}
    validate_rule(merged)
    merged["updated_at"] = now_iso()
    merged["updated_by"] = actor
    await db.partner_fee_rules.update_one(
        {"id": rule_id, "org_id": org_id},
        {"$set": {k: merged[k] for k in merged if k not in ("id", "org_id", "code",
                                                            "created_at", "created_by")}})
    return await get_rule(rule_id, org_id)
