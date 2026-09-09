"""KALIBRASI TEMPLATE JADWAL (Fase 37) — dari Analitik Telat langsung ke template.

Mengapa modul ini ada?
  Fase 32 sudah menghitung pekerjaan mana yang paling sering telat dan memberi
  **rekomendasi kalibrasi**. Tetapi ujung rekomendasinya hanya kalimat "buka Template
  Jadwal → ubah hari mulai/selesai langkah ini": supervisor harus pindah layar, mencari
  langkahnya, lalu MENGETIK ULANG SELURUH template (`PUT /build/templates/{id}` menuntut
  payload penuh). Akibatnya di lapangan kalibrasi tidak pernah dilakukan dan template
  tetap tidak realistis — analitik jadi hiasan.

Tiga jenis kalibrasi (SSOT `calibration_kind`):
  1. `step_duration`   — ubah durasi langkah (± hari kerja). Langkah SETELAHNYA ikut
     bergeser agar template tetap konsisten (tanpa tumpang tindih / lompatan).
  2. `wait_time`       — ubah lamanya waktu tunggu wajib SEBELUM langkah boleh dimulai
     (mis. curing beton). Ini menahan gerbang kesiapan saat berjalan.
  3. `wait_into_plan`  — MASUKKAN waktu tunggu itu ke tanggal rencana. Ini menutup
     kebutaan model yang lama: `wait_days` hanya menahan gerbang saat berjalan tetapi
     TIDAK pernah masuk `day_from/day_to`, sehingga rencana sistematis optimistis dan
     pekerjaan yang wajib menunggu curing tercatat "telat" — padahal fisika betonnya
     yang tidak bisa dipaksa.

Kejujuran yang dijaga (tidak boleh dilanggar):
  * **Pratinjau = hasil**: `plan()` dipakai pratinjau DAN eksekusi.
  * **Jadwal unit yang sudah ada TIDAK diubah** — bukti kerja tidak boleh bergeser.
    Angka baru berlaku untuk jadwal BERIKUTNYA. Mengubah tanggal jadwal berjalan tetap
    lewat Fase 34 (`POST /build/bulk/shift`, wajib penyebab + catatan).
  * Setiap kalibrasi menyimpan **sebelum→sesudah** sehingga bisa dikembalikan tepat, dan
    masuk `audit_logs`.
"""
import logging
import math

from core_utils import new_id, now_iso
from db import db, ORG_ID
from reference_p37 import CALIBRATION_KINDS, CAUSE_LABEL, KIND_LABEL

logger = logging.getLogger("sipro.build.calibration")

COLLECTION = "build_calibrations"
KINDS = CALIBRATION_KINDS
MAX_TEMPLATE_DAYS = 400
MAX_WAIT_DAYS = 60
DEFAULT_WDPW = 6


# ============================ util ============================
async def ensure_indexes():
    """Satu `client_ref` = satu kalibrasi (klik ganda tidak boleh dobel)."""
    await db.build_calibrations.create_index(
        [("org_id", 1), ("client_ref", 1)], name="uq_calibration_client_ref", unique=True,
        partialFilterExpression={"client_ref": {"$type": "string"}})
    await db.build_calibrations.create_index([("org_id", 1), ("template_id", 1),
                                             ("created_at", -1)], name="ix_calibration_tpl")


def _sorted_steps(tpl: dict) -> list:
    return sorted(list(tpl.get("steps") or []),
                  key=lambda s: (int(s.get("day_from") or 0), str(s.get("code"))))


def _wdpw(tpl: dict) -> int:
    try:
        return max(1, int(tpl.get("work_days_per_week") or DEFAULT_WDPW))
    except (TypeError, ValueError):
        return DEFAULT_WDPW


def _week_of(day_from: int, wdpw: int) -> int:
    return max(1, math.ceil(max(1, int(day_from)) / wdpw))


def _total_days(steps: list) -> int:
    return max([int(s.get("day_to") or s.get("day_from") or 1) for s in steps], default=0)


