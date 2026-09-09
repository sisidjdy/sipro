"""Analitik & BI (Fase 44) — `docs/v2/31_ANALYTICS_BI_SPEC.md` §7.

Keputusan yang tercermin di kode ini:
  1. **Semua angka lewat lapisan `metrics`** — router TIDAK menghitung apa pun sendiri, supaya
     angka di BI tidak bisa berbeda dengan angka di halaman operasional.
  2. **RBAC + row-scope**: peran ber-`view_own` (sales) hanya melihat datanya sendiri; itu
     dipaksakan di server dengan `owner_email`, bukan disembunyikan di layar.
  3. **Setiap jawaban membawa kelengkapan** (`state`: lengkap/sebagian/kosong) supaya layar
     bisa jujur tanpa menebak.
  4. Urutan rute: path statis sebelum path ber-parameter (pelajaran `verify_api_contract`).
"""
import csv
import io

import analytics_engine as eng
import metrics
from db import ORG_ID
from fastapi import APIRouter, Depends, HTTPException, Response
from rbac import is_scoped_sales, audit_log, require_permission

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _scope(user: dict) -> str:
    """Email pemilik data bila perannya hanya boleh melihat miliknya sendiri (sales)."""
    return user.get("email") if is_scoped_sales(user) else None


@router.get("/metrics")
async def metric_catalog(persona: str = None,
                        user: dict = Depends(require_permission("analytics", "view"))):
    """Kamus metrik: kode, nama, rumus, satuan, kebutuhan data, tautan drill-down."""
    return {"data": metrics.catalog(persona), "personas": eng.DASHBOARDS.keys().__len__(),
            "dashboards": {k: v for k, v in eng.DASHBOARDS.items()},
            "snapshot_codes": sorted(eng.SNAPSHOT_CODES)}


@router.get("/executive")
async def executive(project_id: str = None, period: str = None, date_from: str = None,
                    date_to: str = None,
                    user: dict = Depends(require_permission("analytics", "view"))):
    rng = eng.resolve_range(period, date_from, date_to)
    return {"data": await eng.dashboard("eksekutif", org_id=user.get("org_id", ORG_ID),
                                        date_from=rng["from"], date_to=rng["to"],
                                        project_id=project_id, owner_email=_scope(user))}


@router.get("/sales/funnel")
async def sales_funnel(period: str = None, date_from: str = None, date_to: str = None,
                       group_by: str = "source", project_id: str = None,
                       user: dict = Depends(require_permission("analytics", "view"))):
    """Dashboard Penjualan & Lead: funnel, conversion, aging, kualitas sumber, kohor."""
    rng = eng.resolve_range(period, date_from, date_to)
    data = await eng.dashboard("penjualan", org_id=user.get("org_id", ORG_ID),
                               date_from=rng["from"], date_to=rng["to"],
                               project_id=project_id, owner_email=_scope(user))
    data["group_by"] = group_by
    if group_by != "source":
        data["metrics"].append(eng.decorate("LED-01", await metrics.compute(
            "LED-01", org_id=user.get("org_id", ORG_ID), date_from=rng["from"],
            date_to=rng["to"], owner_email=_scope(user), group_by=group_by)))
    return {"data": data}


@router.get("/sales/cohort")
async def sales_cohort(period: str = None, date_from: str = None, date_to: str = None,
                       user: dict = Depends(require_permission("analytics", "view"))):
    rng = eng.resolve_range(period, date_from, date_to)
    return {"data": await eng.one("LED-15", org_id=user.get("org_id", ORG_ID),
                                  date_from=rng["from"], date_to=rng["to"],
                                  owner_email=_scope(user))}


@router.get("/sales/units-sold")
async def units_sold(project_id: str = None, granularity: str = "month", period: str = None,
                     date_from: str = None, date_to: str = None,
                     user: dict = Depends(require_permission("analytics", "view"))):
    rng = eng.resolve_range(period, date_from, date_to)
    return {"data": await eng.one("SLS-01", org_id=user.get("org_id", ORG_ID),
                                  date_from=rng["from"], date_to=rng["to"],
                                  project_id=project_id, granularity=granularity)}


