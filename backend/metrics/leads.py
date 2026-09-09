"""metrics/leads.py — kamus metrik LEAD & LIFECYCLE (LED-01..15), spec Dok 31 §4.

Keputusan penting: **conversion & velocity dihitung dari `stage_history`, bukan dari status
akhir lead.** Menghitung dari status akhir akan menyembunyikan lead yang sempat masuk tahap
lanjut lalu turun lagi — dan itu justru kebocoran yang ingin dilihat manajer. Lead yang tidak
punya `stage_history` (data sebelum Fase 41) TIDAK dianggap "tidak pernah lolos tahap";
ia dihitung sebagai cakupan yang belum penuh dan dikatakan apa adanya.
"""
from datetime import datetime, timezone

import reference as ref
from db import ORG_ID, db
from metrics.base import bucket_days, day_range_query, div, median, month_of, pct, result

STAGE_ORDER = ("acquisition", "nurturing", "appointment", "booking", "won")
QUALIFIED_STAGES = ("appointment", "booking", "won")
WON_STAGES = ("booking", "won")
LOST_STAGES = ("lost",)
MIN_SOURCE_SAMPLE = 5   # BI-01: sumber dengan lead lebih sedikit tidak layak jadi "terbaik"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _leads(org_id: str, date_from: str = None, date_to: str = None,
                 owner_email: str = None) -> list:
    q = {"org_id": org_id, **day_range_query("created_at", date_from, date_to)}
    if owner_email:
        q["assigned_to"] = owner_email
    return await db.leads.find(q, {"_id": 0}).to_list(50000)


def _reached(lead: dict) -> set:
    """Tahap yang PERNAH dicapai lead (dari riwayat + tahap sekarang)."""
    reached = {lead.get("stage")} if lead.get("stage") else set()
    for h in lead.get("stage_history") or []:
        for key in ("from", "to", "stage"):
            if h.get(key):
                reached.add(h[key])
    return {s for s in reached if s}


def _label(group: str, value: str) -> str:
    opts = (ref.GROUPS.get(group) or {}).get("options") or []
    return next((o["label"] for o in opts if o["value"] == value), value or "(kosong)")


# ---------------------------------------------------------------------- LED-01
async def leads_in(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                   owner_email: str = None, group_by: str = "source", **_) -> dict:
    """Lead masuk = `count(leads)` pada periode, dipecah per sumber/kampanye/mitra/sales."""
    rows = await _leads(org_id, date_from, date_to, owner_email)
    field = {"source": "source", "campaign": "campaign", "partner": "partner_id",
             "sales": "assigned_to"}.get(group_by, "source")
    per_key, series = {}, {}
    for lead in rows:
        key = lead.get(field) or "(tanpa nilai)"
        label = _label("lead_source", key) if field == "source" else key
        row = per_key.setdefault(key, {"key": key, "label": label, "value": 0})
        row["value"] += 1
        bucket = month_of(lead.get("created_at"))
        series[bucket] = series.get(bucket, 0) + 1
    return result("LED-01", len(rows), label="Lead masuk", unit="count",
                  breakdown=sorted(per_key.values(), key=lambda r: -r["value"]),
                  series=[{"bucket": b, "value": v} for b, v in sorted(series.items())],
                  inputs={"group_by": group_by},
                  missing=["belum ada lead pada periode ini"] if not rows else None,
                  drill="/leads")


