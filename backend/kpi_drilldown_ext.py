"""Drill-down KPI Marketing (Kampanye & Biaya Iklan, Atribusi) dan Detail Proyek (Fase 93).

Angka-angka di sini dihitung dengan fungsi yang SAMA dengan laporannya (ads_report /
masterplan) supaya rincian selalu cocok dengan kartu."""
import ads_engine as eng
import ads_report as rep
import reference as ref
from db import db, ORG_ID

CAMPAIGN_HUB = "/campaigns?hub="


def _row(id_, title, subtitle="", amount=None, status=None, group=None, href=None, **extra):
    return {"id": id_, "title": title, "subtitle": subtitle, "amount": amount, "status": status,
            "status_group": group, "href": href, **extra}


def _dates(p, days):
    if p.get("date_from") and p.get("date_to"):
        return p["date_from"], p["date_to"]
    d0, d1 = eng.default_range(days)
    return p.get("date_from") or d0, p.get("date_to") or d1


async def _campaigns(org, p):
    q = {"org_id": org}
    for k in ("platform", "status"):
        if p.get(k):
            q[k] = p[k]
    if p.get("project_id"):
        q["project_ids"] = p["project_id"]
    if p.get("campaign_id"):
        q["id"] = p["campaign_id"]
    return await db.campaigns.find(q, {"_id": 0}).sort("name", 1).to_list(2000)


async def ads(user: dict, sub: str, p: dict):
    org = user.get("org_id", ORG_ID)
    d0, d1 = _dates(p, 90 if p.get("ctx") == "attribution" else 30)
    campaigns = await _campaigns(org, p)
    rng = f"date_from={d0}&date_to={d1}"
    if sub in ("campaigns", "spend", "impressions", "clicks", "leads_platform"):
        spend_map = await eng.campaign_spend_totals([c["id"] for c in campaigns], org_id=org, date_from=d0, date_to=d1)
        field = {"spend": "spend", "impressions": "impressions", "clicks": "clicks", "leads_platform": "leads_platform"}.get(sub)
        title = {"campaigns": "Kampanye dalam rentang", "spend": "Biaya iklan per kampanye",
                 "impressions": "Impresi per kampanye", "clicks": "Klik per kampanye",
                 "leads_platform": "Lead menurut platform, per kampanye"}[sub]
        rows = []
        for c in campaigns:
            sp = spend_map.get(c["id"]) or {"spend": 0, "impressions": 0, "clicks": 0, "leads_platform": 0, "days": [], "sources": []}
            amount = sp.get(field, 0) if field else None
            if field and not amount and sub != "campaigns":
                continue
            src = ", ".join(ref.label_of("ad_spend_source", s) for s in (sp.get("sources") or [])) or "biaya belum diinput"
            rows.append(_row(c["id"], c["name"], f"{ref.label_of('ad_platform', c.get('platform'))} · {len(sp.get('days') or [])} hari terisi · {src}",
                             amount=amount, status=c.get("status"), group="campaign_status",
                             href=f"{CAMPAIGN_HUB}biaya&campaign_id={c['id']}&{rng}",
                             unit="idr" if sub in ("spend", "campaigns") else "count"))
        rows.sort(key=lambda r: -(r["amount"] or 0))
        return title, f"{CAMPAIGN_HUB}{'kampanye' if sub == 'campaigns' else 'biaya'}&{rng}", rows, sub != "campaigns"
    # lead-lead di balik funnel: leads / hot / qualified / booked
    by_ext = {str(c["external_id"]).strip().lower(): c for c in campaigns if c.get("external_id")}
    by_name = {str(c["name"]).strip().lower(): c for c in campaigns}
    leads = await db.leads.find({"org_id": org, "created_at": {"$gte": d0, "$lte": f"{d1}T23:59:59.999999+00:00"}},
                                {"_id": 0, "id": 1, "name": 1, "phone": 1, "source": 1, "campaign": 1, "stage": 1,
                                 "score": 1, "score_band": 1, "attribution": 1, "assigned_to": 1}).sort("created_at", -1).to_list(20000)
    deals = await rep._deal_value_by_lead(org)
    matched_only = p.get("ctx") != "attribution"
    rows = []
    for l in leads:
        camp = rep.match_campaign(l, by_ext, by_name)
        if matched_only and not camp:
            continue
        if p.get("campaign_id") and (not camp or camp["id"] != p["campaign_id"]):
            continue
        if p.get("source") and l.get("source") != p["source"]:
            continue
        dv = deals.get(l["id"])
        booked = rep.lead_booked(l, dv)
        if sub == "hot" and l.get("score_band") != "hot":
            continue
        if sub == "qualified" and l.get("stage") not in rep.FUNNEL_QUALIFIED:
            continue
        if sub == "booked" and not booked:
            continue
        rows.append(_row(l["id"], l.get("name") or "-",
                         " · ".join(x for x in [ref.label_of("lead_source", l.get("source")) if l.get("source") else "",
                                                (camp["name"] if camp else (l.get("campaign") or "(tanpa kampanye)")),
                                                l.get("assigned_to") or ""] if x),
                         status=l.get("stage"), group="lead_stage", href=f"/leads/{l['id']}",
                         score=l.get("score"), score_band=l.get("score_band")))
    title = {"leads": "Lead dari kampanye", "hot": "Lead panas dari kampanye",
             "qualified": "Lead terkualifikasi (janji temu / booking / menang)", "booked": "Lead yang booking"}.get(sub, "Lead")
    stage_q = {"qualified": "&stage=appointment,booking,won", "booked": "&stage=booking,won", "hot": "&score_band=hot"}.get(sub, "")
    return title, f"/leads?created_from={d0}&created_to={d1}{stage_q}", rows, False


async def project(user: dict, sub: str, p: dict):
    org = user.get("org_id", ORG_ID)
    pid = p.get("project_id")
    q = {"org_id": org, "project_id": pid}
    statuses = {"available": ["available"], "held": ["reserved", "booked"],
                "sold": ["booked", "sold", "handed_over"], "value": None, "all": None}.get(sub)
    if statuses:
        q["status"] = {"$in": statuses}
    if sub == "progress":
        q["construction_status"] = {"$nin": [None, "not_started"]}
    units = await db.units.find(q, {"_id": 0}).sort("code", 1).to_list(5000)
    clusters = {c["id"]: c.get("name") for c in await db.clusters.find({"org_id": org, "project_id": pid}, {"_id": 0, "id": 1, "name": 1}).to_list(500)}
    title = {"available": "Unit tersedia", "held": "Unit dipegang / booking", "sold": "Unit terjual (kumulatif)",
             "value": "Nilai unit (harga jual)", "progress": "Progres konstruksi per unit", "all": "Semua unit"}.get(sub, "Unit")
    rows = []
    for u in units:
        prog = u.get("construction_progress")
        rows.append(_row(u["id"], u.get("code") or "-",
                         " · ".join(x for x in [clusters.get(u.get("cluster_id")) or "", u.get("type") or "",
                                                f"konstruksi {ref.label_of('construction_status', u.get('construction_status'))}" if u.get("construction_status") else "",
                                                f"progres {prog}%" if prog is not None else ""] if x),
                         amount=u.get("price") if sub in ("value", "sold", "held", "available", "all") else None,
                         status=u.get("status"), group="unit_status", href=f"/units/{u['id']}"))
    if sub == "progress":
        rows.sort(key=lambda r: r["subtitle"])
    href_all = f"/projects/{pid}?tab=units" + (f"&status={','.join(statuses)}" if statuses else "")
    return title, href_all, rows, sub != "progress"
