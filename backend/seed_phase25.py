"""Site Plan / Showroom Digital (EPIC P29) — demo kavling multi-blok.

Proyek demo awal hanya memiliki 1 blok (A-01..A-06) sehingga peta site plan tidak
memperlihatkan tata letak nyata (beberapa blok dipisah jalan, tipe & posisi
berbeda). Modul ini menambah blok B (rumah tipe besar) dan blok C (ruko/kavling
siap bangun) pada proyek demo pertama.

IDempoten: bila blok B sudah ada untuk proyek tersebut, tidak ada penambahan.
Semua unit baru berstatus `available` (data jujur — belum ada deal), sehingga
reservasi lewat klik-peta bisa diuji langsung tanpa data palsu.
"""
import logging

from db import db, ORG_ID
from core_utils import new_id, now_iso

logger = logging.getLogger("sipro.seed")

# (code, type, price, luas_bangunan, luas_tanah, orientation, corner)
# orientation memakai nilai KANONIK SSOT (`unit_orientation`, Fase 28b).
DEMO_PLOTS = [
    ("B-01", "Tipe 70/120", 1_250_000_000, 70, 120, "utara", True),
    ("B-02", "Tipe 70/120", 1_180_000_000, 70, 120, "utara", False),
    ("B-03", "Tipe 54/105", 980_000_000, 54, 105, "utara", False),
    ("B-04", "Tipe 54/105", 980_000_000, 54, 105, "selatan", False),
    ("B-05", "Tipe 36/72", 685_000_000, 36, 72, "selatan", False),
    ("B-06", "Tipe 36/72", 685_000_000, 36, 72, "selatan", True),
    ("C-01", "Ruko", 1_650_000_000, 120, 80, "timur", True),
    ("C-02", "Ruko", 1_550_000_000, 120, 80, "timur", False),
    ("C-03", "Ruko", 1_550_000_000, 120, 80, "timur", False),
    ("C-04", "Kavling", 720_000_000, 0, 96, "barat", False),
    ("C-05", "Kavling", 720_000_000, 0, 96, "barat", False),
    ("C-06", "Kavling", 810_000_000, 0, 108, "barat", True),
]


async def seed_site_plan_demo(org_id: str = ORG_ID) -> int:
    """Tambah kavling blok B & C ke proyek demo pertama. Return jumlah unit dibuat."""
    project = await db.projects.find_one({"org_id": org_id}, {"_id": 0, "id": 1, "name": 1},
                                         sort=[("created_at", 1)])
    if not project:
        return 0
    existing = await db.units.count_documents(
        {"org_id": org_id, "project_id": project["id"], "code": {"$regex": "^B-"}})
    if existing:
        return 0

    ts = now_iso()
    docs = []
    for code, utype, price, lb, lt, orientation, corner in DEMO_PLOTS:
        docs.append({
            "id": new_id(), "org_id": org_id, "project_id": project["id"],
            "code": code, "type": utype, "price": int(price),
            "luas_bangunan": lb, "luas_tanah": lt,
            "orientation": orientation, "corner": corner,
            "block": code.split("-")[0],
            "status": "available", "construction_status": "not_started",
            "construction_progress": 0, "payment_status": "none",
            "reserved_by_deal": None, "booked_by_deal": None,
            "created_at": ts, "updated_at": ts,
        })
    await db.units.insert_many(docs)
    logger.info("Seed site plan: %d kavling demo (blok B & C) di proyek %s",
                len(docs), project.get("name"))
    return len(docs)
