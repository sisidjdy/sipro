"""Adapter Meta Ads — kontrak sama untuk live & simulasi (lihat `ads_adapters/__init__.py`).

Live memakai Graph API. Tanpa token, `mode()` = "simulation" dan data diambil dari database
(hasil input manual/CSV) — bukan angka karangan. Bila token DIISI tetapi salah, `probe()`
melaporkan kegagalan apa adanya (tidak pernah berpura-pura sukses).
"""
import logging
import os

import httpx

from db import db, ORG_ID

logger = logging.getLogger("sipro.ads.meta")

PLATFORM = "meta"
from meta_api import GRAPH_BASE as GRAPH  # noqa: E402 — satu konstanta versi (Fase 94B)
TOKEN_ENV = ("META_SYSTEM_USER_TOKEN", "META_PAGE_TOKEN")
ACCOUNT_ENV = "META_AD_ACCOUNT_ID"
TIMEOUT = 12.0


def token() -> str:
    for name in TOKEN_ENV:
        if os.environ.get(name):
            return os.environ[name]
    return ""


def account_id() -> str:
    raw = os.environ.get(ACCOUNT_ENV, "")
    return raw if raw.startswith("act_") or not raw else f"act_{raw}"


def mode() -> str:
    return "live" if token() and account_id() else "simulation"


def missing_env() -> list:
    out = []
    if not token():
        out.append(" / ".join(TOKEN_ENV))
    if not account_id():
        out.append(ACCOUNT_ENV)
    return out


async def probe() -> tuple:
    """-> (sehat, pesan). Dipakai halaman Status Integrasi saat mode live."""
    if mode() != "live":
        return None, "Mode simulasi: kredensial Meta belum diisi."
    url = f"{GRAPH}/{account_id()}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            res = await client.get(url, params={"fields": "name,account_status",
                                               "access_token": token()})
        if res.status_code == 200:
            name = (res.json() or {}).get("name") or account_id()
            return True, f"Terhubung ke akun iklan {name}."
        detail = ((res.json() or {}).get("error") or {}).get("message") or res.text[:160]
        return False, f"Meta menolak kredensial (HTTP {res.status_code}): {detail}"
    except Exception as exc:  # noqa: BLE001 — jaringan/DNS: laporkan apa adanya
        return False, f"Tidak bisa menghubungi Graph API: {exc}"


async def list_campaigns(period: dict = None, *, org_id: str = ORG_ID) -> list:
    """[CampaignDTO] = {external_id, name, objective, status, budget_daily, budget_total,
    start_date, end_date, source}."""
    if mode() != "live":
        rows = await db.campaigns.find({"org_id": org_id, "platform": PLATFORM},
                                       {"_id": 0}).to_list(2000)
        return [{"external_id": r.get("external_id"), "name": r["name"],
                 "objective": r.get("objective"), "status": r.get("status"),
                 "budget_daily": r.get("budget_daily") or 0,
                 "budget_total": r.get("budget_total") or 0,
                 "start_date": r.get("start_date"), "end_date": r.get("end_date"),
                 "source": r.get("source") or "manual"} for r in rows]
    url = f"{GRAPH}/{account_id()}/campaigns"
    fields = "id,name,objective,status,daily_budget,lifetime_budget,start_time,stop_time"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        res = await client.get(url, params={"fields": fields, "limit": 200,
                                           "access_token": token()})
    res.raise_for_status()
    out = []
    for r in (res.json() or {}).get("data") or []:
        out.append({
            "external_id": r.get("id"), "name": r.get("name"),
            "objective": (r.get("objective") or "").lower(), "status": (r.get("status") or "").lower(),
            "budget_daily": int(int(r.get("daily_budget") or 0) / 100),
            "budget_total": int(int(r.get("lifetime_budget") or 0) / 100),
            "start_date": (r.get("start_time") or "")[:10] or None,
            "end_date": (r.get("stop_time") or "")[:10] or None,
            "source": "api",
        })
    return out


async def daily_insights(period: dict = None, *, org_id: str = ORG_ID) -> list:
    """[SpendDTO] = {date, campaign_external_id, campaign_name, adset_id, ad_id, spend,
    impressions, clicks, leads_platform, currency, source}."""
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
    url = f"{GRAPH}/{account_id()}/insights"
    params = {
        "level": "ad", "time_increment": 1, "limit": 500, "access_token": token(),
        "fields": "date_start,campaign_id,campaign_name,adset_id,ad_id,spend,impressions,"
                  "clicks,actions,account_currency",
    }
    if period.get("from") and period.get("to"):
        params["time_range"] = f'{{"since":"{period["from"]}","until":"{period["to"]}"}}'
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        res = await client.get(url, params=params)
    res.raise_for_status()
    out = []
    for r in (res.json() or {}).get("data") or []:
        leads = None
        for act in r.get("actions") or []:
            if act.get("action_type") in ("lead", "onsite_conversion.lead_grouped"):
                leads = int(float(act.get("value") or 0))
        out.append({
            "date": r.get("date_start"), "campaign_external_id": r.get("campaign_id"),
            "campaign_name": r.get("campaign_name"), "adset_id": r.get("adset_id"),
            "ad_id": r.get("ad_id"), "spend": int(round(float(r.get("spend") or 0))),
            "impressions": int(r.get("impressions") or 0) or None,
            "clicks": int(r.get("clicks") or 0) or None, "leads_platform": leads,
            "currency": (r.get("account_currency") or "IDR").upper(), "source": "api",
        })
    return out
