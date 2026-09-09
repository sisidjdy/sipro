"""BUILD ENGINE (Fase 31) — jadwal pembangunan BERBUKTI per unit.

Mengapa modul ini ada? Sebelum Fase 31 progres konstruksi hanya:
  * fase level PROYEK dengan angka persen yang **diketik manual**, lalu
  * `recompute_project_progress()` menimpa `construction_progress` **semua unit** dengan
    angka proyek yang sama.
Akibatnya: progres per rumah tidak nyata, tidak ada jadwal tanggal, tidak ada pengingat,
tidak ada eskalasi, dan angka bisa dinaikkan tanpa bukti apa pun.

Fase 31 mengubahnya menjadi mesin kerja:
  1. TEMPLATE per tipe unit (bisa dikonfigurasi supervisor) → daftar item pekerjaan,
     bobot, hari ke-N, dependensi, waktu tunggu (curing), hold point, checklist mutu,
     dan jumlah foto minimal.
  2. JADWAL per unit dengan tanggal kalender nyata (hari kerja/kalender bisa dipilih,
     hari libur bisa didaftar) → setiap item punya tanggal mulai & selesai rencana.
  3. GERBANG: item hanya bisa dikerjakan bila pekerjaan sebelumnya SUDAH DIVERIFIKASI dan
     waktu tunggu (mis. curing beton) benar-benar terlewati. Hold point tidak bisa dilompati.
  4. BUKTI: pengajuan hasil wajib foto (≥ minimal), checklist kritis harus lulus, dan
     catatan kerja. Foto masuk lewat object storage (ada watermark + EXIF dibuang).
  5. ANTI-KECURANGAN: foto yang identik dengan bukti pekerjaan lain DITOLAK (hash SHA-256),
     pengaju tidak boleh memverifikasi pekerjaannya sendiri, dan menerobos gerbang
     (override) wajib beralasan serta dilaporkan ke direksi.
  6. PROGRES NYATA: progres unit = Σ bobot item terverifikasi ÷ Σ bobot seluruh item.
"""
import logging
from datetime import date, datetime, timedelta

import build_catalog as bcat
import workhub as wh
from core_utils import new_id, now, now_iso, today_iso_date
from db import db, ORG_ID
from engine import add_activity, create_notification, emit

logger = logging.getLogger("sipro.build")

ITEM_OPEN = ["blocked", "ready", "in_progress", "submitted", "rework"]
ACTIVE_SCHEDULE = ["not_started", "in_progress", "at_risk", "on_hold"]


# ============================ kalender jadwal ============================
def _d(value) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def is_workday(day: date, work_days_per_week: int, holidays: set, off_days=None) -> bool:
    """Minggu libur bila 6 hari kerja; Sabtu+Minggu libur bila 5; tanpa libur bila 7.

    Fase 36: bila MASTER kalender kerja sudah ada (`build_calendar`), pola hari dikirim
    sebagai `off_days` (kumpulan indeks hari libur mingguan, 0=Senin) sehingga pola seperti
    "Jumat libur" atau "Sabtu setengah hari tetap masuk" bisa dinyatakan apa adanya —
    tidak lagi dipaksa menjadi angka 5/6/7. Parameter opsional agar jalur lama tetap jalan.
    """
    if day.isoformat() in holidays:
        return False
    wd = day.weekday()          # 0=Senin .. 6=Minggu
    if off_days is not None:
        return wd not in off_days
    if work_days_per_week >= 7:
        return True
    if work_days_per_week == 6:
        return wd != 6
    return wd < 5


def date_for_day(start: date, n: int, mode: str, wdpw: int, holidays: set,
                 off_days=None) -> date:
    """Tanggal untuk 'hari ke-n' template (n=1 → hari pertama pelaksanaan)."""
    if mode == "calendar_days":
        return start + timedelta(days=max(0, n - 1))
    day, counted = start, 0
    for _ in range(4000):
        if is_workday(day, wdpw, holidays, off_days):
            counted += 1
            if counted >= n:
                return day
        day += timedelta(days=1)
    return day


