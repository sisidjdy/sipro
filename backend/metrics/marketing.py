"""metrics/marketing.py — kamus metrik MARKETING (MKT-01..05), spec Dok 31 §2 (persona DM).

Modul ini SENGAJA TIDAK menghitung ulang CPL/CAC/ROAS-nya sendiri: ia memanggil
`ads_report.campaign_performance` / `attribution` / `capi_summary` yang sudah dipakai halaman
"Kampanye & Biaya Iklan". Kalau dihitung ulang di sini, dua layar akan mulai berbeda — tepat
penyakit yang lapisan metrik ini seharusnya menyembuhkan (dan gate `verify_analytics.py`
membuktikan angkanya identik dengan `/api/ads/performance`).
"""
import ads_report as rep
from db import ORG_ID, db
from metrics.base import pct, result


async def spend_total(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                      **_) -> dict:
    """Biaya iklan periode = `Σ ad_spend.spend`, dengan status kelengkapan per kampanye."""
    data = await rep.campaign_performance(org_id=org_id, date_from=date_from, date_to=date_to)
    totals, rows = data["totals"], data["rows"]
    tanpa_biaya = [r["name"] for r in rows if r["cost_status"] == "missing"]
    return result("MKT-01", totals["spend"], label="Biaya iklan", unit="idr",
                  breakdown=[{"key": r["campaign_id"], "label": r["name"], "value": r["spend"],
                             "cost_status": r["cost_status"], "platform": r["platform_label"]}
                             for r in rows],
                  inputs={"kampanye": totals["campaigns"],
                          "kampanye_tanpa_biaya": totals["campaigns_without_cost"],
                          "rentang": data["range"]},
                  coverage={"rows": totals["campaigns"] - len(tanpa_biaya),
                            "total": totals["campaigns"]} if tanpa_biaya else None,
                  missing=[f"{len(tanpa_biaya)} kampanye belum punya biaya pada rentang ini"]
                  if tanpa_biaya else None,
                  drill="/campaigns?hub=biaya")


async def campaign_efficiency(*, org_id: str = ORG_ID, date_from: str = None,
                              date_to: str = None, **_) -> dict:
    """Efisiensi kampanye: CPL & conversion per kampanye (untuk grafik sebar CPL vs konversi).

    Kampanye yang biayanya belum diinput ikut dikirim dengan `cpl: null` supaya tidak hilang
    dari layar — hilangnya kampanye dari grafik akan dibaca sebagai "tidak ada kampanye itu".
    """
    data = await rep.campaign_performance(org_id=org_id, date_from=date_from, date_to=date_to)
    rows = data["rows"]
    breakdown = [{"key": r["campaign_id"], "label": r["name"], "value": r["cpl"],
                  "spend": r["spend"], "leads": r["leads"], "booked": r["booked"],
                  "booking_rate": r["booking_rate"], "roas": r["roas"],
                  "cost_status": r["cost_status"], "platform": r["platform_label"]}
                 for r in rows]
    berbiaya = [r for r in rows if r["cpl"] is not None]
    best = min(berbiaya, key=lambda r: r["cpl"], default=None)
    return result("MKT-02", best["cpl"] if best else None,
                  label="CPL kampanye terbaik", unit="idr", breakdown=breakdown,
                  inputs={"kampanye_terbaik": best["name"] if best else None,
                          "kampanye_berbiaya": len(berbiaya), "kampanye": len(rows)},
                  coverage={"rows": len(berbiaya), "total": len(rows)}
                  if berbiaya and len(berbiaya) != len(rows) else None,
                  missing=["belum ada kampanye dengan biaya & lead pada rentang ini"]
                  if not berbiaya else None,
                  drill="/campaigns?hub=kinerja")


