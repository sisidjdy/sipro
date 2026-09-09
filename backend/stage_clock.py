"""stage_clock.py — Fase 41: JAM TAHAP (umur tahap + SLA) sebagai FIELD NYATA.

Tiga cacat NYATA yang ditutup modul ini (semuanya masih ada sesudah Fase 40):

  1. **Umur tahap dihitung ulang di setiap request.** `listing.attach_aging` menurunkan
     `stage_entered_at` dari `stage_history` pada setiap pembacaan daftar. Akibatnya angka
     itu TIDAK bisa difilter/diurutkan di database, tidak bisa diberi index, dan laporan
     "umur tahap" harus memindai seluruh riwayat setiap kali dibuka. Sekarang jam tahap
     disimpan sebagai field: `stage_entered_at`, `stage_sla_hours`, `stage_due_at`,
     `stage_due2_at` — sehingga "tampilkan yang lewat SLA" menjadi query, bukan loop Python.
  2. **Ambang SLA adalah angka mati di komponen frontend** (72 jam di daftar Lead, 48 di
     Tugas & Komplain, 168 di Deal, 336 di Pembeli, 720 di AR). Kebijakan tidak bisa diubah
     tanpa deploy, dan dua layar bisa memakai angka berbeda untuk hal yang sama. Sekarang
     SLA dibaca dari Pusat Konfigurasi (`settings_store`) per entitas & per tahap, lalu
     DIBAWA di dalam baris (`stage_sla_hours`) supaya UI tidak perlu tahu angkanya.
  3. **"Lewat SLA" tanpa dasar.** Bila ambangnya karangan komponen, kalimat "lewat SLA" di
     tabel adalah klaim tanpa dasar. Sekarang setiap baris menyertakan `sla_state`
     (`ok|over|over2|none`) yang lahir dari kebijakan tersimpan; tahap akhir (SLA 0) jujur
     dinyatakan `none` = tidak ada janji waktu, bukan "dalam SLA".

Cara jam tahap tetap benar:
  * `stamp()` dipanggil di pintu transisi (lead lifecycle, deal, tugas, komplain, dokumen, AR).
  * `reconcile()` = jaring pengaman untuk jalur penulisan mana pun yang belum lewat `stamp`
    (seed, impor, endpoint lama). Ia mendeteksi ketidaksesuaian `stage_clock_stage != tahap`
    dan mengisi dari BUKTI yang tercatat, sambil menuliskan asal buktinya (`stage_clock_source`)
    supaya tidak ada angka yang mengaku lebih pasti dari kenyataannya.
  * `resync()` dipanggil saat kebijakan SLA diubah — kalau tidak, setting hanya jadi hiasan
    karena baris lama masih memakai ambang lama.
"""
import logging

from pymongo import UpdateOne

import settings_store as cfg
from core_utils import now, now_iso
from db import db, ORG_ID
from listing import hours_since, parse_iso
from listing import stage_entered_at as derive_entered

logger = logging.getLogger("sipro.stage_clock")

# Nama field tersimpan — SATU nama untuk semua koleksi (walau field tahapnya berbeda:
# `stage` di lead, `status` di deal/tugas/komplain/AR/dokumen, `kyc_status` di pembeli),
# supaya UI, index, dan gate tidak perlu tahu kosakata masing-masing koleksi.
ENTERED = "stage_entered_at"
SLA = "stage_sla_hours"
DUE = "stage_due_at"
DUE2 = "stage_due2_at"
CLOCK_STAGE = "stage_clock_stage"
CLOCK_SRC = "stage_clock_source"
CLOCK_FIELDS = (ENTERED, SLA, DUE, DUE2, CLOCK_STAGE, CLOCK_SRC)

SLA_FILTERS = ("over", "over2", "ok", "none")
# Kolom sort tambahan untuk daftar (dipakai router lewat `SORTS`): mengurutkan
# `stage_entered_at` ASC = yang paling lama menganggur di tahapnya muncul lebih dulu.
SORTS = {"stage_entered_at": ENTERED, "stage_due_at": DUE, "stage_sla_hours": SLA}

