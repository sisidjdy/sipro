"""metrics/rab.py — kamus metrik RAB TERSTRUKTUR (RAB-01..06), Fase 81b.

Membungkus `rab_engine` (Fase 80/81) ke kontrak metrik supaya angka HPP/margin, komposisi RAB,
kendali fasum vs progres fase, selisih SPK vs RAB, dan aktivitas versi RAB yang tampil di BI
SAMA PERSIS dengan yang tampil di `/boq` › Ringkasan & HPP. Tidak ada rumus baru di sini.
"""
import rab_engine as re_
from db import ORG_ID, db
from metrics.base import day_range_query, pct, result

DRILL_RAB = "/boq?hub=items"
DRILL_SPK = "/subcon"
THIN_MARGIN_PCT = 10.0


async def _projects(org_id: str, project_id: str = None) -> list:
    q = {"org_id": org_id}
    if project_id:
        q["id"] = project_id
    return await db.projects.find(q, {"_id": 0, "id": 1, "name": 1}).to_list(500)


async def _summaries(org_id: str, project_id: str = None) -> tuple:
    rows, kosong = [], []
    for p in await _projects(org_id, project_id):
        s = await re_.project_summary(org_id, p["id"])
        if not s["total_rab"]:
            kosong.append(p.get("name") or p["id"])
            continue
        rows.append(s)
    return rows, kosong


def _missing(rows: list, kosong: list) -> list:
    if not rows:
        return ["belum ada RAB tipe/fasum/umum pada proyek mana pun — susun RAB di RAB/BoQ → Rincian RAB"]
    out = []
    if kosong:
        out.append(f"{len(kosong)} proyek belum punya RAB: " + ", ".join(kosong[:3]))
    tanpa = sum(r["units_without_template"] for r in rows)
    if tanpa:
        out.append(f"{tanpa} unit bertipe tanpa RAB tipe — HPP unit itu hanya biaya bersama")
    return out


def _coverage(rows: list, kosong: list):
    """Cakupan: unit ber-RAB tipe / seluruh unit (bila ada unit tanpa RAB tipe), atau proyek ber-RAB / seluruh proyek."""
    units = sum(r["units"] for r in rows)
    tanpa = sum(r["units_without_template"] for r in rows)
    if rows and tanpa:
        return {"rows": units - tanpa, "total": units}
    return {"rows": len(rows), "total": len(rows) + len(kosong)} if rows and kosong else None


