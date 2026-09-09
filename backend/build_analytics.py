"""ANALITIK KETERLAMBATAN (Fase 32).

Permintaan owner: "Tunjukkan pekerjaan dan pelaksana paling sering telat, supaya template
bisa dikalibrasi dari data nyata".

Semua angka berasal dari data yang sudah ada (`build_items`), jadi tidak ada input manual
yang bisa dipoles:
  * pekerjaan BELUM selesai & lewat tenggat  → telat berjalan (hari ini - rencana selesai)
  * pekerjaan SUDAH diverifikasi tetapi lewat → telat historis (tanggal verifikasi - rencana)

Keluarannya bukan hanya tabel, tetapi juga **rekomendasi kalibrasi template** yang bisa
langsung dieksekusi supervisor (durasi kurang, waktu tunggu tidak realistis, material
selalu terlambat, dsb) — supaya analitik benar-benar mengubah cara kerja.
"""
from datetime import date

from db import db
from core_utils import today_iso_date
from reference_p31 import DELAY_CAUSE_LABEL

FIELDS = {"_id": 0, "step_code": 1, "name": 1, "unit_id": 1, "unit_code": 1, "week": 1,
          "status": 1, "planned_start": 1, "planned_finish": 1, "verified_at": 1,
          "assigned_to": 1, "delay_cause": 1, "delay_note": 1, "schedule_id": 1,
          "wait_days": 1, "day_from": 1, "day_to": 1, "rework_count": 1}


def _late_days(item: dict, ref: str) -> int:
    pf = str(item.get("planned_finish") or "")[:10]
    if not pf:
        return 0
    end = str(item.get("verified_at") or "")[:10] if item.get("status") == "done" else ref
    if not end or end <= pf:
        return 0
    return (date.fromisoformat(end) - date.fromisoformat(pf)).days


def _avg(total: float, n: int) -> float:
    return round(total / n, 1) if n else 0.0


def _dominant(tally: dict) -> dict:
    if not tally:
        return None
    code = max(tally, key=tally.get)
    return {"cause": code, "label": DELAY_CAUSE_LABEL.get(code, code), "count": tally[code]}