ENTITIES = {
    "lead": {
        "label": "Lead", "collection": "leads", "stage_field": "stage",
        "history": "stage_history", "changed": "stage_changed_at",
        "sla_key": "lead.sla_hours", "vocab": "lead_stage",
        "list_path": "/leads", "filter_param": "stage",
    },
    "deal": {
        "label": "Deal & Unit", "collection": "deals", "stage_field": "status",
        "history": "status_history", "changed": None,
        "sla_key": "deal.sla_hours", "vocab": "deal_status",
        "list_path": "/customers?hub=deal", "filter_param": "status",
    },
    "task": {
        "label": "Tugas", "collection": "tasks", "stage_field": "status",
        "history": None, "changed": None,
        "sla_key": "task.sla_hours", "vocab": "task_status",
        "list_path": "/tasks", "filter_param": "status",
    },
    "complaint": {
        "label": "Komplain", "collection": "complaints", "stage_field": "status",
        "history": "status_history", "changed": None,
        "sla_key": "complaint.sla_hours", "vocab": "complaint_status",
        "list_path": "/complaints", "filter_param": "status",
    },
    "customer": {
        "label": "Pembeli", "collection": "customers", "stage_field": "kyc_status",
        "history": None, "changed": None,
        "sla_key": "customer.sla_hours", "vocab": "kyc_status",
        "list_path": "/customers?hub=pembeli", "filter_param": "kyc_status",
    },
    "ar_invoice": {
        "label": "Tagihan (AR)", "collection": "ar_invoices", "stage_field": "status",
        "history": None, "changed": None,
        "sla_key": "ar.sla_hours", "vocab": "ar_status",
        "list_path": "/finance?tab=ar", "filter_param": "status",
    },
    "document": {
        "label": "Dokumen", "collection": "documents", "stage_field": "status",
        "history": None, "changed": None,
        "sla_key": "document.sla_hours", "vocab": "document_status",
        "list_path": "/documents", "filter_param": "status",
    },
}


def spec(entity: str) -> dict:
    if entity not in ENTITIES:
        raise ValueError(f"Entitas umur tahap tidak dikenal: {entity}. "
                         f"Pilihan: {', '.join(ENTITIES)}")
    return ENTITIES[entity]


# ------------------------------------------------------------------ kebijakan SLA
async def policy(entity: str, *, org_id: str = ORG_ID, project_id: str = None) -> dict:
    """Ambang SLA per tahap dari Pusat Konfigurasi (SSOT), bukan angka mati di kode/UI."""
    raw = await cfg.get(spec(entity)["sla_key"], org_id=org_id, project_id=project_id)
    out = {}
    for key, value in (raw or {}).items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            logger.warning("Nilai SLA %s.%s bukan angka: %r (diabaikan)", entity, key, value)
    return out


def sla_for(pol: dict, stage) -> float:
    """Ambang tahap ini. 0/None = tahap akhir → TIDAK ADA janji waktu (bukan 'dalam SLA')."""
    value = (pol or {}).get(str(stage))
    if value is None:
        value = (pol or {}).get("default")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _plus(entered_iso, hours) -> str:
    if not entered_iso or not hours:
        return None
    base = parse_iso(entered_iso)
    if not base:
        return None
    from datetime import timedelta
    return (base + timedelta(hours=float(hours))).isoformat()


def clock_patch(stage, entered_iso, sla_hours, source="transition") -> dict:
    """Isi field jam tahap (murni — bisa diuji tanpa database)."""
    return {
        ENTERED: entered_iso, SLA: sla_hours,
        DUE: _plus(entered_iso, sla_hours),
        DUE2: _plus(entered_iso, sla_hours * 2 if sla_hours else None),
        CLOCK_STAGE: stage, CLOCK_SRC: source,
    }


async def patch_for(entity: str, stage, *, org_id: str = ORG_ID, project_id: str = None,
                    at: str = None, pol: dict = None, source: str = "transition") -> dict:
    pol = pol if pol is not None else await policy(entity, org_id=org_id, project_id=project_id)
    return clock_patch(stage, at or now_iso(), sla_for(pol, stage), source)