def _snap(step: dict) -> dict:
    return {"code": step.get("code"), "name": step.get("name"),
            "day_from": int(step.get("day_from") or 1),
            "day_to": int(step.get("day_to") or step.get("day_from") or 1),
            "week": int(step.get("week") or 1),
            "wait_days": int(step.get("wait_days") or 0),
            "duration": (int(step.get("day_to") or step.get("day_from") or 1)
                         - int(step.get("day_from") or 1) + 1)}


def _pred_end(steps: list, step: dict) -> int:
    """Hari terakhir pendahulu langsung (0 bila langkah ini tidak punya pendahulu)."""
    codes = set(step.get("predecessors") or [])
    if not codes:
        return 0
    return max([int(s.get("day_to") or s.get("day_from") or 1)
                for s in steps if s.get("code") in codes], default=0)


# ============================ perhitungan (pratinjau = hasil) ============================
def plan(tpl: dict, step_code: str, kind: str, delta_days: int = 0) -> dict:
    """Hitung dampak satu kalibrasi. TIDAK menulis apa pun.

    Dipakai oleh pratinjau MAUPUN eksekusi supaya pratinjau tidak bisa berbohong.
    """
    if kind not in KINDS:
        raise ValueError("Jenis kalibrasi tidak dikenal.")
    steps = _sorted_steps(tpl)
    if not steps:
        raise ValueError("Template ini belum punya langkah pekerjaan.")
    target = next((s for s in steps if s.get("code") == step_code), None)
    if not target:
        raise ValueError(f"Langkah '{step_code}' tidak ada pada template "
                         f"{tpl.get('code')}.")
    wdpw = _wdpw(tpl)
    before_target = _snap(target)
    before_total = _total_days(steps)

    shift = 0
    wait_after = before_target["wait_days"]
    if kind == "step_duration":
        new_dur = before_target["duration"] + int(delta_days)
        if int(delta_days) == 0:
            raise ValueError("Tidak ada perubahan: jumlah hari kalibrasi masih 0.")
        if new_dur < 1:
            raise ValueError(f"Durasi minimal 1 hari kerja — '{step_code}' sekarang "
                             f"{before_target['duration']} hari, tidak bisa dikurangi "
                             f"{abs(int(delta_days))} hari.")
        shift = int(delta_days)
    elif kind == "wait_time":
        wait_after = before_target["wait_days"] + int(delta_days)
        if int(delta_days) == 0:
            raise ValueError("Tidak ada perubahan: jumlah hari kalibrasi masih 0.")
        if wait_after < 0:
            raise ValueError(f"Waktu tunggu tidak bisa negatif — sekarang "
                             f"{before_target['wait_days']} hari.")
        if wait_after > MAX_WAIT_DAYS:
            raise ValueError(f"Waktu tunggu maksimal {MAX_WAIT_DAYS} hari.")
    else:  # wait_into_plan
        if not before_target["wait_days"]:
            raise ValueError(f"'{step_code}' tidak punya waktu tunggu wajib, jadi tidak ada "
                             "yang perlu dimasukkan ke rencana. Pakai kalibrasi durasi bila "
                             "tanggalnya yang terlalu ketat.")
        gap = before_target["day_from"] - _pred_end(steps, target) - 1
        shift = before_target["wait_days"] - gap
        if shift <= 0:
            raise ValueError(f"Rencana sudah memberi jeda {gap} hari sebelum '{step_code}', "
                             f"sudah cukup untuk waktu tunggu {before_target['wait_days']} "
                             "hari. Tidak ada yang perlu digeser.")

    # ---- bangun daftar langkah baru (salinan, tidak menyentuh dokumen asli)
    new_steps, rows = [], []
    for s in steps:
        row = dict(s)
        d_from = int(row.get("day_from") or 1)
        d_to = int(row.get("day_to") or d_from)
        changed = False
        if row.get("code") == step_code:
            if kind == "step_duration":
                d_to = d_from + before_target["duration"] + int(delta_days) - 1
                changed = True
            elif kind == "wait_into_plan":
                d_from, d_to = d_from + shift, d_to + shift
                changed = True
            else:
                row["wait_days"] = wait_after
                changed = True
        elif shift and d_from > before_target["day_to"]:
            # Hanya langkah yang benar-benar MULAI setelah langkah ini selesai yang bergeser.
            # Langkah paralel (rentangnya bertumpang dengan langkah ini) sengaja dibiarkan
            # supaya kalibrasi tidak diam-diam mengubah urutan kerja yang sudah disepakati.
            d_from, d_to = d_from + shift, d_to + shift
            changed = True
        row["day_from"], row["day_to"] = d_from, d_to
        row["week"] = _week_of(d_from, wdpw)
        new_steps.append(row)
        if changed:
            rows.append({"code": row.get("code"), "name": row.get("name"),
                         "before": _snap(s), "after": _snap(row),
                         "is_target": row.get("code") == step_code})

    after_total = _total_days(new_steps)
    if after_total > MAX_TEMPLATE_DAYS:
        raise ValueError(f"Total durasi template menjadi {after_total} hari kerja "
                         f"(batas {MAX_TEMPLATE_DAYS}). Periksa kembali angkanya.")

    return {
        "kind": kind, "kind_label": KIND_LABEL.get(kind, kind),
        "template_id": tpl.get("id"), "template_code": tpl.get("code"),
        "template_name": tpl.get("name"), "step_code": step_code,
        "step_name": target.get("name"), "delta_days": int(delta_days),
        "shift_days": shift, "wait_after": wait_after,
        "before": before_target, "after": _snap(next(
            s for s in new_steps if s.get("code") == step_code)),
        "rows": rows, "shifted_count": len([r for r in rows if not r["is_target"]]),
        "total_days_before": before_total, "total_days_after": after_total,
        "steps": new_steps,
        "explain": _explain(kind, target, before_target, wait_after, shift,
                            before_total, after_total),
        "moves_planned_dates": bool(shift),
    }


