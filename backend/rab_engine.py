"""Fase 80 — RAB TERSTRUKTUR: RAB per TIPE unit (tertempel pada tipe) + RAB add-on, RAB fasum/fasos
(tertaut fase konstruksi proyek), RAB umum, alokasi biaya bersama → HPP per unit, dan SPK dari RAB.

Prinsip: angka RAB unit hidup di TIPE (satu sumber), proyek hanya mengalikan dengan jumlah unit
tipe itu; SPK unit mengambil baris dari RAB tipe + add-on deal aktif pada unit, boleh dioverride
tetapi jejak RAB vs nilai disimpan (`rab_lines`).
"""
import re

from core_utils import new_id, now_iso
from db import ORG_ID, db

SCOPES = ("unit", "fasum", "umum")
ALLOCATIONS = ("rata", "luas_tanah", "harga_jual")
FACILITIES = [("jalan", "Jalan lingkungan"), ("drainase", "Drainase & saluran"),
              ("gerbang_pos", "Gerbang & pos jaga"), ("taman_rth", "Taman / RTH"),
              ("masjid", "Masjid / musholla"), ("pju_listrik", "PJU & jaringan listrik"),
              ("air_bersih", "Air bersih"), ("ipal", "IPAL / sanitasi"), ("tps", "TPS / sampah"),
              ("lainnya", "Lainnya")]
UMUM_KINDS = [("perizinan", "Perizinan"), ("land_clearing", "Land clearing / cut-fill"),
              ("overhead", "Overhead proyek"), ("pemasaran", "Pemasaran"), ("lainnya", "Lainnya")]
DEAL_DEAD = ("cancelled", "expired", "lost", "released")
SPK_KIND_SCOPE = {"unit": "unit", "addon": "unit", "unit_addon": "unit", "fasum": "fasum", "umum": "umum"}


def _i(v) -> int:
    return int(round(float(v or 0)))


def normalize_items(items: list) -> list:
    out = []
    for i, it in enumerate(items or []):
        qty = float(it.get("qty") or it.get("quantity") or 0)
        price = _i(it.get("unit_price"))
        out.append({"code": (it.get("code") or f"R{i + 1:02d}").strip(), "description": (it.get("description") or "").strip(),
                    "category": it.get("category") or "lainnya", "uom": it.get("uom") or "unit",
                    "qty": qty, "unit_price": price, "amount": _i(qty * price),
                    "step_code": (it.get("step_code") or None)})
    return out


# ============================================================ RAB template per tipe / add-on
async def get_template(org: str, kind: str, ref_code: str) -> dict:
    doc = await db.rab_templates.find_one({"org_id": org, "kind": kind, "ref_code": ref_code}, {"_id": 0})
    return doc or {"org_id": org, "kind": kind, "ref_code": ref_code, "items": [], "total": 0}


async def save_template(org: str, kind: str, ref_code: str, items: list, actor: str, note: str = None) -> dict:
    if kind not in ("unit_type", "addon"):
        raise ValueError("Jenis template harus unit_type atau addon.")
    coll = db.unit_types if kind == "unit_type" else db.addon_items
    if not await coll.find_one({"org_id": org, "code": ref_code}, {"_id": 0, "id": 1}):
        raise ValueError(f"{'Tipe unit' if kind == 'unit_type' else 'Add-on'} '{ref_code}' tidak ada di master.")
    norm = normalize_items(items)
    if any(not it["description"] for it in norm):
        raise ValueError("Setiap baris RAB wajib punya uraian.")
    ts = now_iso()
    key = {"org_id": org, "kind": kind, "ref_code": ref_code}
    prev = await db.rab_templates.find_one(key, {"_id": 0})
    version = int((prev or {}).get("version") or (1 if prev and prev.get("items") else 0))
    if prev and prev.get("items") and prev["items"] != norm:
        # Fase 81: versi lama disimpan utuh (riwayat perubahan harga satuan / baris) sebelum ditimpa
        await db.rab_template_versions.insert_one({
            "id": new_id(), **key, "version": version, "items": prev["items"], "total": _i(prev.get("total")),
            "saved_by": prev.get("updated_by"), "saved_at": prev.get("updated_at"), "note": prev.get("note"),
            "replaced_by": actor, "replaced_at": ts})
        version += 1
    elif not (prev and prev.get("items")):
        version = 1
    await db.rab_templates.update_one(
        key, {"$set": {"items": norm, "total": sum(i["amount"] for i in norm), "updated_by": actor, "updated_at": ts,
                       "version": version, "note": (note or "").strip() or None},
              "$setOnInsert": {"id": new_id(), "created_at": ts}}, upsert=True)
    return await get_template(org, kind, ref_code)