def next_workday(from_day: date, wdpw: int, holidays: set, off_days=None) -> date:
    day = from_day
    for _ in range(60):
        if is_workday(day, wdpw, holidays, off_days):
            return day
        day += timedelta(days=1)
    return from_day


# ============================ template ============================
async def template_for_unit(org: str, unit: dict, template_id: str = None) -> dict:
    """Pilih template: eksplisit → khusus proyek → global per tipe unit."""
    if template_id:
        tpl = await db.build_templates.find_one({"id": template_id, "org_id": org}, {"_id": 0})
        if not tpl:
            raise ValueError("Template jadwal tidak ditemukan.")
        return tpl
    utype = unit.get("type")
    if utype in bcat.NO_BUILD_UNIT_TYPES:
        raise ValueError(f"Tipe unit '{utype}' dijual sebagai tanah — tidak punya jadwal "
                         "pembangunan. Pilih template lain bila unit ini akan dibangun.")
    keys = await expand_type_keys(org, unit_type_keys(unit))
    for pid in (unit.get("project_id"), None):
        rows = await db.build_templates.find(
            {"org_id": org, "is_active": {"$ne": False}, "project_id": pid},
            {"_id": 0}).sort("code", 1).to_list(200)
        hit = [t for t in rows if template_matches(t, keys)]
        if hit:
            hit.sort(key=lambda t: (not t.get("unit_types"), not t.get("is_default")))
            return hit[0]
    raise ValueError(f"Belum ada template jadwal untuk tipe unit '{utype}'. "
                     "Buat/duplikasi template di tab 'Template Jadwal' lebih dulu.")


def _norm(v) -> str:
    return str(v or "").strip().lower()


def _key(v) -> str:
    """Kunci longgar: huruf/angka saja — "Tipe 36/72", "TIPE-36-72", "tipe 36 / 72" → "tipe3672"."""
    return "".join(ch for ch in str(v or "").lower() if ch.isalnum())


def type_key_match(a: str, b: str) -> bool:
    """Sama persis (dinormalkan) ATAU salah satu memuat yang lain (mis. "30/60" ⊂ "Rumah Tapak 30/60")."""
    ka, kb = _key(a), _key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    short, long_ = sorted((ka, kb), key=len)
    return len(short) >= 3 and short in long_


def unit_type_keys(unit: dict) -> set:
    """Kunci pencocokan tipe unit: nama tipe (`type`) DAN kode master (`unit_type_code`).

    Template menyimpan `unit_types` sebagai teks; di lapangan pemakai bisa menulis kode
    ("TIPE-36-72") atau nama ("Tipe 36/72") — keduanya harus dianggap sama unit."""
    return {_norm(unit.get("type")), _norm(unit.get("unit_type_code"))} - {""}


def template_matches(tpl: dict, keys: set) -> bool:
    """Template tanpa `unit_types` berlaku untuk semua tipe yang bisa dibangun."""
    types = [t for t in (tpl.get("unit_types") or []) if _norm(t)]
    return not types or any(type_key_match(t, k) for t in types for k in keys)


async def expand_type_keys(org: str, keys: set) -> set:
    """Jembatani kode ↔ nama tipe lewat master `unit_types` (mis. TIPE-36-72 ↔ Tipe 36/72)."""
    if not keys:
        return keys
    rows = await db.unit_types.find({"org_id": org}, {"_id": 0, "code": 1, "name": 1}).to_list(500)
    out = set(keys)
    for r in rows:
        pair = {_norm(r.get("code")), _norm(r.get("name"))} - {""}
        if pair & keys:
            out |= pair
    return out


def validate_steps(steps: list) -> list:
    """Kembalikan daftar peringatan (bukan error) supaya supervisor sadar dampaknya."""
    warns = []
    codes = [s.get("code") for s in steps]
    if len(set(codes)) != len(codes):
        warns.append("Ada kode item ganda — kode harus unik.")
    total = round(sum(float(s.get("weight") or 0) for s in steps), 2)
    if abs(total - 100) > 0.5:
        warns.append(f"Total bobot {total}% (ideal 100%). Progres tetap dihitung "
                     "proporsional, tetapi angka jadi sulit dibaca.")
    for s in steps:
        for p in s.get("predecessors") or []:
            if p not in codes:
                warns.append(f"Item '{s.get('code')}' merujuk pendahulu '{p}' yang tidak ada.")
    return warns