def _explain(kind: str, target: dict, before: dict, wait_after: int, shift: int,
             total_before: int, total_after: int) -> str:
    """Satu kalimat yang menjelaskan akibatnya dengan jujur (dipakai UI & POC)."""
    name = target.get("name")
    if kind == "step_duration":
        arah = "bertambah" if shift > 0 else "berkurang"
        return (f"Durasi '{name}' {arah} {abs(shift)} hari kerja "
                f"({before['duration']} → {before['duration'] + shift} hari). Total durasi "
                f"template {total_before} → {total_after} hari kerja.")
    if kind == "wait_time":
        return (f"Waktu tunggu wajib sebelum '{name}' menjadi {wait_after} hari "
                f"(sebelumnya {before['wait_days']} hari). Ini menahan gerbang kesiapan saat "
                "berjalan; TANGGAL RENCANA tidak berubah — bila tanggalnya yang terlalu "
                "ketat, pakai kalibrasi durasi atau masukkan waktu tunggu ke rencana.")
    return (f"'{name}' digeser {shift} hari kerja supaya jaraknya dari pekerjaan pendahulu "
            f"minimal {before['wait_days']} hari — sesuai waktu tunggu wajib (mis. curing) "
            "yang selama ini TIDAK pernah masuk tanggal rencana. Waktu tunggunya tidak "
            f"dipersingkat. Total durasi template {total_before} → {total_after} hari kerja.")


