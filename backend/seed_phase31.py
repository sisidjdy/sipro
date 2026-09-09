"""Seed Fase 31 — template jadwal pembangunan + jadwal demo per unit + perbaikan cacat.

Tiga pekerjaan yang dilakukan (semua IDEMPOTEN):

1. **Template default** (`build_templates`) dari `build_catalog`: rumah tapak 9 minggu dan
   ruko 15 minggu. Template milik pengguna (hasil duplikasi/ubah) tidak pernah ditimpa.

2. **Jadwal demo** untuk beberapa unit dengan tanggal mulai berbeda supaya papan pantau
   langsung memperlihatkan kondisi nyata: ada yang tepat waktu, ada yang TERLAMBAT, ada
   yang belum mulai, dan ada yang tertahan menunggu curing. Pekerjaan yang ditandai
   selesai pada seed memakai foto **placeholder berlabel "contoh"** melalui lapisan
   storage yang sama dengan unggahan pengguna — tidak ada bukti palsu yang disamarkan
   sebagai dokumentasi asli.

3. **Perbaikan cacat lama (D-A & D-F)**:
   * `units.construction_progress` yang dulu ditimpa massal dari progres PROYEK direset
     ke 0 untuk unit yang belum punya jadwal (angka itu tidak pernah nyata per rumah).
   * `units.deal_id / lead_id / lead_name / customer_id` diisi dari deal terkait supaya
     unit benar-benar terikat pada lead & pembeli.
"""
import logging

import build_catalog as bcat
import build_engine as be
import build_policy as bpol
import indexes as ix
import build_reports as breports
import opname as op
import storage
from core_utils import new_id, now, now_iso
from db import db, ORG_ID
from seed_phase28 import _placeholder_png

logger = logging.getLogger("sipro.seed")

MARKER = "seed_31_build"

# (offset hari mulai, jumlah item yang diverifikasi, jumlah item yang menunggu verifikasi)
DEMO_PLAN = [(-45, 6, 1), (-14, 2, 0), (3, 0, 0), (-7, 1, 0)]


async def _ensure_templates(org: str) -> int:
    made = 0
    ts = now_iso()
    for tpl in bcat.DEFAULT_TEMPLATES:
        exists = await db.build_templates.find_one({"org_id": org, "code": tpl["code"]},
                                                  {"_id": 0, "id": 1})
        if exists:
            continue
        await db.build_templates.insert_one({
            **tpl, "id": new_id(), "org_id": org, "project_id": None, "is_active": True,
            "is_default": True, "version": 1, "created_by": "seed",
            "created_at": ts, "updated_at": ts})
        made += 1
    return made


async def _evidence(org: str, item: dict, count: int) -> list:
    """Foto contoh untuk bukti seed — lewat storage nyata (ada watermark + hash)."""
    out = []
    for n in range(count):
        text = f"Contoh bukti: {item['name'][:44]} ({n + 1})"
        rec = await storage.save_file(
            data=_placeholder_png(text, (62, 96 + n * 14, 82)),
            filename=f"contoh-{item['step_code'].lower()}-{n + 1}.png",
            content_type="image/png", org_id=org, owner_type="build_item",
            owner_id=item["id"], uploaded_by="seed", doc_type="build_evidence",
            tag="build", optimize=True,
            watermark_lines=[f"CONTOH · unit {item.get('unit_code')}", text[:60]])
        out.append({
            "file_id": rec["id"], "sha256": rec.get("sha256"),
            "filename": rec.get("original_filename"), "content_type": rec.get("content_type"),
            "size": rec.get("size"), "uploaded_by": "seed", "uploaded_at": rec.get("created_at"),
            "watermark": rec.get("watermark"), "by_other_person": False,
            "attached_by": "seed", "attached_at": now_iso(),
        })
    return out