async def list_templates(org: str, kind: str) -> list:
    coll = db.unit_types if kind == "unit_type" else db.addon_items
    masters = await coll.find({"org_id": org}, {"_id": 0}).sort("code", 1).to_list(500)
    tpls = {t["ref_code"]: t for t in await db.rab_templates.find({"org_id": org, "kind": kind}, {"_id": 0}).to_list(500)}
    steps_by_type = await _schedule_steps_by_type(org) if kind == "unit_type" else {}
    out = []
    for m in masters:
        t = tpls.get(m["code"]) or {}
        row = {"ref_code": m["code"], "name": m.get("name"), "active": m.get("active", True),
               "items": len(t.get("items") or []), "total": _i(t.get("total")), "updated_at": t.get("updated_at"),
               "version": t.get("version") or 0}
        if kind == "unit_type":
            known = _known_steps(steps_by_type, m.get("name"), m["code"])
            used = {it["step_code"] for it in t.get("items") or [] if it.get("step_code")}
            row.update({"building_area": m.get("building_area"), "land_area_std": m.get("land_area_std"),
                        "base_price": m.get("base_price"),
                        "units_count": await db.units.count_documents({"org_id": org, "unit_type_code": m["code"]}),
                        "margin": _i(m.get("base_price")) - _i(t.get("total")) if t else None,
                        "has_schedule_template": known is not None,
                        "step_mismatch": len(_step_mismatch(t.get("items"), known)),
                        "steps_without_rab": len((known or set()) - used) if known is not None else 0})
        else:
            row.update({"unit_price": m.get("unit_price"), "pricing_mode": m.get("pricing_mode"), "uom": m.get("uom"),
                        "margin": _i(m.get("unit_price")) - _i(t.get("total")) if t else None})
        out.append(row)
    return out


# ============================================================ sinkron RAB tipe ↔ template jadwal unit
def _norm(v) -> str:
    return str(v or "").strip().lower()


async def _schedule_steps_by_type(org: str) -> dict:
    """{tipe_unit (nama/kode, dinormalkan): {kode_langkah}} dari semua template jadwal aktif."""
    out = {}
    async for t in db.build_templates.find({"org_id": org, "is_active": {"$ne": False}},
                                           {"_id": 0, "unit_types": 1, "steps.code": 1}):
        codes = {s.get("code") for s in t.get("steps") or [] if s.get("code")}
        for name in t.get("unit_types") or []:
            out.setdefault(_norm(name), set()).update(codes)
    return out


def _known_steps(steps_by_type: dict, name: str, code: str):
    """Kode langkah tipe unit — template boleh menulis nama ("Tipe 36/72"), kode ("TIPE-36-72"),
    atau potongan ("30/60" untuk "Rumah Tapak 30/60")."""
    import build_engine as be
    hits = [v for k, v in steps_by_type.items() if be.type_key_match(k, name) or be.type_key_match(k, code)]
    return set().union(*hits) if hits else None


async def _templates_for_type(org: str, name: str, code: str) -> list:
    import build_engine as be
    keys = {_norm(name), _norm(code)} - {""}
    rows = await db.build_templates.find(
        {"org_id": org, "is_active": {"$ne": False}, "unit_types": {"$exists": True, "$ne": []}},
        {"_id": 0, "id": 1, "code": 1, "name": 1, "project_id": 1, "unit_types": 1,
         "steps.code": 1, "steps.name": 1}).to_list(200)
    return [t for t in rows if be.template_matches(t, keys)]


def _step_mismatch(items: list, known) -> list:
    """Baris RAB yang `step_code`-nya tidak ada di template jadwal tipe (known=None → tipe belum punya template)."""
    return [{"code": it.get("code"), "description": it.get("description"), "step_code": it["step_code"]}
            for it in items or [] if it.get("step_code") and (known is None or it["step_code"] not in known)]