async def stamp(entity: str, doc_id: str, stage, *, org_id: str = ORG_ID,
                project_id: str = None, at: str = None, source: str = "transition") -> dict:
    """Setel jam tahap saat dokumen BARU MASUK sebuah tahap (dipanggil di pintu transisi)."""
    patch = await patch_for(entity, stage, org_id=org_id, project_id=project_id, at=at,
                            source=source)
    await db[spec(entity)["collection"]].update_one({"id": doc_id}, {"$set": patch})
    return patch


# ------------------------------------------------------------------ pembacaan
def state_of(row: dict, ref_iso: str = None) -> str:
    """`ok` | `over` | `over2` | `none` (tahap tanpa SLA). Perbandingan string ISO UTC."""
    ref = ref_iso or now_iso()
    if not row.get(SLA):
        return "none"
    if row.get(DUE2) and row[DUE2] < ref:
        return "over2"
    if row.get(DUE) and row[DUE] < ref:
        return "over"
    return "ok"


async def attach(rows: list, entity: str, *, org_id: str = ORG_ID, project_id: str = None,
                 pol: dict = None) -> list:
    """Lengkapi baris daftar: umur total, umur tahap, ambang SLA, keadaan SLA.

    Field umur (`age_hours`, `stage_age_hours`) tetap DITURUNKAN saat baca — memang harus,
    karena nilainya berubah setiap detik. Yang berubah pada Fase 41: acuannya adalah field
    TERSIMPAN `stage_entered_at`, bukan hasil pemindaian `stage_history` di setiap request.
    Baris lama yang belum tersentuh `reconcile()` tetap dilayani (turunan) dan ditandai
    `stage_clock_source="derived"` agar ketidakpastiannya terlihat, bukan disembunyikan.
    """
    rows = rows or []
    if not rows:
        return rows
    sp = spec(entity)
    pol = pol if pol is not None else await policy(entity, org_id=org_id, project_id=project_id)
    ref = now()
    ref_iso = ref.isoformat()
    for row in rows:
        stage = row.get(sp["stage_field"])
        entered = row.get(ENTERED)
        if not entered:
            entered = derive_entered(row, sp.get("history") or "stage_history", sp["stage_field"])
            row[CLOCK_SRC] = row.get(CLOCK_SRC) or "derived"
        sla_hours = row.get(SLA) if row.get(SLA) is not None else sla_for(pol, stage)
        row[ENTERED] = entered
        row[SLA] = sla_hours
        if not row.get(DUE):
            row[DUE] = _plus(entered, sla_hours)
            row[DUE2] = _plus(entered, sla_hours * 2 if sla_hours else None)
        row["age_hours"] = hours_since(row.get("created_at"), ref)
        row["stage_age_hours"] = hours_since(entered, ref)
        row["sla_state"] = state_of(row, ref_iso)
        age = row["stage_age_hours"]
        row["sla_over_hours"] = (round(age - sla_hours, 2)
                                 if sla_hours and age and age > sla_hours else 0)
    return rows


def apply_sla_filter(query: dict, entity: str, value) -> dict:
    """Filter "lewat SLA" DI DATABASE atas field tersimpan (dulu mustahil).

    Nilai tak dikenal membuat hasil KOSONG (pola `listing.apply_in`) supaya pemakai sadar
    filternya tidak berlaku, bukan diabaikan diam-diam.
    """
    v = str(value or "").strip().lower()
    if not v:
        return query
    spec(entity)
    if v not in SLA_FILTERS:
        query["id"] = {"$in": []}
        return query
    ref = now_iso()
    if v == "over":
        query[DUE] = {"$ne": None, "$lt": ref}
    elif v == "over2":
        query[DUE2] = {"$ne": None, "$lt": ref}
    elif v == "ok":
        query["$and"] = list(query.get("$and") or []) + [
            {SLA: {"$ne": None}}, {"$or": [{DUE: None}, {DUE: {"$gte": ref}}]}]
    else:
        query["$and"] = list(query.get("$and") or []) + [
            {"$or": [{SLA: None}, {SLA: {"$exists": False}}]}]
    return query


