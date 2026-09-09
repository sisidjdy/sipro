"""Fase 34 — JADWAL MASSAL & GESER TANGGAL SERENTAK (mesin).

Masalah bisnis yang ditutup (nyata, terlihat di data):
  * Menjadwalkan rumah SATU-SATU tidak mungkin untuk proyek puluhan/ratusan unit.
    Akibatnya banyak rumah berjalan TANPA tenggat, TANPA pengingat, TANPA eskalasi
    (pada data demo: 14 dari 18 unit belum punya jadwal).
  * Ketika proyek mundur (hujan, material telat, izin), tanggal harus digeser
    SERENTAK. Sebelum fase ini satu-satunya cara adalah MENGHAPUS lalu membuat ulang
    jadwal — yang MEMBAKAR bukti kerja (foto + checklist + verifikasi) dan memutus
    jejak audit. Sekarang penggeseran = operasi resmi yang beralasan dan tercatat.

Invarian yang ditegakkan di sini (diuji `scripts/poc_34.py`, dijaga `verify_34.py`):
  INV-34-1 Pekerjaan yang SUDAH selesai & terverifikasi TIDAK boleh berubah tanggal.
  INV-34-2 Geser massal WAJIB beralasan (SSOT `build_delay_cause`) + catatan ≥10 huruf.
  INV-34-3 Jadwal massal tidak menimpa jadwal yang sudah ada (dilewati + alasan).
  INV-34-4 Unit tipe non-bangunan (kavling) tidak bisa dijadwalkan.
  INV-34-5 Hanya Manajer Proyek/direksi (dijaga router).
  INV-34-6 Pratinjau = hasil: satu fungsi hitung dipakai pratinjau DAN eksekusi.
  INV-34-7 Setelah geser: gerbang & progres dihitung ulang (tidak ada 'telat' palsu).
  INV-34-8 Batas 100 unit per operasi + `client_ref` idempoten (klik ganda tidak dobel).
  INV-34-9 Geser ke belakang tidak boleh menaruh pekerjaan belum selesai SEBELUM
           pekerjaan yang sudah diverifikasi.
"""
import logging
from datetime import timedelta

import build_catalog as bcat
import build_calendar as bcal
import build_engine as be
import indexes as ix
import reference as ref
from core_utils import new_id, now_iso, today_iso_date
from db import db
from engine import add_activity, create_notification, emit

logger = logging.getLogger("sipro.build.bulk")

MAX_BATCH = 100
SHIFT_MIN, SHIFT_MAX = -180, 365
WAVE_MODES = ("same", "per_unit", "per_block")


async def ensure_indexes():
    """Index operasi massal — idempotensi dijaga DATABASE, bukan hanya kode."""
    await db.build_bulk_runs.create_index([("org_id", 1), ("created_at", -1)])
    # Partial index (bukan sparse): pada index gabungan, `sparse` tidak melewati dokumen
    # yang `client_ref`-nya kosong sehingga operasi massal KEDUA tanpa penanda akan
    # bentrok "null" dan gagal 500. Lihat indexes.ensure_optional_unique.
    await ix.ensure_optional_unique(
        "build_bulk_runs", [("org_id", 1), ("kind", 1), ("client_ref", 1)],
        "uq_build_bulk_client_ref", "client_ref")


def block_of(code: str) -> str:
    """Blok/cluster diturunkan dari kode unit ('A-01' → 'A'), bukan field baru."""
    c = str(code or "").strip()
    if "-" in c:
        return c.split("-")[0].upper()
    return (c[:1].upper() or "-")


def plan_for_template(tpl: dict, start_date: str, cal: dict = None) -> dict:
    """Hitung tanggal mulai efektif + target selesai TANPA menulis ke database.

    Fase 36: bila `cal` (hasil `build_calendar.params_for`) diberikan, hari libur & pola
    hari kerja MASTER yang dipakai — pratinjau jadwal massal jadi sama persis dengan hasil
    `generate_schedule`. Tanpa `cal`, perilaku lama (nilai template) dipertahankan.
    """
    steps = tpl.get("steps") or []
    if not steps:
        raise ValueError("Template ini belum punya item pekerjaan.")
    if cal:
        mode, wdpw, holidays, off = cal["mode"], cal["wdpw"], cal["holidays"], cal["off_days"]
    else:
        mode = tpl.get("calendar_mode", "working_days")
        wdpw = int(tpl.get("work_days_per_week") or 6)
        holidays = set(tpl.get("holidays") or [])
        off = None
    start = be.next_workday(be._d(start_date), wdpw, holidays, off) \
        if mode == "working_days" else be._d(start_date)
    last = max(int(s.get("day_to") or s.get("day_from") or 1) for s in steps)
    finish = be.date_for_day(start, last, mode, wdpw, holidays, off)
    return {"start": start.isoformat(), "finish": finish.isoformat(),
            "items": len(steps), "days": last, "mode": mode}


