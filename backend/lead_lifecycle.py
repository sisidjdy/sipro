"""LEAD LIFECYCLE sebagai GERBANG BUKTI (Fase 29b).

Masalah yang diperbaiki (terbukti di audit): stage lead bisa dipilih bebas dari dropdown.
Pada environment ini `nurturing → booking` berhasil walau lead tidak punya deal, dan
`booking → won` berhasil walau deal masih 'booked' (belum akad/lunas). Akibatnya laporan
funnel tidak bisa dipercaya.

Aturan baru:
  * Setiap stage punya SYARAT BUKTI yang diperiksa pada DATA (bukan janji pengguna).
  * `won` TIDAK BISA manual — hanya lahir dari event legal (AJB/lunas) lewat `advance_on_deal`.
  * `lost` / `recycle` wajib beralasan (SSOT `lead_close_reason`).
  * Setiap perpindahan dicatat di `stage_history` (siapa, kapan, dari→ke, alasan, bukti).
  * Supervisor boleh override (mis. data lama), tetapi wajib alasan dan tetap tercatat.
"""
import logging

import stage_clock as clock
from core_utils import now_iso
from db import db, ORG_ID
from engine import add_activity, emit


def _ls():
    import lead_scoring
    return lead_scoring

logger = logging.getLogger("sipro.lifecycle")

ORDER = ["acquisition", "nurturing", "appointment", "booking", "won"]
CLOSED = {"lost", "recycle"}

# Transisi yang boleh dilakukan MANUAL oleh pengguna (won tidak termasuk!)
MANUAL_FLOW = {
    "acquisition": ["nurturing", "lost", "recycle"],
    "nurturing": ["appointment", "booking", "lost", "recycle"],
    "appointment": ["booking", "nurturing", "lost", "recycle"],
    "booking": ["lost"],
    "won": [],
    "recycle": ["nurturing", "acquisition", "lost"],
    "lost": ["recycle"],
}

REASON_REQUIRED = {"lost", "recycle"}


async def requirements(lead: dict) -> dict:
    """Syarat bukti per stage untuk SATU lead + status terpenuhinya (untuk UI checklist)."""
    org = lead.get("org_id", ORG_ID)
    lid = lead["id"]
    contacted = bool(lead.get("first_contact_at"))
    appts = await db.appointments.count_documents({"org_id": org, "lead_id": lid})
    appt_done = await db.appointments.count_documents(
        {"org_id": org, "lead_id": lid, "status": {"$in": ["done", "scheduled"]}})
    deals = await db.deals.find({"org_id": org, "lead_id": lid}, {"_id": 0, "status": 1,
                                                                 "legal_stage": 1,
                                                                 "scheme_id": 1}).to_list(20)
    live = [d for d in deals if d.get("status") not in ("canceled", "expired", "failed")]
    akad = [d for d in deals if d.get("status") in ("completed", "sold")
            or d.get("legal_stage") in ("ajb", "bast")]
    disposition = lead.get("disposition")
    slik = lead.get("slik") or {}
    slik_ok = slik.get("status") in ("clear", "flagged")   # 'rejected'/kosong = belum lolos
    # Fase 30a: bukti iDeb ikut dilaporkan pada label supaya checklist tidak hanya
    # mengatakan "sudah diperiksa" tanpa memperlihatkan bahwa ada lampirannya.
    slik_ev = len(slik.get("evidence") or [])
    slik_note = ""
    if slik.get("status"):
        slik_note = f" (hasil: {slik.get('status')}, {slik_ev} bukti)"
    # Konfigurasi `slik.gate`: off | before_booking | before_spr — hanya `before_booking`
    # yang menjadikan SLIK syarat tahap booking; `before_spr` ditegakkan saat terbit SPR (docgen).
    import settings_store as cfg
    slik_gate = str(await cfg.get("slik.gate", org_id=org) or "before_spr")
    # Gerbang per JENIS skema (`[CFG] slik.scheme_kinds`): reservasi hidup yang skemanya
    # tunai tidak dikenai SLIK. Tanpa reservasi (jenis belum diketahui) gerbang tetap berlaku.
    slik_kinds = list(await cfg.get("slik.scheme_kinds", org_id=org) or [])
    live_kinds = set()
    for d in live:
        if d.get("scheme_id"):
            sch = await db.payment_schemes.find_one(
                {"id": d["scheme_id"]}, {"_id": 0, "kind": 1})
            live_kinds.add((sch or {}).get("kind"))
    slik_applies = not live_kinds or any(k in slik_kinds for k in live_kinds)
    slik_req = ([{"key": "slik", "label": ("Pra-skrining BI/SLIK sudah dilakukan & tidak ditolak"
                                           + slik_note),
                  "met": slik_ok, "action": "Jalankan pra-skrining BI/SLIK", "link": "slik"}]
                if slik_gate == "before_booking" and slik_applies else [])
    return {
        "nurturing": [
            {"key": "first_contact", "label": "Kontak pertama tercatat (WA/telepon/kunjungan)",
             "met": contacted, "action": "Kirim WA / catat kontak pertama", "link": "wa"},
        ],
        "appointment": [
            {"key": "first_contact", "label": "Kontak pertama tercatat", "met": contacted,
             "action": "Kirim WA / catat kontak pertama", "link": "wa"},
            {"key": "appointment", "label": "Ada jadwal survey/janji temu", "met": appts > 0,
             "action": "Jadwalkan survey", "link": "appointment"},
        ],
        "booking": slik_req + [
            {"key": "appointment_result", "label": "Survey terjadwal / sudah dilakukan",
             "met": appt_done > 0, "action": "Jadwalkan & catat hasil survey", "link": "appointment"},
            {"key": "deal", "label": "Ada SPR/reservasi unit (deal aktif)", "met": len(live) > 0,
             "action": "Buat reservasi unit", "link": "reserve"},
        ],
        "won": [
            {"key": "akad", "label": "Deal selesai (AJB/serah terima) — otomatis, tidak manual",
             "met": len(akad) > 0, "action": "Selesaikan proses legal deal", "link": "deal"},
        ],
        "quality": [
            {"key": "disposition", "label": "Penilaian respons lead (positif/netral/negatif)",
             "met": bool(disposition), "action": "Nilai respons lead", "link": "disposition"},
        ],
    }


