"""seed_phase46.py — data demo IZIN BERTINGKAT + mutu/temuan per UNIT (idempoten).

Kenapa seed ini ada: layar baru Fase 46 (Papan Unit, Unit 360 → tab Pembangunan, tab
Dokumen & Izin) tidak bisa DIBUKTIKAN pada database bersih tanpa contoh izin yang
menempel di tingkat cluster/blok/unit dan tanpa temuan/inspeksi yang benar-benar terikat
ke satu rumah. Yang ada sebelumnya hanya izin tingkat proyek tanpa masa berlaku.

Yang ditulis di sini (semua BERSANDAR pada objek yang sudah ada — cluster/blok/unit hasil
migrasi V2, bukan objek karangan):

  * **PBG tingkat cluster** yang masih lama masa berlakunya → keadaan "aktif & aman".
  * **SLF tingkat blok** yang berakhir 21 hari lagi → keadaan "menjelang kedaluwarsa"
    sehingga peringatan (notifikasi + tugas) benar-benar bisa dilihat & diuji.
  * **Pengesahan site plan tingkat unit** yang tanggalnya sudah lewat → keadaan
    "kedaluwarsa meski status disetujui", cacat yang dulu tidak pernah terlihat.
  * **ANDALALIN tingkat proyek** yang masih diproses → membuktikan izin belum ada tidak
    dianggap "aman".
  * **Temuan (punch) + inspeksi QC terikat unit** untuk unit yang jadwalnya sedang berjalan,
    supaya tab Pembangunan di Unit 360 punya isi nyata.

Izin lama Fase 10 SENGAJA TIDAK diberi `expiry_at`: repo tidak boleh mengarang tanggal
dokumen legal. Keadaan "masa berlaku belum dicatat" adalah informasi, bukan kekosongan
yang harus ditutup dengan angka.

Ditandai `demo_batch="fase46"` sehingga bisa dikenali, tidak pernah dobel, dan mudah dibuang.
"""
import logging
from datetime import date, timedelta

import migrations_p46 as mig46
import sequences as seq
from core_utils import new_id, now_iso, today_iso_date
from db import ORG_ID, db

logger = logging.getLogger("sipro.seed")
BATCH = "fase46"


def _plus(days: int) -> str:
    return (date.fromisoformat(today_iso_date()) + timedelta(days=days)).isoformat()


async def _permit(org: str, project: dict, spec: dict) -> bool:
    """Buat satu izin bila belum ada (kunci alami: org+type+scope+scope_id)."""
    key = {"org_id": org, "type": spec["type"], "scope": spec["scope"],
           "scope_id": spec["scope_id"]}
    if await db.permits.find_one(key, {"_id": 0, "id": 1}):
        return False
    ts = now_iso()
    await db.permits.insert_one({
        "id": new_id(), "org_id": org, "project_id": project["id"],
        "project_name": project.get("name"), "demo_batch": BATCH,
        "status": spec.get("status", "approved"), "authority": spec.get("authority"),
        "reference_no": spec.get("reference_no"), "reminder_days": spec.get("reminder_days", 30),
        "deadline": spec.get("deadline"), "expiry_at": spec.get("expiry_at"),
        "requirement_code": spec.get("requirement_code"),
        "name": spec["name"], "type": spec["type"], "scope": spec["scope"],
        "scope_id": spec["scope_id"], "scope_object": spec.get("scope_object"),
        "submitted_at": ts if spec.get("status") != "not_started" else None,
        "approved_at": ts if spec.get("status", "approved") == "approved" else None,
        "notes": spec.get("notes"), "created_by": "seed", "created_at": ts, "updated_at": ts,
    })
    return True


async def _punch(org: str, project: dict, unit: dict, spec: dict) -> bool:
    key = {"org_id": org, "unit_id": unit["id"], "title": spec["title"]}
    if await db.punch_items.find_one(key, {"_id": 0, "id": 1}):
        return False
    ts = now_iso()
    await db.punch_items.insert_one({
        "id": new_id(), "org_id": org, "project_id": project["id"],
        "project_name": project.get("name"), "unit_id": unit["id"],
        "unit_code": unit.get("code"), "demo_batch": BATCH,
        "title": spec["title"], "description": spec["description"],
        "location": f"Unit {unit.get('code')} · {spec['location']}",
        "category": spec.get("category", "finishing"), "severity": spec["severity"],
        "status": spec.get("status", "open"), "assigned_to": spec.get("assigned_to"),
        "due_date": spec.get("due_date"), "photo": None,
        "opened_by": "pm@sipro.co.id", "closed_at": None,
        "created_at": ts, "updated_at": ts,
    })
    return True