async def step_sync_check(org: str, ref_code: str) -> dict:
    """Cek sinkron RAB tipe vs template jadwal tipe unit: kode langkah RAB yang tidak dikenal
    tidak akan pernah tertaut ke item jadwal unit (lingkup SPK/opname kosong), jadi diperingatkan."""
    ut = await db.unit_types.find_one({"org_id": org, "code": ref_code}, {"_id": 0, "name": 1})
    name = (ut or {}).get("name")
    tpls = await _templates_for_type(org, name, ref_code)
    known = {}
    for t in tpls:
        for s in t.get("steps") or []:
            if s.get("code"):
                known.setdefault(s["code"], s.get("name"))
    rab = await get_template(org, "unit_type", ref_code)
    linked = [it for it in rab.get("items") or [] if it.get("step_code")]
    unknown = _step_mismatch(linked, set(known) if tpls else None)
    used = {it["step_code"] for it in linked}
    return {"ref_code": ref_code, "unit_type_name": name, "has_template": bool(tpls),
            "templates": [{"id": t["id"], "code": t.get("code"), "name": t.get("name"), "project_id": t.get("project_id")} for t in tpls],
            "linked": len(linked), "unknown_steps": unknown,
            "steps_without_rab": [{"code": c, "name": n} for c, n in known.items() if c not in used],
            "ok": not unknown}


async def rab_step_warnings_for_template(org: str, tpl: dict) -> list:
    """Peringatan untuk editor template jadwal: RAB tipe yang memakai kode langkah di luar template ini."""
    codes = {s.get("code") for s in tpl.get("steps") or []}
    warns = []
    for name in tpl.get("unit_types") or []:
        ut = await db.unit_types.find_one(
            {"org_id": org, "$or": [{"name": name}, {"code": name},
                                    {"name": {"$regex": f"^{re.escape(str(name))}$", "$options": "i"}},
                                    {"code": {"$regex": f"^{re.escape(str(name))}$", "$options": "i"}}]},
            {"_id": 0, "code": 1})
        if not ut:
            continue
        rab = await db.rab_templates.find_one({"org_id": org, "kind": "unit_type", "ref_code": ut["code"]}, {"_id": 0, "items": 1})
        bad = sorted({it["step_code"] for it in (rab or {}).get("items") or [] if it.get("step_code") and it["step_code"] not in codes})
        if bad:
            warns.append(f"RAB tipe {ut['code']} ({name}) memakai kode langkah {', '.join(bad)} yang tidak ada di template ini — "
                         "baris RAB itu tidak akan masuk lingkup SPK/opname. Samakan kode di RAB atau tambahkan langkahnya.")
    return warns


async def type_step_reference(org: str) -> dict:
    """{(kode_tipe, step_code): {suggested_value, cost_code, boq_description}} dari RAB tipe."""
    out = {}
    async for t in db.rab_templates.find({"org_id": org, "kind": "unit_type"}, {"_id": 0}):
        for it in t.get("items") or []:
            if not it.get("step_code"):
                continue
            key = (t["ref_code"], it["step_code"])
            cur = out.setdefault(key, {"suggested_value": 0, "cost_code": it["code"], "boq_description": it["description"],
                                       "category": it.get("category")})
            cur["suggested_value"] += it["amount"]
    return out


# ============================================================ SPK dari RAB
async def _active_deal(org: str, unit_id: str) -> dict:
    return await db.deals.find_one({"org_id": org, "unit_id": unit_id, "status": {"$nin": list(DEAL_DEAD)}},
                                   {"_id": 0}, sort=[("created_at", -1)]) or {}