# ============================ penerima tugas ============================
async def _pick_assignee(org: str, project: dict, role: str) -> str:
    """Staf proyek dengan peran tsb & beban paling ringan; jatuh ke siapa pun berperan itu."""
    members = project.get("members") or []
    cands = []
    if members:
        cands = await db.users.find(
            {"org_id": org, "email": {"$in": members}, "role": role, "is_active": True},
            {"_id": 0, "email": 1}).to_list(50)
    if not cands:
        cands = await db.users.find({"org_id": org, "role": role, "is_active": True},
                                    {"_id": 0, "email": 1}).to_list(50)
    if not cands:
        return None
    best, best_load = None, None
    for c in cands:
        load = await db.tasks.count_documents(
            {"org_id": org, "assigned_to": c["email"], "status": {"$in": wh.ACTIVE_STATES}})
        if best_load is None or load < best_load:
            best, best_load = c["email"], load
    return best


# ============================ pembangkitan jadwal ============================
async def _buyer_binding(org: str, unit: dict) -> dict:
    """Ikatan unit → deal → lead → customer (perbaikan cacat: dulu tidak pernah disimpan)."""
    deal_id = unit.get("booked_by_deal") or unit.get("sold_by_deal") or unit.get("reserved_by_deal")
    out = {"deal_id": deal_id, "lead_id": None, "lead_name": None, "customer_id": None,
           "customer_name": None}
    # Unit yang berstatus `available` TIDAK punya pembeli — apa pun tautan yang masih
    # tertinggal di dokumennya. Tanpa penjaga ini, satu tautan basi (mis. sisa pembatalan)
    # dipakai ulang untuk "mengikat" kembali rumah yang sudah kembali ke stok kepada pembeli
    # yang justru mundur.
    if str(unit.get("status") or "") == "available":
        out["deal_id"] = None
        return out
    if not deal_id:
        return out
    deal = await db.deals.find_one({"id": deal_id, "org_id": org},
                                  {"_id": 0, "lead_id": 1, "customer_id": 1})
    if not deal:
        return out
    out["lead_id"] = deal.get("lead_id")
    if deal.get("lead_id"):
        lead = await db.leads.find_one({"id": deal["lead_id"]}, {"_id": 0, "name": 1})
        out["lead_name"] = (lead or {}).get("name")
    # Fase 53: pembeli dibaca dari KONTRAK dulu (satu kontrak per deal, tautannya pasti),
    # baru jatuh ke pencarian lewat `customers.lead_id`. Sebelumnya hanya cara kedua yang
    # ada — dan cara itu putus untuk pembeli lama yang membeli unit kedua (satu orang, dua
    # lead), karena satu baris pembeli hanya bisa menyimpan satu `lead_id`.
    contract = await db.contracts.find_one({"org_id": org, "deal_id": deal_id},
                                           {"_id": 0, "customer_id": 1, "id": 1})
    cust = None
    if contract and contract.get("customer_id"):
        out["contract_id"] = contract["id"]
        cust = await db.customers.find_one({"id": contract["customer_id"]},
                                           {"_id": 0, "id": 1, "name": 1})
    if not cust:
        cust = await db.customers.find_one(
            {"org_id": org, "lead_id": deal.get("lead_id")}, {"_id": 0, "id": 1, "name": 1}) \
            if deal.get("lead_id") else None
    if cust:
        out["customer_id"], out["customer_name"] = cust["id"], cust.get("name")
    return out