# ----------------------------------------------------------------- LED-02 / 03
async def stage_conversion(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                           owner_email: str = None, **_) -> dict:
    """Conversion per tahap = `masuk tahap n+1 / masuk tahap n` (kohor lead periode ini)."""
    rows = await _leads(org_id, date_from, date_to, owner_email)
    tanpa_riwayat = [r for r in rows if not r.get("stage_history")]
    counts = {stage: 0 for stage in STAGE_ORDER}
    for lead in rows:
        reached = _reached(lead)
        for stage in STAGE_ORDER:
            if stage in reached:
                counts[stage] += 1
    steps = []
    for i, stage in enumerate(STAGE_ORDER[:-1]):
        nxt = STAGE_ORDER[i + 1]
        steps.append({"key": f"{stage}->{nxt}",
                      "label": f"{_label('lead_stage', stage)} → {_label('lead_stage', nxt)}",
                      "from_count": counts[stage], "to_count": counts[nxt],
                      "value": pct(counts[nxt], counts[stage]),
                      "drop_pct": None if not counts[stage]
                      else round(100 - (counts[nxt] / counts[stage] * 100), 1)})
    overall = pct(counts["won"] + counts["booking"], counts["acquisition"]) \
        if counts["acquisition"] else None
    return result("LED-02", overall, label="Conversion per tahap", unit="pct",
                  breakdown=steps,
                  inputs={"lead": len(rows), "per_tahap": counts},
                  coverage={"rows": len(rows) - len(tanpa_riwayat), "total": len(rows)}
                  if tanpa_riwayat else None,
                  missing=[f"{len(tanpa_riwayat)} lead tanpa riwayat tahap — hanya tahap "
                           "terakhirnya yang diketahui"] if tanpa_riwayat else None,
                  drill="/leads")


async def stage_drop(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                     owner_email: str = None, **_) -> dict:
    """Churn per tahap = `1 - conversion`, plus lead yang HILANG di tahap itu."""
    conv = await stage_conversion(org_id=org_id, date_from=date_from, date_to=date_to,
                                  owner_email=owner_email)
    rows = await _leads(org_id, date_from, date_to, owner_email)
    lost_at = {}
    for lead in rows:
        if lead.get("stage") not in LOST_STAGES:
            continue
        hist = [h for h in (lead.get("stage_history") or []) if h.get("to") in LOST_STAGES]
        prev = (hist[-1].get("from") if hist else None) or "(tidak diketahui)"
        row = lost_at.setdefault(prev, {"key": prev, "label": _label("lead_stage", prev),
                                        "value": 0})
        row["value"] += 1
    worst = max((s for s in conv["breakdown"] if s["drop_pct"] is not None),
                key=lambda s: s["drop_pct"], default=None)
    return result("LED-03", worst["drop_pct"] if worst else None,
                  label="Churn tahap terburuk", unit="pct",
                  breakdown=[*conv["breakdown"]],
                  inputs={"tahap_terburuk": worst["key"] if worst else None,
                          "lost_per_tahap": {k: v["value"] for k, v in lost_at.items()}},
                  coverage=conv["coverage"], missing=conv["missing"] or None,
                  drill="/leads?stage=lost")


# ---------------------------------------------------------------------- LED-04
async def stage_velocity(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                         owner_email: str = None, **_) -> dict:
    """Velocity per tahap = median lama tinggal di tahap, dihitung dari selisih waktu antar
    entri `stage_history` (field ringkasan `stage_durations` TIDAK dipakai karena tidak
    pernah terisi — memakai field kosong akan menghasilkan 0 hari yang menyesatkan)."""
    rows = await _leads(org_id, date_from, date_to, owner_email)
    per_stage, dipakai = {}, 0
    for lead in rows:
        hist = sorted((lead.get("stage_history") or []), key=lambda h: h.get("at") or "")
        if not hist:
            continue
        dipakai += 1
        for i, entry in enumerate(hist):
            stage = entry.get("to")
            start = entry.get("at")
            end = hist[i + 1].get("at") if i + 1 < len(hist) else None
            if not (stage and start):
                continue
            finish = datetime.fromisoformat(end) if end else _now()
            hours = (finish - datetime.fromisoformat(start)).total_seconds() / 3600
            per_stage.setdefault(stage, []).append(round(hours / 24, 2))
    breakdown = [{"key": stage, "label": _label("lead_stage", stage),
                  "value": median(vals), "count": len(vals)}
                 for stage, vals in per_stage.items()]
    breakdown.sort(key=lambda r: -(r["value"] or 0))
    allv = [v for vals in per_stage.values() for v in vals]
    return result("LED-04", median(allv), label="Velocity tahap (median hari)", unit="days",
                  breakdown=breakdown, inputs={"lead_berriwayat": dipakai},
                  coverage={"rows": dipakai, "total": len(rows)} if dipakai != len(rows) else None,
                  missing=[f"{len(rows) - dipakai} lead tanpa riwayat tahap"]
                  if dipakai != len(rows) else None,
                  drill="/tasks?tab=aging")


