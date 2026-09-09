"""Fase 79 — verifikasi API ringan pendamping pengujian UI (iteration_127).

Cakupan:
- Aturan pemutus amandemen: pengaju != pemutus (kecuali super_admin), role pemutus.
- RBAC endpoint GET Fase 79 untuk persona finance / finance_manager (temuan iteration_127).
- PDF invoice biaya (INB) & kuitansi biaya (KWB).
"""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base.rstrip("/") + "/api"

PWD = "Sipro#2026"


def _resolve_contracts():
    """Kontrak uji dicari dari API (bukan ID basis data lama): kontrak cash ber-skema all-in
    dan kontrak KPR yang masih punya tahap pencairan terbuka. Bisa dioverride lewat env
    P79_CASH_CID / P79_KPR_CID; bila tidak ada, modul di-skip dengan petunjuk seed."""
    cash, kpr = os.environ.get("P79_CASH_CID"), os.environ.get("P79_KPR_CID")
    if cash and kpr:
        return cash, kpr
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": "superadmin@sipro.co.id", "password": PWD}, timeout=30)
    if r.status_code != 200:
        return cash, kpr
    rows = s.get(f"{BASE}/contracts", params={"limit": 200}, timeout=60).json().get("data") or []
    for c in rows:
        sch = (c.get("costs") or {}).get("scheme_code")
        if not cash and str(c.get("scheme") or "").startswith("cash") and sch and sch != "MANUAL":
            led = s.get(f"{BASE}/contracts/{c['id']}/costs-ledger", timeout=60).json().get("data") or {}
            if not led.get("receipts"):  # amandemen skema hanya sah sebelum ada kuitansi biaya
                cash = c["id"]
        if not kpr and c.get("scheme") == "kpr":
            app = (s.get(f"{BASE}/contracts/{c['id']}/kpr", timeout=60).json().get("data") or {}).get("application") or {}
            # tahap terbuka yang syaratnya sudah terpenuhi (akad tercatat), bukan serah terima
            if any(t.get("status") == "open" and t.get("condition") == "akad" for t in app.get("tranches") or []):
                kpr = c["id"]
    return cash, kpr


CASH_CID, KPR_CID = _resolve_contracts()
if not (CASH_CID and KPR_CID):
    pytest.skip("butuh kontrak all-in cash + kontrak KPR bertahap terbuka — jalankan tests/seed_p78_ui.py",
                allow_module_level=True)


def sess(email):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200, r.text[:200]
    return s


@pytest.fixture(scope="module")
def su():
    return sess("superadmin@sipro.co.id")


@pytest.fixture(scope="module")
def fin():
    return sess("finance@sipro.co.id")


@pytest.fixture(scope="module")
def finlead():
    return sess("finlead@sipro.co.id")


# ---------------------------------------------------------------- RBAC GET (temuan)
@pytest.mark.parametrize("path", [
    "/allin-schemes",
    "/kpr/tranche-reminders",
    f"/contracts/{CASH_CID}/allin-amendments",
    f"/contracts/{CASH_CID}/costs-ledger",
])
def test_finance_persona_can_read_p79_endpoints(fin, path):
    r = fin.get(BASE + path)
    assert r.status_code == 200, f"finance ditolak: {r.status_code} {r.text[:160]}"


def test_finance_manager_can_read_tranche_reminders(finlead):
    r = finlead.get(f"{BASE}/kpr/tranche-reminders")
    assert r.status_code == 200, f"finance_manager ditolak: {r.status_code} {r.text[:160]}"


# ------------------------------------------------- aturan pengaju != pemutus
def test_amendment_decider_rules(su, fin, finlead):
    schemes = su.get(f"{BASE}/allin-schemes").json()["data"]
    contract = su.get(f"{BASE}/contracts/{CASH_CID}").json()["data"]
    current = (contract.get("costs") or {}).get("scheme_name")
    target = next(s for s in schemes if s["name"] != current and s.get("is_active", True))

    # bersihkan pending lama (hanya satu pending per kontrak)
    for a in su.get(f"{BASE}/contracts/{CASH_CID}/allin-amendments").json()["data"]:
        if a["status"] == "pending":
            su.post(f"{BASE}/allin-amendments/{a['id']}/decide",
                    json={"approve": False, "note": "TEST_bersihkan pending lama"})

    r = fin.post(f"{BASE}/contracts/{CASH_CID}/allin-amendments",
                 json={"scheme_id": target["id"], "reason": "TEST_amandemen aturan pemutus"})
    assert r.status_code == 200, r.text[:200]
    aid = r.json()["data"]["id"]

    # pengaju (finance) tidak boleh memutuskan
    r = fin.post(f"{BASE}/allin-amendments/{aid}/decide", json={"approve": True, "note": "TEST_self"})
    assert r.status_code == 403, f"finance seharusnya ditolak: {r.status_code} {r.text[:160]}"

    # penolakan tanpa alasan ditolak
    r = finlead.post(f"{BASE}/allin-amendments/{aid}/decide", json={"approve": False, "note": ""})
    assert r.status_code == 400 and "penolakan" in r.text.lower(), r.text[:200]

    # finance_manager lain boleh memutuskan
    r = finlead.post(f"{BASE}/allin-amendments/{aid}/decide",
                     json={"approve": True, "note": "TEST_disetujui finance manager"})
    assert r.status_code == 200, r.text[:200]
    data = r.json()["data"]
    assert data["status"] == "approved"
    assert data["decided_by"] == "finlead@sipro.co.id"

    got = su.get(f"{BASE}/contracts/{CASH_CID}").json()["data"]
    assert (got.get("costs") or {}).get("scheme_name") == target["name"]