# ============================ dampak nyata (jujur) ============================
async def impact(org: str, tpl: dict) -> dict:
    """Berapa jadwal berjalan yang TIDAK diubah, dan berapa rumah yang akan memakai angka baru."""
    running = await db.build_schedules.count_documents(
        {"org_id": org, "template_id": tpl.get("id")})
    types = list(tpl.get("unit_types") or [])
    uq = {"org_id": org}
    if types:
        # Tipe unit disimpan pada field `type` di koleksi `units` (sama seperti dipakai
        # `build_engine._pick_template` & `build_bulk`) — bukan `unit_type`. Salah nama field
        # membuat angka "rumah belum terjadwal" selalu 0 alias pratinjau membohongi perencana.
        uq["type"] = {"$in": types}
    if tpl.get("project_id"):
        uq["project_id"] = tpl.get("project_id")
    units = await db.units.find(uq, {"_id": 0, "id": 1}).to_list(3000)
    ids = [u["id"] for u in units]
    scheduled = set()
    if ids:
        rows = await db.build_schedules.find(
            {"org_id": org, "unit_id": {"$in": ids}}, {"_id": 0, "unit_id": 1}).to_list(3000)
        scheduled = {r["unit_id"] for r in rows}
    return {
        "schedules_running": running,
        "schedules_unchanged_note": (
            f"{running} jadwal unit yang sudah dibuat TIDAK diubah — bukti kerja tidak boleh "
            "bergeser. Untuk menggeser tanggal jadwal berjalan, pakai 'Geser jadwal' "
            "(wajib penyebab + catatan)." if running else
            "Belum ada jadwal unit yang memakai template ini."),
        "units_matching": len(ids),
        "units_unscheduled": len([i for i in ids if i not in scheduled]),
        "unit_types": types,
    }


# ============================ eksekusi ============================
async def _template(org: str, template_id: str) -> dict:
    tpl = await db.build_templates.find_one({"id": template_id, "org_id": org}, {"_id": 0})
    if not tpl:
        raise ValueError("Template tidak ditemukan.")
    return tpl


async def preview(org: str, data: dict) -> dict:
    tpl = await _template(org, data["template_id"])
    out = plan(tpl, data["step_code"], data["kind"], int(data.get("delta_days") or 0))
    out["impact"] = await impact(org, tpl)
    out.pop("steps", None)          # pratinjau tidak perlu membawa seluruh template
    return out


async def apply(org: str, actor: str, data: dict) -> dict:
    """Terapkan kalibrasi ke template + catat jejaknya. Idempoten lewat `client_ref`."""
    ref = (data.get("client_ref") or "").strip() or None
    if ref:
        seen = await db.build_calibrations.find_one({"org_id": org, "client_ref": ref},
                                                   {"_id": 0})
        if seen:
            logger.info("Kalibrasi diputar ulang (client_ref sama): %s", ref)
            return {"calibration": seen, "replayed": True,
                    "template": await _template(org, seen["template_id"])}
    tpl = await _template(org, data["template_id"])
    out = plan(tpl, data["step_code"], data["kind"], int(data.get("delta_days") or 0))
    imp = await impact(org, tpl)
    version = int(tpl.get("version") or 1) + 1
    doc = {
        "id": new_id(), "org_id": org, "template_id": tpl["id"],
        "template_code": tpl.get("code"), "template_name": tpl.get("name"),
        "step_code": out["step_code"], "step_name": out["step_name"],
        "kind": out["kind"], "kind_label": out["kind_label"],
        "delta_days": out["delta_days"], "shift_days": out["shift_days"],
        "cause": data.get("cause"), "cause_label": CAUSE_LABEL.get(data.get("cause")),
        "note": (data.get("note") or "").strip(), "source": data.get("source"),
        "rows": out["rows"], "explain": out["explain"],
        "total_days_before": out["total_days_before"],
        "total_days_after": out["total_days_after"],
        "template_version_before": int(tpl.get("version") or 1),
        "template_version_after": version,
        "schedules_running_at_apply": imp["schedules_running"],
        "units_unscheduled_at_apply": imp["units_unscheduled"],
        "actor": actor, "created_at": now_iso(), "client_ref": ref,
        "rolled_back_at": None, "rolled_back_by": None, "rollback_of": None,
    }
    await db.build_calibrations.insert_one(dict(doc))
    await db.build_templates.update_one(
        {"id": tpl["id"], "org_id": org},
        {"$set": {"steps": out["steps"], "version": version, "updated_at": now_iso(),
                  "updated_by": actor, "last_calibrated_at": doc["created_at"],
                  "last_calibrated_by": actor}})
    logger.info("Template %s dikalibrasi (%s/%s) oleh %s", tpl.get("code"),
                out["kind"], out["step_code"], actor)
    return {"calibration": doc, "replayed": False,
            "template": await _template(org, tpl["id"]), "impact": imp}