# ---------------------------------------------------------------------- LED-05
async def aging_distribution(*, org_id: str = ORG_ID, owner_email: str = None, **_) -> dict:
    """Distribusi umur tahap lead AKTIF (ember sama dengan laporan Umur Tahap & SLA)."""
    q = {"org_id": org_id, "stage": {"$nin": ["won", "lost"]}}
    if owner_email:
        q["assigned_to"] = owner_email
    rows = await db.leads.find(q, {"_id": 0, "stage": 1, "stage_entered_at": 1,
                                   "stage_due_at": 1, "id": 1}).to_list(50000)
    buckets, tanpa = {}, 0
    for lead in rows:
        entered = lead.get("stage_entered_at")
        if not entered:
            tanpa += 1
            continue
        days = (_now() - datetime.fromisoformat(entered)).total_seconds() / 86400
        key = bucket_days(days)
        row = buckets.setdefault(key, {"key": key, "label": key, "value": 0})
        row["value"] += 1
    order = ["0-1 hari", "1-3 hari", "3-7 hari", ">7 hari"]
    breakdown = [buckets.get(k, {"key": k, "label": k, "value": 0}) for k in order]
    tua = sum(b["value"] for b in breakdown if b["key"] == ">7 hari")
    return result("LED-05", tua, label="Lead menganggur >7 hari", unit="count",
                  breakdown=breakdown, inputs={"lead_aktif": len(rows)},
                  coverage={"rows": len(rows) - tanpa, "total": len(rows)} if tanpa else None,
                  missing=[f"{tanpa} lead tanpa penanda masuk tahap"] if tanpa else None,
                  drill="/leads?sla=over")


# ---------------------------------------------------------------------- LED-06
async def speed_to_lead(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                        owner_email: str = None, **_) -> dict:
    """Speed-to-lead = median(`response_time_minutes`) + pangsa ≤ 15 menit."""
    rows = await _leads(org_id, date_from, date_to, owner_email)
    vals = [r["response_time_minutes"] for r in rows
            if r.get("response_time_minutes") is not None]
    fast = len([v for v in vals if v <= 15])
    return result("LED-06", median(vals), label="Speed-to-lead (median menit)", unit="count",
                  breakdown=[{"key": "<=15", "label": "Dibalas ≤ 15 menit", "value": fast},
                             {"key": ">15", "label": "Lebih dari 15 menit",
                              "value": len(vals) - fast}],
                  inputs={"lead": len(rows), "punya_waktu_respons": len(vals),
                          "pangsa_cepat_pct": pct(fast, len(vals))},
                  coverage={"rows": len(vals), "total": len(rows)} if vals else None,
                  missing=[f"{len(rows) - len(vals)} lead belum punya waktu respons tercatat"]
                  if len(vals) != len(rows) else None,
                  drill="/leads")


# ---------------------------------------------------------------------- LED-07
async def win_rate(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                   owner_email: str = None, **_) -> dict:
    """Win rate = `menang / (menang + hilang)` — lead yang masih berjalan tidak dihitung."""
    rows = await _leads(org_id, date_from, date_to, owner_email)
    won = len([r for r in rows if r.get("stage") in WON_STAGES])
    lost = len([r for r in rows if r.get("stage") in LOST_STAGES])
    return result("LED-07", pct(won, won + lost), label="Win rate", unit="pct",
                  breakdown=[{"key": "won", "label": "Menang/booking", "value": won},
                             {"key": "lost", "label": "Hilang", "value": lost},
                             {"key": "open", "label": "Masih berjalan",
                              "value": len(rows) - won - lost}],
                  inputs={"lead": len(rows)},
                  missing=["belum ada lead yang selesai (menang/hilang)"]
                  if not (won + lost) else None,
                  drill="/leads")


