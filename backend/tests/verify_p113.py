"""P113: verify leads x sales matrix restored to defaults + purge TEST_P113 tasks."""
import os
import asyncio
import requests
from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

fe = dotenv_values("/app/frontend/.env")
BASE = (fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
be = dotenv_values("/app/backend/.env")


def main():
    r = requests.post(f"{BASE}/api/auth/login", json={
        "email": "superadmin@sipro.co.id", "password": "Sipro#2026"}, timeout=30)
    print("login", r.status_code)
    token = r.json().get("data", {}).get("token") or r.json().get("token") or \
        r.json().get("access_token") or r.json().get("data", {}).get("access_token")
    h = {"Authorization": f"Bearer {token}"}
    p = requests.get(f"{BASE}/api/admin/permissions", headers=h, timeout=30)
    print("perms", p.status_code)
    data = p.json()["data"]
    cell = data["matrix"]["leads"]["sales"]
    print("matrix.leads.sales =", sorted(cell))
    assert sorted(cell) == ["create", "update", "view_own"], cell
    print("defaults present:", "defaults" in data)
    print("defaults.leads.sales =", sorted(data.get("defaults", {}).get("leads", {}).get("sales", [])))


async def purge():
    cli = AsyncIOMotorClient(os.environ.get("MONGO_URL") or be["MONGO_URL"])
    db = cli[be["DB_NAME"]]
    res = await db.tasks.delete_many({"title": {"$regex": "^TEST_P113"}})
    print("purged tasks:", res.deleted_count)
    left = await db.tasks.count_documents({"title": {"$regex": "TEST_P113"}})
    print("remaining TEST_P113 tasks:", left)


if __name__ == "__main__":
    main()
    asyncio.run(purge())
