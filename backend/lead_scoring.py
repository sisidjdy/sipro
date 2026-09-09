"""SKOR LEAD BERBASIS EVENT TERKONFIGURASI (Fase 88B/89).

Skor = penjumlahan EVENT yang terjadi pada lead. Daftar event, poinnya (+/−), parameter
(jendela hari, batas, ambang), dan status aktif semuanya diatur admin di Pusat Konfigurasi
(`lead.score.events`). Event SISTEM dideteksi otomatis dari data yang sudah ditulis mesin lain
(aktivitas, agenda, pesan WA masuk, disposisi, tahap); event KUSTOM dibuat admin dan dicatat
sales dari kartu skor (mis. "Hadir open house" +10). `compute()` murni & sinkron — mengembalikan
rincian per event supaya layar bisa menjawab "kenapa skornya begini".
"""
import logging
from datetime import datetime, timedelta, timezone

import reference as ref
import settings_store as cfg
from core_utils import now_iso
from db import ORG_ID, db

logger = logging.getLogger("sipro.lead_score")

OPEN_STAGES_EXCLUDED = ("won", "lost", "recycle")
DISPOSITION_EVENT = {"positive": "disposition_positive", "negative": "disposition_negative",
                     "no_response": "disposition_no_response"}


def _e(key, label, points, desc, **params):
    return {"key": key, "label": label, "points": points, "active": True, "kind": "system",
            "desc": desc, "params": params}


# Event bawaan. `params` menentukan cara hitung: per_unit×jumlah dibatasi `cap` dalam `window_days`;
# `idle` memakai threshold_days + per minggu. Event tanpa params = poin tetap sekali.
DEFAULT_EVENTS: list = [
    _e("base", "Skor dasar", 30, "Titik awal setiap lead."),
    _e("source", "Sumber lead", 0, "Poin menurut sumber (SSOT reference.SOURCE_SCORE; kolom poin diabaikan)."),
    _e("new_24h", "Lead baru (< 24 jam)", 10, "Lead yang baru masuk dianggap paling hangat."),
    _e("first_contact", "Sudah dihubungi (kontak pertama)", 10, "first_contact_at terisi."),
    _e("stage_nurturing", "Tahap: nurturing", 10, "Lead sedang dibina."),
    _e("stage_appointment", "Tahap: janji temu", 25, "Sudah ada janji survey/temu."),
    _e("stage_booking", "Tahap: booking", 35, "Sudah keep unit."),
    _e("stage_won", "Tahap: won", 40, "Menjadi customer."),
    _e("activity", "Aktivitas follow-up", 5, "Per aktivitas (komentar/catatan) dalam jendela hari, dibatasi cap.",
       window_days=14, cap=20),
    _e("appointment_scheduled", "Agenda/survey terjadwal", 10, "Ada agenda berstatus scheduled."),
    _e("appointment_done", "Survey/agenda dihadiri", 15, "Ada agenda berstatus done."),
    _e("inbound_reply", "Balasan WA dari lead", 10, "Per pesan masuk, dibatasi cap.", cap=20),
    _e("disposition_positive", "Disposisi positif", 15, "Disposisi terakhir positif."),
    _e("disposition_negative", "Disposisi negatif", -20, "Disposisi terakhir negatif."),
    _e("disposition_no_response", "Disposisi tidak merespons", -10, "Disposisi terakhir tidak merespons."),
    _e("idle", "Diam tanpa sentuhan", -5, "Per minggu setelah threshold_days tanpa aktivitas/pesan/agenda, dibatasi cap.",
       threshold_days=7, cap=30),
    _e("closed", "Lead ditutup (lost/recycle)", -40, "Lead yang sudah ditutup."),
]
SYSTEM_KEYS = {e["key"] for e in DEFAULT_EVENTS}


def default_events() -> list:
    return [dict(e, params=dict(e["params"])) for e in DEFAULT_EVENTS]


def default_bands() -> dict:
    return dict(cfg.DEFAULTS["lead.score.bands"]["value"])