# ---------------------------------------------------------------------- RAB-01
async def rab_total(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """RAB total terstruktur = Σ (RAB tipe × unit + RAB add-on terjual + fasum/fasos + umum + item lama)."""
    rows, kosong = await _summaries(org_id, project_id)
    comp = {"unit_rab": 0, "addon_rab": 0, "fasum": 0, "umum": 0, "legacy": 0}
    for r in rows:
        for k in comp:
            comp[k] += r[k]
    labels = {"unit_rab": "RAB unit (tipe × jumlah unit)", "addon_rab": "RAB add-on terjual",
              "fasum": "Fasum / fasos", "umum": "Umum", "legacy": "Item RAB lama (tanpa lingkup)"}
    return result("RAB-01", sum(r["total_rab"] for r in rows) if rows else None, label="RAB total terstruktur", unit="idr",
                  breakdown=[{"key": k, "label": labels[k], "value": v} for k, v in comp.items() if v],
                  inputs={**comp, "proyek": len(rows),
                          "per_proyek": [{"project_id": r["project_id"], "label": r["project_name"], "value": r["total_rab"]} for r in rows]},
                  coverage=_coverage(rows, kosong), missing=_missing(rows, kosong) or None, drill=DRILL_RAB)


# ---------------------------------------------------------------------- RAB-02
async def hpp_margin(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Margin HPP proyeksi = (harga jual seluruh unit + add-on terjual) − RAB total terstruktur."""
    rows, kosong = await _summaries(org_id, project_id)
    sell = sum(r["total_price"] + r["addon_sell"] for r in rows)
    rab = sum(r["total_rab"] for r in rows)
    unpriced = sum(1 for r in rows for u in r["per_unit"] if not u["price"])
    missing = _missing(rows, kosong)
    if rows and unpriced:
        missing.append(f"{unpriced} unit belum punya harga jual")
    return result("RAB-02", (sell - rab) if rows else None, label="Margin HPP proyeksi (RAB terstruktur)", unit="idr",
                  breakdown=[{"key": r["project_id"], "label": r["project_name"], "value": r["margin"], "pct": r["margin_pct"],
                              "total_price": r["total_price"], "addon_sell": r["addon_sell"], "total_rab": r["total_rab"]} for r in rows],
                  inputs={"nilai_jual": sell, "rab_total": rab, "margin_pct": pct(sell - rab, sell), "unit_tanpa_harga": unpriced},
                  coverage=_coverage(rows, kosong) or ({"rows": sum(r["units"] for r in rows) - unpriced, "total": sum(r["units"] for r in rows)} if rows and unpriced else None),
                  missing=missing or None, drill=DRILL_RAB)


# ---------------------------------------------------------------------- RAB-03
async def margin_per_type(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Margin per tipe unit = (Σ harga jual − Σ HPP) / Σ harga jual per tipe; unit bermargin tipis (<10%) dihitung."""
    rows, kosong = await _summaries(org_id, project_id)
    per, thin = {}, []
    for r in rows:
        for u in r["per_unit"]:
            t = per.setdefault(u["unit_type_code"] or "—", {"key": u["unit_type_code"] or "—", "label": u["type"] or u["unit_type_code"] or "—",
                                                            "units": 0, "price": 0, "hpp": 0, "thin": 0})
            t["units"] += 1
            t["price"] += u["price"]
            t["hpp"] += u["hpp"]
            if u["price"] and (u["margin_pct"] or 0) < THIN_MARGIN_PCT:
                t["thin"] += 1
                thin.append({"unit_code": u["unit_code"], "project": r["project_name"], "margin_pct": u["margin_pct"]})
    breakdown = [{**t, "value": pct(t["price"] - t["hpp"], t["price"]), "margin": t["price"] - t["hpp"]} for t in per.values()]
    total_price = sum(t["price"] for t in per.values())
    total_hpp = sum(t["hpp"] for t in per.values())
    return result("RAB-03", pct(total_price - total_hpp, total_price) if rows else None, label="Margin HPP per tipe unit", unit="pct",
                  breakdown=sorted(breakdown, key=lambda x: (x["value"] is None, x["value"] or 0)),
                  inputs={"unit_margin_tipis": len(thin), "ambang_pct": THIN_MARGIN_PCT, "tipe": len(per),
                          "unit_tipis": sorted(thin, key=lambda x: x["margin_pct"] if x["margin_pct"] is not None else 0)[:20]},
                  coverage=_coverage(rows, kosong), missing=_missing(rows, kosong) or None, drill=DRILL_RAB)


# ---------------------------------------------------------------------- RAB-04
async def fasum_over_phase(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """SPK fasum melampaui progres fase = count(termin disetujui % > progres fase tertaut %)."""
    projects = await _projects(org_id, project_id)
    rows, total, over_value, headroom_value, no_phase = [], 0, 0, 0, 0
    for p in projects:
        for s in await re_.fasum_control(org_id, p["id"]):
            total += 1
            if not s["covered_value"]:
                no_phase += 1
            elif s["over"]:
                over_value += s["contract_value"] * (s["billed_pct"] - s["cap_pct"]) // 100
            else:
                headroom_value += s["contract_value"] * s["headroom_pct"] // 100
            rows.append({"key": s["spk_id"], "label": f"{s['spk_number']} · {p.get('name')}", "value": s["billed_pct"],
                         "cap_pct": s["cap_pct"] if s["covered_value"] else None, "over": s["over"],
                         "contract_value": s["contract_value"], "facilities": s["facilities"],
                         "phases": [f"{x['name']} {x['progress']}%" for x in s["phases"]], "pending_pct": s["pending_pct"]})
    missing = []
    if not total:
        missing.append("belum ada SPK fasum/fasos — buat lewat SPK dari RAB mode fasum")
    elif no_phase:
        missing.append(f"{no_phase} SPK fasum tanpa tautan fase konstruksi (tidak dikendalikan)")
    return result("RAB-04", sum(1 for r in rows if r["over"]) if total else None, label="SPK fasum melampaui progres fase", unit="count",
                  breakdown=sorted(rows, key=lambda r: (not r["over"], -(r["value"] or 0))),
                  inputs={"spk_fasum": total, "tanpa_fase": no_phase, "nilai_melampaui": over_value, "sisa_termin_boleh": headroom_value},
                  coverage={"rows": total - no_phase, "total": total} if total and no_phase else None,
                  missing=missing or None, drill=DRILL_SPK)


# ---------------------------------------------------------------------- RAB-05
async def spk_vs_rab(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Selisih SPK vs RAB = Σ (nilai kontrak SPK − dasar RAB) pada SPK yang lahir dari RAB (override beralasan)."""
    q = {"org_id": org_id, "rab_lines.0": {"$exists": True}, "status": {"$ne": "cancelled"}}
    if project_id:
        q["project_id"] = project_id
    rows, rab, contract, overrides = [], 0, 0, 0
    async for s in db.spk.find(q, {"_id": 0, "id": 1, "spk_number": 1, "spk_kind": 1, "contract_value": 1, "rab_total": 1,
                                   "override_count": 1, "project_id": 1, "subcontractor_name": 1}).sort("spk_number", 1):
        rt, cv = re_._i(s.get("rab_total")), re_._i(s.get("contract_value"))
        rab += rt
        contract += cv
        overrides += int(s.get("override_count") or 0)
        rows.append({"key": s["id"], "label": f"{s.get('spk_number')} · {s.get('spk_kind') or 'unit'}", "value": cv - rt,
                     "rab_total": rt, "contract_value": cv, "override_count": s.get("override_count") or 0,
                     "subcontractor": s.get("subcontractor_name"), "pct": pct(cv - rt, rt)})
    return result("RAB-05", (contract - rab) if rows else None, label="Selisih SPK terhadap RAB (override)", unit="idr",
                  breakdown=sorted(rows, key=lambda r: -abs(r["value"])),
                  inputs={"spk_dari_rab": len(rows), "dasar_rab": rab, "nilai_kontrak": contract, "baris_override": overrides,
                          "selisih_pct": pct(contract - rab, rab)},
                  missing=["belum ada SPK yang dibuat dari RAB"] if not rows else None, drill=DRILL_SPK)


# ---------------------------------------------------------------------- RAB-06
async def rab_revisions(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None, **_) -> dict:
    """Revisi RAB tipe/add-on = count(versi tersimpan pada rentang) + arah perubahan total per tipe."""
    q = {"org_id": org_id, **day_range_query("replaced_at", date_from, date_to)}
    per, series = {}, {}
    cur = {(t["kind"], t["ref_code"]): re_._i(t.get("total")) for t in
           await db.rab_templates.find({"org_id": org_id}, {"_id": 0, "kind": 1, "ref_code": 1, "total": 1}).to_list(1000)}
    n = 0
    async for v in db.rab_template_versions.find(q, {"_id": 0, "kind": 1, "ref_code": 1, "total": 1, "replaced_at": 1, "note": 1}):
        n += 1
        k = (v["kind"], v["ref_code"])
        row = per.setdefault(k, {"key": f"{v['kind']}:{v['ref_code']}", "label": v["ref_code"], "kind": v["kind"], "value": 0,
                                 "first_total": re_._i(v.get("total")), "current_total": cur.get(k, 0), "notes": []})
        row["value"] += 1
        if v.get("note"):
            row["notes"].append(v["note"])
        day = (v.get("replaced_at") or "")[:10]
        series[day] = series.get(day, 0) + 1
    for row in per.values():
        row["delta"] = row["current_total"] - row["first_total"]
        row["notes"] = row["notes"][-3:]
    return result("RAB-06", n if cur else None, label="Revisi RAB tipe/add-on", unit="count",
                  breakdown=sorted(per.values(), key=lambda r: -r["value"]),
                  series=[{"date": d, "value": c} for d, c in sorted(series.items())],
                  inputs={"template_ber_rab": len(cur), "tipe_direvisi": len(per),
                          "kenaikan_total": sum(r["delta"] for r in per.values() if r["delta"] > 0),
                          "penurunan_total": sum(r["delta"] for r in per.values() if r["delta"] < 0)},
                  missing=["belum ada RAB tipe/add-on tersimpan"] if not cur else None, drill=DRILL_RAB)


METRICS = {
    "RAB-01": {"fn": rab_total, "label": "RAB total terstruktur", "unit": "idr", "persona": "proyek", "snapshot": True,
               "formula": "Σ (RAB tipe × unit) + RAB add-on terjual + fasum/fasos + umum + item lama",
               "requires": ["rab_templates", "units", "boq_items", "deals"], "drill": DRILL_RAB},
    "RAB-02": {"fn": hpp_margin, "label": "Margin HPP proyeksi (RAB terstruktur)", "unit": "idr", "persona": "eksekutif", "snapshot": True,
               "formula": "(harga jual seluruh unit + add-on terjual) − RAB total terstruktur",
               "requires": ["rab_templates", "units", "boq_items", "deals"], "drill": DRILL_RAB},
    "RAB-03": {"fn": margin_per_type, "label": "Margin HPP per tipe unit", "unit": "pct", "persona": "eksekutif", "snapshot": True,
               "formula": "(Σ harga jual − Σ HPP) / Σ harga jual per tipe; HPP = RAB tipe + alokasi biaya bersama",
               "requires": ["rab_templates", "units", "unit_types"], "drill": DRILL_RAB},
    "RAB-04": {"fn": fasum_over_phase, "label": "SPK fasum melampaui progres fase", "unit": "count", "persona": "proyek", "snapshot": True,
               "formula": "count(SPK fasum dengan termin disetujui % > progres fase konstruksi tertaut %)",
               "requires": ["spk", "construction_phases", "progress_claims"], "drill": DRILL_SPK},
    "RAB-05": {"fn": spk_vs_rab, "label": "Selisih SPK terhadap RAB (override)", "unit": "idr", "persona": "proyek", "snapshot": True,
               "formula": "Σ (nilai kontrak SPK − dasar RAB) pada SPK yang lahir dari RAB",
               "requires": ["spk"], "drill": DRILL_SPK},
    "RAB-06": {"fn": rab_revisions, "label": "Revisi RAB tipe/add-on", "unit": "count", "persona": "proyek",
               "formula": "count(versi RAB tersimpan pada rentang) + selisih total versi pertama → aktif per tipe",
               "requires": ["rab_template_versions", "rab_templates"], "drill": DRILL_RAB},
}
