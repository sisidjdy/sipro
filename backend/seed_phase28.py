"""Seed Fase 28b — peta SVG demo langsung tersedia + orientasi kavling kanonik.

Masalah nyata yang diperbaiki: pada DB bersih, koleksi `site_plans` kosong sehingga
halaman Site Plan selalu memakai fallback "tata letak blok otomatis" dan peta realistis
(jalan, cul-de-sac, taman, danau) baru muncul kalau pengguna membuka Studio Peta lalu
menekan "Bangkitkan". Untuk demo maupun pengujian, peta seharusnya sudah ada.

IDEMPOTEN: peta hanya dibangkitkan bila proyek belum punya dokumen `site_plans`;
perubahan manual pengguna (unggah SVG arsitek / pemetaan ulang) tidak pernah ditimpa.
"""
import io
import logging

import site_plan_svg as svgplan
import storage
from core_utils import new_id, now_iso
from db import db, ORG_ID

logger = logging.getLogger("sipro.seed")

# Foto contoh: gambar PLACEHOLDER yang dibangkitkan sendiri (bukan foto proyek asli) dan
# labelnya menyebut "contoh" secara terbuka, supaya galeri foto bisa langsung dilihat &
# diuji di DB bersih tanpa menyamarkan data palsu sebagai dokumentasi nyata.
DEMO_SHOTS = [
    ("diary", "Contoh dokumentasi: pengecoran kolom lantai 1", (58, 104, 84)),
    ("diary", "Contoh dokumentasi: pemasangan bekisting", (74, 96, 122)),
    ("punch", "Contoh temuan: retak rambut dinding", (150, 82, 70)),
]


def _placeholder_png(text: str, tone) -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (640, 400), tone)
    d = ImageDraw.Draw(img)
    for y in range(400):
        d.line([(0, y), (640, y)], fill=(min(255, tone[0] + y // 7),
                                         min(255, tone[1] + y // 9),
                                         min(255, tone[2] + y // 11)))
    d.rectangle([24, 300, 616, 376], fill=(255, 255, 255))
    d.text((40, 332), text[:60], fill=(28, 44, 38))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def seed_demo_photos(org_id: str = ORG_ID) -> int:
    """Lampirkan foto contoh ke satu buku harian & satu temuan punch (idempoten).

    Dikawal marker `finance_configs.key = "seed_28b_photos"`; foto diunggah lewat
    LAPISAN STORAGE yang sama dengan unggahan pengguna, jadi alurnya identik
    (bukan jalur khusus seed).
    """
    marker = {"key": "seed_28b_photos", "org_id": org_id}
    if await db.finance_configs.count_documents(marker):
        return 0
    diary = await db.site_diaries.find_one({"org_id": org_id}, {"_id": 0, "id": 1, "project_id": 1},
                                           sort=[("log_date", -1)])
    punch = await db.punch_items.find_one({"org_id": org_id, "unit_id": {"$nin": [None, ""]}},
                                          {"_id": 0, "id": 1, "project_id": 1})
    if not punch:
        # Temuan punch demo dibuat SEBELUM Fase 28b, saat UI belum punya field "kavling
        # terkait", sehingga tidak pernah tertaut ke unit. Tautkan satu temuan ke kavling
        # pertama proyeknya agar galeri per-kavling & portal pembeli punya contoh nyata.
        cand = await db.punch_items.find_one({"org_id": org_id},
                                             {"_id": 0, "id": 1, "project_id": 1})
        if cand:
            unit = await db.units.find_one({"org_id": org_id, "project_id": cand["project_id"]},
                                           {"_id": 0, "id": 1}, sort=[("code", 1)])
            if unit:
                await db.punch_items.update_one({"id": cand["id"]},
                                                {"$set": {"unit_id": unit["id"]}})
                punch = cand
    if not diary and not punch:
        return 0
    made = 0
    for kind, label, tone in DEMO_SHOTS:
        target = diary if kind == "diary" else punch
        if not target:
            continue
        rec = await storage.save_file(
            data=_placeholder_png(label, tone), filename=f"{label[:24]}.png",
            content_type="image/png", org_id=org_id,
            owner_type="site_diary" if kind == "diary" else "punch_item",
            owner_id=target["id"], uploaded_by="seed", doc_type="foto_lapangan",
            tag="contoh")
        coll = db.site_diaries if kind == "diary" else db.punch_items
        await coll.update_one({"id": target["id"]},
                              {"$addToSet": {"photos": rec["id"]},
                               "$set": {"photo": rec["id"]}})
        made += 1
    await db.finance_configs.insert_one({**marker, "created_at": now_iso(),
                                         "note": f"{made} foto contoh lapangan"})
    logger.info("Seed Fase 28b: %d foto contoh lapangan dilampirkan", made)
    return made


async def seed_demo_plans(org_id: str = ORG_ID) -> int:
    """Bangkitkan peta demo untuk setiap proyek yang punya unit tapi belum punya peta."""
    made = 0
    projects = await db.projects.find({"org_id": org_id}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
    for p in projects:
        if await db.site_plans.count_documents({"org_id": org_id, "project_id": p["id"]}):
            continue
        units = await db.units.find({"org_id": org_id, "project_id": p["id"]},
                                    {"_id": 0, "id": 1, "code": 1}).to_list(3000)
        if not units:
            continue
        built = svgplan.generate_demo_plan(units)
        ts = now_iso()
        await db.site_plans.insert_one({
            "id": new_id(), "org_id": org_id, "project_id": p["id"],
            "source": "generated", "view_box": built["view_box"], "shapes": built["shapes"],
            "filename": None, "updated_by": "seed", "updated_at": ts, "created_at": ts,
        })
        made += 1
        logger.info("Seed Fase 28b: peta demo dibangkitkan untuk proyek %s (%d shape)",
                    p.get("name"), len(built["shapes"]))
    return made