async def gate(lead: dict, target: str) -> tuple:
    """Boleh pindah ke `target`? Kembalikan (ok, alasan_penolakan, bukti_terpakai)."""
    if target in CLOSED:
        return True, None, {}
    reqs = (await requirements(lead)).get(target) or []
    unmet = [r for r in reqs if not r["met"]]
    if unmet:
        names = "; ".join(r["label"] for r in unmet)
        return False, (f"Syarat belum terpenuhi untuk tahap ini → {names}. "
                       "Lakukan aksinya dulu (atau minta supervisor melakukan override "
                       "dengan alasan)."), {}
    return True, None, {r["key"]: True for r in reqs}


async def record(lead: dict, to_stage: str, *, actor: str, reason: str = None,
                 evidence: dict = None, override: bool = False, source: str = "manual") -> dict:
    """Terapkan perpindahan stage + catat riwayat (SATU pintu untuk semua pemanggil)."""
    org = lead.get("org_id", ORG_ID)
    ts = now_iso()
    frm = lead.get("stage")
    entry = {"from": frm, "to": to_stage, "at": ts, "actor": actor, "reason": reason,
             "evidence": evidence or {}, "override": bool(override), "source": source}
    updates = {"stage": to_stage, "updated_at": ts, "stage_changed_at": ts}
    # Fase 41: jam tahap ditulis SEBAGAI FIELD (stage_entered_at / stage_due_at / SLA efektif)
    # supaya umur tahap bisa difilter & dilaporkan tanpa memindai `stage_history` tiap request.
    updates.update(await clock.patch_for("lead", to_stage, org_id=org, at=ts))
    if to_stage in CLOSED and reason:
        updates["close_reason"] = reason
    if to_stage == "won":
        updates["won_at"] = ts
    updates.update(await _ls().rescore(org, {**lead, **updates}))
    await db.leads.update_one({"id": lead["id"]},
                              {"$set": updates, "$push": {"stage_history": entry}})
    label = f"Tahap lead {frm} → {to_stage}"
    if override:
        label += " (override supervisor)"
    if reason:
        label += f": {reason}"
    await add_activity(entity_type="lead", entity_id=lead["id"], type="system", body=label,
                       actor=actor, org_id=org)
    await emit("lead.stage_changed", "lead", lead["id"],
               {"from": frm, "to": to_stage, "override": bool(override), "source": source},
               org_id=org)
    return await db.leads.find_one({"id": lead["id"]}, {"_id": 0})


async def mark_first_contact(lead: dict, *, actor: str, channel: str = "whatsapp",
                             note: str = None) -> dict:
    """Kontak pertama = bukti nyata; menghitung waktu respons SEKALI & menaikkan stage.

    Dipakai oleh tombol 'Catat Kontak Pertama' MAUPUN oleh pengiriman WA dari record lead
    (dulu kirim WA tidak berpengaruh apa pun pada lifecycle).
    """
    from datetime import datetime

    from core_utils import now
    org = lead.get("org_id", ORG_ID)
    ts = now_iso()
    updates = {"updated_at": ts}
    if not lead.get("first_contact_at"):
        minutes = None
        created = lead.get("created_at")
        if created:
            try:
                minutes = max(0, round((now() - datetime.fromisoformat(created)).total_seconds() / 60))
            except (TypeError, ValueError):
                minutes = None
        updates["first_contact_at"] = ts
        updates["response_time_minutes"] = minutes
        updates["first_contact_channel"] = channel
    await db.leads.update_one({"id": lead["id"]}, {"$set": updates})
    fresh = await db.leads.find_one({"id": lead["id"]}, {"_id": 0})
    # Tutup tugas "hubungi lead" yang terbuka (bukti pekerjaan benar-benar dilakukan).
    await db.tasks.update_many(
        {"org_id": org, "related_entity_type": "lead", "related_entity_id": lead["id"],
         "type": "contact", "status": {"$in": ["open", "in_progress", "snoozed", "submitted"]}},
        {"$set": {"status": "done", "review": "approved", "completed_at": ts,
                  "completed_by": actor, "verified_by": "system",
                  "outcome": note or f"Kontak pertama via {channel}", "updated_at": ts}})
    if fresh.get("stage") == "acquisition":
        fresh = await record(fresh, "nurturing", actor=actor, source=f"contact:{channel}",
                            evidence={"first_contact": True})
    return fresh