# ------------------------------------------------------------------ pemeliharaan
def _evidence(doc: dict, sp: dict) -> tuple:
    """Kapan dokumen ini masuk tahapnya SEKARANG — dari bukti tercatat, berurut kepercayaan."""
    changed = sp.get("changed")
    if changed and doc.get(changed):
        return doc[changed], "transition"
    stage = doc.get(sp["stage_field"])
    for entry in reversed(doc.get(sp.get("history") or "__none__") or []):
        if not isinstance(entry, dict):
            continue
        if entry.get("to") == stage or entry.get("stage") == stage:
            at = entry.get("at") or entry.get("created_at")
            if at:
                return at, "history"
    # Tanpa riwayat: `updated_at` adalah fakta terdekat yang tercatat (perubahan status
    # PASTI terjadi pada atau sebelum itu). Ditandai supaya tidak mengaku sebagai transisi.
    if doc.get("updated_at"):
        return doc["updated_at"], "reconcile:updated_at"
    return doc.get("created_at"), "reconcile:created_at"


async def reconcile(entity: str = None, *, org_id: str = ORG_ID, limit: int = 20000) -> dict:
    """Isi/perbaiki jam tahap untuk dokumen yang tahapnya berubah lewat jalur tanpa `stamp`."""
    out = {}
    for ent in ([entity] if entity else list(ENTITIES)):
        sp = spec(ent)
        col = db[sp["collection"]]
        pol = await policy(ent, org_id=org_id)
        ops = []
        cursor = col.find({"org_id": org_id,
                           "$expr": {"$ne": [f"${CLOCK_STAGE}", f"${sp['stage_field']}"]}},
                          {"_id": 0}).limit(limit)
        async for doc in cursor:
            stage = doc.get(sp["stage_field"])
            entered, src = _evidence(doc, sp)
            ops.append(UpdateOne({"id": doc["id"]},
                                 {"$set": clock_patch(stage, entered, sla_for(pol, stage), src)}))
        if ops:
            await col.bulk_write(ops, ordered=False)
        out[ent] = len(ops)
    return out


async def resync(entity: str = None, *, org_id: str = ORG_ID, limit: int = 50000) -> dict:
    """Terapkan kebijakan SLA TERBARU ke seluruh baris.

    Dipanggil setelah setting `*.sla_hours` diubah. Tanpa ini, ambang lama tetap menempel
    pada baris yang sudah ada dan Pusat Konfigurasi hanya jadi hiasan.
    """
    filled = await reconcile(entity, org_id=org_id)
    out = {}
    for ent in ([entity] if entity else list(ENTITIES)):
        sp = spec(ent)
        col = db[sp["collection"]]
        pol = await policy(ent, org_id=org_id)
        ops = []
        cursor = col.find({"org_id": org_id, ENTERED: {"$ne": None}},
                          {"_id": 0, "id": 1, sp["stage_field"]: 1, ENTERED: 1, SLA: 1,
                           DUE: 1, DUE2: 1, CLOCK_SRC: 1}).limit(limit)
        async for doc in cursor:
            stage = doc.get(sp["stage_field"])
            want = clock_patch(stage, doc[ENTERED], sla_for(pol, stage),
                               doc.get(CLOCK_SRC) or "resync")
            if any(doc.get(k) != want[k] for k in (SLA, DUE, DUE2)):
                ops.append(UpdateOne({"id": doc["id"]}, {"$set": want}))
        if ops:
            await col.bulk_write(ops, ordered=False)
        out[ent] = {"filled": filled.get(ent, 0), "resynced": len(ops)}
    return out


async def resync_for_setting(key: str, *, org_id: str = ORG_ID) -> dict:
    """Jembatan dari Pusat Konfigurasi: setting SLA mana → entitas mana yang harus disegarkan."""
    for ent, sp in ENTITIES.items():
        if sp["sla_key"] == key:
            return await resync(ent, org_id=org_id)
    return {}


# ------------------------------------------------------------------ laporan
def drill_for(entity: str, stage=None, sla: str = None) -> str:
    """Tautan daftar yang SUDAH terfilter — dibentuk backend supaya definisi angka =
    definisi filter (aturan Fase 40: KPI wajib bisa ditelusuri sampai barisnya)."""
    sp = spec(entity)
    path = sp["list_path"]
    parts = []
    if stage:
        parts.append(f"{sp['filter_param']}={stage}")
    if sla:
        parts.append(f"sla={sla}")
    if not parts:
        return path
    return path + ("&" if "?" in path else "?") + "&".join(parts)