async def rollback(org: str, actor: str, calibration_id: str, note: str,
                   client_ref: str = None) -> dict:
    """Kembalikan template ke nilai sebelum kalibrasi ini — tepat, bukan kira-kira."""
    cal = await db.build_calibrations.find_one({"id": calibration_id, "org_id": org},
                                              {"_id": 0})
    if not cal:
        raise ValueError("Kalibrasi tidak ditemukan.")
    if cal.get("rolled_back_at"):
        raise ValueError("Kalibrasi ini sudah dikembalikan "
                         f"({str(cal['rolled_back_at'])[:10]} oleh {cal.get('rolled_back_by')}).")
    if cal.get("rollback_of"):
        raise ValueError("Baris ini adalah pembatalan kalibrasi — tidak bisa dibatalkan lagi. "
                         "Terapkan kalibrasi baru bila perlu.")
    tpl = await _template(org, cal["template_id"])
    by_code = {s.get("code"): s for s in tpl.get("steps") or []}
    for row in cal.get("rows") or []:
        cur, aft = by_code.get(row["code"]), row["after"]
        if not cur:
            raise ValueError(f"Langkah '{row['code']}' sudah tidak ada di template — "
                             "kembalikan secara manual di Template Jadwal.")
        same = (int(cur.get("day_from") or 1) == aft["day_from"]
                and int(cur.get("day_to") or 1) == aft["day_to"]
                and int(cur.get("wait_days") or 0) == aft["wait_days"])
        if not same:
            raise ValueError(
                f"Template sudah berubah setelah kalibrasi ini (langkah {row['code']}). "
                "Kembalikan kalibrasi yang paling baru lebih dulu supaya tidak ada "
                "perubahan orang lain yang terhapus tanpa sengaja.")
    steps = []
    for s in tpl.get("steps") or []:
        row = next((r for r in cal.get("rows") or [] if r["code"] == s.get("code")), None)
        if not row:
            steps.append(s)
            continue
        bef = row["before"]
        steps.append({**s, "day_from": bef["day_from"], "day_to": bef["day_to"],
                      "week": bef["week"], "wait_days": bef["wait_days"]})
    version = int(tpl.get("version") or 1) + 1
    ts = now_iso()
    reverse = {
        "id": new_id(), "org_id": org, "template_id": tpl["id"],
        "template_code": tpl.get("code"), "template_name": tpl.get("name"),
        "step_code": cal["step_code"], "step_name": cal.get("step_name"),
        "kind": cal["kind"], "kind_label": cal.get("kind_label"),
        "delta_days": -int(cal.get("delta_days") or 0),
        "shift_days": -int(cal.get("shift_days") or 0),
        "cause": "pembatalan_kalibrasi",
        "cause_label": CAUSE_LABEL.get("pembatalan_kalibrasi"),
        "note": note.strip(), "source": "rollback",
        "rows": [{"code": r["code"], "name": r["name"], "before": r["after"],
                  "after": r["before"], "is_target": r["is_target"]}
                 for r in cal.get("rows") or []],
        "explain": (f"Kalibrasi {cal.get('kind_label')} pada '{cal.get('step_name')}' "
                    "dikembalikan ke nilai sebelumnya."),
        "total_days_before": cal.get("total_days_after"),
        "total_days_after": cal.get("total_days_before"),
        "template_version_before": int(tpl.get("version") or 1),
        "template_version_after": version,
        "schedules_running_at_apply": cal.get("schedules_running_at_apply"),
        "units_unscheduled_at_apply": cal.get("units_unscheduled_at_apply"),
        "actor": actor, "created_at": ts,
        "client_ref": (client_ref or "").strip() or None,
        "rolled_back_at": None, "rolled_back_by": None, "rollback_of": cal["id"],
    }
    await db.build_calibrations.insert_one(dict(reverse))
    await db.build_calibrations.update_one(
        {"id": cal["id"], "org_id": org},
        {"$set": {"rolled_back_at": ts, "rolled_back_by": actor}})
    await db.build_templates.update_one(
        {"id": tpl["id"], "org_id": org},
        {"$set": {"steps": steps, "version": version, "updated_at": ts,
                  "updated_by": actor}})
    return {"calibration": reverse, "reverted": cal["id"],
            "template": await _template(org, tpl["id"])}


