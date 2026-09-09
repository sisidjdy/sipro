"""Pra-skrining BI/SLIK sebagai GERBANG BUKTI sebelum tahap Booking (Fase 30a).

JUJUR SOAL MODE: OJK tidak membuka API publik untuk iDeb SLIK — hasilnya diperoleh
petugas melalui kanal resmi (portal SLIK lembaga keuangan / partner bank) lalu DICATAT
di sini bersama BUKTINYA. Yang benar-benar dijamin sistem (bukan janji):

  1. Hasil yang MELOLOSKAN lead (clear/flagged) WAJIB berbukti — lampiran iDeb
     (tangkapan layar/PDF) diverifikasi benar ada di penyimpanan berkas.
  2. Hasil `rejected` wajib beralasan, MENAHAN lead di bawah Booking, melahirkan TUGAS
     tindak lanjut (jobdesk SM-12), dan menawarkan penutupan lead dengan alasan SSOT.
  3. Setiap pemeriksaan masuk RIWAYAT (siapa/kapan/hasil/bukti) — hasil lama tidak
     bisa dihapus diam-diam dengan menimpa hasil baru.
  4. Hasil pra-skrining MENGALIR ke pengajuan KPR sebagai catatan awal, TETAPI tidak
     pernah menggantikan hasil resmi bank (`financing_apps.slik_status` tetap menunggu
     bank) — supaya laporan pembiayaan tidak berbohong.
"""
import logging

import reference as ref
from core_utils import now_iso
from db import db, ORG_ID
from engine import add_activity, emit

logger = logging.getLogger("sipro.slik")

MODE = "simulation"
PASSING = ("clear", "flagged")             # meloloskan lead ke tahap booking
EVIDENCE_REQUIRED = ("clear", "flagged")   # yang meloloskan WAJIB berbukti
HOLDING = ("rejected",)                    # menahan lead
JOBDESK_REJECTED = "SM-12"                 # jobdesk tindak lanjut SLIK ditolak
CLOSE_REASON = "financing"                 # SSOT lead_close_reason
MAX_EVIDENCE = 6


def options() -> list:
    """Pilihan hasil untuk UI ('pending' dikecualikan: itu keadaan awal, bukan hasil)."""
    return [{"value": o["value"], "label": o["label"]}
            for o in ref.GROUPS["slik_status"]["options"] if o["value"] != "pending"]


def valid_statuses() -> set:
    return set(ref.values("slik_status"))


def requires_evidence(status: str) -> bool:
    return status in EVIDENCE_REQUIRED


async def evidence_refs(org: str, ids: list) -> list:
    """Metadata berkas bukti yang BENAR ADA (mencegah id fiktif dijadikan "bukti")."""
    clean, seen = [], set()
    for i in (ids or []):
        s = str(i or "").strip()
        if s and s not in seen:
            seen.add(s)
            clean.append(s)
    clean = clean[:MAX_EVIDENCE]
    if not clean:
        return []
    rows = await db.files.find(
        {"org_id": org, "id": {"$in": clean}, "is_deleted": False},
        {"_id": 0, "id": 1, "original_filename": 1, "content_type": 1, "size": 1,
         "uploaded_by": 1, "created_at": 1}).to_list(MAX_EVIDENCE)
    found = {r["id"] for r in rows}
    missing = [i for i in clean if i not in found]
    if missing:
        raise ValueError("Berkas bukti tidak ditemukan di penyimpanan: " + ", ".join(missing))
    order = {fid: n for n, fid in enumerate(clean)}
    rows.sort(key=lambda r: order.get(r["id"], 99))
    return [{"file_id": r["id"], "filename": r.get("original_filename"),
             "content_type": r.get("content_type"), "size": r.get("size"),
             "uploaded_by": r.get("uploaded_by"), "uploaded_at": r.get("created_at")}
            for r in rows]


def summary(lead: dict) -> dict:
    """Bentuk ringkas untuk UI: hasil terakhir + apakah meloloskan + jumlah bukti."""
    s = dict((lead or {}).get("slik") or {})
    if not s:
        return None
    s["label"] = ref.label_of("slik_status", s.get("status"))
    s["passing"] = s.get("status") in PASSING
    s["holding"] = s.get("status") in HOLDING
    s["evidence_count"] = len(s.get("evidence") or [])
    s["history_count"] = len((lead or {}).get("slik_history") or [])
    return s


def history(lead: dict) -> list:
    """Riwayat pemeriksaan (terbaru dulu) + label SSOT untuk tampilan."""
    rows = list((lead or {}).get("slik_history") or [])
    out = []
    for h in reversed(rows[-20:]):
        e = dict(h)
        e["label"] = ref.label_of("slik_status", e.get("status"))
        e["evidence_count"] = len(e.get("evidence") or [])
        out.append(e)
    return out


async def followup_task(org: str, lead_id: str) -> dict:
    """Tugas tindak lanjut SLIK yang MASIH terbuka untuk lead ini (bila ada)."""
    row = await db.tasks.find_one(
        {"org_id": org, "jobdesk_code": JOBDESK_REJECTED, "related_entity_id": lead_id,
         "status": {"$in": ["open", "in_progress", "snoozed", "submitted"]}},
        {"_id": 0, "id": 1, "title": 1, "assigned_to": 1, "due_date": 1, "status": 1,
         "priority": 1}, sort=[("created_at", -1)])
    return row