async def plan_for_template_at(org: str, project_id: str, tpl: dict, start_date: str) -> dict:
    """Versi sadar-kalender (Fase 36) — dipakai kandidat & pratinjau jadwal massal."""
    cal = await bcal.params_for(org, project_id, tpl)
    return plan_for_template(tpl, start_date, cal)


async def _scheduled_unit_ids(org: str, project_id: str = None) -> list:
    q = {"org_id": org}
    if project_id:
        q["project_id"] = project_id
    return await db.build_schedules.distinct("unit_id", q)


# ============================ blok / kandidat ============================
async def blocks(org: str, project_id: str = None) -> list:
    """Ringkasan per blok: berapa rumah, sudah/belum terjadwal."""
    q = {"org_id": org}
    if project_id:
        q["project_id"] = project_id
    units = await db.units.find(q, {"_id": 0, "id": 1, "code": 1, "type": 1}).to_list(1000)
    have = set(await _scheduled_unit_ids(org, project_id))
    agg = {}
    for u in units:
        b = block_of(u.get("code"))
        row = agg.setdefault(b, {"block": b, "units": 0, "scheduled": 0, "unscheduled": 0,
                                "buildable": 0, "types": []})
        row["units"] += 1
        utype = u.get("type")
        if utype and utype not in row["types"]:
            row["types"].append(utype)
        buildable = utype not in bcat.NO_BUILD_UNIT_TYPES
        if buildable:
            row["buildable"] += 1
        if u["id"] in have:
            row["scheduled"] += 1
        elif buildable:
            row["unscheduled"] += 1
    return sorted(agg.values(), key=lambda r: r["block"])


async def candidates(org: str, project_id: str = None, block: str = None,
                     unit_type: str = None) -> list:
    """Unit yang BELUM punya jadwal + template yang akan dipakai / alasan tidak bisa."""
    have = await _scheduled_unit_ids(org, project_id)
    q = {"org_id": org, "id": {"$nin": have}}
    if project_id:
        q["project_id"] = project_id
    if unit_type:
        q["type"] = unit_type
    rows = await db.units.find(q, {"_id": 0, "id": 1, "code": 1, "type": 1, "status": 1,
                                   "project_id": 1, "lead_name": 1}).sort("code", 1).to_list(500)
    cache, out = {}, []
    today = today_iso_date()
    for u in rows:
        b = block_of(u.get("code"))
        if block and b != block:
            continue
        row = {**u, "block": b, "schedulable": False, "reason": None, "template_id": None,
               "template_code": None, "template_name": None, "template_days": 0,
               "template_items": 0}
        key = (u.get("project_id"), u.get("type"))
        if key not in cache:
            try:
                cache[key] = await be.template_for_unit(org, u)
            except ValueError as e:
                cache[key] = str(e)
        tpl = cache[key]
        if isinstance(tpl, str):
            row["reason"] = tpl
            out.append(row)
            continue
        try:
            plan = await plan_for_template_at(org, u.get("project_id"), tpl, today)
        except ValueError as e:
            row["reason"] = str(e)
            out.append(row)
            continue
        row.update({"schedulable": True, "template_id": tpl.get("id"),
                    "template_code": tpl.get("code"), "template_name": tpl.get("name"),
                    "template_days": plan["days"], "template_items": plan["items"]})
        out.append(row)
    return out