async def sync_unit_binding(org: str, unit_id: str) -> dict:
    """Simpan ikatan pembeli pada dokumen unit + jadwalnya (dipakai laporan & portal)."""
    unit = await db.units.find_one({"id": unit_id, "org_id": org}, {"_id": 0})
    if not unit:
        return {}
    b = await _buyer_binding(org, unit)
    # Add-on pembeli (dari deal/penawaran marketing) MENEMPEL pada unit & jadwalnya — Pembangunan
    # dan SPK membaca dari sini, bukan menebak dari catatan marketing.
    deal = await db.deals.find_one({"id": b["deal_id"]}, {"_id": 0, "addons": 1}) if b.get("deal_id") else None
    addons = [{"code": a.get("code"), "name": a.get("name"), "qty": a.get("qty"), "uom": a.get("uom"),
               "amount": a.get("amount"), "category": a.get("category")}
              for a in (deal or {}).get("addons") or []
              if (a.get("finance_treatment") or "revenue") != "info"]
    await db.units.update_one({"id": unit_id}, {"$set": {
        "deal_id": b["deal_id"], "lead_id": b["lead_id"], "lead_name": b["lead_name"],
        "customer_id": b["customer_id"], "addons": addons, "addon_codes": [a["code"] for a in addons],
        "updated_at": now_iso()}})
    await db.build_schedules.update_many({"org_id": org, "unit_id": unit_id}, {"$set": {
        "deal_id": b["deal_id"], "lead_id": b["lead_id"], "lead_name": b["lead_name"],
        "customer_id": b["customer_id"], "customer_name": b["customer_name"], "addons": addons,
        "updated_at": now_iso()}})
    return b


