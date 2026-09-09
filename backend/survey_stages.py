"""survey_stages — tahapan catatan survey (langkah berurutan, tiap langkah punya poin).

Sebelum ini survey hanya punya satu daftar datar `survey.checklist_items` (teks dipisah koma)
yang terkubur di kelompok "Lead & Lifecycle". Tidak ada urutan, tidak ada pengelompokan,
tidak ada poin yang wajib dinilai sebelum survey boleh diselesaikan.

Konfigurasi hidup di koleksi `survey_stage_configs` (satu dokumen per organisasi). Survey
BARU menyalin tahapan saat dibuat (`survey.stages` + `checklist[].stage_key`), sehingga
mengubah konfigurasi tidak mengubah survey yang sedang berjalan.
"""
import re

from pymongo.errors import DuplicateKeyError

import settings_store as cfg
from core_utils import new_id, now_iso
from db import db

COLL = "survey_stage_configs"
DEFAULT_STAGES = [
    ("Verifikasi & kebutuhan pembeli",
     "Pastikan identitas dan kebutuhan pembeli sebelum meninjau lokasi.",
     [("Identitas pembeli sesuai data lead", True), ("Kebutuhan tipe unit & jumlah kamar", True),
      ("Rencana skema pembayaran (cash/KPR)", False)]),
    ("Kondisi lokasi & kavling",
     "Tinjau fisik lokasi bersama pembeli.",
     [("Akses jalan menuju lokasi", True), ("Kondisi tanah & kontur", True),
      ("Batas kavling & patok jelas", True), ("Saluran drainase", False)]),
    ("Utilitas & lingkungan", "Kesiapan utilitas dan lingkungan sekitar.",
     [("Ketersediaan listrik", True), ("Ketersediaan air / PDAM", True),
      ("Lingkungan & keamanan sekitar", False)]),
    ("Dokumentasi & rekomendasi", "Foto bukti kunjungan dan kesimpulan sales.",
     [("Foto tampak depan kavling/unit", True), ("Foto lingkungan sekitar", False),
      ("Minat & keberatan pembeli dicatat", True)]),
]


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:40] or "item"


def normalize(stages: list) -> list:
    """Beri kunci unik & urutan; tolak nama tahap ganda."""
    out, seen_stage, seen_item = [], set(), set()
    for i, s in enumerate(stages, start=1):
        key, n = slug(s["name"]), 2
        while key in seen_stage:
            key, n = f"{slug(s['name'])}_{n}", n + 1
        seen_stage.add(key)
        items = []
        for it in s.get("items") or []:
            ik, m = slug(it["label"]), 2
            while ik in seen_item:
                ik, m = f"{slug(it['label'])}_{m}", m + 1
            seen_item.add(ik)
            items.append({"key": ik, "label": str(it["label"]).strip(),
                          "required": bool(it.get("required")), "hint": it.get("hint")})
        out.append({"key": key, "order": i, "name": str(s["name"]).strip(),
                    "description": s.get("description"), "items": items})
    return out


def validate(stages: list) -> list:
    warns = []
    if not any(s.get("items") for s in stages):
        warns.append("Tidak ada satu pun poin pemeriksaan — survey akan kosong.")
    for s in stages:
        if not s.get("items"):
            warns.append(f"Tahap '{s['name']}' tidak punya poin pemeriksaan.")
    return warns


async def ensure_default(org: str) -> bool:
    if await db[COLL].find_one({"org_id": org}, {"_id": 0, "id": 1}):
        return False
    # Organisasi yang sudah mengubah `survey.checklist_items` lama: bawa isinya jadi satu tahap.
    legacy = [str(x).strip() for x in
              (await cfg.get("survey.checklist_items", org_id=org) or []) if str(x).strip()]
    default_labels = {lb for _n, _d, items in DEFAULT_STAGES for lb, _r in items}
    if legacy and set(legacy) - default_labels:
        stages = [{"name": "Pemeriksaan lokasi", "description": "Dipindahkan dari checklist lama.",
                   "items": [{"label": lb, "required": False} for lb in legacy]}]
    else:
        stages = [{"name": n, "description": d,
                   "items": [{"label": lb, "required": r} for lb, r in items]}
                  for n, d, items in DEFAULT_STAGES]
    ts = now_iso()
    try:
        await db[COLL].insert_one({"id": new_id(), "org_id": org, "stages": normalize(stages),
                                   "version": 1, "updated_by": "system", "created_at": ts,
                                   "updated_at": ts})
    except DuplicateKeyError:
        return False
    return True


async def get_config(org: str) -> dict:
    await ensure_default(org)
    doc = await db[COLL].find_one({"org_id": org}, {"_id": 0})
    doc["warnings"] = validate(doc.get("stages") or [])
    return doc


async def save_config(org: str, stages: list, actor: str) -> dict:
    norm = normalize(stages)
    cur = await db[COLL].find_one({"org_id": org}, {"_id": 0, "version": 1})
    upd = {"stages": norm, "version": int((cur or {}).get("version") or 0) + 1,
           "updated_by": actor, "updated_at": now_iso()}
    await db[COLL].update_one({"org_id": org}, {"$set": upd, "$setOnInsert": {
        "id": new_id(), "org_id": org, "created_at": now_iso()}}, upsert=True)
    return await get_config(org)


async def checklist_for_new_survey(org: str) -> tuple:
    """(stages ringkas, checklist datar ber-`stage_key`) untuk survey yang baru dibuat."""
    conf = await get_config(org)
    stages = [{"key": s["key"], "order": s["order"], "name": s["name"],
               "description": s.get("description")} for s in conf["stages"]]
    items = [{"key": it["key"], "label": it["label"], "status": "na", "note": None,
              "stage_key": s["key"], "required": bool(it.get("required")), "hint": it.get("hint")}
             for s in conf["stages"] for it in s["items"]]
    return stages, items


def unfinished_required(checklist: list) -> list:
    return [c["label"] for c in checklist or [] if c.get("required") and c.get("status") == "na"]