@router.get("/leads/aging")
async def leads_aging(user: dict = Depends(require_permission("analytics", "view"))):
    return {"data": await eng.one("LED-05", org_id=user.get("org_id", ORG_ID),
                                  owner_email=_scope(user))}


@router.get("/leads/demography")
async def leads_demography(dimension: str = "age",
                           user: dict = Depends(require_permission("analytics", "view"))):
    return {"data": await eng.one("LED-12", org_id=user.get("org_id", ORG_ID),
                                  dimension=dimension)}


@router.get("/marketing/performance")
async def marketing_performance(period: str = None, date_from: str = None, date_to: str = None,
                                level: str = "campaign",
                                user: dict = Depends(require_permission("analytics", "view"))):
    rng = eng.resolve_range(period, date_from, date_to)
    data = await eng.dashboard("marketing", org_id=user.get("org_id", ORG_ID),
                               date_from=rng["from"], date_to=rng["to"])
    data["level"] = level
    return {"data": data}


@router.get("/marketing/cac")
async def marketing_cac(components: str = "ads,partner", period: str = None,
                        date_from: str = None, date_to: str = None,
                        user: dict = Depends(require_permission("analytics", "view"))):
    """CAC dengan komponen yang BISA DIPILIH (transparan): ads, partner, opex."""
    rng = eng.resolve_range(period, date_from, date_to)
    return {"data": await eng.one("LED-08", org_id=user.get("org_id", ORG_ID),
                                  date_from=rng["from"], date_to=rng["to"],
                                  components=components)}


@router.get("/project/budget-vs-actual")
async def budget_vs_actual(project_id: str = None, drill: str = "category",
                           user: dict = Depends(require_permission("analytics", "view"))):
    return {"data": await eng.one("PRJ-03", org_id=user.get("org_id", ORG_ID),
                                  project_id=project_id, drill=drill)}


@router.get("/project/schedule-health")
async def schedule_health(project_id: str = None, period: str = None, date_from: str = None,
                          date_to: str = None,
                          user: dict = Depends(require_permission("analytics", "view"))):
    rng = eng.resolve_range(period, date_from, date_to)
    return {"data": await eng.dashboard("proyek", org_id=user.get("org_id", ORG_ID),
                                        date_from=rng["from"], date_to=rng["to"],
                                        project_id=project_id)}


@router.get("/users/daily")
async def users_daily(date: str = None, user_email: str = None, period: str = None,
                      date_from: str = None, date_to: str = None,
                      user: dict = Depends(require_permission("analytics", "view"))):
    """Dashboard Kinerja Tim. Peran ber-scope hanya melihat dirinya sendiri (dipaksa server)."""
    rng = eng.resolve_range(period, date or date_from, date or date_to)
    scoped = _scope(user)
    return {"data": await eng.dashboard("tim", org_id=user.get("org_id", ORG_ID),
                                        date_from=rng["from"], date_to=rng["to"],
                                        owner_email=scoped or user_email)}


@router.get("/users/leaderboard")
async def users_leaderboard(metric: str = "USR-02", period: str = None, date_from: str = None,
                            date_to: str = None,
                            user: dict = Depends(require_permission("analytics", "view"))):
    """Peringkat user pada satu metrik tim (rincian metrik = peringkatnya)."""
    if metric not in metrics.REGISTRY or metrics.REGISTRY[metric]["persona"] != "tim":
        raise HTTPException(status_code=400,
                            detail=f"Metrik '{metric}' bukan metrik kinerja tim.")
    rng = eng.resolve_range(period, date_from, date_to)
    return {"data": await eng.one(metric, org_id=user.get("org_id", ORG_ID),
                                  date_from=rng["from"], date_to=rng["to"],
                                  owner_email=_scope(user))}


