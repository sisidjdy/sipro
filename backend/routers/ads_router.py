"""Kampanye & Biaya Iklan + Atribusi/CAPI (Fase 43) — `docs/v2/30_MARKETING_INTEGRATION_SPEC.md`.

Keputusan yang tercermin di kode ini:
  1. **Biaya iklan tidak pernah "kira-kira".** Semua angka masuk lewat `ads_engine` yang
     idempoten pada kunci natural, jadi laporan mingguan yang diunduh ulang tidak pernah
     melipatgandakan biaya.
  2. **Dry-run adalah bagian dari kontrak**, bukan fitur tambahan: `POST /ads/spend/import`
     default `dry_run=true` dan menyimpan laporan yang bisa dibuka ulang, sehingga yang
     dikomit adalah TEPAT yang sudah dilihat pemakai.
  3. **Mode simulasi mengatakan dirinya simulasi.** `POST /ads/sync` menolak dengan 400
     berbahasa Indonesia bila kredensial belum diisi — bukan mengembalikan sukses palsu.
  4. Urutan rute: semua path statis (`/spend/imports`, `/capi/...`, `/health`) didaftarkan
     SEBELUM path ber-parameter — pelajaran gate `verify_api_contract`.
  5. RBAC: `ads:view` melihat, `ads:create` mendaftarkan kampanye & mengisi biaya,
     `ads:update` mengubah kampanye & MENGOMIT impor, `ads:manage` menarik data platform &
     mengirim ulang event CAPI (aksi yang menyentuh sistem luar).
"""
import logging

import ads_adapters as adapters
import ads_engine as eng
import ads_report as rep
import capi
import listing as lst
import reference as ref
from core_utils import now_iso, parse_pagination, serialize_doc, today_iso_date
from db import db, ORG_ID
from fastapi import APIRouter, Depends, HTTPException
from models_p43 import AdsSync, CampaignCreate, CampaignUpdate, SpendEntry, SpendImport
from rbac import audit_log, require_permission

logger = logging.getLogger("sipro.ads_router")
router = APIRouter(prefix="/ads", tags=["ads"])

CAMPAIGN_SORTS = {"name": "name", "code": "code", "platform": "platform",
                  "status": "status", "objective": "objective", "start_date": "start_date",
                  "end_date": "end_date", "budget_total": "budget_total",
                  "created_at": "created_at", "updated_at": "updated_at"}
SPEND_SORTS = {"date": "date", "spend": "spend", "platform": "platform",
               "campaign_name": "campaign_name", "source": "source",
               "impressions": "impressions", "clicks": "clicks",
               "updated_at": "updated_at"}


def _range(date_from: str = None, date_to: str = None, days: int = 30) -> tuple:
    if date_from and date_to:
        return date_from, date_to
    d0, d1 = eng.default_range(days)
    return date_from or d0, date_to or d1


# =============================================================== master kampanye
@router.get("/campaigns")
async def list_campaigns(q: str = None, platform: str = None, status: str = None,
                         objective: str = None, project_id: str = None,
                         sort: str = None, direction: str = None,
                         date_from: str = None, date_to: str = None,
                         skip: int = 0, limit: int = 50,
                         user: dict = Depends(require_permission("ads", "view"))):
    """Daftar kampanye + biaya terpakai pada rentang (bawaan 30 hari terakhir)."""
    org = user.get("org_id", ORG_ID)
    skip, limit = parse_pagination(skip, limit)
    date_from, date_to = _range(date_from, date_to)
    query = {"org_id": org}
    lst.apply_in(query, "platform", platform, ref.values("ad_platform"))
    lst.apply_in(query, "status", status, ref.values("campaign_status"))
    lst.apply_in(query, "objective", objective, ref.values("campaign_objective"))
    if project_id:
        query["project_ids"] = project_id
    lst.apply_search(query, q, ("name", "code", "external_id", "audience_note"))
    total = await db.campaigns.count_documents(query)
    rows = await (db.campaigns.find(query, {"_id": 0})
                  .sort(lst.sort_spec(sort, direction, CAMPAIGN_SORTS, ("created_at", -1)))
                  .skip(skip).limit(limit).to_list(limit))
    spend = await eng.campaign_spend_totals([r["id"] for r in rows], org_id=org,
                                           date_from=date_from, date_to=date_to)
    for row in rows:
        sp = spend.get(row["id"]) or {}
        row["spend_range"] = sp.get("spend", 0)
        row["spend_days"] = len(sp.get("days") or [])
        row["spend_sources"] = sp.get("sources") or []
        row["budget_used_pct"] = (round(row["spend_range"] / row["budget_total"] * 100, 1)
                                  if row.get("budget_total") else None)
    counts = {}
    for st in ref.values("campaign_status"):
        counts[st] = await db.campaigns.count_documents({"org_id": org, "status": st})
    return {"data": serialize_doc(rows), "total": total, "counts": counts,
            "range": {"from": date_from, "to": date_to}}


