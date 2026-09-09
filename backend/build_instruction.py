"""INSTRUKSI KERJA per STEP konstruksi (Fase 32).

Permintaan owner: "setiap progress itu harus menjadi task dan masing masing harus
upload foto sebagai bukti ... setiap step pada konstruksi itu buat menjadi instruksi
task dan harus ada validasinya".

Sebelum fase ini, deskripsi task hanya "Minggu 1 · rencana … · bukti minimal 2 foto",
sehingga pelaksana masih harus menebak APA yang dikerjakan dan APA yang diperiksa.
Modul ini menyusun instruksi lengkap **dari data template** (bukan teks yang diketik
ulang), jadi instruksi selalu sinkron bila supervisor mengubah template.

SATU sumber instruksi dipakai bersama oleh: deskripsi task Work Hub, Papan Mandor, dan
sheet jadwal unit — supaya tidak ada dua versi instruksi yang berbeda.
"""

WIB_HOURS = 7


def item_link(item: dict) -> str:
    """Deep link ke pekerjaan yang dimaksud (dulu semua task menuju '/construction')."""
    return f"/construction?tab=board&item={item.get('id')}"


def unit_link(item: dict) -> str:
    return f"/construction?tab=monitor&unit={item.get('unit_id')}"


def _fmt(d) -> str:
    return str(d or "")[:10]


def checklist_stat(item: dict) -> dict:
    rows = item.get("checklist") or []
    return {
        "total": len(rows),
        "critical": sum(1 for c in rows if c.get("critical")),
        "answered": sum(1 for c in rows if (c.get("result") or "pending") != "pending"),
    }


def photo_stat(item: dict) -> dict:
    photos = [e for e in (item.get("evidence") or [])
              if str(e.get("content_type") or "").startswith("image")]
    need = int(item.get("min_photos") or 0)
    return {"attached": len(photos), "required": need,
            "short": max(0, need - len(photos))}


def instruction_lines(item: dict, sched: dict = None) -> list:
    """Instruksi kerja apa adanya — urutan, lingkup, bukti, mutu, gerbang, validator."""
    cl = checklist_stat(item)
    ph = photo_stat(item)
    out = [
        f"LANGKAH {item.get('step_code')} — {item.get('name')}",
        (f"Unit {item.get('unit_code')} · minggu {item.get('week')} "
         f"(hari {item.get('day_from')}–{item.get('day_to')}) · bobot progres "
         f"{item.get('weight')}%"),
        (f"Rencana kerja: {_fmt(item.get('planned_start'))} sampai "
         f"{_fmt(item.get('planned_finish'))}"),
    ]
    tasks = [t for t in (item.get("tasks") or []) if t]
    if tasks:
        out.append("Lingkup pekerjaan yang harus dituntaskan:")
        out += [f"  {i}. {t}" for i, t in enumerate(tasks, start=1)]
    out.append(f"Bukti WAJIB: minimal {ph['required']} foto pekerjaan, diambil lewat "
               "aplikasi agar otomatis diberi watermark unit + tanggal.")
    if cl["total"]:
        out.append(f"Checklist mutu yang harus dijawab ({cl['total']} butir"
                   + (f", {cl['critical']} KRITIS wajib LULUS" if cl["critical"] else "")
                   + "):")
        for c in item.get("checklist") or []:
            tag = "[KRITIS] " if c.get("critical") else ""
            out.append(f"  - {tag}{c.get('text')}")
    if item.get("hold_point"):
        out.append("HOLD POINT: " + (item.get("hold_note")
                                     or "pekerjaan berikutnya tidak boleh jalan sebelum "
                                        "pekerjaan ini lulus diperiksa."))
    if int(item.get("wait_days") or 0):
        out.append(f"Waktu tunggu setelah pekerjaan ini: {item.get('wait_days')} hari"
                   + (f" — {item.get('wait_reason')}" if item.get("wait_reason") else ""))
    preds = [p for p in (item.get("predecessors") or []) if p]
    if preds:
        out.append("Urutan wajib: pekerjaan " + ", ".join(preds)
                   + " harus DIVERIFIKASI lebih dulu — tidak boleh dilangkahi.")
    out.append("Validasi: hasil kerja diperiksa "
               + (item.get("verifier_hint") or "supervisor proyek")
               + ". Anda tidak bisa menandai pekerjaan ini selesai sendiri.")
    if sched and sched.get("lead_name"):
        out.append(f"Rumah ini sudah dibeli {sched.get('lead_name')} — kerapian dan mutu "
                   "langsung terlihat pembeli di portal.")
    return out


def instruction_text(item: dict, sched: dict = None) -> str:
    return "\n".join(instruction_lines(item, sched))


def task_description(item: dict, sched: dict = None) -> str:
    """Deskripsi task Work Hub = instruksi kerja (dipotong aman untuk penyimpanan)."""
    return instruction_text(item, sched)[:4000]


def brief(item: dict) -> dict:
    """Ringkasan step untuk kartu (Papan Mandor / antrean) — field jelas, bukan teks bebas."""
    cl = checklist_stat(item)
    ph = photo_stat(item)
    return {
        "id": item.get("id"), "step_code": item.get("step_code"), "name": item.get("name"),
        "unit_id": item.get("unit_id"), "unit_code": item.get("unit_code"),
        "schedule_id": item.get("schedule_id"), "project_id": item.get("project_id"),
        "week": item.get("week"), "weight": item.get("weight"),
        "work_category": item.get("work_category"),
        "status": item.get("status"), "planned_start": item.get("planned_start"),
        "planned_finish": item.get("planned_finish"),
        "min_photos": ph["required"], "photos_attached": ph["attached"],
        "checklist_total": cl["total"], "checklist_critical": cl["critical"],
        # Checklist LENGKAP ikut dikirim (Fase 35): dialog "Ajukan hasil" di Papan Mandor
        # merender butir mutu dari data ini. Dulu hanya jumlahnya yang dikirim, sehingga
        # pengajuan dari Papan Mandor berangkat TANPA jawaban checklist lalu ditolak server
        # ("Checklist mutu belum lengkap") — dan di lokasi tanpa sinyal penolakan itu baru
        # terlihat setelah antrean terkirim. Ini juga yang membuat cuplikan offline berguna.
        "checklist": [{"code": c.get("code"), "text": c.get("text"),
                       "critical": bool(c.get("critical")), "result": c.get("result"),
                       "note": c.get("note")} for c in (item.get("checklist") or [])],
        "hold_point": bool(item.get("hold_point")), "hold_note": item.get("hold_note"),
        "wait_days": int(item.get("wait_days") or 0), "wait_reason": item.get("wait_reason"),
        "predecessors": list(item.get("predecessors") or []),
        "tasks": list(item.get("tasks") or []),
        "assigned_to": item.get("assigned_to"), "verifier_hint": item.get("verifier_hint"),
        "submitted_by": item.get("submitted_by"),
        "rejected_reason": item.get("rejected_reason"),
        "delay_cause": item.get("delay_cause"),
        "gate_reasons": list(item.get("gate_reasons") or []),
        "gate_ready_at": item.get("gate_ready_at"),
        "task_id": item.get("task_id"), "link": item_link(item),
        "instruction": instruction_lines(item),
    }