async def unit_draft(org: str, unit: dict, mode: str) -> dict:
    """Baris SPK satu unit: RAB tipe (mode unit/unit_addon) + add-on deal aktif (mode addon/unit_addon)."""
    lines, warnings = [], []
    base = {"unit_id": unit["id"], "unit_code": unit.get("code"), "unit_type_code": unit.get("unit_type_code")}
    if mode in ("unit", "unit_addon"):
        tpl = await get_template(org, "unit_type", unit.get("unit_type_code") or "")
        if not tpl.get("items"):
            warnings.append(f"Tipe {unit.get('unit_type_code') or unit.get('type') or '-'} belum punya RAB tipe.")
        for it in tpl.get("items") or []:
            lines.append({**base, "source": "rab_type", "code": it["code"], "description": it["description"],
                          "category": it.get("category"), "step_code": it.get("step_code"),
                          "rab_amount": it["amount"], "value": it["amount"]})
    deal = await _active_deal(org, unit["id"])
    if mode in ("addon", "unit_addon"):
        addons = deal.get("addons") or []
        if not addons:
            warnings.append("Tidak ada add-on pada deal aktif unit ini." if deal else "Unit belum punya deal aktif (add-on kosong).")
        for a in addons:
            tpl = await get_template(org, "addon", a.get("code") or "")
            qty = float(a.get("qty") or 1)
            per = _i(tpl.get("total"))
            mult = qty if (a.get("pricing_mode") in ("per_m2", "per_item")) else 1
            amt = _i(per * mult)
            if not tpl.get("items"):
                warnings.append(f"Add-on {a.get('code')} belum punya RAB add-on — nilai diisi manual.")
            lines.append({**base, "source": "addon", "code": a.get("code"), "description": f"Add-on: {a.get('name') or a.get('code')}",
                          "category": "finishing", "step_code": None, "qty": qty, "rab_amount": amt, "value": amt,
                          "sell_amount": _i(a.get("amount"))})
    return {**base, "unit_type": unit.get("type"), "deal_id": deal.get("id"), "deal_status": deal.get("status"),
            "customer_name": deal.get("customer_name") or deal.get("lead_name"), "lines": lines,
            "total": sum(x["value"] for x in lines), "warnings": warnings}


async def spk_draft(org: str, project_id: str, unit_ids: list, mode: str) -> dict:
    if mode not in ("unit", "addon", "unit_addon"):
        raise ValueError("Mode harus unit, addon, atau unit_addon.")
    units = await db.units.find({"org_id": org, "project_id": project_id, "id": {"$in": unit_ids}}, {"_id": 0}).to_list(200)
    if len(units) != len(set(unit_ids)):
        raise ValueError("Ada unit yang tidak ditemukan pada proyek ini.")
    rows = [await unit_draft(org, u, mode) for u in sorted(units, key=lambda u: u.get("code") or "")]
    return {"mode": mode, "units": rows, "total": sum(r["total"] for r in rows)}


async def fasum_draft(org: str, project_id: str, scope: str, boq_item_ids: list) -> dict:
    items = await db.boq_items.find({"org_id": org, "project_id": project_id, "scope": scope,
                                     "id": {"$in": boq_item_ids}}, {"_id": 0}).to_list(500)
    lines = [{"source": "boq", "boq_item_id": b["id"], "code": b.get("cost_code"), "description": b.get("description"),
              "category": b.get("category"), "facility": b.get("facility"), "phase_id": b.get("phase_id"),
              "rab_amount": _i(b.get("amount")), "value": _i(b.get("amount"))} for b in items]
    return {"mode": scope, "lines": lines, "total": sum(x["value"] for x in lines)}


def validate_lines(lines: list) -> list:
    out = []
    for ln in lines:
        v = _i(ln.get("value"))
        if v < 0:
            raise ValueError("Nilai baris SPK tidak boleh negatif.")
        rab = _i(ln.get("rab_amount"))
        out.append({**{k: ln.get(k) for k in ("unit_id", "unit_code", "unit_type_code", "source", "code", "description",
                                              "category", "step_code", "boq_item_id", "facility", "phase_id", "qty")},
                    "rab_amount": rab, "value": v, "override": v != rab,
                    "override_reason": (ln.get("override_reason") or "").strip() or None})
    if any(l["override"] and not l["override_reason"] for l in out):
        raise ValueError("Baris yang nilainya berbeda dari RAB wajib diberi alasan override.")
    return out


async def assert_boq_not_contracted(org: str, lines: list) -> None:
    """Item RAB fasum/umum hanya boleh dikontrakkan di satu SPK aktif (hindari komitmen ganda)."""
    ids = [l["boq_item_id"] for l in lines if l.get("boq_item_id")]
    if not ids:
        return
    async for s in db.spk.find({"org_id": org, "status": {"$nin": ["cancelled"]}, "rab_lines.boq_item_id": {"$in": ids}},
                               {"_id": 0, "spk_number": 1, "rab_lines.boq_item_id": 1, "rab_lines.description": 1}):
        dup = next((l for l in s.get("rab_lines") or [] if l.get("boq_item_id") in ids), None)
        if dup:
            raise ValueError(f"Item RAB '{dup.get('description')}' sudah dikontrakkan di {s.get('spk_number')} — "
                             "satu item RAB tidak boleh dibayar lewat dua SPK. Batalkan SPK itu atau pilih item lain.")