async def _finish_item(org: str, item: dict, *, verified: bool, actor_do: str,
                       actor_check: str) -> None:
    """Tandai item seed sebagai diajukan (dan opsional diverifikasi) dengan bukti nyata."""
    ev = await _evidence(org, item, max(1, int(item.get("min_photos") or 1)))
    checklist = [{**c, "result": "pass", "note": None} for c in item.get("checklist") or []]
    when = f"{item['planned_finish']}T09:30:00+00:00"
    upd = {
        "status": "done" if verified else "submitted",
        "checklist": checklist, "evidence": ev,
        "note": ("Data awal demo: pekerjaan dikerjakan sesuai checklist mutu; "
                 "foto bukti berlabel CONTOH."),
        "started_at": f"{item['planned_start']}T01:00:00+00:00",
        "submitted_at": when, "submitted_by": actor_do, "updated_at": now_iso(),
        "history": [{"at": when, "action": "submit", "actor": actor_do,
                     "note": "Seed data awal", "photos": len(ev)}],
    }
    if verified:
        upd.update({"verified_at": when, "verified_by": actor_check,
                    "verify_note": "Diverifikasi pada penyiapan data awal."})
        upd["history"].append({"at": when, "action": "verify", "actor": actor_check,
                               "note": "Seed data awal"})
    await db.build_items.update_one({"id": item["id"]}, {"$set": upd})


async def _demo_schedules(org: str) -> int:
    from datetime import timedelta
    project = await db.projects.find_one({"org_id": org}, {"_id": 0})
    if not project:
        return 0
    units = await db.units.find({"org_id": org, "project_id": project["id"]},
                                {"_id": 0}).sort("code", 1).to_list(60)
    buildable = [u for u in units if u.get("type") not in bcat.NO_BUILD_UNIT_TYPES]
    if not buildable:
        return 0
    site = await db.users.find_one({"org_id": org, "role": "site_engineer"},
                                   {"_id": 0, "email": 1}) or {}
    pm = await db.users.find_one({"org_id": org, "role": "project_manager"},
                                 {"_id": 0, "email": 1}) or {}
    made = 0
    today = now().date()
    for (offset, n_done, n_submit), unit in zip(DEMO_PLAN, buildable):
        if await db.build_schedules.count_documents({"org_id": org, "unit_id": unit["id"]}):
            continue
        try:
            tpl = await be.template_for_unit(org, unit)
            sched = await be.generate_schedule(
                org, unit, tpl, (today + timedelta(days=offset)).isoformat(), "seed")
        except ValueError as e:
            logger.info("Seed 31: lewati unit %s — %s", unit.get("code"), e)
            continue
        made += 1
        items = await db.build_items.find({"org_id": org, "schedule_id": sched["id"]},
                                          {"_id": 0}).sort("order", 1).to_list(500)
        for it in items[:n_done]:
            await _finish_item(org, it, verified=True, actor_do=site.get("email", "seed"),
                               actor_check=pm.get("email", "seed"))
        for it in items[n_done:n_done + n_submit]:
            await _finish_item(org, it, verified=False, actor_do=site.get("email", "seed"),
                               actor_check=pm.get("email", "seed"))
        await be.refresh_gates(org, sched["id"])
        await be.recompute_schedule(org, sched["id"])
    return made


async def _fix_unit_defects(org: str) -> dict:
    """D-A: buang progres unit warisan yang sebenarnya angka PROYEK. D-F: ikat unit↔lead."""
    scheduled = set(await db.build_schedules.distinct("unit_id", {"org_id": org}))
    reset = 0
    async for u in db.units.find({"org_id": org}, {"_id": 0, "id": 1, "construction_progress": 1}):
        if u["id"] in scheduled:
            continue
        if int(u.get("construction_progress") or 0) > 0:
            await db.units.update_one({"id": u["id"]}, {"$set": {
                "construction_progress": 0, "construction_status": "not_started",
                "updated_at": now_iso()}})
            reset += 1
    bound = 0
    async for u in db.units.find(
            {"org_id": org, "$or": [{"booked_by_deal": {"$nin": [None, ""]}},
                                    {"reserved_by_deal": {"$nin": [None, ""]}},
                                    {"sold_by_deal": {"$nin": [None, ""]}}]},
            {"_id": 0, "id": 1}):
        await be.sync_unit_binding(org, u["id"])
        bound += 1
    return {"progress_reset": reset, "units_bound": bound}


