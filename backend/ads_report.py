"""ads_report.py — Fase 43: metrik pemasaran yang TIDAK BOLEH BERBOHONG.

Aturan kejujuran angka (spec `docs/v2/30_MARKETING_INTEGRATION_SPEC.md` §8, pelajaran
Fase 36/37):

1. **Biaya belum diinput ≠ biaya nol.** Bila satu kampanye belum punya baris `ad_spend`
   pada rentang yang dilihat, CPL/CAC/ROAS dikembalikan `null` dengan `cost_status="missing"`
   dan alasan berbahasa Indonesia. Menampilkan "CPL Rp 0" akan membuat kampanye termahal
   terlihat paling efisien.
2. **Biaya setengah terisi harus mengaku.** `cost_status="partial"` menyebutkan berapa hari
   dari rentang yang benar-benar punya angka biaya (`spend_days` vs `expected_days`), jadi
   pembaca tahu metriknya masih akan berubah.
3. **Sumber angka selalu diberi label** (`sources`: manual/csv/api). Angka yang diketik tangan
   tidak boleh tampil seolah tarikan API platform.
4. **Lead yang tidak cocok kampanye dihitung dan dilaporkan** (`unmatched_leads`), bukan
   dibuang diam-diam — tanpa itu total lead di layar ini akan berbeda dengan Pipeline Lead
   dan tidak ada yang tahu kenapa.
5. **Semua angka bisa direkonstruksi**: setiap baris membawa pembilang & penyebutnya
   (spend, leads, qualified, booked, revenue), sehingga CPL bisa dihitung ulang dengan tangan.
"""
import logging
import os
from datetime import datetime, timezone

import ads_engine as eng
import capi
import reference as ref
from core_utils import now_iso
from db import db, ORG_ID

logger = logging.getLogger("sipro.ads_report")

# Tahap lead yang dianggap lolos kualifikasi / sudah memesan. SATU definisi untuk seluruh
# aplikasi (dulu ditulis ulang di `omnichannel_router.attribution`, sehingga dua layar bisa
# menjawab "qualified" dengan angka berbeda).
FUNNEL_QUALIFIED = ("appointment", "booking", "won")
FUNNEL_BOOKED = ("booking", "won")
COST_NOTE_MISSING = "data biaya belum lengkap"

# Sumber lead yang MEMANG berbayar (peta ini milik `capi.PLATFORM_BY_SOURCE`, tidak ditulis
# ulang di sini). `whatsapp` sengaja TIDAK otomatis dianggap iklan: click-to-chat organik dan
# click-to-WhatsApp berbayar memakai sumber yang sama, jadi yang menentukan adalah ada/tidaknya
# atribusi kampanye pada leadnya.
PAID_SOURCES = ("meta_ads", "google_lead", "tiktok_ads")


def _label(group: str, value: str) -> str:
    try:
        return ref.label_of(group, value)
    except KeyError:
        return value


def compute_metrics(*, spend, leads, qualified, booked, revenue, impressions=None,
                    clicks=None, platform_leads=None, cost_status="complete") -> dict:
    """Metrik turunan. Metrik berbasis biaya = None bila biaya belum ada (bukan 0)."""
    has_cost = cost_status != "missing" and int(spend or 0) > 0
    out = {
        "ctr": round(clicks / impressions * 100, 2) if impressions and clicks else None,
        "cpc": int(round(spend / clicks)) if has_cost and clicks else None,
        "cpl": int(round(spend / leads)) if has_cost and leads else None,
        "cost_per_qualified": int(round(spend / qualified)) if has_cost and qualified else None,
        "cac": int(round(spend / booked)) if has_cost and booked else None,
        "roas": round(revenue / spend, 2) if has_cost and revenue else None,
        "qualified_rate": round(qualified / leads * 100, 1) if leads else None,
        "booking_rate": round(booked / leads * 100, 1) if leads else None,
        "lead_gap": (leads - platform_leads) if platform_leads is not None else None,
    }
    out["cost_note"] = None if has_cost else COST_NOTE_MISSING
    return out


def _expected_days(campaign: dict, date_from: str, date_to: str, today: str) -> int:
    """Jumlah hari yang SEHARUSNYA punya angka biaya: irisan rentang laporan, masa kampanye,
    dan hari yang sudah berjalan (hari depan tidak pernah dituntut)."""
    start = max(x for x in (date_from, campaign.get("start_date")) if x)
    end_candidates = [date_to, today]
    if campaign.get("end_date"):
        end_candidates.append(campaign["end_date"])
    end = min(x for x in end_candidates if x)
    if end < start:
        return 0
    d0 = datetime.fromisoformat(start).date()
    d1 = datetime.fromisoformat(end).date()
    return (d1 - d0).days + 1