@router.post("/campaigns")
async def create_campaign(payload: CampaignCreate,
                          user: dict = Depends(require_permission("ads", "create"))):
    org = user.get("org_id", ORG_ID)
    try:
        doc = await eng.create_campaign(payload.model_dump(exclude_none=True), org_id=org,
                                       actor=user.get("email"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await audit_log(user, "create", "campaigns", doc["id"],
                    {"name": doc["name"], "platform": doc["platform"]})
    return {"data": serialize_doc(doc)}


@router.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, payload: CampaignUpdate,
                          user: dict = Depends(require_permission("ads", "update"))):
    org = user.get("org_id", ORG_ID)
    try:
        doc = await eng.update_campaign(campaign_id, payload.model_dump(exclude_none=True),
                                      org_id=org, actor=user.get("email"))
    except ValueError as exc:
        code = 404 if "tidak ditemukan" in str(exc) else 400
        raise HTTPException(status_code=code, detail=str(exc))
    await audit_log(user, "update", "campaigns", campaign_id, {"status": doc.get("status")})
    return {"data": serialize_doc(doc)}


# ================================================================== biaya iklan
@router.get("/spend")
async def list_spend(date_from: str = None, date_to: str = None, platform: str = None,
                     campaign_id: str = None, source: str = None, period: str = "daily",
                     sort: str = None, direction: str = None, skip: int = 0, limit: int = 50,
                     user: dict = Depends(require_permission("ads", "view"))):
    """Baris biaya harian + deret agregasi (harian/mingguan/bulanan) pada satu rentang."""
    org = user.get("org_id", ORG_ID)
    skip, limit = parse_pagination(skip, limit)
    date_from, date_to = _range(date_from, date_to)
    if period not in ref.values("ads_period"):
        period = "daily"
    query = {"org_id": org}
    lst.apply_in(query, "platform", platform, ref.values("ad_platform"))
    lst.apply_in(query, "source", source, ref.values("ad_spend_source"))
    if campaign_id:
        query["campaign_id"] = campaign_id
    lst.apply_range(query, "date", date_from, date_to)
    query["date"] = {"$gte": date_from, "$lte": date_to}
    total = await db.ad_spend.count_documents(query)
    rows = await (db.ad_spend.find(query, {"_id": 0, "history": 0})
                  .sort(lst.sort_spec(sort, direction, SPEND_SORTS, ("date", -1)))
                  .skip(skip).limit(limit).to_list(limit))
    series = await eng.spend_series(org_id=org, date_from=date_from, date_to=date_to,
                                   period=period, platform=platform, campaign_id=campaign_id)
    campaigns = await db.campaigns.find({"org_id": org},
                                        {"_id": 0, "id": 1, "name": 1, "platform": 1,
                                         "status": 1, "external_id": 1}).sort("name", 1) \
        .to_list(2000)
    totals = {
        "spend": sum(b["spend"] for b in series),
        "impressions": sum(b["impressions"] for b in series),
        "clicks": sum(b["clicks"] for b in series),
        "leads_platform": sum(b["leads_platform"] for b in series),
        "days": sum(b["days"] for b in series), "rows": total,
        "sources": sorted({s for b in series for s in b["sources"]}),
    }
    return {"data": serialize_doc(rows), "total": total, "series": series, "totals": totals,
            "campaigns": serialize_doc(campaigns), "period": period,
            "range": {"from": date_from, "to": date_to}}


@router.post("/spend")
async def create_spend(payload: SpendEntry,
                       user: dict = Depends(require_permission("ads", "create"))):
    """Entri manual harian. Idempoten: mengirim tanggal yang sama = memperbarui, bukan
    menambah baris kedua (dengan jejak nilai lama)."""
    org = user.get("org_id", ORG_ID)
    try:
        status, doc = await eng.manual_entry(payload.model_dump(), org_id=org,
                                            actor=user.get("email"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await audit_log(user, status, "ad_spend", doc["id"],
                    {"date": doc["date"], "spend": doc["spend"]})
    return {"data": serialize_doc(doc), "result": status,
            "result_label": ref.label_of("ads_row_status",
                                         {"inserted": "new", "updated": "update"}
                                         .get(status, "unchanged"))}


@router.get("/spend/template")
async def spend_template(user: dict = Depends(require_permission("ads", "view"))):
    """Contoh berkas CSV: kolom wajib + opsional, dengan satu baris contoh yang sah."""
    org = user.get("org_id", ORG_ID)
    sample = await db.campaigns.find_one({"org_id": org}, {"_id": 0, "name": 1, "platform": 1,
                                                          "external_id": 1})
    header = ",".join(eng.CSV_COLUMNS)
    row = {
        "date": today_iso_date(), "platform": (sample or {}).get("platform") or "meta",
        "campaign_name": (sample or {}).get("name") or "Nama kampanye persis seperti terdaftar",
        "campaign_id": (sample or {}).get("external_id") or "", "spend": "1250000",
        "adset_name": "Ad set A", "adset_id": "", "ad_name": "", "ad_id": "",
        "impressions": "41000", "clicks": "820", "leads_platform": "7", "currency": "IDR",
    }
    csv_text = header + "\n" + ",".join(str(row.get(c, "")) for c in eng.CSV_COLUMNS) + "\n"
    # Profil pemetaan kolom yang pernah berhasil dipakai (per platform) supaya tim tidak
    # mengisi ulang pemetaan setiap bulan.
    profiles = await db.ads_import_profiles.find({"org_id": org}, {"_id": 0}).to_list(20)
    return {"data": {"columns": list(eng.CSV_COLUMNS), "required": list(eng.CSV_REQUIRED),
                     "optional": list(eng.CSV_OPTIONAL), "csv": csv_text,
                     "currency": eng.CURRENCY, "max_rows": eng.MAX_IMPORT_ROWS,
                     "profiles": serialize_doc(profiles)}}


@router.get("/spend/imports")
async def list_imports(status: str = None, skip: int = 0, limit: int = 20,
                       user: dict = Depends(require_permission("ads", "view"))):
    """Riwayat impor (tanpa daftar barisnya, supaya ringan)."""
    org = user.get("org_id", ORG_ID)
    skip, limit = parse_pagination(skip, limit)
    query = {"org_id": org}
    lst.apply_in(query, "status", status, ref.values("ads_import_status"))
    total = await db.ads_imports.count_documents(query)
    rows = await (db.ads_imports.find(query, {"_id": 0, "rows": 0})
                  .sort("created_at", -1).skip(skip).limit(limit).to_list(limit))
    return {"data": serialize_doc(rows), "total": total}


@router.post("/spend/import")
async def import_spend(payload: SpendImport,
                       user: dict = Depends(require_permission("ads", "create"))):
    """Impor CSV. `dry_run=true` (bawaan) hanya memvalidasi & menyimpan laporan pratinjau."""
    org = user.get("org_id", ORG_ID)
    doc = await eng.import_csv(payload.csv_text, org_id=org, actor=user.get("email"),
                               filename=payload.filename, mapping=payload.mapping,
                               dry_run=payload.dry_run)
    if not payload.dry_run and doc.get("status") == "committed":
        await audit_log(user, "import", "ad_spend", doc["id"],
                        {"file": doc.get("filename"), "applied": doc.get("applied")})
    return {"data": serialize_doc(doc)}


@router.post("/spend/import/{import_id}/commit")
async def commit_import(import_id: str,
                        user: dict = Depends(require_permission("ads", "update"))):
    """Simpan baris dari laporan pratinjau — yang dikomit TEPAT yang sudah dilihat pemakai."""
    org = user.get("org_id", ORG_ID)
    doc = await db.ads_imports.find_one({"id": import_id, "org_id": org}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Laporan impor tidak ditemukan.")
    if doc.get("status") == "failed":
        raise HTTPException(status_code=400,
                            detail=f"Berkas ini ditolak saat validasi: {doc.get('error')}")
    already = doc.get("status") == "committed"
    try:
        fresh = await eng.apply_import(doc, org_id=org, actor=user.get("email"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not already:
        await audit_log(user, "import_commit", "ad_spend", import_id,
                        {"applied": fresh.get("applied")})
    return {"data": serialize_doc(fresh), "already_committed": already}


@router.get("/spend/import/{import_id}")
async def get_import(import_id: str,
                     user: dict = Depends(require_permission("ads", "view"))):
    org = user.get("org_id", ORG_ID)
    doc = await db.ads_imports.find_one({"id": import_id, "org_id": org}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Laporan impor tidak ditemukan.")
    return {"data": serialize_doc(doc)}


# =========================================================== kinerja & atribusi
@router.get("/performance")
async def performance(date_from: str = None, date_to: str = None, platform: str = None,
                      project_id: str = None, status: str = None,
                      user: dict = Depends(require_permission("ads", "view"))):
    """CPL/CAC/ROAS per kampanye. Metrik biaya = null bila biayanya belum diinput."""
    org = user.get("org_id", ORG_ID)
    date_from, date_to = _range(date_from, date_to)
    data = await rep.campaign_performance(org_id=org, date_from=date_from, date_to=date_to,
                                          platform=platform, project_id=project_id,
                                          status=status)
    return {"data": data}


@router.get("/attribution")
async def attribution(level: str = "campaign", date_from: str = None, date_to: str = None,
                      user: dict = Depends(require_permission("ads", "view"))):
    """Funnel atribusi lead per kampanye/adset/iklan/creative + campuran kanal."""
    org = user.get("org_id", ORG_ID)
    date_from, date_to = _range(date_from, date_to, days=90)
    data = await rep.attribution(org_id=org, level=level, date_from=date_from,
                                 date_to=date_to)
    return {"data": data}


# ==================================================================== CAPI & mode
@router.get("/capi/summary")
async def capi_summary(user: dict = Depends(require_permission("ads", "view"))):
    org = user.get("org_id", ORG_ID)
    return {"data": await rep.capi_summary(org)}


@router.get("/capi/events")
async def capi_events(platform: str = None, event: str = None, status: str = None,
                      transport: str = None, skip: int = 0, limit: int = 50,
                      user: dict = Depends(require_permission("ads", "view"))):
    """Audit event konversi yang dikirim balik ke platform (termasuk hash identitas)."""
    org = user.get("org_id", ORG_ID)
    skip, limit = parse_pagination(skip, limit)
    query = {"org_id": org}
    lst.apply_in(query, "platform", platform)
    lst.apply_in(query, "event_name", event, ref.values("capi_event_name"))
    lst.apply_in(query, "status", status, ref.values("capi_status"))
    lst.apply_in(query, "transport", transport, ref.values("integration_mode"))
    total = await db.conversion_events.count_documents(query)
    rows = await (db.conversion_events.find(query, {"_id": 0})
                  .sort("created_at", -1).skip(skip).limit(limit).to_list(limit))
    for row in rows:
        ud = row.get("user_data") or {}
        # Hash tetap ditampilkan sebagian saja: cukup untuk membuktikan payload siap-live,
        # tanpa memindahkan seluruh hash ke layar.
        row["user_data_preview"] = {k: f"{v[:12]}…" for k, v in ud.items() if v}
        row.pop("user_data", None)
    return {"data": serialize_doc(rows), "total": total,
            "summary": await rep.capi_summary(org)}


@router.post("/capi/events/{event_row_id}/resend")
async def capi_resend(event_row_id: str,
                      user: dict = Depends(require_permission("ads", "manage"))):
    org = user.get("org_id", ORG_ID)
    try:
        doc = await capi.resend_conversion(event_row_id, org_id=org, actor=user.get("email"))
    except ValueError as exc:
        code = 404 if "tidak ditemukan" in str(exc) else 400
        raise HTTPException(status_code=code, detail=str(exc))
    await audit_log(user, "resend", "conversion_events", event_row_id,
                    {"status": doc.get("status")})
    return {"data": serialize_doc(doc)}


@router.get("/health")
async def health(probe: bool = False,
                 user: dict = Depends(require_permission("ads", "view"))):
    """Kesiapan integrasi per platform. `probe=true` benar-benar memanggil API platform
    (hanya berarti bila kredensial ada) supaya "live" tidak sekadar klaim."""
    org = user.get("org_id", ORG_ID)
    return {"data": await rep.integration_health(org, probe=probe)}


@router.post("/sync")
async def sync_platform(payload: AdsSync,
                        user: dict = Depends(require_permission("ads", "manage"))):
    """Tarik kampanye + biaya harian dari platform. Hanya berjalan bila kredensial ADA;
    di mode simulasi ini DITOLAK dengan alasan — bukan mengarang hasil sinkronisasi."""
    org = user.get("org_id", ORG_ID)
    adapter = adapters.get(payload.platform)
    if not adapter:
        raise HTTPException(status_code=400,
                            detail=f"Belum ada adapter tarik-data untuk platform "
                                   f"{ref.label_of('ad_platform', payload.platform)}. "
                                   "Biaya iklannya diinput manual atau lewat impor CSV.")
    if adapter.mode() != "live":
        missing = ", ".join(adapter.missing_env())
        raise HTTPException(status_code=400, detail=(
            f"{ref.label_of('ad_platform', payload.platform)} masih mode simulasi — "
            f"kredensial belum diisi ({missing}). Selama itu biaya iklan diisi manual atau "
            "impor CSV; tombol ini akan bekerja begitu kredensialnya dipasang."))
    date_from, date_to = _range(payload.date_from, payload.date_to, days=7)
    period = {"from": date_from, "to": date_to}
    try:
        remote_campaigns = await adapter.list_campaigns(period, org_id=org)
        insights = await adapter.daily_insights(period, org_id=org)
    except Exception as exc:  # noqa: BLE001 — kegagalan platform dilaporkan apa adanya
        raise HTTPException(status_code=502, detail=f"Platform menolak permintaan: {exc}")
    out = {"campaigns_new": 0, "campaigns_updated": 0, "spend_inserted": 0,
           "spend_updated": 0, "spend_unchanged": 0, "spend_rejected": []}
    index = await eng.campaign_index(org)
    for c in remote_campaigns:
        hit = eng.resolve_campaign(index, payload.platform, external_id=c.get("external_id"),
                                  name=c.get("name"))
        body = {**c, "platform": payload.platform, "source": "api",
                "last_synced_at": now_iso()}
        if hit:
            await eng.update_campaign(hit["id"], body, org_id=org, actor=user.get("email"))
            out["campaigns_updated"] += 1
        else:
            await eng.create_campaign(body, org_id=org, actor=user.get("email"))
            out["campaigns_new"] += 1
    index = await eng.campaign_index(org)
    for row in insights:
        camp = eng.resolve_campaign(index, payload.platform,
                                   external_id=row.get("campaign_external_id"),
                                   name=row.get("campaign_name"))
        if not camp:
            out["spend_rejected"].append(
                f"{row.get('date')} — kampanye '{row.get('campaign_name')}' tidak dikenal")
            continue
        if (row.get("currency") or "IDR").upper() != eng.CURRENCY:
            out["spend_rejected"].append(
                f"{row.get('date')} — mata uang {row.get('currency')} tidak didukung")
            continue
        status, _doc = await eng.upsert_spend({
            "platform": payload.platform, "campaign_id": camp["id"],
            "campaign_external_id": camp.get("external_id"), "campaign_name": camp["name"],
            "adset_id": row.get("adset_id") or "", "adset_name": row.get("adset_name"),
            "ad_id": row.get("ad_id") or "", "ad_name": row.get("ad_name"),
            "date": row.get("date"), "spend": int(row.get("spend") or 0),
            "impressions": row.get("impressions"), "clicks": row.get("clicks"),
            "leads_platform": row.get("leads_platform"), "currency": eng.CURRENCY,
        }, org_id=org, source="api", actor=f"sync:{user.get('email')}")
        out[f"spend_{status}"] += 1
    await audit_log(user, "sync", "ad_spend", payload.platform, out)
    return {"data": out, "range": period, "mode": adapter.mode()}