@router.get("/snapshots")
async def snapshots(code: str = None, limit: int = 60,
                    user: dict = Depends(require_permission("analytics", "view"))):
    """Snapshot harian (percepatan). BUKAN sumber kebenaran — selalu bisa dihitung ulang."""
    org = user.get("org_id", ORG_ID)
    if code:
        return {"data": await eng.snapshot_series(code, org_id=org, limit=limit),
                "code": code}
    out = {}
    for c in sorted(eng.SNAPSHOT_CODES):
        rows = await eng.snapshot_series(c, org_id=org, limit=2)
        if rows:
            out[c] = rows[-1]
    return {"data": out, "codes": sorted(eng.SNAPSHOT_CODES)}


@router.post("/snapshots/rebuild")
async def rebuild_snapshots(date: str = None,
                            user: dict = Depends(require_permission("analytics", "manage"))):
    """Hitung ulang snapshot (INV-14: snapshot tidak boleh jadi kebenaran yang tak bisa diuji)."""
    out = await eng.rebuild_snapshots(org_id=user.get("org_id", ORG_ID), date=date,
                                      actor=user.get("email"))
    await audit_log(user, "rebuild", "metric_snapshots", out["date"], {"metrics": out["metrics"]})
    return {"data": out}


@router.get("/export/{metric}")
async def export_metric(metric: str, period: str = None, date_from: str = None,
                        date_to: str = None, project_id: str = None,
                        user: dict = Depends(require_permission("analytics", "view"))):
    """Ekspor CSV rincian satu metrik (Dok 31 §9.5). Baris = rincian drill-down-nya.

    Kode metrik ada di PATH, bukan query, karena ekspor tanpa menyebut metrik tidak punya
    arti — dan endpoint yang wajib menolak permintaan tanpa parameter akan selalu terlihat
    "bermasalah" di penyisiran endpoint (`audit_endpoint_sweep`). Menaruhnya di path membuat
    kontraknya jujur: tidak ada bentuk permintaan yang sah tanpa kode metrik.
    """
    if metric not in metrics.REGISTRY:
        raise HTTPException(status_code=400, detail=f"Metrik '{metric}' tidak ada di kamus.")
    rng = eng.resolve_range(period, date_from, date_to)
    res = await eng.one(metric, org_id=user.get("org_id", ORG_ID), date_from=rng["from"],
                        date_to=rng["to"], project_id=project_id, owner_email=_scope(user))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["metrik", res["code"], res["label"]])
    writer.writerow(["rentang", rng["from"], rng["to"]])
    writer.writerow(["kelengkapan", res["state"], "; ".join(res.get("missing") or [])])
    writer.writerow([])
    keys = sorted({k for row in res["breakdown"] for k in row})
    if keys:
        writer.writerow(keys)
        for row in res["breakdown"]:
            writer.writerow([row.get(k) for k in keys])
    else:
        writer.writerow(["nilai"])
        writer.writerow([res["value"] if res["value"] is not None else "belum ada data"])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition":
                             f'attachment; filename="{metric}-{rng["from"]}-{rng["to"]}.csv"'})


@router.get("/metric/{code}")
async def metric_detail(code: str, period: str = None, date_from: str = None,
                        date_to: str = None, project_id: str = None, dimension: str = None,
                        components: str = "ads,partner", group_by: str = None,
                        user: dict = Depends(require_permission("analytics", "view"))):
    """Satu metrik lengkap dengan rincian (dipakai drill-down & kamus metrik)."""
    if code not in metrics.REGISTRY:
        raise HTTPException(status_code=404, detail=f"Metrik '{code}' tidak ada di kamus.")
    rng = eng.resolve_range(period, date_from, date_to)
    extra = {k: v for k, v in (("dimension", dimension), ("group_by", group_by)) if v}
    return {"data": await eng.one(code, org_id=user.get("org_id", ORG_ID),
                                  date_from=rng["from"], date_to=rng["to"],
                                  project_id=project_id, owner_email=_scope(user),
                                  components=components, **extra)}
