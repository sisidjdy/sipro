"""target_store.py — Fase 45: lapisan DATA untuk target proyek (`docs/v2/32` §2).

Pemisahan yang disengaja: `target_engine.py` hanya ARITMATIKA (fungsi murni, mudah diuji),
modul ini yang menyentuh database — mengambil REALISASI dari sumber yang sudah ada, menyimpan
periode hasil hitungan, dan menjalankan penyesuaian bulanan.

Aturan penting: **realisasi target tidak pernah diinput ulang.** Unit terjual & nilainya
dibaca dari `deals` (peristiwa `booked_at` yang benar-benar tercatat) — sumber yang sama
dengan metrik SLS-01/SLS-03 di Analitik & BI. Kalau realisasi bisa diketik manual, target akan
selalu "tercapai" di laporan dan tidak ada gunanya.
"""
import logging

import target_engine as te
from core_utils import new_id, now_iso
from db import ORG_ID, db

logger = logging.getLogger("sipro.targets")

SOLD_DEAL_STATUS = ("booked", "completed")


def _i(v) -> int:
    try:
        return int(round(float(v or 0)))
    except (TypeError, ValueError):
        return 0


async def actuals_for(org: str, *, project_id: str = None, cluster_id: str = None,
                      owner_email: str = None) -> dict:
    """`{period: {"unit": n, "revenue": rp}}` dari `deals` yang benar-benar terjual.

    Deal tanpa `booked_at` TIDAK dibuang diam-diam: jumlahnya dilaporkan lewat
    `actuals_coverage()` supaya cakupan angka realisasi bisa dinilai.
    """
    q = {"org_id": org, "status": {"$in": list(SOLD_DEAL_STATUS)}}
    if project_id:
        q["project_id"] = project_id
    if owner_email:
        q["assigned_to"] = owner_email
    deals = await db.deals.find(q, {"_id": 0, "booked_at": 1, "created_at": 1, "price": 1,
                                    "unit_id": 1, "assigned_to": 1}).to_list(20000)
    if cluster_id:
        unit_ids = [d.get("unit_id") for d in deals if d.get("unit_id")]
        units = await db.units.find({"org_id": org, "id": {"$in": unit_ids}},
                                    {"_id": 0, "id": 1, "cluster_id": 1}).to_list(20000)
        allowed = {u["id"] for u in units if u.get("cluster_id") == cluster_id}
        deals = [d for d in deals if d.get("unit_id") in allowed]
    out = {}
    for d in deals:
        stamp = d.get("booked_at") or d.get("created_at")
        if not stamp:
            continue
        period = str(stamp)[:7]
        row = out.setdefault(period, {"unit": 0, "revenue": 0})
        row["unit"] += 1
        row["revenue"] += _i(d.get("price"))
    return out


async def actuals_coverage(org: str, *, project_id: str = None) -> dict:
    q = {"org_id": org, "status": {"$in": list(SOLD_DEAL_STATUS)}}
    if project_id:
        q["project_id"] = project_id
    total = await db.deals.count_documents(q)
    no_stamp = await db.deals.count_documents({**q, "booked_at": None, "created_at": None})
    no_price = await db.deals.count_documents({**q, "price": {"$in": [None, 0]}})
    return {"deals": total, "tanpa_tanggal": no_stamp, "tanpa_harga": no_price}


async def avg_price_of(org: str, *, project_id: str = None, cluster_id: str = None) -> dict:
    """Harga rata-rata unit: dari harga unit yang BERHARGA (bukan tebakan).

    Dipakai metode `revenue_first` (menurunkan unit dari pendapatan) dan untuk mengubah
    rencana unit menjadi rencana pendapatan. Bila tidak ada unit berharga, nilainya 0 dan
    mesin target akan MENOLAK menghitung, bukan memakai angka karangan.
    """
    q = {"org_id": org}
    if project_id:
        q["project_id"] = project_id
    if cluster_id:
        q["cluster_id"] = cluster_id
    units = await db.units.find(q, {"_id": 0, "price": 1}).to_list(20000)
    priced = [_i(u.get("price")) for u in units if _i(u.get("price"))]
    return {"avg_price": int(round(sum(priced) / len(priced))) if priced else 0,
            "units": len(units), "priced": len(priced),
            "unpriced": len(units) - len(priced)}