def cost_status_of(*, spend_days: int, expected_days: int) -> str:
    if spend_days <= 0:
        return "missing"
    if expected_days and spend_days < expected_days:
        return "partial"
    return "complete"


# ----------------------------------------------------------------- pencocokan lead
def match_campaign(lead: dict, by_ext: dict, by_name: dict):
    """Kampanye pemilik lead: ID platform lebih dipercaya daripada nama."""
    attribution = lead.get("attribution") or {}
    ext = attribution.get("campaign_id")
    if ext:
        hit = by_ext.get(str(ext).strip().lower())
        if hit:
            return hit
    name = lead.get("campaign")
    if name:
        return by_name.get(str(name).strip().lower())
    return None


async def _lead_rows(org_id: str, date_from: str, date_to: str) -> list:
    q = {"org_id": org_id}
    if date_from or date_to:
        cond = {}
        if date_from:
            cond["$gte"] = date_from
        if date_to:
            cond["$lte"] = f"{date_to}T23:59:59.999999+00:00"
        q["created_at"] = cond
    return await db.leads.find(q, {
        "_id": 0, "id": 1, "source": 1, "campaign": 1, "stage": 1, "score_band": 1,
        "attribution": 1, "partner_id": 1, "created_at": 1,
    }).to_list(20000)


async def _deal_value_by_lead(org_id: str) -> dict:
    """{lead_id: {booked, revenue}} — pendapatan hanya dari deal yang benar-benar jadi."""
    out = {}
    async for d in db.deals.find({"org_id": org_id},
                                 {"_id": 0, "lead_id": 1, "status": 1, "price": 1}):
        lid = d.get("lead_id")
        if not lid:
            continue
        row = out.setdefault(lid, {"booked": 0, "revenue": 0})
        if d.get("status") in ("booked", "completed"):
            row["booked"] += 1
            row["revenue"] += int(d.get("price") or 0)
    return out


def lead_booked(lead: dict, dv: dict | None) -> bool:
    """SATU definisi "lead yang booking" untuk kartu funnel DAN drilldown-nya (BI-02).

    Satuannya LEAD (bukan jumlah deal): lead dihitung booking bila punya deal booked/selesai,
    atau tahapnya sudah booking/menang walau deal-nya masih reservasi. Sebelumnya kartu
    menjumlah `dv["booked"]` (deal) dan mengabaikan tahap lead bila deal ada tetapi belum
    booked, sedangkan drilldown menghitung lead — kartu 15 ≠ rincian 20.
    """
    return bool((dv and dv["booked"]) or (lead.get("stage") in FUNNEL_BOOKED))


