"""Audit Tahap 3 (WA-05..09, WA-14) & Tahap 4 (RBAC-02) — 2026-09-06. Server hidup (conftest BASE_URL)."""
import uuid

import pytest

from conftest import BASE_URL, _login, _sess


@pytest.fixture(scope="module")
def s_admin():
    return _sess(_login("superadmin@sipro.co.id"))


def _api(s, method, path, **kw):
    return getattr(s, method)(f"{BASE_URL}/api{path}", timeout=30, **kw)


def _mk(s, name, **over):
    body = {"name": name, "category": "utility", "body": "Halo {{nama}}, tagihan unit {{unit}}.",
            "variables": ["nama", "unit"], "examples": {"nama": "Budi", "unit": "A-01"}}
    body.update(over)
    return _api(s, "post", "/wa-templates", json=body)


def test_wa09_duplicate_code_rejected_409(s_admin):
    name = f"Dup {uuid.uuid4().hex[:5]}"
    a = _mk(s_admin, name)
    assert a.status_code == 200, a.text
    b = _mk(s_admin, name)
    assert b.status_code == 409 and "sudah dipakai" in b.json()["detail"]
    _api(s_admin, "delete", f"/wa-templates/{a.json()['data']['id']}")


def test_wa05_status_approved_cannot_be_set_by_hand(s_admin):
    t = _mk(s_admin, f"St {uuid.uuid4().hex[:5]}").json()["data"]
    r = _api(s_admin, "put", f"/wa-templates/{t['id']}", json={"status": "pending"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "pending"
    r = _api(s_admin, "put", f"/wa-templates/{t['id']}", json={"status": "approved"})
    assert r.status_code == 400 and "approved" in r.json()["detail"]
    _api(s_admin, "delete", f"/wa-templates/{t['id']}")


def test_wa07_category_hint_is_warning_not_block(s_admin):
    r = _mk(s_admin, f"Promo {uuid.uuid4().hex[:5]}", body="Halo {{nama}}, ada diskon dan promo unit {{unit}}!")
    assert r.status_code == 200
    assert any("promosi" in w for w in r.json()["warnings"]), r.json()
    _api(s_admin, "delete", f"/wa-templates/{r.json()['data']['id']}")


def test_wa08_template_in_use_cannot_be_deleted(s_admin):
    rows = {t["code"]: t for t in _api(s_admin, "get", "/wa-templates").json()["data"]}
    used = rows["reminder_installment_due"]
    assert any(u["type"] == "reminder" for u in used["used_by"]), used["used_by"]
    r = _api(s_admin, "delete", f"/wa-templates/{used['id']}")
    assert r.status_code == 409 and "Pengingat" in r.json()["detail"]
    assert rows["welcome"]["category"] == "marketing" and rows["price_info"]["category"] == "marketing"


def test_wa14_reminder_mapping_roundtrip(s_admin):
    before = {r["kind"]: r["template_code"] for r in _api(s_admin, "get", "/wa-templates/reminder-mapping").json()["data"]}
    assert set(before) == {"installment_due", "installment_overdue", "arrears_warning", "warranty_expiring", "booking_fee_due"}
    r = _api(s_admin, "put", "/wa-templates/reminder-mapping", json={"mapping": {"installment_due": "tidak_ada"}})
    assert r.status_code == 400
    r = _api(s_admin, "put", "/wa-templates/reminder-mapping", json={"mapping": {"installment_due": "reminder_installment_overdue"}})
    assert r.status_code == 200 and r.json()["data"]["installment_due"] == "reminder_installment_overdue"
    cfgv = _api(s_admin, "get", "/settings", params={"group": "pengingat"}).json()
    vals = {x["key"]: x["value"] for x in (cfgv.get("data") or [])}
    if vals:
        assert vals.get("reminder.template_installment") == "reminder_installment_overdue", "settings = satu kebenaran"
    r = _api(s_admin, "put", "/wa-templates/reminder-mapping", json={"mapping": {"installment_due": before["installment_due"]}})
    assert r.status_code == 200


def test_wa06_frozen_after_meta_approved(s_admin):
    import os, sys
    sys.path.insert(0, "/app/backend")
    t = _mk(s_admin, f"Frz {uuid.uuid4().hex[:5]}").json()["data"]
    # simulasi Meta APPROVED langsung di DB (webhook/sync di mode simulasi tidak tersedia)
    import asyncio
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient

    async def mark():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        await db.wa_templates.update_one({"id": t["id"]}, {"$set": {"meta_status": "APPROVED"}})
    asyncio.run(mark())
    r = _api(s_admin, "put", f"/wa-templates/{t['id']}", json={"body": "Halo {{nama}} unit {{unit}} diubah."})
    assert r.status_code == 400 and "APPROVED" in r.json()["detail"]
    r = _api(s_admin, "put", f"/wa-templates/{t['id']}", json={"name": "Nama baru", "examples": {"nama": "Siti", "unit": "B-02"}})
    assert r.status_code == 200 and r.json()["data"]["examples"]["nama"] == "Siti"
    _api(s_admin, "delete", f"/wa-templates/{t['id']}")


def test_rbac02_action_meta_served(s_admin):
    d = _api(s_admin, "get", "/admin/permissions").json()["data"]
    assert "action_meta" in d
    for a in d["actions"]:
        m = d["action_meta"][a]
        assert m["label"] and m["label"] != a and m["help"], a
    assert d["action_meta"]["override"]["weight"] == 3 and d["action_meta"]["view"]["weight"] == 1
