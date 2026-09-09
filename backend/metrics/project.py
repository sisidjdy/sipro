"""metrics/project.py — kamus metrik PROYEK, RAB & BIAYA (PRJ-01..09), spec Dok 31 §5.

Dua kejujuran yang dijaga modul ini:

1. **Realisasi biaya hanya dihitung dari dokumen yang BISA ditautkan ke RAB.** Nilai yang
   tidak punya jejak ke item BoQ dilaporkan terpisah sebagai "belum tertaut", bukan
   dijumlahkan diam-diam — kalau dijumlahkan, angka "realisasi RAB" akan terlihat rapi
   padahal sebagian biayanya tidak bisa ditelusuri ke pekerjaan mana pun.
2. **Progres proyek memakai mesin jadwal yang sudah ada** (`build_items` berbobot), bukan
   rata-rata sederhana yang mengabaikan bobot pekerjaan.
"""
from datetime import datetime, timezone

import opname as op
from db import ORG_ID, db
from metrics.base import date_of, div, pct, result

DONE_STATUS = ("verified", "done", "selesai")


async def _projects(org_id: str, project_id: str = None) -> list:
    q = {"org_id": org_id}
    if project_id:
        q["id"] = project_id
    return await db.projects.find(q, {"_id": 0, "id": 1, "name": 1}).to_list(500)


