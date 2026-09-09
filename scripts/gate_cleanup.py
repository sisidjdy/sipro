"""Cleanup for a lead created by the P75 negative test, never general user-data purge."""
from pathlib import Path
from dotenv import dotenv_values
from pymongo import MongoClient


def cleanup_p75_lead(lead_id):
    env = dotenv_values(Path(__file__).resolve().parent.parent / "backend/.env")
    with MongoClient(env["MONGO_URL"]) as client:
        db = client[env["DB_NAME"]]
        lead = db.leads.find_one({"id": lead_id}, {"_id": 0})
        if not lead or not lead.get("name", "").startswith("Gate P75 biaya bebas "):
            return
        org = lead["org_id"]
        for coll in ("deals", "contracts", "customers", "documents"):
            if db[coll].count_documents({"org_id": org, "lead_id": lead_id}):
                raise RuntimeError(f"Tidak menghapus fixture {lead_id}: ada transaksi {coll}.")
        appointments = [a["id"] for a in db.appointments.find({"org_id": org, "lead_id": lead_id}, {"_id": 0, "id": 1})]
        ids = [lead_id] + appointments
        for coll in ("activities", "tasks", "notifications", "events", "audit_logs", "surveys", "appointments", "lead_score_events"):
            db[coll].delete_many({"org_id": org, "$or": [
                {"lead_id": lead_id}, {"related_entity_id": {"$in": ids}},
                {"entity_id": {"$in": ids}}, {"appointment_id": {"$in": appointments}}]})
        db.leads.delete_one({"id": lead_id, "org_id": org})