# ============================ daftar & riwayat ============================
async def history(org: str, template_id: str = None, limit: int = 50) -> list:
    q = {"org_id": org}
    if template_id:
        q["template_id"] = template_id
    rows = await db.build_calibrations.find(q, {"_id": 0}).sort(
        "created_at", -1).to_list(max(1, min(int(limit or 50), 200)))
    return rows


async def applied_map(org: str) -> tuple:
    """Kalibrasi yang MASIH berlaku, dua sudut pandang.

    1. `by_kind`: (template_id, step_code, kind) → kalibrasi terakhir yang masih berlaku.
       Dipakai agar kartu rekomendasi tidak menyuruh mengerjakan hal yang sudah dikerjakan.
    2. `by_step`: (template_id, step_code) → kalibrasi terakhir apa pun jenisnya, supaya
       daftar langkah template bisa menandai "sudah dikalibrasi" untuk SEMUA langkah —
       bukan hanya langkah yang kebetulan muncul di tabel telat.
    """
    rows = await db.build_calibrations.find(
        {"org_id": org, "rolled_back_at": None, "rollback_of": None},
        {"_id": 0}).sort("created_at", -1).to_list(500)
    by_kind, by_step = {}, {}
    for r in rows:
        by_kind.setdefault((r["template_id"], r["step_code"], r["kind"]), r)
        by_step.setdefault((r["template_id"], r["step_code"]), r)
    return by_kind, by_step


def _applied_badge(cal: dict) -> dict:
    """Ringkasan kalibrasi aktif yang cukup untuk ditampilkan & dibatalkan dari UI."""
    if not cal:
        return None
    return {"id": cal["id"], "at": cal["created_at"], "by": cal.get("actor"),
            "kind": cal.get("kind"), "kind_label": cal.get("kind_label"),
            "delta_days": cal.get("delta_days"), "shift_days": cal.get("shift_days"),
            "cause": cal.get("cause"), "cause_label": cal.get("cause_label"),
            "note": cal.get("note")}