def merge_events(configured) -> list:
    """Konfigurasi admin + event sistem baru yang belum ada di konfigurasi (tidak hilang)."""
    by_key = {e.get("key"): e for e in (configured or []) if isinstance(e, dict) and e.get("key")}
    out = []
    for d in default_events():
        c = by_key.pop(d["key"], None)
        if c:
            out.append({**d, **c, "kind": "system", "params": {**d["params"], **(c.get("params") or {})}})
        else:
            out.append(d)
    for k, c in by_key.items():
        out.append({"key": k, "label": c.get("label") or k, "points": int(c.get("points") or 0),
                    "active": c.get("active", True), "kind": "custom", "desc": c.get("desc") or "",
                    "params": {"window_days": int((c.get("params") or {}).get("window_days") or 0),
                               "cap": int((c.get("params") or {}).get("cap") or 0)}})
    return out


def _dt(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _capped(per: int, n: int, cap: int) -> int:
    raw = per * n
    if not cap:
        return raw
    return max(-abs(cap), min(abs(cap), raw))


def compute(lead: dict, facts: dict = None, events: list = None, bands: dict = None,
            now: datetime = None) -> dict:
    """Skor 0..100 + band + rincian per event. Sinkron & murni (bisa diuji tanpa DB)."""
    ev = {e["key"]: e for e in merge_events(events) if e.get("active", True)}
    b = {**default_bands(), **(bands or {})}
    f = facts or {}
    now = now or datetime.now(timezone.utc)
    rows = []

    def add(key, pts, label=None, detail=None):
        e = ev.get(key)
        if e and pts:
            rows.append({"key": key, "label": label or e["label"], "points": int(pts), "detail": detail})

    def flat(key, cond, label=None, detail=None):
        if key in ev and cond:
            add(key, ev[key]["points"], label, detail)

    flat("base", True)
    src = lead.get("source")
    if "source" in ev:
        add("source", ref.SOURCE_SCORE.get(src, 10),
            f"Sumber: {ref.label_of('lead_source', src) if src else '-'}")
    stage = lead.get("stage")
    flat(f"stage_{stage}", True, f"Tahap: {ref.label_of('lead_stage', stage) if stage else '-'}")
    flat("first_contact", bool(lead.get("first_contact_at")))
    created = _dt(lead.get("created_at"))
    flat("new_24h", bool(created and now - created < timedelta(hours=24)))
    if "activity" in ev and int(f.get("activities_recent") or 0):
        n = int(f["activities_recent"])
        p = ev["activity"]["params"]
        add("activity", _capped(ev["activity"]["points"], n, p.get("cap")),
            f"{n} aktivitas dalam {p.get('window_days')} hari")
    flat("appointment_scheduled", int(f.get("appointments_scheduled") or 0) > 0)
    flat("appointment_done", int(f.get("appointments_done") or 0) > 0)
    if "inbound_reply" in ev and int(f.get("inbound_replies") or 0):
        n = int(f["inbound_replies"])
        add("inbound_reply", _capped(ev["inbound_reply"]["points"], n, ev["inbound_reply"]["params"].get("cap")),
            f"{n} balasan WA dari lead")
    dk = DISPOSITION_EVENT.get(lead.get("disposition"))
    if dk:
        flat(dk, True, f"Disposisi: {ref.label_of('lead_disposition', lead['disposition'])}")
    if "idle" in ev and stage not in OPEN_STAGES_EXCLUDED:
        last = _dt(f.get("last_touch_at")) or created
        p = ev["idle"]["params"]
        if last:
            idle_days = (now - last).days
            if idle_days >= int(p.get("threshold_days") or 7):
                weeks = 1 + (idle_days - int(p.get("threshold_days") or 7)) // 7
                add("idle", _capped(ev["idle"]["points"], weeks, p.get("cap")),
                    f"Diam {idle_days} hari tanpa sentuhan",
                    "Hubungi lead ini untuk menghentikan penurunan.")
    flat("closed", stage in ("lost", "recycle"))
    # Event kustom yang dicatat sales (activities type=score_event, meta.event_key).
    for key, n in (f.get("custom_events") or {}).items():
        e = ev.get(key)
        if e and e.get("kind") == "custom" and n:
            add(key, _capped(e["points"], int(n), e["params"].get("cap")),
                f"{e['label']} ×{n}" if int(n) > 1 else e["label"])
    score = max(0, min(100, sum(r["points"] for r in rows)))
    band = "hot" if score >= b["hot_min"] else "warm" if score >= b["warm_min"] else "cold"
    return {"score": score, "score_band": band, "score_breakdown": rows,
            "score_bands": b, "score_at": now.isoformat()}


async def events_for(org: str) -> list:
    return merge_events(await cfg.get("lead.score.events", org_id=org))


async def facts_for(org: str, lead: dict, events: list = None) -> dict:
    """Fakta keterlibatan dari koleksi yang benar-benar ditulis mesin lain."""
    ev = {e["key"]: e for e in (events or await events_for(org))}
    now = datetime.now(timezone.utc)
    win = int((ev.get("activity") or {}).get("params", {}).get("window_days") or 14)
    since = (now - timedelta(days=win)).isoformat()
    lid = lead["id"]
    acts = await db.activities.find({"org_id": org, "entity_type": "lead", "entity_id": lid},
                                    {"_id": 0, "type": 1, "meta": 1, "created_at": 1}
                                    ).sort("created_at", -1).to_list(300)
    appts = await db.appointments.find({"org_id": org, "lead_id": lid},
                                       {"_id": 0, "status": 1, "created_at": 1, "updated_at": 1}).to_list(50)
    convs = await db.conversations.find({"org_id": org, "lead_id": lid}, {"_id": 0, "id": 1}).to_list(20)
    inbound, last_msg = 0, None
    if convs:
        cids = [c["id"] for c in convs]
        inbound = await db.messages.count_documents(
            {"org_id": org, "conversation_id": {"$in": cids}, "direction": "in"})
        m = await db.messages.find({"org_id": org, "conversation_id": {"$in": cids}},
                                   {"_id": 0, "created_at": 1}).sort("created_at", -1).to_list(1)
        last_msg = m[0]["created_at"] if m else None
    custom: dict = {}
    for a in acts:
        if a.get("type") != "score_event":
            continue
        key = (a.get("meta") or {}).get("event_key")
        e = ev.get(key)
        if not e:
            continue
        w = int(e["params"].get("window_days") or 0)
        if w and a["created_at"] < (now - timedelta(days=w)).isoformat():
            continue
        custom[key] = custom.get(key, 0) + 1
    touches = [a["created_at"] for a in acts] + [last_msg] + \
        [a.get("updated_at") or a.get("created_at") for a in appts] + \
        [lead.get("first_contact_at"), lead.get("disposition_at"), lead.get("updated_at")]
    touches = [t for t in touches if t]
    return {
        "activities_recent": sum(1 for a in acts if a["created_at"] >= since and a.get("type") != "score_event"),
        "appointments_scheduled": sum(1 for a in appts if a.get("status") == "scheduled"),
        "appointments_done": sum(1 for a in appts if a.get("status") == "done"),
        "inbound_replies": inbound, "custom_events": custom,
        "last_touch_at": max(touches) if touches else None,
    }


async def rescore(org: str, lead: dict) -> dict:
    """Skor terkonfigurasi + fakta keterlibatan — patch siap `$set` pada lead."""
    events = await events_for(org)
    bands = await cfg.get("lead.score.bands", org_id=org)
    facts = await facts_for(org, lead, events)
    out = compute(lead, facts, events, bands)
    out["score_facts"] = facts
    return out


async def rescore_all(org: str = ORG_ID) -> dict:
    """Sapuan harian: lead terbuka dinilai ulang supaya yang diam benar-benar turun."""
    changed = total = 0
    cur = db.leads.find({"org_id": org, "stage": {"$nin": list(OPEN_STAGES_EXCLUDED)}}, {"_id": 0})
    async for lead in cur:
        total += 1
        patch = await rescore(org, lead)
        if patch["score"] != lead.get("score") or patch["score_band"] != lead.get("score_band"):
            changed += 1
        await db.leads.update_one({"id": lead["id"]}, {"$set": {**patch, "updated_at_score": now_iso()}})
    logger.info("Skor lead disapu: %s lead, %s berubah", total, changed)
    return {"total": total, "changed": changed}