async def advance_on_deal(deal: dict, *, stage: str, actor: str = "system", reason: str = None):
    """Lifecycle mengikuti bukti transaksi: booking saat reservasi, won saat akad/lunas."""
    lid = deal.get("lead_id")
    if not lid:
        return None
    lead = await db.leads.find_one({"id": lid}, {"_id": 0})
    if not lead:
        return None
    cur = lead.get("stage")
    if cur == stage or cur in ("won",):
        return lead
    if stage == "booking" and cur not in ("acquisition", "nurturing", "appointment"):
        return lead
    return await record(lead, stage, actor=actor, reason=reason, source="deal",
                        evidence={"deal_id": deal.get("id"), "deal_status": deal.get("status")})


async def set_disposition(lead: dict, *, disposition: str, actor: str, note: str = None,
                          intent_tags: list = None) -> dict:
    """Penilaian KUALITATIF agen (niat lead) — memandu langkah berikutnya, bukan sekadar catatan."""
    org = lead.get("org_id", ORG_ID)
    ts = now_iso()
    upd = {"disposition": disposition, "disposition_at": ts, "disposition_by": actor,
           "disposition_note": note, "updated_at": ts}
    if intent_tags:
        upd["intent_tags"] = intent_tags[:8]
    upd.update(await _ls().rescore(org, {**lead, **upd}))
    await db.leads.update_one({"id": lead["id"]}, {"$set": upd})
    labels = {"positive": "positif (berminat)", "neutral": "netral (menimbang)",
              "negative": "negatif (tidak berminat)", "no_response": "tidak merespons"}
    await add_activity(entity_type="lead", entity_id=lead["id"], type="system",
                       body=f"Respons lead dinilai {labels.get(disposition, disposition)}"
                            + (f": {note}" if note else ""), actor=actor, org_id=org)
    return await db.leads.find_one({"id": lead["id"]}, {"_id": 0})


def next_actions(lead: dict, reqs: dict) -> list:
    """Langkah berikutnya (NBA) berbasis stage + kualitas respons + syarat yang belum lengkap."""
    stage = lead.get("stage")
    disp = lead.get("disposition")
    out = []
    if stage == "acquisition":
        out.append({"key": "wa", "label": "Hubungi via WhatsApp sekarang",
                    "reason": "Speed-to-lead: peluang turun drastis setelah 5 menit",
                    "priority": "urgent"})
    if stage in ("nurturing", "appointment") and not disp:
        out.append({"key": "disposition", "label": "Nilai respons lead",
                    "reason": "Penilaian niat menentukan langkah & prioritas berikutnya",
                    "priority": "high"})
    if stage in ("nurturing",) and disp in (None, "positive", "neutral"):
        out.append({"key": "appointment", "label": "Jadwalkan survey / janji temu",
                    "reason": "Lead berminat perlu melihat unit", "priority": "high"})
    if stage == "appointment":
        out.append({"key": "reserve", "label": "Buat reservasi (SPR) unit",
                    "reason": "Survey selesai — kunci unit sebelum diambil orang lain",
                    "priority": "high"})
    if stage == "booking":
        out.append({"key": "deal", "label": "Lanjutkan proses PPJB/KPR di halaman Deal",
                    "reason": "Booking wajib berlanjut ke PPJB ≤30 hari", "priority": "high"})
    if disp == "negative" and stage not in CLOSED:
        out.append({"key": "close", "label": "Tandai lost/daur ulang dengan alasan",
                    "reason": "Respons negatif — jangan biarkan pipeline menggantung",
                    "priority": "medium"})
    if disp == "no_response" and stage not in CLOSED:
        out.append({"key": "wa", "label": "Kirim template aktivasi ulang",
                    "reason": "Lead diam — coba template re-engagement", "priority": "medium"})
    unmet = [r for r in (reqs.get(ORDER[min(ORDER.index(stage) + 1, len(ORDER) - 1)])
                         if stage in ORDER else []) or [] if not r["met"]]
    for u in unmet[:2]:
        out.append({"key": u["link"], "label": u["action"],
                    "reason": f"Syarat naik tahap: {u['label']}", "priority": "medium"})
    seen, uniq = set(), []
    for o in out:
        if o["key"] in seen:
            continue
        seen.add(o["key"])
        uniq.append(o)
    return uniq[:4]
