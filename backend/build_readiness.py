"""GERBANG "MULAI BANGUN" (Fase 46) — jujur, beralasan, dan bisa diatur.

Latar belakang cacat yang ditutup:
  * Setting `build.require_dp_before_start` sudah ada sejak Fase 39 tetapi **tidak pernah
    dibaca satu jalur kode pun**. Artinya klausul SPR ("pembangunan dimulai setelah
    pembayaran tahap pertama diterima") hanya hidup di kertas.
  * Tombol yang mati tanpa penjelasan adalah UX buruk. Karena itu modul ini TIDAK
    mengembalikan boolean, melainkan DAFTAR ALASAN berkode + tingkat (blocker/warning/info)
    + cara memperbaikinya, sehingga layar bisa menjelaskan kepada manusia.

Keputusan owner (Fase 46): mode bawaan = **PERINGATAN**, bukan blokir.
  * `build.require_dp_before_start` bawaan **False** → DP belum lunas hanya PERINGATAN;
    bila admin menyalakannya, alasan yang sama naik menjadi **blocker** (uji negatif gate).
  * `permit.block_build_without` bawaan kosong → izin hanya peringatan; bila diisi kode izin
    (mis. `PBG`), izin wajib yang tidak ada menjadi **blocker**.
  * Peringatan TIDAK boleh diabaikan diam-diam: memulai pembangunan saat ada peringatan
    wajib `ack=true` + alasan (≥5 huruf) yang dicatat pada jadwal + aktivitas + audit.

Yang tetap dipegang dari fase sebelumnya (tidak ada dua kebenaran):
  * Progres unit tetap milik `build_engine` (Σ bobot item terverifikasi). Modul ini TIDAK
    menulis `construction_progress`.
  * "Mulai bangun" = benar-benar memulai LANGKAH PERTAMA yang sudah terbuka lewat
    `build_actions.start_item`, lalu `build_engine.recompute_schedule` yang menetapkan
    status unit — bukan menimpa status unit secara manual.
"""
import logging

import build_actions as ba
import build_engine as be
import permit_scope as ps
import settings_store as cfg
from core_utils import now_iso
from db import ORG_ID, db
from engine import add_activity, create_notification, emit
from reference_p46 import (GATE_LABEL, READINESS_LABEL, SEVERITY_LABEL,
                          STARTED_UNIT_STATUS)

logger = logging.getLogger("sipro.build.readiness")

WORKABLE = ("ready", "rework", "in_progress")
MIN_REASON = 5


def _reason(code: str, severity: str, detail: str, fix: str = None) -> dict:
    return {"code": code, "label": GATE_LABEL.get(code, code), "severity": severity,
            "severity_label": SEVERITY_LABEL[severity], "detail": detail, "fix": fix}


async def _payment_check(org: str, unit: dict) -> dict:
    """Termin pertama (DP) dibaca dari rencana bayar NYATA (`ar_invoices.items`).

    Bila unit belum punya rencana bayar, hasilnya `paid=None` + `known=False` — bukan
    "belum bayar". Membedakan "belum ada datanya" dari "sudah dicek dan memang belum
    bayar" adalah inti aturan kejujuran repo.
    """
    inv = await db.ar_invoices.find_one({"org_id": org, "unit_id": unit["id"]}, {"_id": 0})
    items = (inv or {}).get("items") or []
    if not items:
        return {"known": False, "paid": None, "label": None, "amount": None,
                "paid_amount": None, "invoice_id": (inv or {}).get("id"),
                "scheme_name": (inv or {}).get("scheme_name")}
    first = items[0]
    amount = int(first.get("amount") or 0)
    paid_amount = int(first.get("paid_amount") or 0)
    paid = first.get("status") == "paid" or (amount > 0 and paid_amount >= amount)
    return {"known": True, "paid": bool(paid), "label": first.get("label"),
            "amount": amount, "paid_amount": paid_amount, "due_date": first.get("due_date"),
            "invoice_id": (inv or {}).get("id"), "scheme_name": (inv or {}).get("scheme_name"),
            "status": first.get("status")}


