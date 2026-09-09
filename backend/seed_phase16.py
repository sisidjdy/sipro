"""Seed data EPIC 2.3 — Progress Claim (Termin) & Change Order (dipisah agar seed.py ramping)."""
from db import db, ORG_ID
from core_utils import new_id


async def seed_subcon_claims(spk1_id, sub1_id, project_id, year, ts, due_date):
    """1 termin 'submitted' (40%→60%) + 1 change order 'draft' (+25jt) untuk SPK/0001."""
    if await db.progress_claims.count_documents({"org_id": ORG_ID}):
        return
    await db.progress_claims.insert_one({
        "id": new_id(), "org_id": ORG_ID, "claim_number": f"TRM/{year}/0001",
        "spk_id": spk1_id, "spk_number": f"SPK/{year}/0001",
        "subcontractor_id": sub1_id, "subcontractor_name": "CV Bangun Jaya",
        "project_id": project_id, "project_name": "Cluster Asri Blok A",
        "period": "Termin 2 (40%→60%)", "prev_pct": 40, "claimed_pct": 60, "verified_pct": None,
        "effective_pct": None, "contract_value_at_submit": 300_000_000,
        "gross_est": 60_000_000, "gross": 0, "retention_pct": 5.0, "retention_held": 0, "net": 0,
        "ap_bill_id": None, "due_date": due_date, "status": "submitted",
        "note": "Pengecoran pelat lantai 2 selesai.", "created_by": "site@sipro.co.id",
        "created_at": ts, "updated_at": ts,
    })
    await db.change_orders.insert_one({
        "id": new_id(), "org_id": ORG_ID, "co_number": f"CO/{year}/0001",
        "spk_id": spk1_id, "spk_number": f"SPK/{year}/0001", "subcontractor_name": "CV Bangun Jaya",
        "project_id": project_id, "project_name": "Cluster Asri Blok A",
        "title": "Tambah pekerjaan tangga beton", "description": "Penambahan struktur tangga blok A.",
        "value_delta": 25_000_000, "time_extension_days": 14, "reason": "Perubahan gambar kerja",
        "original_value": 300_000_000, "new_value": None, "status": "draft",
        "created_by": "pm@sipro.co.id", "created_at": ts, "updated_at": ts,
    })