# ============================ jadwal massal ============================
async def plan_create(org: str, unit_ids: list, template_id: str = None,
                      start_date: str = None, stagger_days: int = 0,
                      wave: str = "same") -> dict:
    """SATU-SATUNYA sumber perhitungan jadwal massal (INV-34-6: pratinjau = hasil)."""
    if not unit_ids:
        raise ValueError("Pilih minimal satu unit rumah yang akan dijadwalkan.")
    if len(unit_ids) > MAX_BATCH:
        raise ValueError(f"Maksimal {MAX_BATCH} unit per operasi supaya bisa diperiksa "
                         "sebelum dijalankan. Bagi menjadi beberapa gelombang.")
    if wave not in WAVE_MODES:
        raise ValueError("Pola gelombang tidak dikenal. Pilih dari daftar.")
    if not start_date:
        raise ValueError("Tanggal mulai wajib — seluruh tenggat, pengingat, dan eskalasi "
                         "dihitung dari tanggal ini.")
    stagger_days = max(0, int(stagger_days or 0))
    units = await db.units.find({"org_id": org, "id": {"$in": list(unit_ids)}},
                               {"_id": 0}).to_list(MAX_BATCH + 10)
    by_id = {u["id"]: u for u in units}
    missing = [uid for uid in unit_ids if uid not in by_id]
    have = set(await _scheduled_unit_ids(org))
    ordered = sorted(by_id.values(), key=lambda u: str(u.get("code") or ""))
    seen_blocks, rows = [], []
    for idx, u in enumerate(ordered):
        b = block_of(u.get("code"))
        if b not in seen_blocks:
            seen_blocks.append(b)
        if wave == "per_unit":
            offset = idx * stagger_days
        elif wave == "per_block":
            offset = seen_blocks.index(b) * stagger_days
        else:
            offset = 0
        raw_start = (be._d(start_date) + timedelta(days=offset)).isoformat()
        row = {"unit_id": u["id"], "unit_code": u.get("code"), "unit_type": u.get("type"),
               "project_id": u.get("project_id"), "block": b, "start_date": raw_start,
               "target_finish_date": None, "items": 0, "template_id": None,
               "template_code": None, "template_name": None, "ok": False, "reason": None}
        if u["id"] in have:
            row["reason"] = ("Sudah punya jadwal — dilewati supaya jadwal & bukti kerja "
                             "yang berjalan tidak ditimpa.")
            rows.append(row)
            continue
        try:
            tpl = await be.template_for_unit(org, u, template_id)
            plan = await plan_for_template_at(org, u.get("project_id"), tpl, raw_start)
        except ValueError as e:
            row["reason"] = str(e)
            rows.append(row)
            continue
        row.update({"ok": True, "template_id": tpl.get("id"), "template_code": tpl.get("code"),
                    "template_name": tpl.get("name"), "start_date": plan["start"],
                    "target_finish_date": plan["finish"], "items": plan["items"]})
        rows.append(row)
    ready = [r for r in rows if r["ok"]]
    summary = {
        "selected": len(unit_ids), "ready": len(ready),
        "skipped": len(rows) - len(ready) + len(missing),
        "items_total": sum(int(r["items"]) for r in ready),
        "first_start": min((r["start_date"] for r in ready), default=None),
        "last_finish": max((r["target_finish_date"] for r in ready), default=None),
        "blocks": sorted({r["block"] for r in ready}),
        "missing": missing,
    }
    return {"rows": rows, "summary": summary}