async def roas(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None, **_) -> dict:
    """ROAS = `nilai deal dari lead kampanye / biaya iklan` (dari laporan kinerja kampanye)."""
    data = await rep.campaign_performance(org_id=org_id, date_from=date_from, date_to=date_to)
    totals = data["totals"]
    missing = []
    if totals["cost_status"] != "complete":
        missing.append("biaya iklan belum lengkap untuk seluruh kampanye pada rentang ini")
    if not totals["revenue"]:
        missing.append("belum ada nilai deal dari lead kampanye pada rentang ini")
    return result("MKT-03", totals.get("roas"), label="ROAS", unit="ratio",
                  breakdown=[{"key": r["campaign_id"], "label": r["name"], "value": r["roas"],
                             "revenue": r["revenue"], "spend": r["spend"],
                             "cost_status": r["cost_status"]} for r in data["rows"]],
                  inputs={"biaya": totals["spend"], "pendapatan": totals["revenue"],
                          "status_biaya": totals["cost_status"]},
                  coverage={"rows": totals["campaigns"] - totals["campaigns_without_cost"],
                            "total": totals["campaigns"]} if totals.get("roas") is not None
                  else None,
                  missing=missing or None, drill="/campaigns?hub=kinerja")


async def channel_mix(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                      **_) -> dict:
    """Campuran kanal: iklan berbayar vs mitra vs organik (lead, booking, biaya, CPL)."""
    data = await rep.attribution(org_id=org_id, level="campaign", date_from=date_from,
                                 date_to=date_to)
    mix = data["channel_mix"]
    total_leads = data["totals"]["leads"]
    for row in mix:
        row["key"] = row["channel_group"]
        row["value"] = row["leads"]
        row["share_pct"] = pct(row["leads"], total_leads)
    return result("MKT-04", len(mix), label="Campuran kanal lead", unit="count",
                  breakdown=mix,
                  inputs={"lead": total_leads, "rentang": data["range"]},
                  missing=["belum ada lead pada rentang ini"] if not total_leads else None,
                  drill="/attribution?hub=funnel")


async def capi_health(*, org_id: str = ORG_ID, **_) -> dict:
    """Kesehatan umpan balik konversi (CAPI): jumlah event per status & transport.

    Ini metrik KEJUJURAN INTEGRASI: selama kredensial belum dipasang, seluruh event berstatus
    `simulated` — dan itu harus terbaca di dashboard, bukan tampak seperti "terkirim".
    """
    summary = await rep.capi_summary(org_id)
    total = summary["total"]
    terkirim = summary["by_status"].get("sent", 0)
    simulasi = summary["by_status"].get("simulated", 0)
    return result("MKT-05", total, label="Event konversi (CAPI)", unit="count",
                  breakdown=[{"key": k, "label": k, "value": v}
                             for k, v in sorted(summary["by_event"].items())],
                  inputs={"terkirim": terkirim, "simulasi": simulasi,
                          "per_transport": summary["by_transport"],
                          "terakhir": summary["last_event_at"]},
                  coverage={"rows": terkirim, "total": total} if total else None,
                  missing=["semua event masih mode simulasi — kredensial platform belum diisi"]
                  if total and not terkirim else
                  (["belum ada event konversi tercatat"] if not total else None),
                  drill="/attribution?hub=capi")


METRICS = {
    "MKT-01": {"fn": spend_total, "label": "Biaya iklan", "unit": "idr",
               "persona": "marketing", "snapshot": True,
               "formula": "Σ ad_spend.spend (via laporan kinerja kampanye)",
               "requires": ["ad_spend", "campaigns"], "drill": "/campaigns?hub=biaya"},
    "MKT-02": {"fn": campaign_efficiency, "label": "CPL kampanye terbaik", "unit": "idr",
               "persona": "marketing", "snapshot": True,
               "formula": "min(CPL) antar kampanye; rincian = CPL & konversi per kampanye",
               "requires": ["ad_spend", "leads"], "drill": "/campaigns?hub=kinerja"},
    "MKT-03": {"fn": roas, "label": "ROAS", "unit": "ratio", "persona": "marketing",
               "snapshot": True, "formula": "nilai deal dari lead kampanye / biaya iklan",
               "requires": ["ad_spend", "deals"], "drill": "/campaigns?hub=kinerja"},
    "MKT-04": {"fn": channel_mix, "label": "Campuran kanal lead", "unit": "count",
               "persona": "marketing", "snapshot": True,
               "formula": "lead per kelompok kanal (ads/mitra/organik)",
               "requires": ["leads", "campaigns"], "drill": "/attribution?hub=funnel"},
    "MKT-05": {"fn": capi_health, "label": "Event konversi (CAPI)", "unit": "count",
               "persona": "marketing", "formula": "count(conversion_events) per status/transport",
               "requires": ["conversion_events"], "drill": "/attribution?hub=capi"},
}