async def evaluate(org: str = ORG_ID, unit_id: str = None) -> dict:
    """Kesiapan satu unit untuk dimulai + seluruh alasannya (tanpa mengubah data)."""
    unit = await db.units.find_one({"id": unit_id, "org_id": org}, {"_id": 0})
    if not unit:
        raise ValueError("Unit tidak ditemukan.")
    project_id = unit.get("project_id")
    require_dp = bool(await cfg.get("build.require_dp_before_start", org_id=org,
                                    project_id=project_id))
    block_codes = list(await cfg.get("permit.block_build_without", org_id=org,
                                     project_id=project_id) or [])
    sched = await db.build_schedules.find_one({"org_id": org, "unit_id": unit_id}, {"_id": 0})
    pay = await _payment_check(org, unit)
    cov = await ps.coverage(org, unit_id=unit_id, required_codes=block_codes)

    reasons, missing = [], []
    started = str(unit.get("construction_status")) in STARTED_UNIT_STATUS

    # ---- 1. jadwal: syarat STRUKTURAL (bukan kebijakan) ----
    first_item = None
    if not sched:
        missing.append("jadwal_pembangunan")
        reasons.append(_reason(
            "no_schedule", "blocker",
            "Unit ini belum punya jadwal pembangunan, jadi tidak ada langkah kerja "
            "yang bisa dimulai.",
            "Buat jadwal lewat tombol 'Buat jadwal dari template' di bawah, dari hub "
            "Pembangunan (Papan Unit), atau penjadwalan massal."))
    else:
        items = await db.build_items.find(
            {"org_id": org, "schedule_id": sched["id"]},
            {"_id": 0, "id": 1, "name": 1, "status": 1, "order": 1, "planned_start": 1,
             "planned_finish": 1, "assigned_to": 1, "gate_reasons": 1}
        ).sort("order", 1).to_list(500)
        first_item = next((i for i in items if i.get("status") in WORKABLE), None)
        if sched.get("status") == "on_hold":
            reasons.append(_reason(
                "schedule_on_hold", "blocker",
                f"Jadwal unit dihentikan sementara ({sched.get('hold_note') or 'tanpa catatan'}).",
                "Lanjutkan jadwal dulu dari Papan Unit / Unit 360 sebelum memulai kerja."))
        elif not first_item and not started:
            locked = next((i for i in items if i.get("gate_reasons")), None)
            detail = " ".join((r.get("detail") or "")
                              for r in (locked or {}).get("gate_reasons") or []) or \
                "Semua langkah masih terkunci gerbang bukti."
            reasons.append(_reason("no_ready_item", "blocker", detail,
                                   "Selesaikan/verifikasi langkah pendahulunya lebih dulu."))

    # ---- 2. pembayaran termin pertama (kebijakan: default PERINGATAN) ----
    sev = "blocker" if require_dp else "warning"
    if not pay["known"]:
        missing.append("rencana_bayar")
        reasons.append(_reason(
            "no_payment_plan", sev,
            "Unit ini belum punya rencana bayar (termin), jadi status DP belum bisa "
            "diperiksa — bukan berarti sudah lunas.",
            "Terbitkan rencana bayar dari transaksi (Customer & Kontrak) lebih dulu."))
    elif not pay["paid"]:
        reasons.append(_reason(
            "dp_unpaid", sev,
            (f"Termin pertama '{pay['label']}' belum terbayar penuh "
             f"(terbayar Rp {pay['paid_amount']:,} dari Rp {pay['amount']:,})."
             .replace(",", ".")),
            "Catat penerimaan pembayaran di Keuangan (AR) lalu ulangi."))

    # ---- 3. perizinan yang menempel pada unit ----
    for code in cov["missing_codes"]:
        reasons.append(_reason(
            "permit_missing", "blocker",
            f"Izin wajib {code} belum ada/aktif untuk unit ini (kebijakan "
            f"'Izin yang memblokir mulai bangun').",
            f"Terbitkan/aktifkan izin {code} pada proyek, cluster, blok, atau unit ini."))
    for w in cov["warnings"]:
        reasons.append(_reason(w["code"], "warning", w["detail"],
                               "Ajukan perpanjangan izin ke instansi terkait."))
    if not cov["permits"]:
        missing.append("perizinan")

    if started:
        reasons.append(_reason(
            "already_started", "info",
            f"Pembangunan unit sudah berjalan (progres {unit.get('construction_progress') or 0}%).",
            None))

    blockers = [r for r in reasons if r["severity"] == "blocker"]
    warnings = [r for r in reasons if r["severity"] == "warning"]
    state = ("started" if started else
             "blocked" if blockers else
             "warning" if warnings else "ready")
    return {
        "unit_id": unit_id, "unit_code": unit.get("code"), "project_id": project_id,
        "state": state, "state_label": READINESS_LABEL[state],
        "can_start": bool(not started and not blockers),
        "needs_ack": bool(not started and not blockers and warnings),
        "reasons": reasons, "blockers": blockers, "warnings": warnings,
        "missing": missing,
        "mode": {"require_dp_before_start": require_dp, "block_build_without": block_codes,
                 "enforced": bool(require_dp or block_codes)},
        "checks": {
            "schedule": ({"id": sched["id"], "status": sched.get("status"),
                          "template_name": sched.get("template_name"),
                          "start_date": sched.get("start_date"),
                          "target_finish_date": sched.get("target_finish_date"),
                          "started_at": sched.get("build_started_at"),
                          "first_item": first_item} if sched else None),
            "payment": pay,
            "permits": {"total": cov["total"], "counts": cov["counts"],
                        "required": cov["required"], "state": cov["state"]},
        },
        "as_of": now_iso(),
    }


