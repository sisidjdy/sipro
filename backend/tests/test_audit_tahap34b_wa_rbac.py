"""Audit Tahap 3-4 Iteration 2 — WA template governance (WA-05..WA-09, WA-14) + RBAC action_meta."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://sipro-next-1.preview.emergentagent.com").rstrip("/")
PASS = "Sipro#2026"


@pytest.fixture(scope="module")
def s_admin():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "superadmin@sipro.co.id", "password": PASS}, timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


# ---------------- WA-09: nama duplikat → 409 di kedua POST ----------------
def test_wa09_duplicate_name_409(s_admin):
    name = f"TESTdup_{uuid.uuid4().hex[:6]}"
    payload = {"name": name, "category": "utility", "language": "id",
               "body": "Halo {{nama}}, ini pesan uji.", "variables": ["nama"],
               "examples": {"nama": "Andi"}}
    r1 = s_admin.post(f"{BASE_URL}/api/wa-templates", json=payload)
    assert r1.status_code == 200, r1.text
    tid1 = r1.json()["data"]["id"]
    try:
        r2 = s_admin.post(f"{BASE_URL}/api/wa-templates", json=payload)
        assert r2.status_code == 409
        assert "sudah dipakai" in r2.text.lower()
    finally:
        s_admin.delete(f"{BASE_URL}/api/wa-templates/{tid1}")


# ---------------- WA-05: PUT status pending→200, approved→400 ----------------
def test_wa05_status_transitions(s_admin):
    name = f"TESTstat_{uuid.uuid4().hex[:6]}"
    r = s_admin.post(f"{BASE_URL}/api/wa-templates", json={
        "name": name, "category": "utility", "language": "id",
        "body": "Notifikasi {{nama}}", "variables": ["nama"], "examples": {"nama": "A"}})
    assert r.status_code == 200, r.text
    tid = r.json()["data"]["id"]
    try:
        r_p = s_admin.put(f"{BASE_URL}/api/wa-templates/{tid}", json={"status": "pending"})
        assert r_p.status_code == 200, r_p.text
        r_a = s_admin.put(f"{BASE_URL}/api/wa-templates/{tid}", json={"status": "approved"})
        assert r_a.status_code == 400, r_a.text
    finally:
        s_admin.delete(f"{BASE_URL}/api/wa-templates/{tid}")


# ---------------- WA-07: warnings promosi, hilang saat category=marketing ----------------
def test_wa07_promo_warning(s_admin):
    name = f"TESTpromo_{uuid.uuid4().hex[:6]}"
    r = s_admin.post(f"{BASE_URL}/api/wa-templates", json={
        "name": name, "category": "utility", "language": "id",
        "body": "Halo {{nama}}, ada diskon & promo unit {{unit}}!",
        "variables": ["nama", "unit"], "examples": {"nama": "A", "unit": "U1"}})
    assert r.status_code == 200, r.text
    body = r.json()
    warnings = body.get("warnings") or []
    assert any("promosi" in w.lower() for w in warnings), warnings
    tid = body["data"]["id"]
    try:
        r2 = s_admin.put(f"{BASE_URL}/api/wa-templates/{tid}", json={"category": "marketing"})
        assert r2.status_code == 200, r2.text
        w2 = r2.json().get("warnings") or []
        assert not any("promosi" in w.lower() for w in w2), w2
    finally:
        s_admin.delete(f"{BASE_URL}/api/wa-templates/{tid}")


# ---------------- WA-08: delete referenced templates → 409 dengan lokasi ----------------
def test_wa08_delete_referenced_reminder(s_admin):
    lst = s_admin.get(f"{BASE_URL}/api/wa-templates").json()["data"]
    by_code = {t["code"]: t for t in lst}
    assert "reminder_installment_due" in by_code
    tid = by_code["reminder_installment_due"]["id"]
    r = s_admin.delete(f"{BASE_URL}/api/wa-templates/{tid}")
    assert r.status_code == 409, r.text
    assert "Pengingat" in r.text


def test_wa08_delete_welcome_referenced(s_admin):
    lst = s_admin.get(f"{BASE_URL}/api/wa-templates").json()["data"]
    by_code = {t["code"]: t for t in lst}
    if "welcome" not in by_code:
        pytest.skip("welcome template tidak ada di seed")
    tid = by_code["welcome"]["id"]
    r = s_admin.delete(f"{BASE_URL}/api/wa-templates/{tid}")
    assert r.status_code == 409, r.text
    assert ("Playbook" in r.text) or ("Otomasi" in r.text), r.text


def test_wa08_list_has_used_by_and_hints(s_admin):
    lst = s_admin.get(f"{BASE_URL}/api/wa-templates").json()["data"]
    assert lst, "template list kosong"
    for t in lst:
        assert "used_by" in t and isinstance(t["used_by"], list)
        assert "hints" in t and isinstance(t["hints"], list)
    by_code = {t["code"]: t for t in lst}
    if "welcome" in by_code:
        assert by_code["welcome"].get("category") == "marketing"
    if "price_info" in by_code:
        assert by_code["price_info"].get("category") == "marketing"


# ---------------- WA-14: reminder-mapping GET/PUT ----------------
EXPECTED_KINDS = {"installment_due", "installment_overdue", "arrears_warning",
                  "warranty_expiring", "booking_fee_due"}


def test_wa14_reminder_mapping_get(s_admin):
    r = s_admin.get(f"{BASE_URL}/api/wa-templates/reminder-mapping")
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    kinds = {row["kind"] for row in rows}
    assert kinds == EXPECTED_KINDS, kinds
    for row in rows:
        assert row["template_code"], row
        assert row.get("missing") is False, row


def test_wa14_put_mapping_unknown_code_400(s_admin):
    r = s_admin.put(f"{BASE_URL}/api/wa-templates/reminder-mapping",
                    json={"mapping": {"installment_due": "kode_yang_tidak_ada_xyz"}})
    assert r.status_code == 400, r.text


def test_wa14_put_mapping_pending_template_400(s_admin):
    name = f"TESTpend_{uuid.uuid4().hex[:6]}"
    r = s_admin.post(f"{BASE_URL}/api/wa-templates", json={
        "name": name, "category": "utility", "language": "id",
        "body": "Tagihan {{nama}}", "variables": ["nama"], "examples": {"nama": "A"}})
    assert r.status_code == 200, r.text
    tid = r.json()["data"]["id"]
    code = r.json()["data"]["code"]
    try:
        rp = s_admin.put(f"{BASE_URL}/api/wa-templates/{tid}", json={"status": "pending"})
        assert rp.status_code == 200, rp.text
        rm = s_admin.put(f"{BASE_URL}/api/wa-templates/reminder-mapping",
                         json={"mapping": {"installment_due": code}})
        assert rm.status_code == 400, rm.text
    finally:
        s_admin.delete(f"{BASE_URL}/api/wa-templates/{tid}")


def test_wa14_put_mapping_change_and_settings_reflect(s_admin):
    # Ubah installment_due ke reminder_installment_overdue → cek settings, kembalikan.
    orig_map = s_admin.get(f"{BASE_URL}/api/wa-templates/reminder-mapping").json()["data"]
    orig_code = next(r for r in orig_map if r["kind"] == "installment_due")["template_code"]
    try:
        r = s_admin.put(f"{BASE_URL}/api/wa-templates/reminder-mapping",
                        json={"mapping": {"installment_due": "reminder_installment_overdue"}})
        assert r.status_code == 200, r.text
        # cek settings
        rs = s_admin.get(f"{BASE_URL}/api/settings?group=pengingat")
        assert rs.status_code == 200, rs.text
        sd = rs.json().get("data") or rs.json()
        # cari key reminder.template_installment
        val = None
        # settings response bisa dict/list; cek keduanya
        if isinstance(sd, dict):
            val = sd.get("reminder.template_installment") or (sd.get("values") or {}).get("reminder.template_installment")
        if val is None and isinstance(sd, list):
            for it in sd:
                if it.get("key") == "reminder.template_installment":
                    val = it.get("value")
        assert val == "reminder_installment_overdue", f"settings value tidak berubah: {val}"
    finally:
        # kembalikan
        s_admin.put(f"{BASE_URL}/api/wa-templates/reminder-mapping",
                    json={"mapping": {"installment_due": orig_code}})


# ---------------- RBAC-02: action_meta lengkap; label≠kode; override w=3, view w=1 ----------------
def test_rbac02_action_meta(s_admin):
    r = s_admin.get(f"{BASE_URL}/api/admin/permissions")
    assert r.status_code == 200, r.text
    data = r.json().get("data") or r.json()
    actions = data["actions"]
    action_meta = data["action_meta"]
    for a in actions:
        assert a in action_meta, f"action {a} tidak ada di action_meta"
        m = action_meta[a]
        assert "label" in m and "weight" in m
        assert m["label"] != a, f"label untuk {a} sama dengan kodenya"
    assert action_meta["view"]["weight"] == 1
    assert action_meta["override"]["weight"] == 3
