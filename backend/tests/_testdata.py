"""Pembersih artefak uji berlabel TAG — dipakai suite legacy yang membuat master tanpa endpoint hapus.

Semua penghapusan dijaga: proyek hanya dibuang bila unitnya tidak punya deal/kontrak,
SPK hanya bila tanpa termin/lampiran. Tidak ada purge massal.
"""
from dotenv import dotenv_values
from pymongo import MongoClient


def _db():
    env = dotenv_values("/app/backend/.env")
    return MongoClient(env["MONGO_URL"])[env["DB_NAME"]]


def purge_tagged(tag: str, *, project_names=(), vendor_names=(), subcon_names=(),
                 unit_type_names=(), addon_names=(), spk_titles=()) -> dict:
    db = _db()
    out = {"projects": 0, "vendors": 0, "subcontractors": 0, "unit_types": 0, "addons": 0, "spk": 0}
    for title in spk_titles:
        for spk in db.spk.find({"title": title}, {"id": 1}):
            if db.progress_claims.count_documents({"spk_id": spk["id"]}) == 0 \
                    and db.spk_attachments.count_documents({"spk_id": spk["id"]}) == 0:
                out["spk"] += db.spk.delete_one({"id": spk["id"]}).deleted_count
    for name in project_names:
        for proj in db.projects.find({"name": name}, {"id": 1}):
            pid = proj["id"]
            unit_ids = [u["id"] for u in db.units.find({"project_id": pid}, {"id": 1})]
            if db.deals.count_documents({"unit_id": {"$in": unit_ids}}) or \
                    db.contracts.count_documents({"project_id": pid}) or \
                    db.spk.count_documents({"project_id": pid}):
                continue
            db.units.delete_many({"project_id": pid})
            for cl in db.clusters.find({"project_id": pid}, {"id": 1}):
                db.blocks.delete_many({"cluster_id": cl["id"]})
            db.clusters.delete_many({"project_id": pid})
            out["projects"] += db.projects.delete_one({"id": pid}).deleted_count
    if vendor_names:
        out["vendors"] = db.vendors.delete_many({"name": {"$in": list(vendor_names)}}).deleted_count
    if subcon_names:
        ids = [s["id"] for s in db.subcontractors.find({"name": {"$in": list(subcon_names)}}, {"id": 1})]
        ids = [i for i in ids if db.spk.count_documents({"subcontractor_id": i}) == 0]
        out["subcontractors"] = db.subcontractors.delete_many({"id": {"$in": ids}}).deleted_count
    if unit_type_names:
        codes = [t["code"] for t in db.unit_types.find({"name": {"$in": list(unit_type_names)}}, {"code": 1})]
        codes = [c for c in codes if db.units.count_documents({"unit_type_code": c}) == 0]
        out["unit_types"] = db.unit_types.delete_many({"code": {"$in": codes}}).deleted_count
    if addon_names:
        out["addons"] = db.addon_items.delete_many({"name": {"$in": list(addon_names)}}).deleted_count
    return out
