"""phase_templates — template TAHAPAN progres proyek (fase kawasan berbobot).

Sebelum ini `construction_phases` hanya lahir dari seed: endpoint POST /construction/phases
ada, tetapi tidak ada layar yang memanggilnya dan tidak ada urutan bawaan yang bisa diatur.
Proyek baru = 0 fase = progres kawasan tidak pernah bisa dicatat.

Template hidup di koleksi `phase_templates` (per organisasi) dan dikelola dari Pusat
Konfigurasi › Tahapan Pembangunan. "Terapkan ke proyek" menyalin baris template menjadi
`construction_phases` proyek itu (nama yang sudah ada dilewati, tidak diduplikasi).
"""
from pymongo.errors import DuplicateKeyError

from core_utils import new_id, now_iso
from db import db
from engine import recompute_project_progress

COLL = "phase_templates"
DEFAULT_CODE = "RUMAH-TAPAK"
DEFAULT_PHASES = [
    ("Persiapan Lahan", 10, 100, "persiapan"), ("Pondasi", 20, 100, "struktur"),
    ("Struktur", 30, 60, "struktur"), ("Dinding & Atap", 20, 20, "arsitektur"),
    ("MEP (Listrik/Air)", 10, 0, "mep"), ("Finishing", 10, 0, "finishing"),
]


def validate_rows(rows: list) -> list:
    """Peringatan (bukan error) supaya pengatur sadar dampaknya pada angka progres."""
    warns = []
    names = [str(r.get("name") or "").strip().lower() for r in rows]
    if len(set(names)) != len(names):
        warns.append("Ada nama fase ganda — nama fase harus unik dalam satu proyek.")
    total = sum(int(r.get("weight") or 0) for r in rows)
    if total != 100:
        warns.append(f"Total bobot {total}% (ideal 100%). Progres tetap proporsional, "
                     "tetapi angka jadi sulit dibaca.")
    return warns


def normalize_rows(rows: list) -> list:
    return [{"name": str(r["name"]).strip(), "weight": int(r["weight"]),
             "planned_pct": int(r.get("planned_pct") or 0), "order": i + 1,
             "work_category": (str(r.get("work_category") or "").strip().lower() or None)}
            for i, r in enumerate(rows)]


async def ensure_default(org: str) -> bool:
    if await db[COLL].find_one({"org_id": org}, {"_id": 0, "id": 1}):
        return False
    ts = now_iso()
    try:
        await db[COLL].insert_one({
            "id": new_id(), "org_id": org, "code": DEFAULT_CODE,
            "name": "Rumah tapak — 6 fase kawasan",
            "description": "Urutan fase kawasan bawaan: persiapan lahan → pondasi → struktur → "
                           "dinding & atap → MEP → finishing.",
            "phases": normalize_rows([{"name": n, "weight": w, "planned_pct": p, "work_category": c}
                                      for n, w, p, c in DEFAULT_PHASES]),
            "is_default": True, "version": 1, "created_by": "system",
            "created_at": ts, "updated_at": ts,
        })
    except DuplicateKeyError:  # dua permintaan pertama berlomba: index unik memenangkan satu
        return False
    return True


async def list_templates(org: str) -> list:
    rows = await db[COLL].find({"org_id": org}, {"_id": 0}).sort("code", 1).to_list(100)
    for r in rows:
        r["phases_count"] = len(r.get("phases") or [])
        r["total_weight"] = sum(int(p.get("weight") or 0) for p in r.get("phases") or [])
        r["warnings"] = validate_rows(r.get("phases") or [])
    return rows


async def apply_to_project(org: str, project_id: str, template: dict, actor: str) -> dict:
    """Salin baris template → construction_phases proyek. Nama yang sudah ada dilewati."""
    ts = now_iso()
    existing = await db.construction_phases.find(
        {"org_id": org, "project_id": project_id}, {"_id": 0, "name": 1, "order": 1}).to_list(300)
    have = {e["name"].strip().lower() for e in existing}
    next_order = max([int(e.get("order") or 0) for e in existing], default=0)
    made, skipped = [], []
    for row in template.get("phases") or []:
        if row["name"].strip().lower() in have:
            skipped.append(row["name"])
            continue
        next_order += 1
        doc = {"id": new_id(), "org_id": org, "project_id": project_id, "name": row["name"],
               "weight": int(row["weight"]), "planned_pct": int(row.get("planned_pct") or 0),
               "work_category": row.get("work_category") or None,
               "progress": 0, "status": "not_started", "order": next_order,
               "template_id": template["id"], "template_code": template.get("code"),
               "created_by": actor, "created_at": ts, "updated_at": ts}
        await db.construction_phases.insert_one(doc)
        doc.pop("_id", None)
        made.append(doc)
    overall = await recompute_project_progress(project_id, org)
    return {"created": made, "skipped": skipped, "overall": overall}