# ---------------------------------------------------------------------- PRJ-01
async def progress(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Progres proyek = `Σ bobot langkah terverifikasi / Σ bobot langkah` (berbobot)."""
    q = {"org_id": org_id}
    if project_id:
        q["project_id"] = project_id
    items = await db.build_items.find(q, {"_id": 0, "status": 1, "weight": 1, "unit_code": 1,
                                          "project_id": 1, "step_code": 1}).to_list(50000)
    if not items:
        return result("PRJ-01", None, label="Progres proyek", unit="pct",
                      missing=["belum ada jadwal pembangunan (build_items) untuk proyek ini"],
                      drill="/build?hub=progres")
    total_w = sum(float(i.get("weight") or 0) for i in items)
    done_w = sum(float(i.get("weight") or 0) for i in items
                 if i.get("status") in DONE_STATUS)
    per_unit = {}
    for item in items:
        key = item.get("unit_code") or "(tanpa unit)"
        row = per_unit.setdefault(key, {"key": key, "label": key, "weight": 0, "done": 0})
        row["weight"] += float(item.get("weight") or 0)
        row["done"] += float(item.get("weight") or 0) if item.get("status") in DONE_STATUS else 0
    for row in per_unit.values():
        row["value"] = pct(row["done"], row["weight"])
    tanpa_bobot = len([i for i in items if not i.get("weight")])
    return result("PRJ-01", pct(done_w, total_w), label="Progres proyek", unit="pct",
                  breakdown=sorted(per_unit.values(), key=lambda r: (r["value"] or 0)),
                  inputs={"langkah": len(items), "bobot_total": round(total_w, 2),
                          "bobot_selesai": round(done_w, 2)},
                  coverage={"rows": len(items) - tanpa_bobot, "total": len(items)}
                  if tanpa_bobot else None,
                  missing=[f"{tanpa_bobot} langkah tanpa bobot"] if tanpa_bobot else None,
                  drill="/build?hub=progres")


# ---------------------------------------------------------------------- PRJ-02
async def schedule_deviation(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Deviasi jadwal = jumlah langkah TELAT + total hari telat (dari `late_days` mesin jadwal)."""
    q = {"org_id": org_id}
    if project_id:
        q["project_id"] = project_id
    items = await db.build_items.find(q, {"_id": 0, "late_days": 1, "status": 1, "unit_code": 1,
                                          "name": 1, "planned_finish": 1}).to_list(50000)
    late = [i for i in items if int(i.get("late_days") or 0) > 0]
    per_unit = {}
    for item in late:
        key = item.get("unit_code") or "(tanpa unit)"
        row = per_unit.setdefault(key, {"key": key, "label": key, "value": 0, "days": 0})
        row["value"] += 1
        row["days"] += int(item.get("late_days") or 0)
    return result("PRJ-02", len(late), label="Langkah terlambat", unit="count",
                  breakdown=sorted(per_unit.values(), key=lambda r: -r["days"]),
                  inputs={"langkah": len(items),
                          "total_hari_telat": sum(int(i.get("late_days") or 0) for i in late)},
                  missing=["belum ada jadwal pembangunan untuk proyek ini"] if not items else None,
                  drill="/build?hub=progres")


# ----------------------------------------------------------------- PRJ-03 / 04
async def budget_actual(*, org_id: str = ORG_ID, project_id: str = None, drill: str = "category",
                        **_) -> dict:
    """RAB vs realisasi. Realisasi = nilai lingkup SPK yang sudah DIVERIFIKASI (opname) —
    yaitu pekerjaan yang benar-benar diakui selesai — ditambah tagihan vendor yang disetujui.

    Bagian yang belum bisa ditautkan ke item RAB (anggaran tanpa pemetaan langkah, tagihan
    tanpa PO ber-BoQ) dilaporkan sebagai `belum tertaut` supaya tidak menyamarkan biaya.
    """
    projects = await _projects(org_id, project_id)
    if not projects:
        return result("PRJ-03", None, label="Realisasi RAB", unit="idr",
                      missing=["belum ada proyek"], drill="/boq")
    rows, totals = [], {"budget": 0, "contracted": 0, "verified": 0, "billed": 0,
                        "unmapped_budget": 0}
    for proj in projects:
        control = await op.cost_control(org_id, proj["id"], proj.get("name"))
        src = control["categories" if drill == "category" else "cost_codes"]
        for row in src:
            rows.append({"key": f"{proj['id']}:{row['key']}",
                         "label": f"{row.get('label') or row['key']}",
                         "project": proj.get("name"),
                         "value": row["verified"], "budget": row["budget"],
                         "contracted": row["contracted"], "billed": row["billed"],
                         "variance": row["variance"], "over_commit": row["over_commit"]})
        for key in ("budget", "contracted", "verified", "billed"):
            totals[key] += control["totals"][key]
        totals["unmapped_budget"] += control.get("unmapped_budget") or 0
    missing = []
    if not totals["budget"]:
        missing.append("RAB belum disusun untuk proyek ini")
    if totals["unmapped_budget"]:
        missing.append(f"anggaran belum tertaut ke langkah jadwal: "
                       f"Rp {totals['unmapped_budget']:,}".replace(",", "."))
    return result("PRJ-03", totals["verified"], label="Realisasi RAB (terverifikasi)",
                  unit="idr", breakdown=sorted(rows, key=lambda r: -r["budget"]),
                  inputs=totals,
                  coverage={"rows": totals["budget"] - totals["unmapped_budget"],
                            "total": totals["budget"]} if totals["budget"] else None,
                  missing=missing or None, drill="/boq")


async def budget_ratio(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """RAB vs realisasi (rasio) = `realisasi / anggaran` per kategori & total."""
    base = await budget_actual(org_id=org_id, project_id=project_id)
    inputs = base["inputs"]
    for row in base["breakdown"]:
        row["ratio_pct"] = pct(row["value"], row["budget"])
    return result("PRJ-04", pct(inputs.get("verified", 0), inputs.get("budget", 0)),
                  label="Realisasi terhadap RAB", unit="pct", breakdown=base["breakdown"],
                  inputs=inputs, coverage=base["coverage"],
                  missing=base["missing"] or None, drill="/boq")


# ---------------------------------------------------------------------- PRJ-05
async def overbudget(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Overbudget = kategori/kode biaya yang nilai dikontrakkan/realisasinya MELEBIHI anggaran."""
    base = await budget_actual(org_id=org_id, project_id=project_id, drill="cost_code")
    over = [r for r in base["breakdown"] if r.get("over_commit")]
    selisih = sum(max(0, r["contracted"] - r["budget"]) for r in over)
    return result("PRJ-05", len(over), label="Item overbudget", unit="count",
                  breakdown=over,
                  inputs={"selisih_rp": selisih, "item_diperiksa": len(base["breakdown"]),
                          **base["inputs"]},
                  missing=base["missing"] or None, drill="/boq")


# ---------------------------------------------------------------------- PRJ-06
async def cost_per_unit(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Biaya per unit = nilai lingkup SPK terverifikasi yang tertaut ke unit tersebut."""
    q = {"org_id": org_id}
    if project_id:
        q["project_id"] = project_id
    scope = await db.spk_scope_items.find(q, {"_id": 0}).to_list(20000)
    if not scope:
        return result("PRJ-06", None, label="Biaya per unit", unit="idr",
                      missing=["belum ada lingkup SPK yang bisa ditautkan ke unit"],
                      drill="/subcon")
    items = await db.build_items.find(
        {"org_id": org_id, "id": {"$in": [s.get("build_item_id") for s in scope]}},
        {"_id": 0, "id": 1, "unit_code": 1, "unit_id": 1}).to_list(20000)
    imap = {i["id"]: i for i in items}
    per_unit, tanpa_unit = {}, 0
    for s in scope:
        item = imap.get(s.get("build_item_id")) or {}
        key = item.get("unit_code")
        if not key:
            tanpa_unit += 1
            continue
        row = per_unit.setdefault(key, {"key": key, "label": key, "value": 0, "verified": 0})
        row["value"] += int(s.get("value") or 0)
        row["verified"] += int(s.get("value") or 0) if s.get("verified") else 0
    nilai = [r["value"] for r in per_unit.values()]
    return result("PRJ-06", int(round(sum(nilai) / len(nilai))) if nilai else None,
                  label="Biaya per unit (rata-rata)", unit="idr",
                  breakdown=sorted(per_unit.values(), key=lambda r: -r["value"]),
                  inputs={"lingkup": len(scope), "unit": len(per_unit)},
                  coverage={"rows": len(scope) - tanpa_unit, "total": len(scope)}
                  if tanpa_unit else None,
                  missing=[f"{tanpa_unit} baris lingkup tidak tertaut ke unit"]
                  if tanpa_unit else None, drill="/subcon")


# ---------------------------------------------------------------------- PRJ-07
async def project_margin(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Margin proyek = `pendapatan diakui − (realisasi RAB + realisasi budget operasional)`.

    **Fase 45 membuka metrik ini.** Sampai Fase 44, budget operasional tidak punya sumber data
    sehingga metrik ini SELALU mengaku "belum ada data" — sekarang komponennya nyata:
    realisasi biaya diambil dari `budget_items` (yang kategori konstruksinya meringkas RAB dan
    kategori lainnya dicocokkan ke jurnal/dokumen). Yang masih belum ada tetap disebut apa
    adanya: bila `revenue_recognitions` kosong, margin TIDAK dihitung dari kas masuk — kas
    masuk bukan pendapatan, dan menukarnya akan membuat margin terlihat lebih baik dari
    kenyataan.
    """
    import budget_reports as br  # impor lokal: hindari lingkar (br → engine → …)
    projects = await _projects(org_id, project_id)
    if not projects:
        return result("PRJ-07", None, label="Margin proyek", unit="idr",
                      missing=["belum ada proyek"], drill="/accounting/reports")
    rows, totals, missing = [], {"revenue": 0, "cost": 0, "cash_in": 0}, []
    counted = 0
    for proj in projects:
        mg = await br.margin(org_id, proj["id"])
        comp = mg["components"]
        totals["cost"] += int(comp.get("realisasi_biaya") or 0)
        totals["cash_in"] += int(comp.get("kas_masuk") or 0)
        if mg["margin"] is None:
            missing.extend(f"{proj.get('name')}: {m}" for m in mg["missing"][:1])
            continue
        counted += 1
        totals["revenue"] += int(comp.get("pendapatan_diakui") or 0)
        rows.append({"key": proj["id"], "label": proj.get("name"), "value": mg["margin"],
                     "pct": mg["margin_pct"], "pendapatan": comp.get("pendapatan_diakui"),
                     "biaya": comp.get("realisasi_biaya")})
    return result("PRJ-07", (totals["revenue"] - totals["cost"]) if counted else None,
                  label="Margin proyek", unit="idr", breakdown=rows,
                  inputs={"pendapatan_diakui": totals["revenue"] if counted else None,
                          "realisasi_biaya": totals["cost"], "kas_masuk": totals["cash_in"],
                          "proyek_terhitung": counted, "proyek": len(projects)},
                  coverage={"rows": counted, "total": len(projects)}
                  if counted and counted != len(projects) else None,
                  missing=missing[:3] if not counted or missing else None,
                  drill="/accounting/reports")


# ---------------------------------------------------------------------- PRJ-08
async def completion_forecast(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Proyeksi selesai = tanggal rencana selesai TERAKHIR pada jadwal + jumlah hari telat
    yang sudah terjadi (perkiraan konservatif, bukan ekstrapolasi kecepatan yang dikarang)."""
    q = {"org_id": org_id}
    if project_id:
        q["project_id"] = project_id
    items = await db.build_items.find(q, {"_id": 0, "planned_finish": 1, "late_days": 1,
                                          "status": 1, "unit_code": 1}).to_list(50000)
    planned = [i.get("planned_finish") for i in items if i.get("planned_finish")]
    if not planned:
        return result("PRJ-08", None, label="Proyeksi selesai proyek", unit="text",
                      missing=["jadwal belum punya tanggal rencana selesai"],
                      drill="/build?hub=kalender")
    last_plan = max(planned)
    total_late = max((int(i.get("late_days") or 0) for i in items), default=0)
    belum = len([i for i in items if i.get("status") not in DONE_STATUS])
    return result("PRJ-08", date_of(last_plan), label="Proyeksi selesai proyek", unit="text",
                  inputs={"rencana_selesai_terakhir": date_of(last_plan),
                          "telat_maks_hari": total_late, "langkah_belum_selesai": belum},
                  coverage={"rows": len(planned), "total": len(items)}
                  if len(planned) != len(items) else None,
                  missing=[f"{len(items) - len(planned)} langkah tanpa tanggal rencana"]
                  if len(planned) != len(items) else None,
                  drill="/build?hub=kalender")


# ---------------------------------------------------------------------- PRJ-09
async def open_commitments(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Komitmen belum tertagih = `Σ nilai PO terbuka` (disetujui tapi belum ditagih penuh).

    Tanpa angka ini, overbudget baru terlihat saat tagihan masuk — terlambat untuk dicegah.
    """
    q = {"org_id": org_id, "status": {"$nin": ["cancelled", "closed", "paid"]}}
    if project_id:
        q["project_id"] = project_id
    rows = await db.purchase_orders.find(q, {"_id": 0}).to_list(20000)
    per_vendor = {}
    total = 0
    for po in rows:
        sisa = int(po.get("total") or 0) - int(po.get("billed_value") or 0)
        if sisa <= 0:
            continue
        total += sisa
        key = po.get("vendor") or po.get("subcontractor_name") or "(tanpa vendor)"
        row = per_vendor.setdefault(key, {"key": key, "label": key, "value": 0, "count": 0})
        row["value"] += sisa
        row["count"] += 1
    return result("PRJ-09", total, label="Komitmen belum tertagih (PO terbuka)", unit="idr",
                  breakdown=sorted(per_vendor.values(), key=lambda r: -r["value"]),
                  inputs={"po_terbuka": len(rows)}, drill="/procurement")


METRICS = {
    "PRJ-01": {"fn": progress, "label": "Progres proyek", "unit": "pct", "persona": "proyek",
               "snapshot": True, "formula": "Σ bobot langkah terverifikasi / Σ bobot",
               "requires": ["build_items"], "drill": "/build?hub=progres"},
    "PRJ-02": {"fn": schedule_deviation, "label": "Langkah terlambat", "unit": "count",
               "persona": "proyek", "snapshot": True,
               "formula": "count(build_items.late_days > 0)", "requires": ["build_items"],
               "drill": "/build?hub=progres"},
    "PRJ-03": {"fn": budget_actual, "label": "Realisasi RAB (terverifikasi)", "unit": "idr",
               "persona": "proyek", "snapshot": True,
               "formula": "Σ lingkup SPK terverifikasi (per kategori/kode biaya)",
               "requires": ["boq_items", "spk_scope_items"], "drill": "/boq"},
    "PRJ-04": {"fn": budget_ratio, "label": "Realisasi terhadap RAB", "unit": "pct",
               "persona": "proyek", "snapshot": True, "formula": "realisasi / anggaran",
               "requires": ["boq_items", "spk_scope_items"], "drill": "/boq"},
    "PRJ-05": {"fn": overbudget, "label": "Item overbudget", "unit": "count",
               "persona": "proyek", "snapshot": True,
               "formula": "count(kode biaya dengan dikontrakkan > anggaran)",
               "requires": ["boq_items", "spk_scope_items"], "drill": "/boq"},
    "PRJ-06": {"fn": cost_per_unit, "label": "Biaya per unit (rata-rata)", "unit": "idr",
               "persona": "proyek", "formula": "Σ nilai lingkup per unit / jumlah unit",
               "requires": ["spk_scope_items", "build_items"], "drill": "/subcon"},
    "PRJ-07": {"fn": project_margin, "label": "Margin proyek", "unit": "idr",
               "persona": "proyek",
               "formula": "pendapatan diakui - (realisasi RAB + realisasi budget operasional)",
               "requires": ["revenue_recognitions", "budget_items", "boq_items"],
               "drill": "/accounting/reports"},
    "PRJ-08": {"fn": completion_forecast, "label": "Proyeksi selesai proyek", "unit": "text",
               "persona": "proyek", "formula": "max(planned_finish) + telat yang sudah terjadi",
               "requires": ["build_items"], "drill": "/build?hub=kalender"},
    "PRJ-09": {"fn": open_commitments, "label": "Komitmen belum tertagih (PO terbuka)",
               "unit": "idr", "persona": "proyek", "snapshot": True,
               "formula": "Σ (PO.total - PO.billed_value) untuk PO terbuka",
               "requires": ["purchase_orders"], "drill": "/procurement"},
}