async def _inspection(org: str, project: dict, unit: dict) -> bool:
    """Inspeksi QC terikat UNIT (bukan fase kawasan) memakai template yang sudah ada."""
    if await db.inspections.find_one({"org_id": org, "unit_id": unit["id"]},
                                     {"_id": 0, "id": 1}):
        return False
    tpl = await db.inspection_templates.find_one({"org_id": org, "is_active": True},
                                                 {"_id": 0})
    if not tpl:
        return False
    items = [{"key": it["key"], "label": it["label"], "result": "pending", "note": None}
             for it in tpl.get("items", [])]
    if not items:
        return False
    ts = now_iso()
    await db.inspections.insert_one({
        "id": new_id(), "org_id": org, "demo_batch": BATCH,
        "inspection_number": await seq.next_number("inspection", org, prefix="QC"),
        "project_id": project["id"], "project_name": project.get("name"),
        "unit_id": unit["id"], "unit_code": unit.get("code"), "phase_id": None,
        "template_id": tpl.get("id"), "template_code": tpl.get("code"),
        "category": tpl.get("category") or "lainnya",
        "title": f"{tpl.get('name') or 'Inspeksi QC'} — unit {unit.get('code')}",
        "items": items, "status": "in_progress",
        "items_total": len(items), "items_pass": 0, "items_fail": 0,
        "punch_ids": [], "punch_created": False, "result_note": None,
        "created_by": "seed", "created_at": ts, "updated_at": ts,
        "finalized_by": None, "finalized_at": None,
        "scheduled_date": None, "scheduled_by": None, "scheduled_note": None,
    })
    return True


async def _candidate_schedule(org: str, project: dict) -> bool:
    """Satu unit **TERJADWAL tetapi BELUM dimulai** supaya gerbang "Mulai Bangun" bisa dicoba.

    Kenapa seed ini ada (temuan uji E2E penutupan Fase 46): SELURUH unit seed yang punya
    jadwal sudah berjalan — seed Fase 31/33/36 sengaja membuat progres, bukti, dan
    keterlambatan yang nyata. Akibatnya tombol **Mulai Bangun** beserta dialog peringatan
    (pengakuan + alasan) TIDAK PERNAH bisa dilihat siapa pun yang membuka demo, dan penguji
    melaporkan tiga user story tidak bisa dibuktikan karena bahannya tidak ada. Fitur yang
    tidak bisa dicapai sama artinya dengan tidak ada.

    Yang dilakukan seed ini HANYA menjadwalkan (tidak menyentuh status pekerjaan): unit
    pertama yang belum punya jadwal diberi jadwal dari template yang berlaku, sehingga
    kesiapannya menjadi **peringatan** (belum ada rencana bayar) — tepat keadaan yang ingin
    ditunjukkan pemilik: boleh dimulai, tetapi peringatannya wajib diakui + beralasan.

    Idempoten lewat penanda `demo_batch` pada jadwal. Bila kelak ada manusia yang benar-benar
    menekan "Mulai Bangun" pada unit ini, seed TIDAK akan membatalkannya atau membuat jadwal
    baru: keputusan manusia tidak boleh dihapus/ditiru oleh seed.
    """
    if await db.build_schedules.find_one({"org_id": org, "demo_batch": BATCH},
                                         {"_id": 0, "id": 1}):
        return False
    scheduled = await db.build_schedules.distinct("unit_id", {"org_id": org})
    unit = await db.units.find_one({"org_id": org, "project_id": project["id"],
                                    "id": {"$nin": scheduled},
                                    "construction_status": "not_started"},
                                   {"_id": 0}, sort=[("code", 1)])
    if not unit:
        return False
    import build_engine as be
    try:
        tpl = await be.template_for_unit(org, unit)
        sched = await be.generate_schedule(org, unit, tpl, today_iso_date(), "seed")
    except ValueError as e:  # template belum ada → biarkan apa adanya, jangan mengarang
        logger.info("Seed Fase 46: calon mulai bangun dilewati (%s).", e)
        return False
    await db.build_schedules.update_one({"id": sched["id"]},
                                        {"$set": {"demo_batch": BATCH}})
    logger.info("Seed Fase 46: unit %s dijadwalkan sebagai calon 'Mulai Bangun' "
                "(belum dimulai).", unit.get("code"))
    return True


