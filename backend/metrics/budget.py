"""metrics/budget.py — kamus metrik TARGET & ANGGARAN (BGT-01..06), Fase 45.

Modul ini tidak menghitung apa pun sendiri: ia MEMBUNGKUS `budget_engine` / `budget_reports` /
`target_store` ke dalam kontrak metrik (`base.result`). Alasannya sama dengan Fase 44 — begitu
dashboard punya rumusnya sendiri, angka di BI mulai berbeda dengan angka di layar Anggaran, dan
sejak itu tidak ada yang percaya keduanya.

Dua kejujuran yang dijaga:
  * Proyek tanpa item anggaran → `value=None` + `missing`, BUKAN Rp 0 (proyek tanpa anggaran
    bukan proyek paling hemat).
  * Metrik yang bergantung pada target hanya berbicara tentang target **AKTIF**. Target draf
    tidak dipakai sebagai janji perusahaan, dan itu dinyatakan di `missing`.
"""
import budget_engine as be
import budget_reports as br
import settings_store as cfg
import target_store as tstore
from db import ORG_ID, db
from metrics.base import result

DRILL_BUDGET = "/boq?hub=realisasi"
DRILL_TARGET = "/boq?hub=target"


async def _projects(org_id: str, project_id: str = None) -> list:
    q = {"org_id": org_id}
    if project_id:
        q["id"] = project_id
    return await db.projects.find(q, {"_id": 0, "id": 1, "name": 1}).to_list(500)


async def _summaries(org_id: str, project_id: str = None) -> tuple:
    """Ringkasan anggaran seluruh proyek yang diminta + daftar proyek tanpa anggaran."""
    rows, kosong = [], []
    for proj in await _projects(org_id, project_id):
        alert = await cfg.get("budget.alert_pct", org_id=org_id, project_id=proj["id"])
        res = await be.compute_project(org_id, proj["id"], alert_pct=alert)
        if res["state"] == "kosong":
            kosong.append(proj.get("name") or proj["id"])
            continue
        rows.append({**res, "name": proj.get("name")})
    return rows, kosong


def _missing_for(rows: list, kosong: list) -> list:
    missing = []
    if not rows:
        missing.append("belum ada item anggaran pada proyek mana pun — susun master anggaran "
                       "dulu di RAB/BoQ → tab Target & Budget")
    elif kosong:
        missing.append(f"{len(kosong)} proyek belum punya item anggaran: "
                       + ", ".join(kosong[:3]))
    return missing