async def generate_schedule(org: str, unit: dict, tpl: dict, start_date: str, actor: str,
                            regenerate: bool = False) -> dict:
    """Buat jadwal + item pekerjaan untuk satu unit. Idempoten per unit."""
    existing = await db.build_schedules.find_one({"org_id": org, "unit_id": unit["id"]},
                                                {"_id": 0})
    if existing and not regenerate:
        raise ValueError("Unit ini sudah punya jadwal. Buka jadwalnya, atau pilih "
                         "'buat ulang' bila belum ada pekerjaan yang diverifikasi.")
    if existing and regenerate:
        verified = await db.build_items.count_documents(
            {"org_id": org, "schedule_id": existing["id"], "status": "done"})
        if verified:
            raise ValueError(f"Tidak bisa dibuat ulang: {verified} pekerjaan sudah "
                             "diverifikasi (bukti kerja tidak boleh dihapus).")
        await db.build_items.delete_many({"org_id": org, "schedule_id": existing["id"]})
        await db.build_schedules.delete_one({"id": existing["id"]})
    project = await db.projects.find_one({"id": unit["project_id"], "org_id": org}, {"_id": 0})
    # Fase 36: kalender kerja MASTER (hari libur + pola hari) menang atas nilai template,
    # sehingga tenggat tidak lagi mendarat di 17 Agustus/Idul Fitri hanya karena daftar
    # libur pada template selalu kosong. `calendar_mode` tetap milik template.
    import build_calendar as bcal
    cal = await bcal.params_for(org, unit.get("project_id"), tpl)
    mode, wdpw, holidays, off = cal["mode"], cal["wdpw"], cal["holidays"], cal["off_days"]
    start = next_workday(_d(start_date), wdpw, holidays, off) if mode == "working_days" \
        else _d(start_date)
    steps = sorted(tpl.get("steps") or [], key=lambda s: (s.get("day_from", 0), s.get("code")))
    if not steps:
        raise ValueError("Template ini belum punya item pekerjaan.")
    ts = now_iso()
    sched_id = new_id()
    binding = await _buyer_binding(org, unit)
    last_day = max(int(s.get("day_to") or s.get("day_from") or 1) for s in steps)
    finish = date_for_day(start, last_day, mode, wdpw, holidays, off)
    roles = {}
    docs = []
    for order, s in enumerate(steps, start=1):
        role = s.get("assignee_role") or "site_engineer"
        if role not in roles:
            roles[role] = await _pick_assignee(org, project or {}, role)
        vrole = s.get("verify_role") or "project_manager"
        if vrole not in roles:
            roles[vrole] = await _pick_assignee(org, project or {}, vrole)
        p_start = date_for_day(start, int(s.get("day_from") or 1), mode, wdpw, holidays, off)
        p_finish = date_for_day(start, int(s.get("day_to") or s.get("day_from") or 1),
                               mode, wdpw, holidays, off)
        docs.append({
            "id": new_id(), "org_id": org, "project_id": unit["project_id"],
            "unit_id": unit["id"], "unit_code": unit.get("code"), "schedule_id": sched_id,
            "step_code": s.get("code"), "name": s.get("name"),
            "work_category": s.get("work_category"), "week": int(s.get("week") or 1),
            "order": order, "weight": float(s.get("weight") or 0),
            "day_from": int(s.get("day_from") or 1),
            "day_to": int(s.get("day_to") or s.get("day_from") or 1),
            "planned_start": p_start.isoformat(), "planned_finish": p_finish.isoformat(),
            "predecessors": list(s.get("predecessors") or []),
            "wait_days": int(s.get("wait_days") or 0), "wait_reason": s.get("wait_reason"),
            "hold_point": bool(s.get("hold_point")), "hold_note": s.get("hold_note"),
            "handover_gate": bool(s.get("handover_gate")),
            "min_photos": int(s.get("min_photos") or 0),
            "checklist": [{**c, "result": "pending", "note": None}
                          for c in (s.get("checklist") or [])],
            "tasks": list(s.get("tasks") or []),
            "assignee_role": role, "assigned_to": roles.get(role),
            "verify_role": vrole, "verifier_hint": roles.get(vrole),
            "status": "blocked", "gate_ready_at": None, "gate_reasons": [],
            "evidence": [], "note": None, "history": [],
            "started_at": None, "submitted_at": None, "submitted_by": None,
            "verified_at": None, "verified_by": None, "verify_note": None,
            "rejected_reason": None, "rework_count": 0, "override": None,
            "delay_cause": None, "delay_note": None,
            "late_days": 0, "escalation_level": 0, "escalated_at": None, "reminded_on": None,
            "task_id": None, "created_at": ts, "updated_at": ts,
        })
    sched = {
        "id": sched_id, "org_id": org, "project_id": unit["project_id"],
        "unit_id": unit["id"], "unit_code": unit.get("code"), "unit_type": unit.get("type"),
        "template_id": tpl.get("id"), "template_code": tpl.get("code"),
        "template_name": tpl.get("name"), "calendar_mode": mode,
        "work_days_per_week": wdpw, "holidays": sorted(holidays),
        "calendar_source": cal["calendar"]["source"],
        "off_weekdays": sorted(off) if off is not None else None,
        "start_date": start.isoformat(), "target_finish_date": finish.isoformat(),
        "status": "not_started", "progress": 0, "planned_progress": 0, "deviation": 0,
        "deviation_days": 0, "late_items": 0, "blocked_items": 0, "overrides": 0,
        "items_total": len(docs), "items_done": 0,
        "hold_cause": None, "hold_note": None, "finished_at": None,
        **binding,
        "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    await db.build_schedules.insert_one(dict(sched))
    await db.build_items.insert_many([dict(d) for d in docs])
    await refresh_gates(org, sched_id)
    await recompute_schedule(org, sched_id)
    await add_activity(entity_type="unit", entity_id=unit["id"], type="system",
                       body=(f"Jadwal pembangunan dibuat dari template '{tpl.get('code')}' — "
                             f"{len(docs)} item, mulai {start.isoformat()}, "
                             f"target selesai {finish.isoformat()}."),
                       actor=actor, org_id=org)
    await emit("build.schedule_created", "unit", unit["id"],
               {"label": unit.get("code"), "schedule_id": sched_id}, org_id=org)
    fresh = await db.build_schedules.find_one({"id": sched_id}, {"_id": 0})
    return fresh


# ============================ gerbang mutu ============================
def gate_of(item: dict, by_code: dict, schedule: dict) -> dict:
    """Boleh dikerjakan? Kembalikan alasan JELAS bila terkunci (bukan 'tidak bisa')."""
    reasons = []
    if (schedule or {}).get("status") == "on_hold":
        reasons.append({"code": "schedule_hold",
                        "detail": "Jadwal unit dihentikan sementara: "
                                  f"{schedule.get('hold_note') or '-'}"})
    ready_at = None
    for pc in item.get("predecessors") or []:
        pred = by_code.get(pc)
        if not pred:
            continue
        if pred.get("status") != "done":
            reasons.append({
                "code": "predecessor", "step": pc,
                "detail": f"'{pred.get('name')}' belum diverifikasi "
                          f"(status: {pred.get('status')})."})
            continue
        wait = int(item.get("wait_days") or 0)
        if wait and pred.get("verified_at"):
            avail = (datetime.fromisoformat(pred["verified_at"]) + timedelta(days=wait))
            if ready_at is None or avail > ready_at:
                ready_at = avail
    if ready_at and not any(r["code"] == "predecessor" for r in reasons):
        if now() < ready_at:
            left = max(1, (ready_at.date() - now().date()).days)
            reasons.append({
                "code": "wait_time", "until": ready_at.isoformat(),
                "detail": (item.get("wait_reason") or "Menunggu waktu tunggu pekerjaan")
                          + f" — baru boleh dimulai {ready_at.date().isoformat()} "
                            f"(sisa {left} hari)."})
    return {"open": not reasons, "reasons": reasons,
            "ready_at": ready_at.isoformat() if ready_at else None}


async def refresh_gates(org: str, schedule_id: str) -> int:
    """Perbarui status blocked/ready + alasan gerbang untuk semua item yang belum jalan."""
    sched = await db.build_schedules.find_one({"id": schedule_id, "org_id": org}, {"_id": 0})
    items = await db.build_items.find({"org_id": org, "schedule_id": schedule_id},
                                      {"_id": 0}).sort("order", 1).to_list(500)
    by_code = {i["step_code"]: i for i in items}
    changed = 0
    for it in items:
        if it.get("status") not in ("blocked", "ready"):
            continue
        g = gate_of(it, by_code, sched)
        want = "ready" if g["open"] else "blocked"
        if it.get("status") != want or it.get("gate_reasons") != g["reasons"]:
            await db.build_items.update_one({"id": it["id"]}, {"$set": {
                "status": want, "gate_reasons": g["reasons"],
                "gate_ready_at": g["ready_at"], "updated_at": now_iso()}})
            changed += 1
        # Fase 32: setiap pekerjaan yang BOLEH dikerjakan wajib punya task berinstruksi.
        # `wh.spawn` idempoten per `source_event`, jadi aman dipanggil berulang — ini
        # menutup celah lama: item yang sudah 'ready' sejak jadwal dibuat (atau dari data
        # seed) tidak pernah punya task sehingga pekerjaannya tak muncul di papan kerja.
        if want == "ready":
            await _spawn_work_task(org, {**it, "status": "ready",
                                         "gate_reasons": g["reasons"]}, sched)
    return changed


async def _spawn_work_task(org: str, item: dict, sched: dict):
    """Satu tugas Work Hub per item yang siap dikerjakan (bukan mesin tugas baru).

    Fase 32: deskripsi task = INSTRUKSI KERJA lengkap (lingkup, checklist mutu beserta
    penanda KRITIS, hold point, waktu tunggu, urutan pendahulu, siapa verifikatornya) dan
    `link` menunjuk langsung ke pekerjaan tersebut di Papan Mandor — dulu deskripsinya
    satu baris dan semua task menuju '/construction' sehingga pelaksana harus mencari
    sendiri pekerjaan mana yang dimaksud.
    """
    if not item.get("assigned_to"):
        return
    import build_instruction as bi
    rows = await wh.spawn(
        org, "TK-10", source_event=f"build.item_ready:{item['id']}",
        assignee_override=item["assigned_to"], entity_type="unit", entity_id=item["unit_id"],
        title=f"{item['name']} — unit {item.get('unit_code')}",
        description=bi.task_description(item, sched),
        due_date=f"{item.get('planned_finish')}T17:00:00+00:00",
        link=bi.item_link(item),
        meta={"build_item_id": item["id"], "schedule_id": item["schedule_id"],
              "unit_code": item.get("unit_code"), "step_code": item.get("step_code"),
              "min_photos": int(item.get("min_photos") or 0),
              "checklist_total": len(item.get("checklist") or [])})
    if rows:
        await db.build_items.update_one({"id": item["id"]},
                                       {"$set": {"task_id": rows[0]["id"]}})


async def reconcile_item_tasks(org: str) -> int:
    """Tutup task pekerjaan yang sudah tidak relevan (anti "task hantu").

    Task bisa tertinggal terbuka bila status item berubah lewat jalur lain (mis. data
    seed/migrasi lama), sehingga papan kerja menampilkan pekerjaan yang sebenarnya sudah
    selesai. Rekonsiliasi ini dijalankan pada tick pemantauan.
    """
    closed = 0
    q = {"org_id": org, "meta.build_item_id": {"$exists": True},
         "jobdesk_code": {"$in": ["TK-10", "TK-12"]},
         "status": {"$in": wh.OPEN_STATES}}
    async for t in db.tasks.find(q, {"_id": 0, "id": 1, "meta": 1}):
        iid = (t.get("meta") or {}).get("build_item_id")
        item = await db.build_items.find_one({"id": iid}, {"_id": 0, "status": 1})
        if item and item.get("status") in ("blocked", "ready", "in_progress", "rework"):
            continue
        review = "approved" if (item or {}).get("status") == "done" else "none"
        note = ("Pekerjaan sudah diverifikasi." if review == "approved"
                else "Pekerjaan sudah diajukan / item tidak aktif lagi.")
        await db.tasks.update_one({"id": t["id"]}, {"$set": {
            "status": "done", "review": review, "completed_at": now_iso(),
            "verify_note": note, "updated_at": now_iso()}})
        closed += 1
    return closed


async def _close_item_tasks(org: str, item: dict, review: str, note: str = None):
    """Tutup tugas Work Hub milik item (agar papan kerja tidak menyimpan tugas hantu)."""
    q = {"org_id": org, "meta.build_item_id": item["id"], "status": {"$in": wh.OPEN_STATES}}
    await db.tasks.update_many(q, {"$set": {
        "status": "done", "review": review, "completed_at": now_iso(),
        "verify_note": note, "updated_at": now_iso()}})


# ============================ progres nyata ============================
def _planned_progress(items: list, ref_day: str) -> float:
    total = sum(float(i.get("weight") or 0) for i in items) or 1
    due = sum(float(i.get("weight") or 0) for i in items
              if str(i.get("planned_finish") or "") <= ref_day)
    return round(due / total * 100, 1)


def _deviation_days(items: list, progress: float, ref_day: str) -> int:
    """Setara berapa hari tertinggal: cari tanggal rencana saat bobot = progres aktual."""
    total = sum(float(i.get("weight") or 0) for i in items) or 1
    cum = 0.0
    reached = None
    for it in sorted(items, key=lambda x: str(x.get("planned_finish") or "")):
        cum += float(it.get("weight") or 0)
        if cum / total * 100 >= progress - 0.01:
            reached = str(it.get("planned_finish") or "")
            break
    if not reached:
        return 0
    delta = (_d(ref_day) - _d(reached)).days
    return max(0, delta)


async def recompute_schedule(org: str, schedule_id: str) -> dict:
    """Progres unit = Σ bobot item DONE ÷ Σ bobot. Menular ke unit & proyek."""
    sched = await db.build_schedules.find_one({"id": schedule_id, "org_id": org}, {"_id": 0})
    if not sched:
        return {}
    items = await db.build_items.find({"org_id": org, "schedule_id": schedule_id},
                                      {"_id": 0}).to_list(500)
    total_w = sum(float(i.get("weight") or 0) for i in items) or 1
    done_w = sum(float(i.get("weight") or 0) for i in items if i.get("status") == "done")
    progress = round(done_w / total_w * 100, 1)
    today = today_iso_date()
    planned = _planned_progress(items, today)
    late = [i for i in items if i.get("status") != "done"
            and str(i.get("planned_finish") or "") < today]
    blocked = [i for i in items if i.get("status") == "blocked"]
    done_n = len([i for i in items if i.get("status") == "done"])
    if sched.get("status") == "on_hold":
        status = "on_hold"
    elif done_n >= len(items) and items:
        status = "done"
    elif progress <= 0 and not any(i.get("status") in ("in_progress", "submitted", "rework")
                                   for i in items):
        status = "not_started"
    else:
        status = "at_risk" if (late or (progress - planned) <= -10) else "in_progress"
    upd = {
        "progress": progress, "planned_progress": planned,
        "deviation": round(progress - planned, 1),
        "deviation_days": _deviation_days(items, progress, today) if progress < planned else 0,
        "late_items": len(late), "blocked_items": len(blocked),
        "items_done": done_n, "items_total": len(items), "status": status,
        "updated_at": now_iso(),
    }
    if status == "done" and not sched.get("finished_at"):
        upd["finished_at"] = now_iso()
    await db.build_schedules.update_one({"id": schedule_id}, {"$set": upd})
    # Fase 46: pemetaan dibuat JUJUR. Sebelumnya jadwal `not_started` menimpa status unit
    # menjadi "Belum dibangun" padahal jadwalnya SUDAH ada (migrasi V2 justru menandainya
    # "scheduled"), dan jadwal `on_hold` dilaporkan "Sedang dibangun" — dua-duanya membuat
    # Papan Unit salah baca. Nilai tetap dari SSOT `construction_status` (Fase 39).
    cstatus = {"not_started": "scheduled", "in_progress": "in_progress",
               "at_risk": "in_progress", "on_hold": "on_hold", "done": "done"}[status]
    unit_set = {"construction_progress": int(round(progress)),
                "construction_status": cstatus, "updated_at": now_iso()}
    await db.units.update_one({"id": sched["unit_id"], "org_id": org}, {"$set": unit_set})
    return {**sched, **upd}


async def recompute_unit_progress(org: str, unit_id: str) -> int:
    sched = await db.build_schedules.find_one({"org_id": org, "unit_id": unit_id},
                                             {"_id": 0, "id": 1})
    if not sched:
        return 0
    out = await recompute_schedule(org, sched["id"])
    return int(round(out.get("progress") or 0))


# ============================ bukti & anti-kecurangan ============================
async def collect_evidence(org: str, file_ids: list, item: dict, actor: str) -> list:
    """Ambil metadata berkas + TOLAK foto yang identik dengan bukti pekerjaan lain."""
    out = []
    for fid in file_ids or []:
        rec = await db.files.find_one({"id": fid, "org_id": org, "is_deleted": False},
                                      {"_id": 0, "data_b64": 0})
        if not rec:
            raise ValueError(f"Berkas bukti {fid[:8]} tidak ditemukan — unggah ulang.")
        sha = rec.get("sha256")
        if sha:
            dup = await db.build_items.find_one(
                {"org_id": org, "id": {"$ne": item["id"]}, "evidence.sha256": sha},
                {"_id": 0, "name": 1, "unit_code": 1})
            if dup:
                raise ValueError(
                    f"Foto '{rec.get('original_filename')}' IDENTIK dengan bukti pekerjaan "
                    f"'{dup.get('name')}' pada unit {dup.get('unit_code')}. "
                    "Unggah foto asli pekerjaan ini (bukti tidak boleh didaur ulang).")
        out.append({
            "file_id": fid, "sha256": sha, "filename": rec.get("original_filename"),
            "content_type": rec.get("content_type"), "size": rec.get("size"),
            "uploaded_by": rec.get("uploaded_by"), "uploaded_at": rec.get("created_at"),
            "watermark": rec.get("watermark"),
            "by_other_person": bool(rec.get("uploaded_by") and rec.get("uploaded_by") != actor),
            "attached_by": actor, "attached_at": now_iso(),
        })
    return out


def checklist_merge(item: dict, answers: list) -> tuple:
    """Terapkan jawaban checklist. Item KRITIS wajib 'pass' — tidak boleh dilewati."""
    given = {a.get("code"): a for a in answers or []}
    merged, missing, failed = [], [], []
    for c in item.get("checklist") or []:
        a = given.get(c.get("code")) or {}
        result = a.get("result") or "pending"
        if result == "pending":
            missing.append(c.get("text"))
        elif c.get("critical") and result != "pass":
            failed.append(c.get("text"))
        merged.append({**c, "result": result, "note": a.get("note")})
    return merged, missing, failed