# ----------------------------------------------------------------- LED-08 / 09
async def cac(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
              components: str = "ads,partner", **_) -> dict:
    """CAC = `(biaya iklan + fee mitra disetujui + opex marketing) / jumlah menang`.

    Komponennya BISA DIPILIH dan setiap komponen dilaporkan terpisah supaya angkanya bisa
    diperdebatkan dengan data, bukan dengan asumsi. `opex` (biaya operasional marketing di
    luar iklan & fee) belum punya sumber data — bila diminta, ia dilaporkan sebagai bagian
    yang belum lengkap, BUKAN dianggap nol.
    """
    wanted = [c.strip() for c in (components or "").split(",") if c.strip()]
    spend = 0
    if "ads" in wanted:
        cursor = db.ad_spend.aggregate([
            {"$match": {"org_id": org_id, **day_range_query("date", date_from, date_to)}},
            {"$group": {"_id": None, "spend": {"$sum": "$spend"}}}])
        async for row in cursor:
            spend += int(row.get("spend") or 0)
    fee = 0
    if "partner" in wanted:
        rows = await db.marketing_fees.find(
            {"org_id": org_id, "status": {"$in": ["approved", "paid"]}},
            {"_id": 0, "amount": 1, "total": 1}).to_list(20000)
        fee = sum(int(r.get("total") or r.get("amount") or 0) for r in rows)
    missing = []
    if "opex" in wanted:
        missing.append("biaya operasional marketing (opex) belum punya sumber data — "
                       "tersedia setelah fase Target & Budget")
    leads_rows = await _leads(org_id, date_from, date_to)
    won = len([r for r in leads_rows if r.get("stage") in WON_STAGES])
    biaya = spend + fee
    if not biaya:
        missing.append("belum ada biaya (iklan/fee) pada periode ini")
    if not won:
        missing.append("belum ada lead menang pada periode ini")
    return result("LED-08", int(round(biaya / won)) if (biaya and won) else None,
                  label="CAC (biaya per akuisisi)", unit="idr",
                  breakdown=[{"key": "ads", "label": "Biaya iklan", "value": spend},
                             {"key": "partner", "label": "Fee mitra disetujui", "value": fee}],
                  inputs={"komponen": wanted, "biaya": biaya, "menang": won},
                  missing=missing or None, drill="/campaigns?hub=kinerja")


async def cpl(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None, **_) -> dict:
    """CPL = `biaya iklan / lead`; cost per qualified = `biaya iklan / lead terkualifikasi`."""
    cursor = db.ad_spend.aggregate([
        {"$match": {"org_id": org_id, **day_range_query("date", date_from, date_to)}},
        {"$group": {"_id": None, "spend": {"$sum": "$spend"}, "rows": {"$sum": 1}}}])
    spend, rows_count = 0, 0
    async for row in cursor:
        spend, rows_count = int(row.get("spend") or 0), int(row.get("rows") or 0)
    leads_rows = await _leads(org_id, date_from, date_to)
    qualified = len([r for r in leads_rows if _reached(r) & set(QUALIFIED_STAGES)])
    missing = []
    if not rows_count:
        missing.append("biaya iklan belum diinput untuk periode ini")
    if not leads_rows:
        missing.append("belum ada lead pada periode ini")
    return result("LED-09", int(round(spend / len(leads_rows))) if (spend and leads_rows) else None,
                  label="CPL (biaya per lead)", unit="idr",
                  breakdown=[{"key": "cpl", "label": "Per lead masuk",
                              "value": int(round(spend / len(leads_rows)))
                              if (spend and leads_rows) else None},
                             {"key": "cpql", "label": "Per lead terkualifikasi",
                              "value": int(round(spend / qualified)) if (spend and qualified)
                              else None}],
                  inputs={"biaya": spend, "lead": len(leads_rows), "terkualifikasi": qualified,
                          "baris_biaya": rows_count},
                  missing=missing or None, drill="/campaigns?hub=kinerja")


# ----------------------------------------------------------------- LED-10 / 11
async def lost_reasons(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                       **_) -> dict:
    """Pareto alasan hilang = `group by close_reason` pada lead berstatus hilang."""
    rows = await _leads(org_id, date_from, date_to)
    lost = [r for r in rows if r.get("stage") in LOST_STAGES]
    per_reason, tanpa = {}, 0
    for lead in lost:
        reason = lead.get("close_reason")
        if not reason:
            tanpa += 1
            continue
        row = per_reason.setdefault(reason, {"key": reason,
                                             "label": _label("lead_close_reason", reason),
                                             "value": 0})
        row["value"] += 1
    top = max(per_reason.values(), key=lambda r: r["value"], default=None)
    return result("LED-10", top["value"] if top else None, label="Alasan hilang teratas",
                  unit="count",
                  breakdown=sorted(per_reason.values(), key=lambda r: -r["value"]),
                  inputs={"lead_hilang": len(lost), "alasan_teratas": top["label"] if top else None},
                  coverage={"rows": len(lost) - tanpa, "total": len(lost)} if lost else None,
                  missing=[f"{tanpa} lead hilang tanpa alasan tercatat"] if tanpa else None,
                  drill="/leads?stage=lost")