async def delays(org: str, project_id: str = None) -> dict:
    ref = today_iso_date()
    q = {"org_id": org}
    if project_id:
        q["project_id"] = project_id
    items = await db.build_items.find(q, FIELDS).to_list(20000)
    scheds = await db.build_schedules.find(
        {"org_id": org, **({"project_id": project_id} if project_id else {})},
        {"_id": 0, "id": 1, "unit_type": 1, "template_code": 1, "unit_code": 1}).to_list(500)
    sched_by_id = {s["id"]: s for s in scheds}

    by_step, by_person, by_type = {}, {}, {}
    late_total, done_total, on_time_done = 0, 0, 0
    for it in items:
        late = _late_days(it, ref)
        sched = sched_by_id.get(it.get("schedule_id")) or {}
        is_done = it.get("status") == "done"
        if is_done:
            done_total += 1
            if not late:
                on_time_done += 1
        if late:
            late_total += 1

        key = it.get("step_code") or it.get("name") or "-"
        row = by_step.setdefault(key, {
            "step_code": it.get("step_code"), "name": it.get("name"),
            "week": it.get("week"), "planned_days": max(
                1, int(it.get("day_to") or 1) - int(it.get("day_from") or 1) + 1),
            "wait_days": int(it.get("wait_days") or 0),
            "units_total": 0, "units_late": 0, "days_total": 0, "max_days": 0,
            "causes": {}, "unit_codes": [], "rework": 0,
            "templates": set(), "unit_types": set()})
        row["units_total"] += 1
        row["rework"] += int(it.get("rework_count") or 0)
        if sched.get("template_code"):
            row["templates"].add(sched["template_code"])
        if sched.get("unit_type"):
            row["unit_types"].add(sched["unit_type"])
        if late:
            row["units_late"] += 1
            row["days_total"] += late
            row["max_days"] = max(row["max_days"], late)
            if it.get("delay_cause"):
                row["causes"][it["delay_cause"]] = row["causes"].get(it["delay_cause"], 0) + 1
            if len(row["unit_codes"]) < 8 and it.get("unit_code"):
                row["unit_codes"].append(it["unit_code"])

        who = it.get("assigned_to") or "(belum ada pelaksana)"
        prow = by_person.setdefault(who, {
            "assigned_to": who, "items_total": 0, "items_late": 0, "items_done": 0,
            "days_total": 0, "max_days": 0, "causes": {}, "no_cause": 0})
        prow["items_total"] += 1
        if is_done:
            prow["items_done"] += 1
        if late:
            prow["items_late"] += 1
            prow["days_total"] += late
            prow["max_days"] = max(prow["max_days"], late)
            if it.get("delay_cause"):
                prow["causes"][it["delay_cause"]] = prow["causes"].get(it["delay_cause"], 0) + 1
            else:
                prow["no_cause"] += 1

        utype = sched.get("unit_type") or "(tanpa tipe)"
        trow = by_type.setdefault(utype, {
            "unit_type": utype, "items_total": 0, "items_late": 0, "days_total": 0,
            "templates": set()})
        trow["items_total"] += 1
        if sched.get("template_code"):
            trow["templates"].add(sched["template_code"])
        if late:
            trow["items_late"] += 1
            trow["days_total"] += late

    steps = []
    for r in by_step.values():
        if not r["units_late"]:
            continue
        steps.append({
            "step_code": r["step_code"], "name": r["name"], "week": r["week"],
            "planned_days": r["planned_days"], "wait_days": r["wait_days"],
            "units_total": r["units_total"], "units_late": r["units_late"],
            "avg_days": _avg(r["days_total"], r["units_late"]), "max_days": r["max_days"],
            "late_rate": round(r["units_late"] / max(1, r["units_total"]) * 100),
            "rework": r["rework"], "unit_codes": r["unit_codes"],
            "dominant_cause": _dominant(r["causes"]),
            "templates": sorted(r["templates"]), "unit_types": sorted(r["unit_types"]),
        })
    steps.sort(key=lambda r: (-r["units_late"], -r["avg_days"]))

    people = []
    for r in by_person.values():
        people.append({
            "assigned_to": r["assigned_to"], "items_total": r["items_total"],
            "items_done": r["items_done"], "items_late": r["items_late"],
            "avg_days": _avg(r["days_total"], r["items_late"]), "max_days": r["max_days"],
            "late_rate": round(r["items_late"] / max(1, r["items_total"]) * 100),
            "dominant_cause": _dominant(r["causes"]),
            "unexplained": r["no_cause"],
        })
    people.sort(key=lambda r: (-r["items_late"], -r["avg_days"]))

    types = []
    for r in by_type.values():
        types.append({
            "unit_type": r["unit_type"], "items_total": r["items_total"],
            "items_late": r["items_late"], "avg_days": _avg(r["days_total"], r["items_late"]),
            "late_rate": round(r["items_late"] / max(1, r["items_total"]) * 100),
            "templates": sorted(r["templates"]),
        })
    types.sort(key=lambda r: -r["late_rate"])

    return {
        "as_of": ref,
        "summary": {
            "items_total": len(items), "items_late": late_total,
            "items_done": done_total, "on_time_done": on_time_done,
            "on_time_rate": round(on_time_done / done_total * 100) if done_total else 0,
            "unexplained": sum(1 for i in items
                               if _late_days(i, ref) and not i.get("delay_cause")),
        },
        "by_step": steps[:20], "by_person": people[:20], "by_unit_type": types,
        "recommendations": _recommend(steps, people, types),
    }