def _weights_map(target: dict) -> dict:
    return {str(k): float(v or 0) for k, v in (target.get("weights") or {}).items()}


def _now_period() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date().isoformat()[:7]


async def compute_for(org: str, target: dict, *, today: str = None) -> dict:
    """Hitung ulang periode sebuah target berdasarkan realisasi terkini (tanpa menyimpan).

    `today` bawaannya adalah **bulan berjalan** (bukan awal horizon). Ini penting: kalau
    bulan berjalan salah, `lock_past` tidak pernah aktif dan seluruh horizon dihitung ulang
    tiap kali — artinya laporan historis bisa berubah diam-diam dan `carry_over` selalu 0.
    Cacat ini tertangkap saat layar target diperiksa di browser (rencana Jan–Des ikut
    berubah padahal Agustus sudah lewat).
    """
    horizon = target.get("horizon") or {}
    months = te.month_list(horizon.get("start"), horizon.get("end"))
    actuals = await actuals_for(org, project_id=target.get("project_id"),
                               cluster_id=target.get("cluster_id"),
                               owner_email=target.get("owner_email"))
    assumptions = target.get("assumptions") or {}
    avg_price = _i(assumptions.get("avg_price"))
    if not avg_price:
        avg_price = (await avg_price_of(org, project_id=target.get("project_id"),
                                        cluster_id=target.get("cluster_id")))["avg_price"]
    policy = target.get("recalc_policy") or {}
    out = te.compute_periods(
        method=target.get("method") or "linear_remaining", months=months,
        unit_target=target.get("unit_target") or 0,
        revenue_target=target.get("revenue_target") or 0, avg_price=avg_price,
        actuals=actuals, existing={p["period"]: p for p in (target.get("periods") or [])},
        weights=_weights_map(target), manual=target.get("manual_plan") or {},
        growth_pct=assumptions.get("growth_pct") or 0, today=today or _now_period(),
        lock_past=policy.get("lock_past", True), keep_total=policy.get("keep_total", True))
    out["avg_price_used"] = avg_price
    out["coverage"] = await actuals_coverage(org, project_id=target.get("project_id"))
    return out


async def preview(org: str, base: dict, *, overrides: dict = None,
                  today: str = None) -> dict:
    """PRATINJAU DAMPAK sebelum disimpan (DoD #1 `docs/v2/32` §6).

    Mengubah metode target adalah keputusan yang berkonsekuensi ke seluruh bulan berikutnya.
    Menyimpan dulu lalu "lihat hasilnya" berarti pemakai sudah mengubah rencana resmi sebelum
    tahu akibatnya. Karena itu pratinjau memakai jalur perhitungan YANG SAMA (bukan tiruan)
    dan mengembalikan `before`/`after` per periode.
    """
    before = await compute_for(org, base, today=today)
    candidate = {**base, **(overrides or {})}
    after = await compute_for(org, candidate, today=today)
    diff = []
    bmap = {p["period"]: p for p in before["periods"]}
    for row in after["periods"]:
        old = (bmap.get(row["period"]) or {}).get("unit_plan")
        if old != row["unit_plan"]:
            diff.append({"period": row["period"], "before": old, "after": row["unit_plan"],
                         "locked": row["locked"]})
    return {"before": before, "after": after, "changes": diff,
            "method_before": base.get("method"), "method_after": candidate.get("method"),
            "formula": after.get("formula")}