async def reschedule_reasons(*, org_id: str = ORG_ID, **_) -> dict:
    """Alasan reschedule/batal survei = `group by reason_code` per peristiwa agenda.

    Peristiwa agenda (reschedule/batal beserta ALASAN berkode) belum direkam sistem: koleksi
    `appointments` hanya menyimpan keadaan terakhir. Karena itu metrik ini mengaku belum
    lengkap alih-alih mengarang pareto dari catatan bebas yang tidak seragam. Perekaman
    peristiwa + kosakata alasannya adalah pekerjaan fase Agenda & Survey V2.
    """
    total = await db.appointments.count_documents({"org_id": org_id})
    berubah = await db.appointments.count_documents(
        {"org_id": org_id, "status": {"$in": ["rescheduled", "cancelled"]}})
    return result("LED-11", None, label="Alasan reschedule survei", unit="count",
                  inputs={"agenda": total, "agenda_berubah_jadwal": berubah},
                  missing=["alasan reschedule/batal belum direkam berkode (agenda hanya "
                           "menyimpan keadaan terakhir) — tersedia pada fase Agenda & Survey V2"],
                  drill="/appointments")


# ---------------------------------------------------------------------- LED-12
async def demography(*, org_id: str = ORG_ID, dimension: str = "age", **_) -> dict:
    """Demografi lead per dimensi (usia/pekerjaan/penghasilan/domisili/tanggungan).

    Field `demography` belum diisi satu lead pun; menampilkan grafik kosong sebagai "0%"
    akan membuat orang menyimpulkan komposisi pembeli dari data yang tidak ada.
    """
    total = await db.leads.count_documents({"org_id": org_id})
    filled = await db.leads.count_documents({"org_id": org_id,
                                            f"demography.{dimension}": {"$nin": [None, ""]}})
    if not filled:
        return result("LED-12", None, label=f"Demografi lead ({dimension})", unit="count",
                      inputs={"lead": total, "terisi": 0},
                      missing=[f"field `demography.{dimension}` belum diisi pada satu lead pun"],
                      drill="/leads")
    rows = await db.leads.find({"org_id": org_id}, {"_id": 0, "demography": 1, "stage": 1}) \
        .to_list(50000)
    per_key = {}
    for lead in rows:
        val = (lead.get("demography") or {}).get(dimension)
        if val in (None, ""):
            continue
        row = per_key.setdefault(str(val), {"key": str(val), "label": str(val), "value": 0,
                                            "won": 0})
        row["value"] += 1
        row["won"] += 1 if lead.get("stage") in WON_STAGES else 0
    return result("LED-12", filled, label=f"Demografi lead ({dimension})", unit="count",
                  breakdown=sorted(per_key.values(), key=lambda r: -r["value"]),
                  inputs={"lead": total, "terisi": filled},
                  coverage={"rows": filled, "total": total} if filled != total else None,
                  missing=[f"{total - filled} lead tanpa data demografi"]
                  if filled != total else None, drill="/leads")