async def candidates(org: str, user: dict, project_id: str = None) -> dict:
    """Rekomendasi Analitik Telat + langkah template yang bisa dikalibrasi sekali klik."""
    import build_analytics as ban
    data = await ban.delays(org, project_id)
    codes = {c for s in data.get("by_step") or [] for c in (s.get("templates") or [])}
    codes |= {c for r in data.get("recommendations") or []
              for c in ((r.get("calibration") or {}).get("templates") or [])}
    # SEMUA template dibawa (bukan hanya yang muncul di data telat): perencana harus bisa
    # mengalibrasi template mana pun dari satu layar. Yang punya bukti telat didahulukan.
    tpls = await db.build_templates.find(
        {"org_id": org}, {"_id": 0, "id": 1, "code": 1, "name": 1, "steps": 1, "version": 1,
                          "work_days_per_week": 1, "unit_types": 1, "project_id": 1,
                          "last_calibrated_at": 1, "last_calibrated_by": 1}).to_list(100)
    tpls.sort(key=lambda t: (0 if t.get("code") in codes else 1, str(t.get("code"))))
    by_code = {t["code"]: t for t in tpls}
    done, done_step = await applied_map(org)

    # bukti telat per (template_code, step_code) supaya daftar langkah template bisa
    # menampilkan alasan kalibrasi tanpa pindah layar
    late_by = {}
    for s in data.get("by_step") or []:
        for c in s.get("templates") or []:
            late_by[(c, s["step_code"])] = {
                "units_total": s["units_total"], "units_late": s["units_late"],
                "avg_days": s["avg_days"], "max_days": s["max_days"],
                "late_rate": s["late_rate"], "rework": s["rework"],
                "dominant_cause": s.get("dominant_cause"), "unit_codes": s.get("unit_codes"),
            }

    def _resolve(tpl_codes: list, step_code: str, kind: str) -> list:
        """Satu rekomendasi bisa menyangkut beberapa template — JANGAN diam-diam semuanya."""
        out = []
        for code in tpl_codes or []:
            tpl = by_code.get(code)
            if not tpl:
                continue
            step = next((s for s in tpl.get("steps") or []
                         if s.get("code") == step_code), None)
            if not step:
                continue
            hit = done.get((tpl["id"], step_code, kind))
            out.append({
                "template_id": tpl["id"], "template_code": code,
                "template_name": tpl.get("name"),
                "current": _snap(step), "version": int(tpl.get("version") or 1),
                # `kind` + `shift_days` ikut dibawa BUKAN hiasan: untuk `wait_into_plan`
                # angka `delta_days` memang 0 (pergeserannya dihitung sistem), jadi tanpa
                # `shift_days` badge di UI berbunyi "sudah diterapkan 0 hari" padahal
                # rencananya bergeser 3 hari — persis jenis angka bohong yang fase ini tutup.
                "applied": ({"at": hit["created_at"], "by": hit["actor"],
                             "note": hit.get("note"), "delta_days": hit.get("delta_days"),
                             "kind": hit.get("kind"), "shift_days": hit.get("shift_days"),
                             "id": hit["id"]} if hit else None),
            })
        return out

    recs = []
    for r in data.get("recommendations") or []:
        cal = r.get("calibration")
        item = {**r, "targets": []}
        if cal:
            item["targets"] = _resolve(cal.get("templates") or r.get("templates"),
                                       cal.get("step_code") or r.get("step_code"),
                                       cal.get("kind"))
        recs.append(item)
    steps = []
    for s in data.get("by_step") or []:
        steps.append({**s, "targets": _resolve(s.get("templates"), s["step_code"],
                                               "step_duration")})
    return {"summary": data.get("summary"), "recommendations": recs, "steps": steps,
            "templates": [_template_card(t, done_step, late_by) for t in tpls],
            "history": await history(org, None, 12)}


def _template_card(tpl: dict, done_step: dict, late_by: dict) -> dict:
    """Template + SELURUH langkahnya siap tampil di layar kalibrasi (satu panggilan API).

    Tanpa ini frontend harus memanggil `/build/templates/{id}` per template lalu menebak
    sendiri langkah mana yang sudah dikalibrasi — tebakan yang mudah salah dan tidak
    punya SSOT. Angka di sini adalah angka template yang berlaku SEKARANG.
    """
    steps = _sorted_steps(tpl)
    out = []
    for s in steps:
        snap = _snap(s)
        snap.update({
            "week": int(s.get("week") or 1),
            "weight": float(s.get("weight") or 0),
            "predecessors": list(s.get("predecessors") or []),
            "wait_reason": s.get("wait_reason"),
            "hold_point": bool(s.get("hold_point")),
            "work_category": s.get("work_category"),
            "applied": _applied_badge(done_step.get((tpl["id"], s.get("code")))),
            "late": late_by.get((tpl.get("code"), s.get("code"))),
        })
        out.append(snap)
    return {"id": tpl["id"], "code": tpl.get("code"), "name": tpl.get("name"),
            "version": int(tpl.get("version") or 1),
            "work_days_per_week": _wdpw(tpl), "unit_types": list(tpl.get("unit_types") or []),
            "project_id": tpl.get("project_id"), "total_days": _total_days(steps),
            "steps_count": len(steps),
            "last_calibrated_at": tpl.get("last_calibrated_at"),
            "last_calibrated_by": tpl.get("last_calibrated_by"),
            "calibrated_steps": len([s for s in out if s.get("applied")]),
            "late_steps": len([s for s in out if s.get("late")]),
            "steps": out}