# --------------------------------------------------------------- kinerja kampanye
async def campaign_performance(*, org_id: str = ORG_ID, date_from: str = None,
                               date_to: str = None, platform: str = None,
                               project_id: str = None, status: str = None) -> dict:
    """Kinerja per kampanye: biaya, lead, kualifikasi, booking, pendapatan, CPL/CAC/ROAS."""
    if not date_from or not date_to:
        date_from, date_to = eng.default_range(30)
    today = datetime.now(timezone.utc).date().isoformat()
    q = {"org_id": org_id}
    if platform:
        q["platform"] = platform
    if status:
        q["status"] = status
    if project_id:
        q["project_ids"] = project_id
    campaigns = await db.campaigns.find(q, {"_id": 0}).sort("name", 1).to_list(2000)
    spend_map = await eng.campaign_spend_totals([c["id"] for c in campaigns], org_id=org_id,
                                               date_from=date_from, date_to=date_to)
    by_ext = {str(c["external_id"]).strip().lower(): c for c in campaigns if c.get("external_id")}
    by_name = {str(c["name"]).strip().lower(): c for c in campaigns}
    leads = await _lead_rows(org_id, date_from, date_to)
    deals = await _deal_value_by_lead(org_id)
    funnel = {c["id"]: {"leads": 0, "hot": 0, "qualified": 0, "booked": 0, "revenue": 0}
              for c in campaigns}
    unmatched = {"leads": 0, "campaign_values": []}
    for lead in leads:
        camp = match_campaign(lead, by_ext, by_name)
        if not camp:
            if lead.get("campaign"):
                unmatched["leads"] += 1
                if lead["campaign"] not in unmatched["campaign_values"]:
                    unmatched["campaign_values"].append(lead["campaign"])
            continue
        f = funnel[camp["id"]]
        f["leads"] += 1
        if lead.get("score_band") == "hot":
            f["hot"] += 1
        if lead.get("stage") in FUNNEL_QUALIFIED:
            f["qualified"] += 1
        dv = deals.get(lead["id"])
        if dv:
            f["revenue"] += dv["revenue"]
        if lead_booked(lead, dv):
            f["booked"] += 1
    rows = []
    for c in campaigns:
        sp = spend_map.get(c["id"]) or {"spend": 0, "impressions": 0, "clicks": 0,
                                        "leads_platform": 0, "days": [], "sources": [],
                                        "rows": 0}
        f = funnel[c["id"]]
        expected = _expected_days(c, date_from, date_to, today)
        cstatus = cost_status_of(spend_days=len(sp["days"]), expected_days=expected)
        metrics = compute_metrics(
            spend=sp["spend"], leads=f["leads"], qualified=f["qualified"], booked=f["booked"],
            revenue=f["revenue"], impressions=sp["impressions"], clicks=sp["clicks"],
            platform_leads=sp["leads_platform"] or None, cost_status=cstatus)
        rows.append({
            "campaign_id": c["id"], "code": c.get("code"), "name": c["name"],
            "platform": c["platform"], "platform_label": _label("ad_platform", c["platform"]),
            "objective": c.get("objective"), "status": c.get("status"),
            "external_id": c.get("external_id"),
            "budget_daily": c.get("budget_daily") or 0, "budget_total": c.get("budget_total") or 0,
            "start_date": c.get("start_date"), "end_date": c.get("end_date"),
            "spend": sp["spend"], "impressions": sp["impressions"], "clicks": sp["clicks"],
            "leads_platform": sp["leads_platform"], "spend_rows": sp["rows"],
            "spend_days": len(sp["days"]), "expected_days": expected,
            "sources": sp["sources"], "cost_status": cstatus,
            "cost_status_label": _label("ads_cost_status", cstatus),
            "budget_used_pct": (round(sp["spend"] / c["budget_total"] * 100, 1)
                                if c.get("budget_total") else None),
            **f, **metrics,
        })
    totals = _totals(rows, date_from, date_to, today)
    return {"rows": rows, "totals": totals, "range": {"from": date_from, "to": date_to},
            "unmatched": unmatched}


def _totals(rows: list, date_from: str, date_to: str, today: str) -> dict:
    agg = {k: sum(int(r.get(k) or 0) for r in rows) for k in
           ("spend", "impressions", "clicks", "leads", "qualified", "booked", "revenue",
            "leads_platform")}
    missing = [r["name"] for r in rows if r["cost_status"] == "missing"]
    partial = [r["name"] for r in rows if r["cost_status"] == "partial"]
    status = "complete"
    if rows and len(missing) == len(rows):
        status = "missing"
    elif missing or partial:
        status = "partial"
    agg.update(compute_metrics(spend=agg["spend"], leads=agg["leads"], qualified=agg["qualified"],
                              booked=agg["booked"], revenue=agg["revenue"],
                              impressions=agg["impressions"], clicks=agg["clicks"],
                              platform_leads=agg["leads_platform"] or None, cost_status=status))
    agg["cost_status"] = status
    agg["cost_status_label"] = _label("ads_cost_status", status)
    agg["campaigns"] = len(rows)
    agg["campaigns_without_cost"] = len(missing)
    agg["campaigns_partial_cost"] = len(partial)
    return agg


# -------------------------------------------------------------------- atribusi
LEVEL_FIELD = {"campaign": None, "adset": "adset_id", "ad": "ad_id", "creative": "creative_id"}


