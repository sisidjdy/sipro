"""Seed akun demo per peran secara idempoten (dipakai uji RBAC). Jalankan dari /app/backend."""
import asyncio
import os

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
os.environ["SEED_DEMO_USERS"] = "true"

import seed  # noqa: E402
from core_utils import new_id, now_iso  # noqa: E402
from db import db  # noqa: E402
from security import hash_password  # noqa: E402


async def main():
    ts = now_iso()
    for u in seed.DEMO_USERS:
        await db.users.update_one({"email": u["email"]}, {"$setOnInsert": {
            "id": new_id(), "org_id": seed.ORG_ID, "name": u["name"], "email": u["email"],
            "role": u["role"], "phone": None, "password_hash": hash_password(seed.TEST_PASSWORD),
            "is_active": True, "created_at": ts, "updated_at": ts}}, upsert=True)
    print("users:", await db.users.count_documents({}))


asyncio.run(main())