# ---------------------------------------------------------------------- LED-13
async def source_quality(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                         **_) -> dict:
    """Kualitas per sumber = funnel (masuk → terkualifikasi → menang) per `source`/mitra."""
    rows = await _leads(org_id, date_from, date_to)
    per_source = {}
    for lead in rows:
        key = lead.get("source") or "(tanpa sumber)"
        row = per_source.setdefault(key, {"key": key, "label": _label("lead_source", key),
                                          "value": 0, "qualified": 0, "won": 0, "lost": 0})
        row["value"] += 1
        reached = _reached(lead)
        row["qualified"] += 1 if reached & set(QUALIFIED_STAGES) else 0
        row["won"] += 1 if lead.get("stage") in WON_STAGES else 0
        row["lost"] += 1 if lead.get("stage") in LOST_STAGES else 0
    for row in per_source.values():
        # BI-02: definisi win rate SAMA dengan LED-07 = menang / (menang + hilang).
        row["win_pct"] = pct(row["won"], row["won"] + row["lost"])
        row["conversion_pct"] = pct(row["won"], row["value"])   # menang / semua lead (nama berbeda)
        row["qualified_pct"] = pct(row["qualified"], row["value"])
        # BI-01: sumber dengan sampel kecil tidak boleh memenangkan "terbaik".
        row["eligible"] = row["value"] >= MIN_SOURCE_SAMPLE
    best = max((r for r in per_source.values() if r["win_pct"] is not None and r["eligible"]),
               key=lambda r: (r["win_pct"], r["won"]), default=None)
    return result("LED-13", best["win_pct"] if best else None, label="Sumber lead terbaik",
                  unit="pct",
                  breakdown=sorted(per_source.values(), key=lambda r: -r["value"]),
                  inputs={"sumber_terbaik": best["label"] if best else None,
                          "lead": len(rows), "sampel_minimum": MIN_SOURCE_SAMPLE},
                  missing=(["belum ada lead pada periode ini"] if not rows else
                           [f"belum ada sumber dengan ≥{MIN_SOURCE_SAMPLE} lead"] if best is None else None),
                  coverage={"rows": sum(1 for r in per_source.values() if r["eligible"]),
                            "total": len(per_source)} if rows else None,
                  drill="/leads")


# ---------------------------------------------------------------------- LED-14
async def no_followup(*, org_id: str = ORG_ID, owner_email: str = None, **_) -> dict:
    """Lead tanpa tindak lanjut = tahap aktif DAN `stage_due_at` sudah lewat (SLA terlampaui)."""
    now = datetime.now(timezone.utc).isoformat()
    q = {"org_id": org_id, "stage": {"$nin": ["won", "lost"]},
         "stage_due_at": {"$ne": None, "$lt": now}}
    if owner_email:
        q["assigned_to"] = owner_email
    rows = await db.leads.find(q, {"_id": 0, "id": 1, "name": 1, "stage": 1,
                                   "assigned_to": 1, "stage_due_at": 1}).to_list(50000)
    per_owner = {}
    for lead in rows:
        key = lead.get("assigned_to") or "(belum ditugaskan)"
        row = per_owner.setdefault(key, {"key": key, "label": key, "value": 0})
        row["value"] += 1
    return result("LED-14", len(rows), label="Lead lewat SLA tanpa tindak lanjut", unit="count",
                  breakdown=sorted(per_owner.values(), key=lambda r: -r["value"]),
                  inputs={"diperiksa_pada": now}, drill="/leads?sla=over")


# ---------------------------------------------------------------------- LED-15
async def cohort(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                 **_) -> dict:
    """Kohor bulanan = matriks (bulan lead masuk) × (tahap tertinggi yang dicapai)."""
    rows = await _leads(org_id, date_from, date_to)
    matrix = {}
    for lead in rows:
        bucket = month_of(lead.get("created_at")) or "(tanpa tanggal)"
        cell = matrix.setdefault(bucket, {"key": bucket, "label": bucket, "value": 0,
                                          **{s: 0 for s in STAGE_ORDER}, "lost": 0})
        cell["value"] += 1
        reached = _reached(lead)
        for stage in STAGE_ORDER:
            if stage in reached:
                cell[stage] += 1
        cell["lost"] += 1 if lead.get("stage") in LOST_STAGES else 0
    return result("LED-15", len(matrix), label="Kohor bulanan lead", unit="count",
                  breakdown=[matrix[k] for k in sorted(matrix)],
                  inputs={"lead": len(rows), "bulan": len(matrix)},
                  missing=["belum ada lead pada periode ini"] if not rows else None,
                  drill="/leads")