async def auto_scope_lines(org: str, spk: dict, lines: list, actor: str) -> dict:
    """Tautkan baris RAB tipe yang punya step_code ke item jadwal unit (bila ada & belum dipakai)."""
    import opname as op
    picks = {}
    for ln in lines:
        if ln.get("source") != "rab_type" or not ln.get("step_code") or not ln.get("unit_id") or ln["value"] <= 0:
            continue
        key = (ln["unit_id"], ln["step_code"])
        picks[key] = picks.get(key, 0) + ln["value"]
    if not picks:
        return {"added": 0, "skipped": 0, "missing_steps": []}
    used = await op.used_item_ids(org)
    to_add, missing = [], []
    for (uid, step), value in picks.items():
        item = await db.build_items.find_one({"org_id": org, "unit_id": uid, "step_code": step}, {"_id": 0, "id": 1})
        if item and item["id"] not in used:
            to_add.append({"build_item_id": item["id"], "value": value, "boq_item_id": None})
        else:
            missing.append(f"{step}" + ("" if item else " (tidak ada di jadwal unit)"))
    if not to_add:
        return {"added": 0, "skipped": len(picks), "missing_steps": missing}
    try:
        res = await op.add_lines(org, spk, to_add, actor)
        return {"added": res["added"], "skipped": len(picks) - res["added"], "missing_steps": missing}
    except ValueError as e:  # lingkup opsional: SPK tetap sah tanpa tautan jadwal
        return {"added": 0, "skipped": len(picks), "missing_steps": missing, "error": str(e)}


# ============================================================ ringkasan proyek: RAB, HPP, margin
def _weight(unit: dict, method: str, type_land: int) -> float:
    if method == "harga_jual":
        return float(unit.get("price") or 0) or 1.0
    if method == "luas_tanah":
        return float(unit.get("luas_tanah") or type_land or 0) or 1.0
    return 1.0