async def _close_followups(org: str, lead_id: str, actor: str, outcome: str) -> int:
    """Hasil baru tidak menahan lead → tutup tugas tindak lanjut yang masih terbuka."""
    ts = now_iso()
    res = await db.tasks.update_many(
        {"org_id": org, "jobdesk_code": JOBDESK_REJECTED, "related_entity_id": lead_id,
         "status": {"$in": ["open", "in_progress", "snoozed", "submitted"]}},
        {"$set": {"status": "done", "review": "approved", "completed_at": ts,
                  "completed_by": actor, "verified_by": "system", "outcome": outcome,
                  "updated_at": ts}})
    return res.modified_count


async def prescreen(lead: dict, *, status: str, note: str = None,
                    evidence_ids: list = None, actor: str = "system") -> dict:
    """Catat satu pemeriksaan pra-skrining. Melempar ValueError bila syarat bukti kurang."""
    org = lead.get("org_id", ORG_ID)
    lid = lead["id"]
    status = str(status or "").strip()
    if status not in valid_statuses():
        raise ValueError("Hasil SLIK tidak valid. Pilihan: "
                         + ", ".join(sorted(valid_statuses())))
    note = (str(note or "").strip() or None)
    if note:
        note = note[:400]
    if status in HOLDING and not note:
        raise ValueError("Alasan wajib diisi bila hasil SLIK ditolak "
                         "(dipakai saat menutup lead).")
    evidence = await evidence_refs(org, evidence_ids)
    if requires_evidence(status) and not evidence:
        raise ValueError(
            "Lampirkan bukti hasil iDeb SLIK (tangkapan layar/PDF) — hasil yang "
            "meloloskan lead ke tahap Booking tidak boleh tanpa bukti.")
    ts = now_iso()
    entry = {"status": status, "note": note, "evidence": evidence, "checked_at": ts,
             "checked_by": actor, "mode": MODE}
    await db.leads.update_one({"id": lid}, {"$set": {"slik": entry, "updated_at": ts},
                                            "$push": {"slik_history": entry}})
    label = ref.label_of("slik_status", status)
    body = f"Pra-skrining BI/SLIK (SIMULASI): {label}"
    if note:
        body += f" — {note}"
    if evidence:
        body += f" · {len(evidence)} bukti dilampirkan"
    await add_activity(entity_type="lead", entity_id=lid, type="system", body=body,
                       actor=actor, org_id=org)
    suggest, closed = None, 0
    if status in HOLDING:
        # Event → jobdesk SM-12 (Work Hub) lahir otomatis lewat dispatcher event bus.
        await emit("lead.slik_rejected", "lead", lid,
                   {"label": lead.get("name"), "note": note}, org_id=org)
        suggest = {
            "stage": "lost", "reason": CLOSE_REASON,
            "reason_label": ref.label_of("lead_close_reason", CLOSE_REASON),
            "note": f"{ref.label_of('lead_close_reason', CLOSE_REASON)} — SLIK ditolak: {note}",
        }
    else:
        closed = await _close_followups(
            org, lid, actor, f"Pra-skrining SLIK diperbarui: {label}")
    fresh = await db.leads.find_one({"id": lid}, {"_id": 0})
    return {"lead": fresh, "slik": entry, "suggest_close": suggest,
            "closed_followups": closed, "mode": MODE}


def financing_note(pre: dict) -> str:
    """Kalimat jujur untuk dokumen KPR: pra-skrining ≠ hasil resmi bank."""
    if not pre:
        return None
    label = ref.label_of("slik_status", pre.get("status"))
    n = len(pre.get("evidence") or [])
    tail = f", {n} bukti dilampirkan" if n else ", tanpa lampiran"
    return (f"Pra-skrining BI/SLIK lead (SIMULASI): {label}{tail} oleh "
            f"{pre.get('checked_by') or '-'}. Hasil RESMI bank masih menunggu.")


def financing_prescreen(lead: dict) -> dict:
    """Salinan hasil pra-skrining lead untuk ditempel ke pengajuan KPR."""
    s = (lead or {}).get("slik") or {}
    if not s.get("status"):
        return None
    return {"status": s.get("status"), "label": ref.label_of("slik_status", s.get("status")),
            "note": s.get("note"), "evidence": s.get("evidence") or [],
            "checked_at": s.get("checked_at"), "checked_by": s.get("checked_by"),
            "lead_id": (lead or {}).get("id"), "mode": MODE,
            "passing": s.get("status") in PASSING}


async def prescreen_for_deal(deal: dict) -> dict:
    """Ambil pra-skrining dari lead pemilik deal (dipakai saat pengajuan KPR dibuat)."""
    lid = (deal or {}).get("lead_id")
    if not lid:
        return None
    lead = await db.leads.find_one({"id": lid}, {"_id": 0, "id": 1, "slik": 1})
    return financing_prescreen(lead) if lead else None
