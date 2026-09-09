"""Bersihkan data uji P112 (tasks & leads berprefix TEST_P112) langsung dari MongoDB.

Alasan: API tidak menyediakan DELETE untuk /work/tasks maupun /leads, jadi data uji
harus dibersihkan di lapisan penyimpanan agar demo tidak tercemar.
"""
import os

from dotenv import dotenv_values
from pymongo import MongoClient

env = dotenv_values("/app/backend/.env")
cli = MongoClient(os.environ.get("MONGO_URL") or env["MONGO_URL"])
db = cli[os.environ.get("DB_NAME") or env["DB_NAME"]]

names = [c for c in db.list_collection_names() if "task" in c]
print("task collections:", names)
for c in names:
    docs = list(db[c].find({"title": {"$regex": "^TEST_P112"}},
                           {"_id": 0, "title": 1, "related_entity_type": 1,
                            "related_entity_id": 1}))
    if docs:
        print(f"-- {c}: {len(docs)} doc(s)")
        for d in docs:
            print("   ", d.get("title"), "|", d.get("related_entity_type"),
                  "|", (d.get("related_entity_id") or "")[:8])
        print("   deleted:", db[c].delete_many({"title": {"$regex": "^TEST_P112"}}).deleted_count)
print("leads deleted:", db.leads.delete_many({"name": {"$regex": "^TEST_P112"}}).deleted_count)
cli.close()