async def project_summary(org: str, project_id: str) -> dict:
    proj = await db.projects.find_one({"org_id": org, "id": project_id}, {"_id": 0}) or {}
    method = proj.get("rab_allocation") if proj.get("rab_allocation") in ALLOCATIONS else "luas_tanah"
    units = await db.units.find({"org_id": org, "project_id": project_id}, {"_id": 0}).sort("code", 1).to_list(2000)
    types = {t["code"]: t for t in await db.unit_types.find({"org_id": org}, {"_id": 0}).to_list(500)}
    tpls = {t["ref_code"]: t for t in await db.rab_templates.find({"org_id": org, "kind": "unit_type"}, {"_id": 0}).to_list(500)}
    addon_tpls = {t["ref_code"]: _i(t.get("total")) for t in await db.rab_templates.find({"org_id": org, "kind": "addon"}, {"_id": 0}).to_list(500)}
    boq = await db.boq_items.find({"org_id": org, "project_id": project_id}, {"_id": 0}).to_list(3000)
    groups = {"fasum": 0, "umum": 0, "legacy": 0}
    facilities = {}
    for b in boq:
        sc = b.get("scope")
        amt = _i(b.get("amount"))
        if sc in ("fasum", "umum"):
            groups[sc] += amt
            fk = b.get("facility") or "lainnya"
            facilities.setdefault((sc, fk), 0)
            facilities[(sc, fk)] += amt
        else:
            groups["legacy"] += amt
    # add-on terjual (deal aktif) → RAB add-on
    addon_rab, addon_sell = 0, 0
    async for d in db.deals.find({"org_id": org, "project_id": project_id, "status": {"$nin": list(DEAL_DEAD)}},
                                 {"_id": 0, "addons": 1}):
        for a in d.get("addons") or []:
            mult = float(a.get("qty") or 1) if a.get("pricing_mode") in ("per_m2", "per_item") else 1
            addon_rab += _i(addon_tpls.get(a.get("code"), 0) * mult)
            addon_sell += _i(a.get("amount"))
    shared = groups["fasum"] + groups["umum"] + groups["legacy"]
    weights = [_weight(u, method, _i((types.get(u.get("unit_type_code")) or {}).get("land_area_std"))) for u in units]
    wsum = sum(weights) or 1.0
    per_unit, per_type, missing = [], {}, 0
    for u, w in zip(units, weights):
        tcode = u.get("unit_type_code") or ""
        tpl = tpls.get(tcode)
        if not tpl:
            missing += 1
        type_total = _i((tpl or {}).get("total"))
        share = _i(shared * w / wsum)
        hpp = type_total + share
        price = _i(u.get("price"))
        per_unit.append({"unit_id": u["id"], "unit_code": u.get("code"), "unit_type_code": tcode, "type": u.get("type"),
                         "status": u.get("status"), "price": price, "rab_type": type_total, "shared": share, "hpp": hpp,
                         "margin": price - hpp, "margin_pct": round((price - hpp) / price * 100, 1) if price else None})
        pt = per_type.setdefault(tcode, {"unit_type_code": tcode, "name": (types.get(tcode) or {}).get("name") or u.get("type"),
                                         "units": 0, "rab_per_unit": type_total, "rab_total": 0, "has_template": bool(tpl)})
        pt["units"] += 1
        pt["rab_total"] += type_total
    unit_rab = sum(p["rab_total"] for p in per_type.values())
    total_price = sum(p["price"] for p in per_unit)
    total_rab = unit_rab + addon_rab + shared
    return {
        "project_id": project_id, "project_name": proj.get("name"), "allocation": method,
        "allocation_options": [{"code": c, "label": l} for c, l in
                               (("rata", "Dibagi rata per unit"), ("luas_tanah", "Proporsional luas tanah"),
                                ("harga_jual", "Proporsional harga jual"))],
        "units": len(units), "units_without_template": missing,
        "unit_rab": unit_rab, "addon_rab": addon_rab, "addon_sell": addon_sell,
        "fasum": groups["fasum"], "umum": groups["umum"], "legacy": groups["legacy"], "shared": shared,
        "total_rab": total_rab, "total_price": total_price, "margin": total_price + addon_sell - total_rab,
        "margin_pct": round((total_price + addon_sell - total_rab) / (total_price + addon_sell) * 100, 1)
        if (total_price + addon_sell) else None,
        "per_type": sorted(per_type.values(), key=lambda r: r["unit_type_code"]),
        "facilities": [{"scope": s, "facility": f, "amount": a} for (s, f), a in sorted(facilities.items())],
        "per_unit": per_unit,
        "control": await rab_control(org, project_id, {"unit": unit_rab + addon_rab, "fasum": groups["fasum"], "umum": groups["umum"]}),
        "fasum_control": await fasum_control(org, project_id),
    }


async def rab_control(org: str, project_id: str, budget: dict) -> list:
    """RAB vs dikontrakkan (SPK dari RAB) vs ditagih (termin disetujui) per lingkup."""
    spks = await db.spk.find({"org_id": org, "project_id": project_id, "spk_kind": {"$exists": True},
                              "status": {"$ne": "cancelled"}}, {"_id": 0, "id": 1, "spk_kind": 1, "contract_value": 1}).to_list(2000)
    rows = {s: {"scope": s, "budget": _i(budget.get(s)), "contracted": 0, "billed": 0, "spk": 0} for s in SCOPES}
    by_id = {}
    for s in spks:
        sc = SPK_KIND_SCOPE.get(s.get("spk_kind"))
        if not sc:
            continue
        rows[sc]["contracted"] += _i(s.get("contract_value"))
        rows[sc]["spk"] += 1
        by_id[s["id"]] = sc
    if by_id:
        async for c in db.progress_claims.find({"org_id": org, "spk_id": {"$in": list(by_id)}, "status": "approved"},
                                               {"_id": 0, "spk_id": 1, "gross": 1}):
            rows[by_id[c["spk_id"]]]["billed"] += _i(c.get("gross"))
    for r in rows.values():
        r["variance"] = r["budget"] - r["contracted"]
        r["over"] = bool(r["budget"] and r["contracted"] > r["budget"])
    return list(rows.values())