# ---------------------------------------------------------------------- BGT-01
async def budget_planned(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Rencana anggaran total = `Σ budget_items.planned_amount` (konstruksi = Σ item RAB)."""
    rows, kosong = await _summaries(org_id, project_id)
    total = sum(r["totals"]["planned"] for r in rows)
    missing = _missing_for(rows, kosong)
    return result("BGT-01", total if rows else None, label="Rencana anggaran total", unit="idr",
                  breakdown=[{"key": r["project_id"], "label": r["name"],
                              "value": r["totals"]["planned"]} for r in rows],
                  inputs={"proyek_beranggaran": len(rows), "proyek_tanpa_anggaran": len(kosong)},
                  coverage={"rows": len(rows), "total": len(rows) + len(kosong)}
                  if kosong and rows else None,
                  missing=missing or None, drill=DRILL_BUDGET)


# ---------------------------------------------------------------------- BGT-02
async def budget_exposure(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Exposure anggaran = `realisasi + komitmen` (dipakai untuk peringatan dini)."""
    rows, kosong = await _summaries(org_id, project_id)
    total = sum(r["totals"]["exposure"] for r in rows)
    return result("BGT-02", total if rows else None,
                  label="Exposure anggaran (realisasi + komitmen)", unit="idr",
                  breakdown=[{"key": r["project_id"], "label": r["name"],
                              "value": r["totals"]["exposure"],
                              "planned": r["totals"]["planned"],
                              "pct": r["totals"]["pct"], "health": r["totals"]["health"]}
                             for r in rows],
                  inputs={"realisasi": sum(r["totals"]["realized"] for r in rows),
                          "komitmen": sum(r["totals"]["committed"] for r in rows)},
                  coverage={"rows": len(rows), "total": len(rows) + len(kosong)}
                  if kosong and rows else None,
                  missing=_missing_for(rows, kosong) or None, drill=DRILL_BUDGET)


# ---------------------------------------------------------------------- BGT-03
async def budget_overbudget(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Item anggaran overbudget = `count(exposure > rencana)` (lintas kategori, bukan hanya RAB)."""
    rows, kosong = await _summaries(org_id, project_id)
    over, waspada = [], 0
    for r in rows:
        for item in r["items"]:
            if item["health"] == "overbudget":
                over.append({"key": item["id"], "label": f"{item['code']} · {r['name']}",
                             "value": item["exposure"], "planned": item["planned"],
                             "pct": item["pct"], "category": item["category"]})
            elif item["health"] == "waspada":
                waspada += 1
    return result("BGT-03", len(over) if rows else None, label="Item anggaran overbudget",
                  unit="count", breakdown=sorted(over, key=lambda x: -(x["pct"] or 0)),
                  inputs={"item_waspada": waspada,
                          "item_diperiksa": sum(len(r["items"]) for r in rows),
                          "selisih_rp": sum(max(0, o["value"] - (o["planned"] or 0))
                                            for o in over)},
                  missing=_missing_for(rows, kosong) or None, drill=DRILL_BUDGET)


# ---------------------------------------------------------------------- BGT-04
async def target_achievement(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Pencapaian target unit = `realisasi unit / target unit` pada target AKTIF.

    Realisasi dibaca dari `deals` (sumber yang sama dengan SLS-01), jadi angka di sini tidak
    bisa berbeda dengan dashboard penjualan.
    """
    projects = await _projects(org_id, project_id)
    rows, tanpa_target = [], []
    total_target = total_actual = 0
    for proj in projects:
        summ = await tstore.project_summary(org_id, proj["id"])
        if summ["state"] == "kosong":
            tanpa_target.append(proj.get("name") or proj["id"])
            continue
        tot = summ["totals"]
        total_target += int(tot.get("unit_target") or 0)
        total_actual += int(tot.get("unit_actual_total") or 0)
        rows.append({"key": proj["id"], "label": proj.get("name"),
                     "value": summ.get("achievement_pct"),
                     "unit_target": tot.get("unit_target"),
                     "unit_actual": tot.get("unit_actual_total"),
                     "method": summ["target"]["method"]})
    missing = []
    if not rows:
        missing.append("belum ada target AKTIF pada proyek mana pun — buat & aktifkan target "
                       "di RAB/BoQ → tab Target & Budget")
    elif tanpa_target:
        missing.append(f"{len(tanpa_target)} proyek belum punya target aktif: "
                       + ", ".join(tanpa_target[:3]))
    return result("BGT-04", round(total_actual / total_target * 100, 1)
                  if total_target else None,
                  label="Pencapaian target unit", unit="pct", breakdown=rows,
                  inputs={"unit_target": total_target, "unit_realisasi": total_actual,
                          "proyek_bertarget": len(rows)},
                  coverage={"rows": len(rows), "total": len(rows) + len(tanpa_target)}
                  if tanpa_target and rows else None,
                  missing=missing or None, drill=DRILL_TARGET)


# ---------------------------------------------------------------------- BGT-05
async def target_gap(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Kekurangan target berjalan (`carry_over`) = kekurangan bulan lampau yang dipindahkan.

    Angka inilah yang menjelaskan "kenapa target bulan ini naik" — tanpa dibawa ke dashboard,
    kenaikan target akan selalu terasa seperti keputusan sepihak sistem.
    """
    projects = await _projects(org_id, project_id)
    rows, total = [], 0
    for proj in projects:
        summ = await tstore.project_summary(org_id, proj["id"])
        if summ["state"] == "kosong":
            continue
        carry = int((summ["totals"] or {}).get("carry_over") or 0)
        total += carry
        cur = summ.get("current_period") or {}
        rows.append({"key": proj["id"], "label": proj.get("name"), "value": carry,
                     "period": cur.get("period"), "unit_plan": cur.get("unit_plan"),
                     "unit_actual": cur.get("unit_actual")})
    return result("BGT-05", total if rows else None,
                  label="Kekurangan target dipindahkan (carry over)", unit="count",
                  breakdown=rows, inputs={"proyek_bertarget": len(rows)},
                  missing=["belum ada target AKTIF pada proyek mana pun"] if not rows else None,
                  drill=DRILL_TARGET)


# ---------------------------------------------------------------------- BGT-06
async def projected_margin(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Margin proyeksi = `harga jual seluruh unit − (RAB total + budget operasional total)`.

    Berbeda dengan PRJ-07 (margin REALISASI), metrik ini menjawab "kalau semuanya berjalan
    sesuai rencana, berapa marginnya" — sehingga keputusan harga bisa diambil sebelum biaya
    benar-benar keluar.
    """
    rows, total, missing = [], 0, []
    for proj in await _projects(org_id, project_id):
        mg = await br.margin(org_id, proj["id"])
        if mg["margin_projected"] is None:
            missing.append(f"{proj.get('name')}: {'; '.join(mg['missing'][:1])}")
            continue
        total += mg["margin_projected"]
        rows.append({"key": proj["id"], "label": proj.get("name"),
                     "value": mg["margin_projected"], "pct": mg["margin_projected_pct"],
                     **mg["components"]})
    return result("BGT-06", total if rows else None, label="Margin proyeksi proyek",
                  unit="idr", breakdown=rows,
                  inputs={"proyek_terhitung": len(rows)},
                  coverage={"rows": len(rows), "total": len(rows) + len(missing)}
                  if missing and rows else None,
                  missing=missing[:3] if not rows or missing else None,
                  drill=DRILL_BUDGET)


METRICS = {
    "BGT-01": {"fn": budget_planned, "label": "Rencana anggaran total", "unit": "idr",
               "persona": "proyek", "snapshot": True,
               "formula": "Σ budget_items.planned_amount (konstruksi = Σ item RAB tertaut)",
               "requires": ["budget_items", "boq_items"], "drill": DRILL_BUDGET},
    "BGT-02": {"fn": budget_exposure, "label": "Exposure anggaran (realisasi + komitmen)",
               "unit": "idr", "persona": "proyek", "snapshot": True,
               "formula": "realisasi + komitmen (per item anggaran, dijumlahkan)",
               "requires": ["budget_items", "purchase_orders", "ap_invoices",
                            "spk_scope_items", "journal_entries"], "drill": DRILL_BUDGET},
    "BGT-03": {"fn": budget_overbudget, "label": "Item anggaran overbudget", "unit": "count",
               "persona": "proyek", "snapshot": True,
               "formula": "count(item dengan exposure > rencana)",
               "requires": ["budget_items"], "drill": DRILL_BUDGET},
    "BGT-04": {"fn": target_achievement, "label": "Pencapaian target unit", "unit": "pct",
               "persona": "eksekutif", "snapshot": True,
               "formula": "unit terjual (deals) / unit target pada target AKTIF",
               "requires": ["project_targets", "deals"], "drill": DRILL_TARGET},
    "BGT-05": {"fn": target_gap, "label": "Kekurangan target dipindahkan (carry over)",
               "unit": "count", "persona": "eksekutif",
               "formula": "Σ carry_over periode (rencana lampau − realisasi lampau)",
               "requires": ["project_targets", "deals"], "drill": DRILL_TARGET},
    "BGT-06": {"fn": projected_margin, "label": "Margin proyeksi proyek", "unit": "idr",
               "persona": "eksekutif", "snapshot": True,
               "formula": "harga jual seluruh unit − (RAB total + budget operasional total)",
               "requires": ["units", "boq_items", "budget_items"], "drill": DRILL_BUDGET},
}