async def save_periods(org: str, target_id: str, computed: dict, *, reason: str,
                       actor: str) -> dict:
    """Simpan periode hasil hitungan + satu entri jejak (`history[]`)."""
    entry = {"at": now_iso(), "by": actor, "method": computed.get("method"), "reason": reason,
             "changed_periods": len(computed.get("changes") or []),
             "changes": (computed.get("changes") or [])[:24],
             "carry_over": (computed.get("totals") or {}).get("carry_over", 0)}
    await db.project_targets.update_one(
        {"id": target_id, "org_id": org},
        {"$set": {"periods": computed["periods"], "totals": computed["totals"],
                  "warnings": computed["warnings"], "missing": computed["missing"],
                  "projection": computed.get("projection"),
                  "last_recalc_at": now_iso(), "last_recalc_by": actor,
                  "updated_at": now_iso()},
         "$push": {"history": {"$each": [entry], "$slice": -60}}})
    return entry


async def recalc_target(org: str, target_id: str, *, reason: str, actor: str,
                        today: str = None) -> dict:
    target = await db.project_targets.find_one({"id": target_id, "org_id": org}, {"_id": 0})
    if not target:
        return {}
    computed = await compute_for(org, target, today=today)
    prev = {p["period"]: p.get("unit_plan") for p in (target.get("periods") or [])}
    computed["changes"] = [{"period": r["period"], "before": prev.get(r["period"]),
                            "after": r["unit_plan"]}
                           for r in computed["periods"]
                           if prev.get(r["period"]) != r["unit_plan"]]
    entry = await save_periods(org, target_id, computed, reason=reason, actor=actor)
    return {"target_id": target_id, "entry": entry, **computed}


async def progress(org: str, target: dict) -> dict:
    """Target vs realisasi per periode + proyeksi (untuk `GET /api/targets/{id}/progress`)."""
    computed = await compute_for(org, target)
    rows, cum_plan, cum_actual = [], 0, 0
    for row in computed["periods"]:
        plan = row["unit_plan"]
        cum_plan += _i(plan)
        cum_actual += _i(row["unit_actual"])
        rows.append({**row, "gap": (_i(row["unit_actual"]) - _i(plan))
                     if plan is not None else None,
                     "achievement_pct": (round(_i(row["unit_actual"]) / plan * 100, 1)
                                         if plan else None),
                     "cumulative_plan": cum_plan, "cumulative_actual": cum_actual})
    totals = computed["totals"]
    return {
        "target_id": target.get("id"), "name": target.get("name"),
        "method": computed["method"], "formula": computed["formula"],
        "status": target.get("status"), "periods": rows, "totals": totals,
        "achievement_pct": (round(totals["unit_actual_total"] / totals["unit_target"] * 100, 1)
                            if totals.get("unit_target") else None),
        "revenue_achievement_pct": (
            round(totals["revenue_actual_total"] / totals["revenue_target"] * 100, 1)
            if totals.get("revenue_target") else None),
        "projection": computed.get("projection"), "warnings": computed["warnings"],
        "missing": computed["missing"], "coverage": computed.get("coverage"),
        "avg_price_used": computed.get("avg_price_used"),
        "history": (target.get("history") or [])[-12:],
    }


async def project_summary(org: str, project_id: str) -> dict:
    """Ringkasan untuk kartu dashboard proyek (`GET /api/projects/{pid}/target-summary`).

    Tanpa target aktif, jawabannya BUKAN nol — melainkan `state: kosong` + ajakan membuat
    target, supaya kartu dashboard tidak menyiratkan "target 0 unit, tercapai 100%".
    """
    target = await db.project_targets.find_one(
        {"org_id": org, "project_id": project_id, "status": "active", "cluster_id": None,
         "owner_email": None}, {"_id": 0})
    if not target:
        count = await db.project_targets.count_documents({"org_id": org,
                                                          "project_id": project_id})
        return {"project_id": project_id, "state": "kosong", "target": None,
                "missing": ["belum ada target AKTIF untuk proyek ini"
                            + (f" ({count} target masih draf/ditutup)" if count else "")],
                "drill": "/boq?hub=target"}
    prog = await progress(org, target)
    now = _now_period()
    current = next((p for p in prog["periods"] if p["period"] == now), None)
    return {
        "project_id": project_id, "state": "lengkap" if not prog["missing"] else "sebagian",
        "target": {"id": target["id"], "name": target.get("name"),
                   "method": target.get("method"), "basis": target.get("basis"),
                   "unit_target": target.get("unit_target"),
                   "revenue_target": target.get("revenue_target"),
                   "horizon": target.get("horizon")},
        "totals": prog["totals"], "achievement_pct": prog["achievement_pct"],
        "revenue_achievement_pct": prog["revenue_achievement_pct"],
        "current_period": current, "projection": prog["projection"],
        "missing": prog["missing"], "drill": "/boq?hub=target",
    }