async def attribution(*, org_id: str = ORG_ID, level: str = "campaign", date_from: str = None,
                      date_to: str = None) -> dict:
    """Funnel atribusi lead per tingkat (kampanye/adset/iklan/creative) + biaya bila ada.

    Tingkat adset/iklan memakai ID yang tercatat pada lead (`attribution.adset_id`, dst).
    Lead lama tanpa ID itu dikelompokkan sebagai "(tanpa ID)" — bukan disembunyikan.
    """
    if level not in ref.values("ads_attribution_level"):
        level = "campaign"
    if not date_from or not date_to:
        date_from, date_to = eng.default_range(90)
    campaigns = await db.campaigns.find({"org_id": org_id}, {"_id": 0}).to_list(2000)
    by_ext = {str(c["external_id"]).strip().lower(): c for c in campaigns if c.get("external_id")}
    by_name = {str(c["name"]).strip().lower(): c for c in campaigns}
    leads = await _lead_rows(org_id, date_from, date_to)
    deals = await _deal_value_by_lead(org_id)
    conv = await _conversions_by_key(org_id, date_from, date_to)
    groups = {}
    for lead in leads:
        camp = match_campaign(lead, by_ext, by_name)
        attr = lead.get("attribution") or {}
        sub = None
        if level != "campaign":
            sub = attr.get(LEVEL_FIELD[level]) or ""
        key = (lead.get("source") or "unknown", camp["id"] if camp else "",
               lead.get("campaign") or "", sub or "")
        g = groups.setdefault(key, {
            "source": key[0], "source_label": _label("lead_source", key[0]),
            "campaign_id": key[1] or None,
            "campaign": (camp["name"] if camp else (lead.get("campaign") or "(tanpa kampanye)")),
            "campaign_known": bool(camp), "level": level,
            "level_id": sub or None, "level_label": sub or "(tanpa ID)",
            "channel_group": channel_group_of(lead, camp),
            "leads": 0, "hot": 0, "qualified": 0, "booked": 0, "revenue": 0,
            "conversions": 0, "conversion_value": 0,
        })
        g["leads"] += 1
        if lead.get("score_band") == "hot":
            g["hot"] += 1
        if lead.get("stage") in FUNNEL_QUALIFIED:
            g["qualified"] += 1
        dv = deals.get(lead["id"])
        if dv:
            g["revenue"] += dv["revenue"]
        if lead_booked(lead, dv):
            g["booked"] += 1
        c = conv.get((lead.get("source") or "unknown", lead.get("campaign") or ""))
        if c:
            g["conversions"] = c["count"]
            g["conversion_value"] = c["value"]
    spend_map = await eng.campaign_spend_totals(
        [c["id"] for c in campaigns], org_id=org_id, date_from=date_from, date_to=date_to)
    rows = sorted(groups.values(), key=lambda r: (-r["leads"], r["campaign"]))
    for r in rows:
        sp = spend_map.get(r["campaign_id"]) if r["campaign_id"] else None
        # Biaya hanya ditempelkan pada tingkat kampanye. Membagi biaya kampanye ke adset
        # secara rata adalah karangan; kalau platform belum mengirim rinciannya, katakan
        # "belum ada rincian", jangan menebak.
        r["spend"] = sp["spend"] if (sp and level == "campaign") else None
        r["spend_note"] = None if r["spend"] is not None else (
            COST_NOTE_MISSING if level == "campaign" else "biaya per tingkat ini belum dirinci")
        r["cpl"] = int(round(r["spend"] / r["leads"])) if r["spend"] and r["leads"] else None
        r["conversion_pct"] = round(r["booked"] / r["leads"] * 100) if r["leads"] else 0
    totals = {k: sum(int(r.get(k) or 0) for r in rows)
              for k in ("leads", "hot", "qualified", "booked", "revenue", "conversions",
                        "conversion_value")}
    # Biaya kampanye dihitung SEKALI per kampanye — baris dikelompokkan per (sumber, kampanye)
    # sehingga satu kampanye bisa muncul di beberapa baris; menjumlahkan r["spend"] menggandakan.
    seen = {r["campaign_id"] for r in rows if r.get("spend") is not None and r.get("campaign_id")}
    totals["spend"] = sum(int((spend_map.get(cid) or {}).get("spend") or 0) for cid in seen)
    totals["cpl"] = (int(round(totals["spend"] / totals["leads"]))
                     if totals["spend"] and totals["leads"] else None)
    return {"rows": rows, "totals": totals, "level": level,
            "range": {"from": date_from, "to": date_to},
            "channel_mix": _channel_mix(rows)}


def channel_group_of(lead: dict, campaign: dict = None) -> str:
    """Kelompok kanal: iklan berbayar / mitra / organik (SSOT `ads_channel_group`)."""
    if lead.get("partner_id") or lead.get("source") == "partner":
        return "partner"
    if campaign or (lead.get("source") in PAID_SOURCES):
        return "ads"
    return "organic"


