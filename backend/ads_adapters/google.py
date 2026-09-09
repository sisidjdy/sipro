"""Adapter Google Ads — kontrak sama untuk live & simulasi.

Live memakai Google Ads REST (`searchStream` + GAQL). Tanpa kredensial lengkap, `mode()` =
"simulation" dan data diambil dari database (input manual/CSV). Biaya Google Ads dilaporkan
dalam `cost_micros` (1/1.000.000 mata uang) — konversi ke rupiah utuh dilakukan di sini,
bukan di layar, supaya semua pemakai melihat satuan yang sama.
"""
import logging
import os

import httpx

from db import db, ORG_ID

logger = logging.getLogger("sipro.ads.google")

PLATFORM = "google"
API = "https://googleads.googleapis.com/v18"
OAUTH = "https://oauth2.googleapis.com/token"
ENV = ("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET",
       "GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_CUSTOMER_ID")
TIMEOUT = 15.0


def missing_env() -> list:
    return [name for name in ENV if not os.environ.get(name)]


def mode() -> str:
    return "simulation" if missing_env() else "live"


def customer_id() -> str:
    return (os.environ.get("GOOGLE_ADS_CUSTOMER_ID") or "").replace("-", "")


async def _access_token() -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        res = await client.post(OAUTH, data={
            "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
            "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        })
    res.raise_for_status()
    return (res.json() or {}).get("access_token") or ""


async def probe() -> tuple:
    if mode() != "live":
        return None, "Mode simulasi: kredensial Google Ads belum lengkap."
    try:
        tok = await _access_token()
        if not tok:
            return False, "Google tidak mengembalikan access token (refresh token ditolak)."
        return True, f"OAuth berhasil untuk customer {customer_id()}."
    except httpx.HTTPStatusError as exc:
        return False, (f"Google menolak kredensial (HTTP {exc.response.status_code}): "
                       f"{exc.response.text[:160]}")
    except Exception as exc:  # noqa: BLE001
        return False, f"Tidak bisa menghubungi Google Ads API: {exc}"


async def _search(query: str) -> list:
    tok = await _access_token()
    headers = {"Authorization": f"Bearer {tok}",
               "developer-token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"]}
    url = f"{API}/customers/{customer_id()}/googleAds:searchStream"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        res = await client.post(url, headers=headers, json={"query": query})
    res.raise_for_status()
    out = []
    for chunk in res.json() or []:
        out.extend(chunk.get("results") or [])
    return out


async def list_campaigns(period: dict = None, *, org_id: str = ORG_ID) -> list:
    if mode() != "live":
        rows = await db.campaigns.find({"org_id": org_id, "platform": PLATFORM},
                                       {"_id": 0}).to_list(2000)
        return [{"external_id": r.get("external_id"), "name": r["name"],
                 "objective": r.get("objective"), "status": r.get("status"),
                 "budget_daily": r.get("budget_daily") or 0,
                 "budget_total": r.get("budget_total") or 0,
                 "start_date": r.get("start_date"), "end_date": r.get("end_date"),
                 "source": r.get("source") or "manual"} for r in rows]
    rows = await _search(
        "SELECT campaign.id, campaign.name, campaign.status, campaign.start_date, "
        "campaign.end_date, campaign_budget.amount_micros FROM campaign")
    out = []
    for r in rows:
        c = r.get("campaign") or {}
        budget = int(int((r.get("campaignBudget") or {}).get("amountMicros") or 0) / 1_000_000)
        out.append({"external_id": str(c.get("id")), "name": c.get("name"),
                    "objective": "leads", "status": (c.get("status") or "").lower(),
                    "budget_daily": budget, "budget_total": 0,
                    "start_date": c.get("startDate"), "end_date": c.get("endDate"),
                    "source": "api"})
    return out


async def daily_insights(period: dict = None, *, org_id: str = ORG_ID) -> list:
    period = period or {}
    if mode() != "live":
        query = {"org_id": org_id, "platform": PLATFORM}
        if period.get("from") or period.get("to"):
            cond = {}
            if period.get("from"):
                cond["$gte"] = period["from"]
            if period.get("to"):
                cond["$lte"] = period["to"]
            query["date"] = cond
        rows = await db.ad_spend.find(query, {"_id": 0}).to_list(5000)
        return [{"date": r["date"], "campaign_external_id": r.get("campaign_external_id"),
                 "campaign_name": r.get("campaign_name"), "adset_id": r.get("adset_id"),
                 "ad_id": r.get("ad_id"), "spend": r.get("spend") or 0,
                 "impressions": r.get("impressions"), "clicks": r.get("clicks"),
                 "leads_platform": r.get("leads_platform"),
                 "currency": r.get("currency") or "IDR",
                 "source": r.get("source") or "manual"} for r in rows]
    where = ""
    if period.get("from") and period.get("to"):
        where = f" WHERE segments.date BETWEEN '{period['from']}' AND '{period['to']}'"
    rows = await _search(
        "SELECT segments.date, campaign.id, campaign.name, ad_group.id, "
        "metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions "
        f"FROM ad_group{where}")
    out = []
    for r in rows:
        m = r.get("metrics") or {}
        out.append({
            "date": (r.get("segments") or {}).get("date"),
            "campaign_external_id": str((r.get("campaign") or {}).get("id") or ""),
            "campaign_name": (r.get("campaign") or {}).get("name"),
            "adset_id": str((r.get("adGroup") or {}).get("id") or ""), "ad_id": "",
            "spend": int(round(int(m.get("costMicros") or 0) / 1_000_000)),
            "impressions": int(m.get("impressions") or 0) or None,
            "clicks": int(m.get("clicks") or 0) or None,
            "leads_platform": int(float(m.get("conversions") or 0)) or None,
            "currency": "IDR", "source": "api",
        })
    return out