def _fmt(reasons: list) -> str:
    return " ".join(f"({i + 1}) {r['detail']}" for i, r in enumerate(reasons))


async def start_build(org: str, unit_id: str, actor: str, *, ack: bool = False,
                      reason: str = None) -> dict:
    """Mulai bangun: menjalankan langkah pertama + mencatat pengakuan peringatan."""
    ev = await evaluate(org, unit_id)
    if ev["state"] == "started":
        raise ValueError(f"Pembangunan unit {ev['unit_code']} sudah berjalan — "
                         "lanjutkan dari daftar langkah, bukan tombol mulai.")
    if ev["blockers"]:
        raise ValueError("Belum bisa dimulai. " + _fmt(ev["blockers"]))
    note = (reason or "").strip()
    if ev["warnings"]:
        if not ack:
            raise ValueError(
                f"Ada {len(ev['warnings'])} peringatan yang harus diakui sebelum mulai: "
                + _fmt(ev["warnings"])
                + " Centang konfirmasi dan tulis alasan agar keputusan ini tercatat.")
        if len(note) < MIN_REASON:
            raise ValueError(f"Alasan minimal {MIN_REASON} huruf — tulis dasar keputusan "
                             "memulai pembangunan meski ada peringatan.")
    sched = await db.build_schedules.find_one({"org_id": org, "unit_id": unit_id}, {"_id": 0})
    item = await db.build_items.find_one(
        {"org_id": org, "schedule_id": sched["id"], "status": {"$in": list(WORKABLE)}},
        {"_id": 0}, sort=[("order", 1)])
    if not item:
        raise ValueError("Tidak ada langkah yang siap dikerjakan pada jadwal unit ini.")
    started_item = await ba.start_item(org, item, sched, actor)
    ts = now_iso()
    await db.build_schedules.update_one({"id": sched["id"], "org_id": org}, {"$set": {
        "build_started_at": sched.get("build_started_at") or ts,
        "build_started_by": actor, "updated_at": ts,
    }, "$push": {"start_gate_log": {
        "at": ts, "by": actor, "acknowledged": bool(ev["warnings"]),
        "reason": note or None,
        "warnings": [{"code": w["code"], "detail": w["detail"]} for w in ev["warnings"]],
        "mode": ev["mode"],
    }}})
    fresh = await be.recompute_schedule(org, sched["id"])
    body = (f"Pembangunan unit {ev['unit_code']} dimulai oleh {actor}"
            + (f" dengan {len(ev['warnings'])} peringatan diakui: {note}"
               if ev["warnings"] else " tanpa peringatan."))
    await add_activity(entity_type="unit", entity_id=unit_id, type="system", body=body,
                       actor=actor, org_id=org)
    if ev["warnings"]:
        rows = await db.users.find({"org_id": org, "is_active": True,
                                    "role": {"$in": ["owner", "project_manager"]}},
                                   {"_id": 0, "email": 1}).to_list(20)
        for r in rows:
            if r["email"] == actor:
                continue
            await create_notification(
                user_email=r["email"],
                title=f"Mulai bangun dengan peringatan — unit {ev['unit_code']}",
                body=body, type="alert", related_entity_type="unit",
                related_entity_id=unit_id, org_id=org)
    await emit("build.started", "unit", unit_id,
               {"label": ev["unit_code"], "warnings": len(ev["warnings"]),
                "acknowledged": bool(ev["warnings"]), "reason": note or None},
               org_id=org)
    logger.info("Mulai bangun unit %s oleh %s (peringatan=%s)", ev["unit_code"], actor,
                len(ev["warnings"]))
    return {"started": True, "unit_id": unit_id, "unit_code": ev["unit_code"],
            "item": started_item, "schedule": fresh,
            "acknowledged": bool(ev["warnings"]), "reason": note or None,
            "warnings": ev["warnings"], "readiness": await evaluate(org, unit_id)}