def _channel_mix(rows: list) -> list:
    out = {}
    for r in rows:
        g = out.setdefault(r["channel_group"], {
            "channel_group": r["channel_group"],
            "label": _label("ads_channel_group", r["channel_group"]),
            "leads": 0, "qualified": 0, "booked": 0, "revenue": 0, "spend": 0})
        for k in ("leads", "qualified", "booked", "revenue"):
            g[k] += int(r.get(k) or 0)
        g["spend"] += int(r.get("spend") or 0)
    for g in out.values():
        g["cpl"] = int(round(g["spend"] / g["leads"])) if g["spend"] and g["leads"] else None
        g["booking_rate"] = round(g["booked"] / g["leads"] * 100, 1) if g["leads"] else None
    order = ref.values("ads_channel_group")
    return sorted(out.values(), key=lambda g: order.index(g["channel_group"]))


async def _conversions_by_key(org_id: str, date_from: str, date_to: str) -> dict:
    q = {"org_id": org_id}
    if date_from:
        q["created_at"] = {"$gte": date_from}
    rows = await db.conversion_events.find(
        q, {"_id": 0, "source": 1, "campaign": 1, "value": 1}).to_list(20000)
    out = {}
    for r in rows:
        key = (r.get("source") or "unknown", r.get("campaign") or "")
        g = out.setdefault(key, {"count": 0, "value": 0})
        g["count"] += 1
        g["value"] += int(r.get("value") or 0)
    return out


# ------------------------------------------------------------------ CAPI & health
async def capi_summary(org_id: str = ORG_ID) -> dict:
    """Ringkasan event CAPI: per event, per transport, per status + kapan terakhir."""
    rows = await db.conversion_events.find(
        {"org_id": org_id},
        {"_id": 0, "event_name": 1, "transport": 1, "status": 1, "created_at": 1,
         "value": 1, "platform": 1}).to_list(20000)
    by_event, by_transport, by_status, by_platform = {}, {}, {}, {}
    for r in rows:
        by_event[r.get("event_name") or "?"] = by_event.get(r.get("event_name") or "?", 0) + 1
        by_transport[r.get("transport") or "?"] = by_transport.get(r.get("transport") or "?", 0) + 1
        by_status[r.get("status") or "?"] = by_status.get(r.get("status") or "?", 0) + 1
        by_platform[r.get("platform") or "?"] = by_platform.get(r.get("platform") or "?", 0) + 1
    last = max((r.get("created_at") or "" for r in rows), default=None)
    return {"total": len(rows), "by_event": by_event, "by_transport": by_transport,
            "by_status": by_status, "by_platform": by_platform, "last_event_at": last or None,
            "value_total": sum(int(r.get("value") or 0) for r in rows)}


async def integration_health(org_id: str = ORG_ID, *, probe: bool = False) -> dict:
    """Kesiapan integrasi per target. HANYA melaporkan "terisi/tidak" — nilai kredensial
    TIDAK pernah keluar dari server (spec §2)."""
    import ads_adapters as adapters
    rows = []
    for target in ref.values("integration_target"):
        spec = adapters.ENV_SPEC[target]
        filled = {name: bool(os.environ.get(name)) for name in spec["env"]}
        missing = [name for name, ok in filled.items() if not ok]
        mode = "simulation" if missing else "live"
        row = {
            "target": target, "label": _label("integration_target", target),
            "platform": spec.get("platform"), "mode": mode,
            "mode_label": _label("integration_mode", mode),
            "env": [{"name": n, "filled": ok} for n, ok in filled.items()],
            "missing_env": missing, "purpose": spec["purpose"],
            "fallback": spec["fallback"], "healthy": None, "message": None,
        }
        if mode == "live" and probe:
            adapter = adapters.get(spec.get("platform"))
            if adapter:
                ok, message = await adapter.probe()
                row["healthy"], row["message"] = ok, message
            else:
                row["healthy"] = None
                row["message"] = "Belum ada adapter yang bisa menguji kredensial ini."
        rows.append(row)
    last_sync = await db.campaigns.find_one({"org_id": org_id, "last_synced_at": {"$ne": None}},
                                           {"_id": 0, "last_synced_at": 1},
                                           sort=[("last_synced_at", -1)])
    spend_sources = await db.ad_spend.distinct("source", {"org_id": org_id})
    return {
        "rows": rows, "checked_at": now_iso(),
        "live_count": sum(1 for r in rows if r["mode"] == "live"),
        "simulation_count": sum(1 for r in rows if r["mode"] == "simulation"),
        "last_synced_at": (last_sync or {}).get("last_synced_at"),
        "spend_sources": sorted(s for s in spend_sources if s),
        "capi_platforms": sorted(set(capi.LIVE_ENV_BY_PLATFORM)),
    }