METRICS = {
    "LED-01": {"fn": leads_in, "label": "Lead masuk", "unit": "count", "persona": "penjualan",
               "snapshot": True, "formula": "count(leads) per periode & sumber",
               "requires": ["leads"], "drill": "/leads"},
    "LED-02": {"fn": stage_conversion, "label": "Conversion per tahap", "unit": "pct",
               "persona": "penjualan", "snapshot": True,
               "formula": "masuk tahap n+1 / masuk tahap n (dari stage_history)",
               "requires": ["leads.stage_history"], "drill": "/leads"},
    "LED-03": {"fn": stage_drop, "label": "Churn tahap terburuk", "unit": "pct",
               "persona": "penjualan", "formula": "1 - conversion per tahap",
               "requires": ["leads.stage_history"], "drill": "/leads?stage=lost"},
    "LED-04": {"fn": stage_velocity, "label": "Velocity tahap (median hari)", "unit": "days",
               "persona": "penjualan", "snapshot": True,
               "formula": "median selisih waktu antar entri stage_history",
               "requires": ["leads.stage_history"], "drill": "/tasks?tab=aging"},
    "LED-05": {"fn": aging_distribution, "label": "Lead menganggur >7 hari", "unit": "count",
               "persona": "penjualan", "snapshot": True,
               "formula": "histogram umur tahap lead aktif", "requires": ["leads"],
               "drill": "/leads?sla=over"},
    "LED-06": {"fn": speed_to_lead, "label": "Speed-to-lead (median menit)", "unit": "count",
               "persona": "penjualan", "snapshot": True,
               "formula": "median(response_time_minutes) + pangsa ≤15 menit",
               "requires": ["leads.response_time_minutes"], "drill": "/leads"},
    "LED-07": {"fn": win_rate, "label": "Win rate", "unit": "pct", "persona": "penjualan",
               "snapshot": True, "formula": "menang / (menang + hilang)",
               "requires": ["leads"], "drill": "/leads"},
    "LED-08": {"fn": cac, "label": "CAC (biaya per akuisisi)", "unit": "idr",
               "persona": "marketing", "snapshot": True,
               "formula": "(biaya iklan + fee mitra disetujui [+ opex]) / menang",
               "requires": ["ad_spend", "marketing_fees"], "drill": "/campaigns?hub=kinerja"},
    "LED-09": {"fn": cpl, "label": "CPL (biaya per lead)", "unit": "idr",
               "persona": "marketing", "snapshot": True,
               "formula": "biaya iklan / lead (dan / lead terkualifikasi)",
               "requires": ["ad_spend", "leads"], "drill": "/campaigns?hub=kinerja"},
    "LED-10": {"fn": lost_reasons, "label": "Alasan hilang teratas", "unit": "count",
               "persona": "penjualan", "formula": "group by close_reason (lead hilang)",
               "requires": ["leads.close_reason"], "drill": "/leads?stage=lost"},
    "LED-11": {"fn": reschedule_reasons, "label": "Alasan reschedule survei", "unit": "count",
               "persona": "penjualan", "formula": "group by alasan reschedule/batal per agenda",
               "requires": ["appointments.reason_code (belum ada)"], "drill": "/appointments"},
    "LED-12": {"fn": demography, "label": "Demografi lead", "unit": "count",
               "persona": "penjualan", "formula": "distribusi demography.* × tahap",
               "requires": ["leads.demography"], "drill": "/leads"},
    "LED-13": {"fn": source_quality, "label": "Sumber lead terbaik", "unit": "pct",
               "persona": "penjualan", "snapshot": True,
               "formula": "win rate per source = menang / (menang + hilang), hanya source dengan ≥5 lead; "
                          "funnel masuk→terkualifikasi→menang",
               "requires": ["leads"], "drill": "/leads"},
    "LED-14": {"fn": no_followup, "label": "Lead lewat SLA tanpa tindak lanjut",
               "unit": "count", "persona": "penjualan", "snapshot": True,
               "formula": "count(lead aktif dengan stage_due_at < sekarang)",
               "requires": ["leads.stage_due_at"], "drill": "/leads?sla=over"},
    "LED-15": {"fn": cohort, "label": "Kohor bulanan lead", "unit": "count",
               "persona": "penjualan", "formula": "matriks bulan masuk × tahap tercapai",
               "requires": ["leads.stage_history"], "drill": "/leads"},
}