async def recalc_tick() -> int:
    """Job penyesuaian bulanan (`targets_recalc_tick`, `docs/v2/32` §2.1).

    Idempoten: satu target hanya dihitung ulang SEKALI per bulan oleh penjadwal
    (`recalc_period`), sehingga menjalankan job berulang tidak menumpuk jejak palsu.
    """
    period = _now_period()
    done = 0
    try:
        cursor = db.project_targets.find(
            {"status": "active", "recalc_policy.mode": "monthly",
             "recalc_period": {"$ne": period}}, {"_id": 0})
        async for target in cursor:
            org = target.get("org_id", ORG_ID)
            await recalc_target(org, target["id"], actor="scheduler",
                                reason=f"Penyesuaian otomatis awal bulan {period}")
            await db.project_targets.update_one({"id": target["id"]},
                                               {"$set": {"recalc_period": period}})
            done += 1
        if done:
            logger.info("Target disesuaikan otomatis untuk %s: %s target", period, done)
    except Exception as exc:  # noqa: BLE001 — dicatat, tidak mematikan scheduler
        logger.warning("Penyesuaian target bulanan gagal: %s", exc)
    return done


async def create_target(org: str, payload: dict, *, actor: str) -> dict:
    """Buat target + langsung hitung periodenya (target tanpa periode tidak ada gunanya)."""
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "project_id": payload["project_id"],
        "cluster_id": payload.get("cluster_id"), "owner_email": payload.get("owner_email"),
        "scope": payload.get("scope") or "project", "name": payload["name"],
        "basis": payload.get("basis") or "both",
        "method": payload.get("method") or "linear_remaining",
        "horizon": payload.get("horizon") or {},
        "unit_target": _i(payload.get("unit_target")),
        "revenue_target": _i(payload.get("revenue_target")),
        "recalc_policy": payload.get("recalc_policy") or {"mode": "monthly",
                                                          "keep_total": True,
                                                          "lock_past": True},
        "weights": payload.get("weights") or {}, "manual_plan": payload.get("manual_plan") or {},
        "assumptions": payload.get("assumptions") or {},
        "status": "draft", "periods": [], "history": [], "note": payload.get("note"),
        "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    await db.project_targets.insert_one(dict(doc))
    doc.pop("_id", None)
    computed = await compute_for(org, doc)
    computed["changes"] = [{"period": r["period"], "before": None, "after": r["unit_plan"]}
                           for r in computed["periods"]]
    await save_periods(org, doc["id"], computed, reason="Target dibuat", actor=actor)
    return await db.project_targets.find_one({"id": doc["id"]}, {"_id": 0})


async def siblings_total(org: str, target: dict) -> list:
    """Target anak (cluster/sales) pada proyek yang sama — untuk validasi anak ≤ induk."""
    return await db.project_targets.find(
        {"org_id": org, "project_id": target.get("project_id"), "status": {"$ne": "closed"},
         "id": {"$ne": target.get("id")},
         "$or": [{"cluster_id": {"$ne": None}}, {"owner_email": {"$ne": None}}]},
        {"_id": 0, "unit_target": 1, "name": 1, "cluster_id": 1, "owner_email": 1}).to_list(200)