def _recommend(steps: list, people: list, types: list) -> list:
    """Rekomendasi kalibrasi template — spesifik, bisa langsung dikerjakan.

    Fase 37: setiap rekomendasi yang benar-benar bisa dieksekusi membawa objek
    `calibration` siap-pakai (`kind`, `step_code`, `templates`, `delta_days`) sehingga
    tombol "Kalibrasi" di layar Analitik Telat cukup meneruskannya ke
    `POST /build/calibration/preview` — tidak ada angka yang diketik ulang di UI dan
    tidak ada tafsir baru di frontend.
    """
    out = []
    for s in steps[:6]:
        if s["units_late"] >= 2 and s["avg_days"] >= 2:
            add = max(1, round(s["avg_days"]))
            out.append({
                "kind": "step_duration", "step_code": s["step_code"],
                "templates": s["templates"],
                "title": f"Tambah durasi {s['step_code']} ± {add} hari",
                "detail": (f"'{s['name']}' telat di {s['units_late']} dari "
                           f"{s['units_total']} rumah (rata-rata {s['avg_days']} hari, "
                           f"maksimal {s['max_days']} hari). Durasi template sekarang "
                           f"{s['planned_days']} hari — kemungkinan terlalu ketat."),
                "action": "Terapkan kalibrasi durasi langsung dari sini.",
                "calibration": {"kind": "step_duration", "step_code": s["step_code"],
                                "templates": s["templates"], "delta_days": int(add),
                                "cause": "data_telat"},
            })
        cause = (s.get("dominant_cause") or {}).get("cause")
        if cause == "material_late" and s["units_late"] >= 2:
            out.append({
                "kind": "material_lead_time", "step_code": s["step_code"],
                "templates": s["templates"],
                "title": f"Majukan pengadaan material untuk {s['step_code']}",
                "detail": (f"Penyebab telat dominan pada '{s['name']}' adalah material "
                           f"belum datang ({s['dominant_cause']['count']} kejadian)."),
                "action": "Buka RAB/BoQ & Pengadaan → jadwalkan PO lebih awal dari minggu "
                          f"{s['week']}.",
                "calibration": None,
            })
        if cause == "manpower_short" and s["units_late"] >= 2:
            out.append({
                "kind": "manpower", "step_code": s["step_code"],
                "templates": s["templates"],
                "title": f"Tambah tukang pada {s['step_code']}",
                "detail": (f"'{s['name']}' sering telat karena tukang kurang "
                           f"({s['dominant_cause']['count']} kejadian)."),
                "action": "Bahas dengan subkontraktor / tambah regu pada minggu tersebut.",
                "calibration": None,
            })
        if s["wait_days"] and s["avg_days"] >= s["wait_days"]:
            # Waktu tunggu (`wait_days`) berlaku SEBELUM langkah ini boleh dimulai — ia
            # menahan gerbang kesiapan setelah pendahulunya diverifikasi (mis. curing beton).
            # Sampai Fase 37 waktu tunggu itu TIDAK pernah masuk `day_from/day_to`, sehingga
            # tanggal rencana sistematis optimistis dan pekerjaannya tercatat "telat" padahal
            # betonnya yang belum boleh dibebani. Jalan keluar yang jujur bukan memperpendek
            # curing, tetapi MEMASUKKAN waktu tunggu itu ke rencana.
            out.append({
                "kind": "wait_time", "step_code": s["step_code"],
                "templates": s["templates"],
                "title": (f"Masukkan waktu tunggu {s['wait_days']} hari ke rencana "
                          f"{s['step_code']}"),
                "detail": (f"'{s['name']}' wajib menunggu {s['wait_days']} hari setelah "
                           "pekerjaan pendahulunya diverifikasi, tetapi tanggal rencana "
                           "belum memperhitungkannya — langkah ini telat rata-rata "
                           f"{s['avg_days']} hari. Waktu tunggunya tidak dipersingkat, "
                           "rencananya yang dibuat jujur."),
                "action": "Terapkan kalibrasi 'masukkan waktu tunggu ke rencana' dari sini.",
                "calibration": {"kind": "wait_into_plan", "step_code": s["step_code"],
                                "templates": s["templates"], "delta_days": 0,
                                "cause": "waktu_tunggu_fisik"},
            })
    for p in people[:3]:
        if p["items_late"] >= 3 and p["late_rate"] >= 40:
            out.append({
                "kind": "workload", "assigned_to": p["assigned_to"],
                "title": f"Tinjau beban kerja {p['assigned_to']}",
                "detail": (f"{p['items_late']} dari {p['items_total']} pekerjaan telat "
                           f"({p['late_rate']}%), rata-rata {p['avg_days']} hari"
                           + (f", {p['unexplained']} tanpa penjelasan penyebab."
                              if p["unexplained"] else ".")),
                "action": "Bagi ulang penugasan pada template (peran pelaksana) atau "
                          "tambah personel.",
                "calibration": None,
            })
    for t in types[:2]:
        if t["items_late"] >= 4 and t["late_rate"] >= 35:
            out.append({
                "kind": "unit_type", "unit_type": t["unit_type"],
                "templates": t["templates"],
                "title": f"Kalibrasi template tipe {t['unit_type']}",
                "detail": (f"{t['items_late']} dari {t['items_total']} pekerjaan pada tipe "
                           f"ini telat ({t['late_rate']}%), rata-rata {t['avg_days']} hari."),
                "action": "Kalibrasi langkah yang paling sering telat pada tabel di bawah.",
                "calibration": None,
            })
    return out[:10]