async def _ensure_policy(org: str) -> int:
    """Kebijakan bukti kerja (Fase 32) harus SELALU ADA sebagai dokumen nyata.

    Sebelumnya kebijakan hanya lahir saat admin menekan simpan, sehingga koleksi
    `build_policies` kosong pada database baru: audit forensik menandainya HIGH dan
    admin tidak bisa melihat "sejak kapan / oleh siapa" aturan berlaku. Sekarang nilai
    bawaan organisasi ditulis satu kali (idempoten) dan tetap bisa diubah admin.
    """
    if await db.build_policies.count_documents({"org_id": org}):
        return 0
    await db.build_policies.insert_one({
        **bpol.DEFAULTS, "org_id": org, "updated_by": "system (bawaan organisasi)",
        "updated_at": now_iso()})
    return 1


async def _ensure_weekly_report(org: str) -> int:
    """Laporan mingguan pekan berjalan dibangkitkan dari jadwal nyata (idempoten).

    Direksi yang baru membuka aplikasi seharusnya langsung melihat laporan pekan ini,
    bukan halaman kosong sampai hari Senin berikutnya. Angka pada laporan dihitung ulang
    dari `build_schedules`/`build_items` — bukan data karangan.
    """
    if await db.build_weekly_reports.count_documents({"org_id": org}):
        return 0
    out = await breports.run_weekly(org, None, "system (laporan awal)")
    return int(out.get("created") or out.get("made") or len(out.get("reports") or []))


async def seed_phase31(org_id: str = ORG_ID) -> dict:
    """Dipanggil di lifespan `server.py` setelah storage siap (butuh unggah foto contoh)."""
    out = {"templates": await _ensure_templates(org_id), "schedules": 0}
    marker = {"key": MARKER, "org_id": org_id}
    if not await db.finance_configs.count_documents(marker):
        out["schedules"] = await _demo_schedules(org_id)
        await db.finance_configs.insert_one({
            **marker, "id": new_id(), "value": out["schedules"], "created_at": now_iso()})
    out.update(await _fix_unit_defects(org_id))
    out["policy"] = await _ensure_policy(org_id)
    out["weekly_reports"] = await _ensure_weekly_report(org_id)
    if out["templates"] or out["schedules"]:
        logger.info("Seed Fase 31: %s template, %s jadwal unit, %s progres warisan direset.",
                    out["templates"], out["schedules"], out.get("progress_reset"))
    return out


async def ensure_build_indexes():
    """Index koleksi Fase 31/32 (dipanggil `seed.ensure_indexes`).

    Diletakkan di sini supaya `seed.py` tetap di bawah batas gate compliance dan semua
    hal tentang jadwal pembangunan berada pada satu file yang jelas.
    """
    await db.build_items.create_index([("org_id", 1), ("schedule_id", 1), ("order", 1)])
    await db.build_items.create_index([("org_id", 1), ("assigned_to", 1), ("status", 1)])
    await db.build_items.create_index([("org_id", 1), ("project_id", 1), ("status", 1)])
    await db.build_schedules.create_index([("org_id", 1), ("unit_id", 1)])
    await db.build_item_submissions.create_index([("org_id", 1), ("item_id", 1)])
    # Penanda antrean offline (Fase 35) WAJIB partial index — lihat penjelasan jebakan
    # `sparse` pada index gabungan di indexes.ensure_optional_unique.
    await ix.ensure_optional_unique(
        "build_item_submissions", [("org_id", 1), ("client_ref", 1)],
        "uq_build_submission_client_ref", "client_ref")
    # Fase 35: kunci pengiriman antrean offline — dua tab/jendela tidak boleh mengirim
    # pekerjaan yang sama berbarengan (bukti dobel). Koleksi ini SEMENTARA: dihapus saat
    # pengajuan ditolak, dan sisanya dibersihkan sendiri oleh TTL 7 hari (jejak audit
    # sesungguhnya ada di `build_item_submissions` yang bisa dibaca GET /build/items/{id}).
    await ix.ensure_optional_unique(
        "build_submit_claims", [("org_id", 1), ("client_ref", 1)],
        "uq_build_submit_claim", "client_ref")
    await db.build_submit_claims.create_index("at", expireAfterSeconds=7 * 24 * 3600)
    await db.build_policies.create_index([("org_id", 1)], unique=True)
    await db.build_weekly_reports.create_index(
        [("org_id", 1), ("project_id", 1), ("week_key", 1)], unique=True)
    await op.ensure_indexes()
    import build_bulk as bb          # Fase 34 — operasi massal jadwal (idempotensi)
    await bb.ensure_indexes()