async def set_allocation(org: str, project_id: str, method: str) -> str:
    if method not in ALLOCATIONS:
        raise ValueError("Metode alokasi harus rata, luas_tanah, atau harga_jual.")
    await db.projects.update_one({"org_id": org, "id": project_id}, {"$set": {"rab_allocation": method, "updated_at": now_iso()}})
    return method


# ============================================================ Fase 81: kendali fasum vs progres fase konstruksi
FACILITY_LABEL = dict(FACILITIES)


async def fasum_phase_cap(org: str, spk: dict) -> dict:
    """Batas termin kumulatif SPK fasum = progres fase konstruksi tertaut, ditimbang nilai baris.
    Baris tanpa fase tidak dibatasi (dihitung 100%) tetapi dilaporkan sebagai `uncovered_value`."""
    lines = spk.get("rab_lines") or []
    total = sum(_i(l.get("value")) for l in lines)
    ids = list({l.get("phase_id") for l in lines if l.get("phase_id")})
    phases = {p["id"]: p for p in await db.construction_phases.find(
        {"org_id": org, "id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "progress": 1, "status": 1}).to_list(200)} if ids else {}
    per_phase, covered, weighted = {}, 0, 0.0
    for l in lines:
        p = phases.get(l.get("phase_id"))
        if not p:
            continue
        v = _i(l.get("value"))
        covered += v
        weighted += v * float(p.get("progress") or 0) / 100.0
        row = per_phase.setdefault(p["id"], {"phase_id": p["id"], "name": p.get("name"), "progress": int(p.get("progress") or 0),
                                             "status": p.get("status"), "value": 0})
        row["value"] += v
    uncovered = total - covered
    cap = int(round((weighted + uncovered) / total * 100)) if total else 100
    return {"cap_pct": max(0, min(100, cap)), "covered_value": covered, "uncovered_value": uncovered,
            "phases": sorted(per_phase.values(), key=lambda r: r["name"] or ""),
            "facilities": sorted({FACILITY_LABEL.get(l.get("facility"), l.get("facility")) for l in lines if l.get("facility")})}


def assert_fasum_claim_within_phase(cap: dict, claimed_pct: int) -> None:
    if not cap["covered_value"] or claimed_pct <= cap["cap_pct"]:
        return
    lag = "; ".join(f"'{p['name']}' {p['progress']}%" for p in cap["phases"])
    raise ValueError(f"Termin fasum tidak boleh melampaui progres fase konstruksi: {lag} → batas termin kumulatif "
                     f"{cap['cap_pct']}% (diajukan {claimed_pct}%). Perbarui progres fase dulu di modul Konstruksi.")


async def fasum_control(org: str, project_id: str) -> list:
    """Per SPK fasum: nilai kontrak, termin disetujui/diajukan (%), progres fase (batas), status melampaui."""
    out = []
    async for s in db.spk.find({"org_id": org, "project_id": project_id, "spk_kind": "fasum", "status": {"$ne": "cancelled"}},
                               {"_id": 0}).sort("spk_number", 1):
        cap = await fasum_phase_cap(org, s)
        billed = int(s.get("progress_pct") or 0)
        open_claim = await db.progress_claims.find_one({"org_id": org, "spk_id": s["id"], "status": {"$in": ["submitted", "verified"]}},
                                                       {"_id": 0, "claimed_pct": 1, "claim_number": 1})
        out.append({"spk_id": s["id"], "spk_number": s.get("spk_number"), "status": s.get("status"),
                    "subcontractor_name": s.get("subcontractor_name"), "contract_value": _i(s.get("contract_value")),
                    "billed_pct": billed, "billed_value": _i(s.get("contract_value")) * billed // 100,
                    "pending_pct": int(open_claim["claimed_pct"]) if open_claim else None,
                    "pending_claim": open_claim.get("claim_number") if open_claim else None,
                    "headroom_pct": max(0, cap["cap_pct"] - billed) if cap["covered_value"] else None,
                    "over": bool(cap["covered_value"]) and billed > cap["cap_pct"], **cap})
    return out


async def ensure_indexes() -> None:
    await db.rab_templates.create_index([("org_id", 1), ("kind", 1), ("ref_code", 1)], unique=True)