# ------------------------------------------------- amandemen ditolak bila ada kuitansi
def _ensure_receipt(su):
    """Pastikan kontrak KPR punya invoice biaya (INB) yang sudah dibayar → kuitansi (KWB)."""
    led = su.get(f"{BASE}/contracts/{KPR_CID}/costs-ledger").json()["data"]
    if led.get("receipts"):
        return led
    for a in su.get(f"{BASE}/contracts/{KPR_CID}/allin-amendments").json()["data"]:
        if a["status"] == "pending":
            su.post(f"{BASE}/allin-amendments/{a['id']}/decide", json={"approve": False, "note": "TEST_bersihkan pending lama"})
    inv = next((i for i in led["invoices"] if i["status"] == "unpaid"), None)
    if not inv:
        r = su.post(f"{BASE}/contracts/{KPR_CID}/cost-invoices")
        assert r.status_code == 200, r.text[:200]
        inv = r.json()["data"]
    r = su.post(f"{BASE}/cost-invoices/{inv['id']}/pay", json={"amount": 1_000_000})
    assert r.status_code == 200, r.text[:200]
    return su.get(f"{BASE}/contracts/{KPR_CID}/costs-ledger").json()["data"]


def test_amendment_blocked_when_receipt_exists(su):
    _ensure_receipt(su)
    schemes = su.get(f"{BASE}/allin-schemes").json()["data"]
    r = su.post(f"{BASE}/contracts/{KPR_CID}/allin-amendments",
                json={"scheme_id": schemes[0]["id"], "reason": "TEST_harus ditolak karena kuitansi"})
    assert r.status_code == 400
    assert "kuitansi" in r.text.lower(), r.text[:200]


# ------------------------------------------------- PDF
def test_cost_invoice_and_receipt_pdf(su):
    led = _ensure_receipt(su)
    inv = next(i for i in led["invoices"] if i["status"] != "void")
    rec = led["receipts"][0]
    for url in (f"/cost-invoices/{inv['id']}/pdf", f"/cost-receipts/{rec['id']}/pdf"):
        r = su.get(BASE + url)
        assert r.status_code == 200, r.text[:160]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:5] == b"%PDF-"


# ------------------------------------------------- pengingat tahap idempoten
def test_tranche_reminder_run_is_idempotent(su):
    su.post(f"{BASE}/kpr/tranche-reminders/run")
    second = su.post(f"{BASE}/kpr/tranche-reminders/run")
    assert second.status_code == 200
    assert second.json()["data"]["notified"] == 0


def test_tranche_reminder_reset_after_cancel(su):
    """Batal pencairan tahap → penanda pengingat direset → run berikutnya mengirim ulang untuk tahap itu."""
    su.post(f"{BASE}/kpr/tranche-reminders/run")
    app = su.get(f"{BASE}/contracts/{KPR_CID}/kpr").json()["data"]["application"]
    t1 = next(t for t in app["tranches"] if t["status"] == "open")
    r = su.post(f"{BASE}/contracts/{KPR_CID}/kpr/disbursements",
                json={"date": "2026-09-02", "amount": t1["amount"], "tranche_code": t1["code"]})
    assert r.status_code == 200, r.text[:200]
    app = r.json()["data"]
    did = next(d["id"] for d in app["disbursements"] if d.get("tranche_code") == t1["code"] and d["status"] != "dibatalkan")
    r = su.post(f"{BASE}/contracts/{KPR_CID}/kpr/disbursements/{did}/cancel",
                json={"reason": "TEST_batal untuk uji reset pengingat"})
    assert r.status_code == 200, r.text[:200]
    res = su.post(f"{BASE}/kpr/tranche-reminders/run").json()["data"]
    assert res["notified"] >= 1, res