async def run_create(org: str, unit_ids: list, template_id: str, start_date: str,
                     stagger_days: int, wave: str, user: dict,
                     client_ref: str = None) -> dict:
    """Jalankan jadwal massal. Idempoten lewat `client_ref` (INV-34-8)."""
    prior = await _prior_run(org, "schedule", client_ref)
    if prior:
        return prior
    plan = await plan_create(org, unit_ids, template_id, start_date, stagger_days, wave)
    actor = user.get("email")
    results, created, project_id = [], 0, None
    for r in plan["rows"]:
        if not r["ok"]:
            results.append({**r, "status": "skipped"})
            continue
        unit = await db.units.find_one({"id": r["unit_id"], "org_id": org}, {"_id": 0})
        try:
            tpl = await be.template_for_unit(org, unit, template_id)
            sched = await be.generate_schedule(org, unit, tpl, r["start_date"], actor)
            created += 1
            project_id = project_id or sched.get("project_id")
            results.append({**r, "status": "created", "schedule_id": sched["id"],
                            "items": int(sched.get("items_total") or 0),
                            "start_date": sched.get("start_date"),
                            "target_finish_date": sched.get("target_finish_date")})
        except ValueError as e:
            results.append({**r, "ok": False, "status": "failed", "reason": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.exception("bulk schedule gagal untuk unit %s", r.get("unit_code"))
            results.append({**r, "ok": False, "status": "failed",
                            "reason": f"Gagal tak terduga: {e}"})
    summary = {**plan["summary"], "created": created,
               "failed": len([x for x in results if x["status"] == "failed"])}
    params = {"start_date": start_date, "wave": wave, "stagger_days": int(stagger_days or 0),
              "template_id": template_id, "units": len(unit_ids), "project_id": project_id}
    run = await _save_run(org, "schedule", actor, client_ref, params, summary, results)
    if created:
        body = (f"{created} rumah kini punya jadwal berbukti "
                f"({summary['items_total']} item pekerjaan, mulai {summary['first_start']}, "
                f"target selesai terakhir {summary['last_finish']}).")
        await create_notification(user_email=actor, title=f"{created} jadwal pembangunan dibuat",
                                  body=body, type="success",
                                  related_entity_type="build_bulk_run",
                                  related_entity_id=run["id"], org_id=org)
        if project_id:
            await add_activity(entity_type="project", entity_id=project_id, type="system",
                               body=(f"Jadwal massal: {body} Dilewati {summary['skipped']} unit."),
                               actor=actor, org_id=org)
            await emit("build.bulk_scheduled", "project", project_id,
                       {"created": created, "run_id": run["id"]}, org_id=org)
    return run


# ============================ geser tanggal serentak ============================
async def shift_targets(org: str, project_id: str = None, block: str = None) -> list:
    """Jadwal yang bisa digeser + berapa pekerjaan yang tanggalnya terkunci bukti."""
    q = {"org_id": org}
    if project_id:
        q["project_id"] = project_id
    rows = await db.build_schedules.find(q, {"_id": 0, "id": 1, "unit_id": 1, "unit_code": 1,
                                             "unit_type": 1, "project_id": 1, "status": 1,
                                             "start_date": 1, "target_finish_date": 1,
                                             "progress": 1, "items_total": 1, "items_done": 1,
                                             "late_items": 1, "shift_history": 1,
                                             }).sort("unit_code", 1).to_list(400)
    out = []
    for r in rows:
        b = block_of(r.get("unit_code"))
        if block and b != block:
            continue
        hist = r.pop("shift_history", None) or []
        out.append({**r, "schedule_id": r["id"], "block": b, "shift_count": len(hist),
                    "last_shift": hist[-1] if hist else None})
    return out


async def plan_shift(org: str, schedule_ids: list, shift_days: int) -> dict:
    """SATU-SATUNYA sumber perhitungan penggeseran (INV-34-6). Tidak menulis apa pun."""
    if not schedule_ids:
        raise ValueError("Pilih minimal satu jadwal unit yang akan digeser.")
    if len(schedule_ids) > MAX_BATCH:
        raise ValueError(f"Maksimal {MAX_BATCH} jadwal per operasi. Bagi per blok.")
    days = int(shift_days or 0)
    if days == 0:
        raise ValueError("Jumlah hari geser tidak boleh 0. Isi angka positif untuk mundur "
                         "(proyek terlambat) atau negatif untuk maju.")
    if not (SHIFT_MIN <= days <= SHIFT_MAX):
        raise ValueError(f"Geser hanya boleh antara {SHIFT_MIN} dan {SHIFT_MAX} hari.")
    scheds = await db.build_schedules.find({"org_id": org, "id": {"$in": list(schedule_ids)}},
                                           {"_id": 0}).sort("unit_code", 1).to_list(MAX_BATCH + 10)
    today = today_iso_date()
    rows = []
    for s in scheds:
        items = await db.build_items.find({"org_id": org, "schedule_id": s["id"]},
                                          {"_id": 0}).sort("order", 1).to_list(500)
        done = [i for i in items if i.get("status") == "done"]
        movable = [i for i in items if i.get("status") != "done"]
        # Fase 36: kalender MASTER dipakai ulang di sini supaya penggeseran tidak menaruh
        # tenggat baru di hari libur (dulu daftar libur pada jadwal selalu kosong).
        cal = await bcal.params_for(org, s.get("project_id"), s)
        mode, wdpw, holidays, off = cal["mode"], cal["wdpw"], cal["holidays"], cal["off_days"]
        raw = be._d(s.get("start_date")) + timedelta(days=days)
        base = be.next_workday(raw, wdpw, holidays, off) if mode == "working_days" else raw
        moves = []
        for i in movable:
            ps = be.date_for_day(base, int(i.get("day_from") or 1), mode, wdpw, holidays, off)
            pf = be.date_for_day(base, int(i.get("day_to") or i.get("day_from") or 1),
                                 mode, wdpw, holidays, off)
            moves.append({"item_id": i["id"], "step_code": i.get("step_code"),
                          "name": i.get("name"), "assigned_to": i.get("assigned_to"),
                          "old_start": i.get("planned_start"), "new_start": ps.isoformat(),
                          "old_finish": i.get("planned_finish"), "new_finish": pf.isoformat()})
        last_done = max((str(i.get("planned_finish") or "") for i in done), default="")
        earliest = min((m["new_start"] for m in moves), default=None)
        new_finish = max((m["new_finish"] for m in moves),
                         default=str(s.get("target_finish_date") or ""))
        if last_done:
            new_finish = max(new_finish, last_done)
        conflict = None
        if last_done and earliest and earliest < last_done:
            conflict = (f"Geser {days} hari membuat pekerjaan yang belum selesai jatuh SEBELUM "
                        f"pekerjaan yang sudah diverifikasi (selesai {last_done}). "
                        "Kurangi jumlah harinya.")
        warning = None
        if not conflict and earliest and earliest < today:
            warning = (f"Sebagian tanggal baru sudah lewat (mulai {earliest}) — pekerjaan "
                       "akan langsung tercatat telat.")
        reason = conflict
        if not reason and not moves:
            reason = ("Semua pekerjaan sudah selesai & terverifikasi — tidak ada tanggal "
                      "yang boleh digeser (bukti terikat waktu).")
        rows.append({
            "schedule_id": s["id"], "unit_id": s.get("unit_id"), "unit_code": s.get("unit_code"),
            "project_id": s.get("project_id"), "block": block_of(s.get("unit_code")),
            "status": s.get("status"), "old_start": s.get("start_date"),
            "new_start": base.isoformat(), "old_finish": s.get("target_finish_date"),
            "new_finish": new_finish, "items_shifted": len(moves), "items_locked": len(done),
            "locked_note": (f"{len(done)} pekerjaan sudah diverifikasi — tanggalnya "
                            "dipertahankan (bukti terikat waktu).") if done else None,
            "conflict": conflict, "warning": warning, "reason": reason,
            "ok": bool(moves) and not conflict,
            "sample": moves[:3], "moves": moves,
        })
    ok_rows = [r for r in rows if r["ok"]]
    summary = {
        "selected": len(schedule_ids), "ready": len(ok_rows),
        "skipped": len(rows) - len(ok_rows), "shift_days": days,
        "items_shifted": sum(r["items_shifted"] for r in ok_rows),
        "items_locked": sum(r["items_locked"] for r in rows),
        "blocked_by_conflict": len([r for r in rows if r["conflict"]]),
        "new_last_finish": max((r["new_finish"] for r in ok_rows), default=None),
    }
    return {"rows": rows, "summary": summary}


def _cause_label(cause: str) -> str:
    return ref.label_of("build_delay_cause", cause)


async def run_shift(org: str, schedule_ids: list, shift_days: int, cause: str, note: str,
                    user: dict, client_ref: str = None) -> dict:
    """Geser tanggal serentak — beralasan, tercatat, dan menjaga bukti (INV-34-1/2/7)."""
    if cause not in ref.values("build_delay_cause"):
        raise ValueError("Penyebab penggeseran tidak dikenal. Pilih dari daftar.")
    clean = (note or "").strip()
    if len(clean) < 10:
        raise ValueError("Catatan penggeseran wajib (minimal 10 karakter) — ini jejak audit "
                         "kenapa tenggat rumah berubah.")
    prior = await _prior_run(org, "shift", client_ref)
    if prior:
        return prior
    plan = await plan_shift(org, schedule_ids, shift_days)
    actor, ts, today = user.get("email"), now_iso(), today_iso_date()
    label = _cause_label(cause)
    results, moved, notify = [], 0, {}
    for r in plan["rows"]:
        slim = {k: v for k, v in r.items() if k != "moves"}
        if not r["ok"]:
            results.append({**slim, "status": "skipped"})
            continue
        for m in r["moves"]:
            upd = {"planned_start": m["new_start"], "planned_finish": m["new_finish"],
                   "updated_at": ts}
            if m["new_finish"] >= today:
                upd.update({"late_days": 0, "escalation_level": 0, "escalated_at": None,
                            "reminded_on": None})
            await db.build_items.update_one({"id": m["item_id"], "org_id": org}, {"$set": upd})
            if m.get("assigned_to"):
                notify.setdefault(m["assigned_to"], set()).add(r["unit_code"])
        hist = {"at": ts, "actor": actor, "days": int(shift_days), "cause": cause,
                "cause_label": label, "note": clean, "from_start": r["old_start"],
                "to_start": r["new_start"], "from_finish": r["old_finish"],
                "to_finish": r["new_finish"], "items_shifted": r["items_shifted"],
                "items_locked": r["items_locked"]}
        await db.build_schedules.update_one({"id": r["schedule_id"], "org_id": org}, {
            "$set": {"start_date": r["new_start"], "target_finish_date": r["new_finish"],
                     "updated_at": ts},
            "$push": {"shift_history": hist}})
        await be.refresh_gates(org, r["schedule_id"])
        await be.recompute_schedule(org, r["schedule_id"])
        await add_activity(
            entity_type="unit", entity_id=r["unit_id"], type="system",
            body=(f"Jadwal digeser {shift_days:+d} hari ({label}): mulai {r['old_start']} → "
                  f"{r['new_start']}, target selesai {r['old_finish']} → {r['new_finish']}. "
                  f"{r['items_shifted']} pekerjaan digeser, {r['items_locked']} "
                  f"dipertahankan karena sudah diverifikasi. Catatan: {clean}"),
            actor=actor, org_id=org)
        moved += 1
        results.append({**slim, "status": "shifted"})
    summary = {**plan["summary"], "shifted": moved,
               "skipped": len([x for x in results if x["status"] == "skipped"]),
               "cause": cause, "cause_label": label, "note": clean}
    run = await _save_run(org, "shift", actor, client_ref,
                          {"shift_days": int(shift_days), "cause": cause, "note": clean,
                           "schedules": len(schedule_ids)}, summary, results)
    for email, units in notify.items():
        codes = ", ".join(sorted(units)[:8])
        await create_notification(
            user_email=email, title="Tenggat pekerjaan Anda berubah",
            body=(f"Jadwal digeser {shift_days:+d} hari ({label}) untuk unit {codes}. "
                  f"Alasan: {clean}. Buka Papan Mandor untuk tenggat terbaru."),
            type="warning", related_entity_type="build_bulk_run",
            related_entity_id=run["id"], org_id=org)
    return run


# ============================ riwayat operasi massal ============================
async def _prior_run(org: str, kind: str, client_ref: str) -> dict:
    if not client_ref:
        return None
    prior = await db.build_bulk_runs.find_one(
        {"org_id": org, "kind": kind, "client_ref": client_ref}, {"_id": 0})
    if prior:
        prior["idempotent_replay"] = True
    return prior


async def _save_run(org: str, kind: str, actor: str, client_ref: str, params: dict,
                    summary: dict, results: list) -> dict:
    doc = {"id": new_id(), "org_id": org, "kind": kind, "client_ref": client_ref,
           "actor": actor, "params": params, "summary": summary,
           "results": [{k: v for k, v in r.items() if k != "moves"} for r in results],
           "created_at": now_iso()}
    try:
        await db.build_bulk_runs.insert_one(dict(doc))
    except Exception:  # noqa: BLE001 — tabrakan client_ref = klik ganda, kembalikan yang ada
        prior = await _prior_run(org, kind, client_ref)
        if prior:
            return prior
        raise
    doc.pop("_id", None)
    return doc


async def runs(org: str, kind: str = None, limit: int = 20) -> list:
    q = {"org_id": org}
    if kind:
        q["kind"] = kind
    return await db.build_bulk_runs.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