async def seed_phase46(org: str = ORG_ID) -> dict:
    """Idempoten: menaikkan izin lama menjadi bertingkat + menambah contoh yang kurang."""
    out = {"migrated": {}, "permits": 0, "punch": 0, "inspections": 0, "candidate": False}
    out["migrated"] = await mig46.run(org)
    project = await db.projects.find_one({"org_id": org}, {"_id": 0})
    if not project:
        return out
    cluster = await db.clusters.find_one({"org_id": org, "project_id": project["id"]},
                                         {"_id": 0})
    block = await db.blocks.find_one({"org_id": org, "project_id": project["id"]}, {"_id": 0})
    # unit yang jadwalnya sudah berjalan → paling masuk akal punya izin unit & temuan mutu
    sched = await db.build_schedules.find_one(
        {"org_id": org, "status": {"$in": ["in_progress", "at_risk"]}},
        {"_id": 0, "unit_id": 1})
    unit = await db.units.find_one({"id": (sched or {}).get("unit_id"), "org_id": org},
                                   {"_id": 0}) if sched else None

    specs = []
    if cluster:
        specs.append({
            "type": "PBG", "name": f"PBG {cluster.get('name') or cluster.get('code')}",
            "scope": "cluster", "scope_id": cluster["id"],
            "scope_object": cluster.get("name") or cluster.get("code"),
            "authority": "DPMPTSP", "reference_no": "PBG/2025/0451",
            "expiry_at": _plus(720), "reminder_days": 60, "requirement_code": "PBG",
            "notes": "Berlaku untuk seluruh unit di cluster ini.",
        })
    if block:
        specs.append({
            "type": "SLF", "name": f"SLF {block.get('name') or block.get('code')}",
            "scope": "block", "scope_id": block["id"],
            "scope_object": block.get("name") or block.get("code"),
            "authority": "Dinas PU", "reference_no": "SLF/2026/0087",
            "expiry_at": _plus(21), "reminder_days": 30, "requirement_code": "SLF",
            "notes": "Perlu perpanjangan sebelum serah terima unit berikutnya.",
        })
    if unit:
        specs.append({
            "type": "SITE_PLAN", "name": f"Pengesahan site plan unit {unit.get('code')}",
            "scope": "unit", "scope_id": unit["id"], "scope_object": unit.get("code"),
            "authority": "Dinas Tata Ruang", "reference_no": "SP/2024/0198",
            # sengaja LEWAT tanggal: membuktikan "disetujui tetapi kedaluwarsa" terlihat
            "expiry_at": _plus(-9), "reminder_days": 14,
            "notes": "Revisi tata letak carport belum disahkan ulang.",
        })
    specs.append({
        "type": "ANDALALIN", "name": "Analisis dampak lalu lintas kawasan",
        "scope": "project", "scope_id": project["id"], "status": "in_progress",
        "authority": "Dinas Perhubungan", "deadline": _plus(30), "reminder_days": 14,
        "notes": "Masih diproses — belum bisa dipakai sebagai bukti izin lengkap.",
    })
    for spec in specs:
        if await _permit(org, project, spec):
            out["permits"] += 1

    if unit:
        punches = [
            {"title": f"Nat keramik tidak rata (unit {unit.get('code')})",
             "description": "Nat keramik ruang tamu bergelombang, perlu dibongkar sebagian.",
             "location": "Ruang tamu", "severity": "medium", "category": "finishing",
             "assigned_to": "site@sipro.co.id", "due_date": _plus(5)},
            {"title": f"Bocor sambungan talang (unit {unit.get('code')})",
             "description": "Sambungan talang belakang menetes saat hujan.",
             "location": "Belakang", "severity": "high", "category": "finishing",
             "assigned_to": "site@sipro.co.id", "due_date": _plus(2)},
        ]
        for p in punches:
            if await _punch(org, project, unit, p):
                out["punch"] += 1
        if await _inspection(org, project, unit):
            out["inspections"] += 1

    # calon "Mulai Bangun" — dijalankan PALING AKHIR supaya tidak dipilih sebagai unit
    # "sedang berjalan" di atas (izin/temuan unit tetap menempel pada unit yang benar).
    out["candidate"] = await _candidate_schedule(org, project)

    if any([out["permits"], out["punch"], out["inspections"], out["candidate"]]):
        logger.info("Seed Fase 46: %s izin bertingkat, %s temuan unit, %s inspeksi unit, "
                    "calon mulai bangun=%s.",
                    out["permits"], out["punch"], out["inspections"], out["candidate"])
    return out