async def aging_report(entity: str, *, org_id: str = ORG_ID, project_id: str = None,
                       query: dict = None) -> dict:
    """Umur tahap per tahap — DIHITUNG DI DATABASE atas field tersimpan.

    Sebelum Fase 41 laporan seperti ini hanya mungkin dengan menarik seluruh dokumen ke
    Python dan memindai `stage_history` baris demi baris (mahal & tidak bisa dipaginasi).
    """
    sp = spec(entity)
    pol = await policy(entity, org_id=org_id, project_id=project_id)
    ref_iso = now_iso()
    match = {"org_id": org_id, **(query or {})}
    if project_id:
        match["project_id"] = project_id
    pipeline = [
        {"$match": match},
        {"$addFields": {"_entered": {"$ifNull": [f"${ENTERED}", "$created_at"]}}},
        {"$addFields": {"_age": {"$dateDiff": {
            "startDate": {"$dateFromString": {"dateString": "$_entered", "onError": None,
                                              "onNull": None}},
            "endDate": "$$NOW", "unit": "minute"}}}},
        {"$group": {
            "_id": f"${sp['stage_field']}",
            "count": {"$sum": 1},
            "over_sla": {"$sum": {"$cond": [
                {"$and": [{"$ne": [f"${DUE}", None]}, {"$lt": [f"${DUE}", ref_iso]}]}, 1, 0]}},
            "over2_sla": {"$sum": {"$cond": [
                {"$and": [{"$ne": [f"${DUE2}", None]}, {"$lt": [f"${DUE2}", ref_iso]}]}, 1, 0]}},
            "avg_minutes": {"$avg": "$_age"},
            "max_minutes": {"$max": "$_age"},
            "p50": {"$percentile": {"input": "$_age", "p": [0.5], "method": "approximate"}},
            "p90": {"$percentile": {"input": "$_age", "p": [0.9], "method": "approximate"}},
            "oldest_entered_at": {"$min": "$_entered"},
            "clock_derived": {"$sum": {"$cond": [
                {"$eq": [{"$ifNull": [f"${ENTERED}", None]}, None]}, 1, 0]}},
        }},
        {"$sort": {"count": -1}},
    ]
    raw = await db[sp["collection"]].aggregate(pipeline).to_list(200)

    def _h(minutes):
        return round(float(minutes) / 60.0, 2) if minutes not in (None, "") else None

    def _p(value):
        if isinstance(value, list) and value:
            return _h(value[0])
        return _h(value)

    rows = []
    for r in raw:
        stage = r["_id"]
        rows.append({
            "stage": stage, "count": r["count"], "over_sla": r["over_sla"],
            "over2_sla": r["over2_sla"], "sla_hours": sla_for(pol, stage),
            "avg_stage_age_hours": _h(r.get("avg_minutes")),
            "p50_stage_age_hours": _p(r.get("p50")),
            "p90_stage_age_hours": _p(r.get("p90")),
            "max_stage_age_hours": _h(r.get("max_minutes")),
            "oldest_entered_at": r.get("oldest_entered_at"),
            "clock_derived": r.get("clock_derived", 0),
            "drill": drill_for(entity, stage),
            "drill_over": drill_for(entity, stage, "over") if sla_for(pol, stage) else None,
        })
    totals = {
        "count": sum(r["count"] for r in rows),
        "over_sla": sum(r["over_sla"] for r in rows),
        "over2_sla": sum(r["over2_sla"] for r in rows),
        "clock_derived": sum(r["clock_derived"] for r in rows),
        "drill_over": drill_for(entity, None, "over"),
    }
    return {"entity": entity, "label": sp["label"], "stage_field": sp["stage_field"],
            "vocab": sp["vocab"], "sla_key": sp["sla_key"], "policy": pol,
            "generated_at": ref_iso, "rows": rows, "totals": totals}
