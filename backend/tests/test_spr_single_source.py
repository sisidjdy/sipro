"""Regresi Jalur 1 — SPR yang terbit == skema yang dipilih sales == piutang Finance.

Untuk 3 jenis skema (cash_keras, cash_bertahap, kpr): reservasi memilih skema → booking →
konversi pembeli → terbit SPR. Angka pada SPR (DP%, setiap termin, komponen biaya, total)
dibandingkan ANGKA PER ANGKA dengan `ar_invoices` (AR) + `deal.pricing.payment_breakdown` +
invoice biaya Finance. Deal uji dihapus paksa di akhir (superadmin).
"""
import re
import time

import pytest
import requests

from tests.conftest import BASE_URL, PASS

API = f"{BASE_URL}/api"
SPR_OF = {"cash_keras": "SPR_CASH", "cash_bertahap": "SPR_CASH_STAGED", "kpr": "SPR_KPR"}
KINDS = ("cash_keras", "cash_bertahap", "kpr")


def _rp_to_int(s: str) -> int:
    return int(re.sub(r"[^\d]", "", s))


def _login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PASS}, timeout=15)
    assert r.status_code == 200, r.text[:200]
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _wait_events():
    for _ in range(30):
        if not requests.get(f"{API}/health", timeout=10).json().get("events_pending"):
            return
        time.sleep(1)


def _ar_of(h, deal_id):
    rows = requests.get(f"{API}/finance/ar", headers=h, params={"limit": 200}, timeout=30).json()["data"]
    return next((r for r in rows if r.get("deal_id") == deal_id), None)


def _slik_clear(h, lead_id):
    ev = requests.post(f"{API}/files/upload", headers=h, timeout=60,
                       files={"file": ("ideb.pdf", b"%PDF-1.4 iDeb SLIK uji\n", "application/pdf")},
                       data={"owner_type": "lead", "owner_id": lead_id, "optimize": "false"})
    assert ev.status_code == 200, ev.text[:200]
    r = requests.post(f"{API}/leads/{lead_id}/slik-prescreen", headers=h, timeout=30,
                      json={"status": "clear", "note": "Kolektibilitas 1 (uji regresi)",
                            "evidence_file_ids": [ev.json()["data"]["id"]]})
    assert r.status_code == 200, r.text[:200]


@pytest.fixture(scope="module")
def sa():
    return _login("superadmin@sipro.co.id")


@pytest.fixture(scope="module")
def masters(sa):
    schemes = requests.get(f"{API}/finance/config/payment-schemes", headers=sa, timeout=30).json()["data"]
    allin = requests.get(f"{API}/allin-schemes", headers=sa, timeout=30).json()["data"]
    allin = [a for a in allin if a.get("is_active", True)]
    # Pilih skema all-in yang MENAGIH pembeli (pass-through) supaya invoice biaya Finance ada.
    pt = [a for a in allin if any((i.get("treatment") or "") == "customer_pass_through"
                                  for i in a.get("items") or [])]
    return {"schemes": schemes, "allin": (pt or allin)[0] if allin else None}


def _flow(sa, masters, kind):
    """Reservasi (skema dipilih) → booking → konversi → SPR. Mengembalikan semua artefak."""
    sch = next((s for s in masters["schemes"] if s.get("kind") == kind and s.get("active", True)), None)
    if not sch:
        pytest.skip(f"tidak ada skema pembayaran aktif berjenis {kind}")
    units = requests.get(f"{API}/units", headers=sa, params={"status": "available", "limit": 200},
                         timeout=30).json()["data"]
    unit = next((u for u in units if u.get("status") == "available" and int(u.get("price") or 0) > 0), None)
    if not unit:
        pytest.skip("tidak ada unit available")
    lead = requests.post(f"{API}/leads", headers=sa, timeout=30, json={
        "name": f"Uji SPR {kind} {int(time.time()) % 100000}",
        "phone": f"0819{int(time.time() * 1000) % 10**8:08d}", "source": "walk_in"}).json()["data"]
    body = {"unit_id": unit["id"], "lead_id": lead["id"], "booking_fee": 5_000_000, "scheme_id": sch["id"]}
    if masters["allin"]:
        body["allin_scheme_id"] = masters["allin"]["id"]
    r = requests.post(f"{API}/deals/reserve", headers=sa, json=body, timeout=30)
    assert r.status_code == 200, r.text[:300]
    deal = r.json()["data"]
    assert deal.get("scheme_id") == sch["id"] and deal.get("scheme_explicit") is True
    requests.post(f"{API}/booking-fee/deals/{deal['id']}/pay", headers=sa, timeout=30,
                  json={"amount": 5_000_000, "method": "transfer", "note": "uji"})
    r = requests.post(f"{API}/deals/{deal['id']}/book", headers=sa, json={"note": "uji"}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    _wait_events()
    ar = _ar_of(sa, deal["id"])
    assert ar, "AR tidak lahir saat booking"
    r = requests.post(f"{API}/deals/{deal['id']}/convert", headers=sa, json={}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    contract = r.json()["data"]["contract"]
    if kind == "kpr":
        _slik_clear(sa, lead["id"])
        r = requests.post(f"{API}/contracts/{contract['id']}/costs", headers=sa, timeout=30,
                          json={"plafon_kredit": int(deal["price"]) * 7 // 10})
        assert r.status_code == 200, r.text[:300]
    return {"scheme": sch, "deal": deal, "lead": lead, "ar": ar, "contract": contract}


def _cleanup(sa, deal_id):
    _wait_events()  # jurnal GL peristiwa titipan harus terbit dulu, baru dihapus bersama deal
    requests.delete(f"{API}/deals/{deal_id}", headers=sa, timeout=60,
                    params={"reason": "uji regresi SPR selesai — deal uji dihapus paksa"})


@pytest.mark.parametrize("kind", KINDS)
def test_spr_identik_dengan_ar_dan_breakdown(sa, masters, kind):
    art = _flow(sa, masters, kind)
    deal, ar, contract, sch = art["deal"], art["ar"], art["contract"], art["scheme"]
    try:
        # (1) AR mengikuti skema yang DIPILIH sales, bukan skema bawaan finance.
        assert ar["scheme_id"] == sch["id"], (ar.get("scheme_name"), sch["name"])
        unit_items = [i for i in ar["items"] if i.get("basis") != "addon"]
        assert [i["label"] for i in unit_items] == [i["label"] for i in sch["items"]]

        # (2) Kontrak: jenis & skema dari deal (bukan tebakan).
        assert contract["scheme"] == kind
        assert contract.get("payment_scheme_id") == sch["id"]

        # (3) Gerbang per jenis skema: SLIK tidak menahan SPR tunai.
        avail = requests.get(f"{API}/contracts/{contract['id']}/documents/available", headers=sa,
                             timeout=30).json()["data"]
        spr = next(a for a in avail if a["code"] == SPR_OF[kind])
        assert spr["can_generate"], spr["blocks"]
        if kind != "kpr":
            assert "slik_belum" not in [b["code"] for b in spr["blocks"]]

        # (4) Terbitkan SPR & bandingkan angka per angka.
        r = requests.post(f"{API}/contracts/{contract['id']}/documents", headers=sa, timeout=60,
                          json={"template_code": SPR_OF[kind]})
        assert r.status_code == 200, r.text[:300]
        content = r.json()["data"]["content"]
        assert "SEMENTARA" not in content and "TIDAK TERISI" not in content

        first = unit_items[0]
        dp_pct = (float(first["value"]) if first.get("basis", "percent") == "percent"
                  else first["amount"] / sum(i["amount"] for i in unit_items) * 100)
        m = re.search(r"Uang Muka : ([\d.,]+)%", content)
        assert m and abs(float(m.group(1).replace(",", ".")) - dp_pct) < 0.01, m and m.group(0)

        skema = content.split("3. Skema Pembayaran", 1)[1]
        lines = re.findall(r"^(\d+)\. (.+?) : Rp ([\d.]+)(?: — jatuh tempo (\d{4}-\d{2}-\d{2}))?",
                           skema, flags=re.M)
        assert len(lines) == len(unit_items), (lines, unit_items)
        for (no, label, rp, due), item in zip(lines, unit_items):
            assert label == item["label"] and _rp_to_int(rp) == int(item["amount"])
            if item.get("due_date"):
                assert due == str(item["due_date"])[:10]
        if kind == "cash_bertahap":
            m = re.search(r"Pelunasan ([\d.,]+)% dibayar bertahap (\d+)× cicilan", skema)
            assert m and int(m.group(2)) == len(unit_items) - 1
            assert abs(float(m.group(1).replace(",", ".")) - (100 - dp_pct)) < 0.01

        # (5) Komponen biaya = snapshot skema all-in (breakdown deal) = invoice biaya Finance.
        harga = content.split("2. Rincian Harga", 1)[1].split("3. Skema Pembayaran", 1)[0]
        comps = (deal.get("costs") or {}).get("components") or []
        bd_rows = {r["code"]: r["amount"] for r in
                   ((deal.get("pricing") or {}).get("payment_breakdown") or {}).get("rows") or []}
        for c in comps:
            if c.get("kpr_only") and kind != "kpr":
                continue
            m = re.search(rf"^{re.escape(c['name'])} : Rp ([\d.]+)", harga, flags=re.M)
            assert m, f"komponen {c['name']} tidak tercetak"
            assert _rp_to_int(m.group(1)) == int(c["amount"])
            if f"COST:{c['code']}" in bd_rows:
                assert int(c["amount"]) == bd_rows[f"COST:{c['code']}"]
            if c.get("treatment") == "developer_borne":
                assert "ditanggung developer" in harga.split(c["name"], 1)[1].splitlines()[0]
        ledger = requests.get(f"{API}/contracts/{contract['id']}/costs-ledger", headers=sa,
                              timeout=30).json()["data"]
        for inv in ledger.get("invoices") or []:
            for it in inv.get("items") or []:
                m = re.search(rf"^{re.escape(it['name'])} : Rp ([\d.]+)", harga, flags=re.M)
                assert m and _rp_to_int(m.group(1)) == int(it["amount"]), it
        assert "belum ditetapkan" not in "\n".join(
            ln for ln in harga.splitlines() if not ln.startswith("PPh"))

        # (6) Total SPR = total breakdown Finance (harga bersih + biaya pembeli).
        m = re.search(r"^Total : Rp ([\d.]+)", harga, flags=re.M)
        assert m and _rp_to_int(m.group(1)) == bd_rows.get("TOTAL", int(deal["price"]))
    finally:
        _cleanup(sa, deal["id"])


def test_konversi_menolak_jenis_berbeda_dari_skema_yang_dipilih(sa, masters):
    sch = next((s for s in masters["schemes"] if s.get("kind") == "cash_bertahap" and s.get("active", True)), None)
    if not sch:
        pytest.skip("tidak ada skema cash_bertahap")
    units = requests.get(f"{API}/units", headers=sa, params={"status": "available", "limit": 200},
                         timeout=30).json()["data"]
    unit = next(u for u in units if u.get("status") == "available" and int(u.get("price") or 0) > 0)
    lead = requests.post(f"{API}/leads", headers=sa, timeout=30, json={
        "name": f"Uji SPR tolak {int(time.time()) % 100000}",
        "phone": f"0818{int(time.time() * 1000) % 10**8:08d}", "source": "walk_in"}).json()["data"]
    deal = requests.post(f"{API}/deals/reserve", headers=sa, timeout=30, json={
        "unit_id": unit["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
        "scheme_id": sch["id"]}).json()["data"]
    try:
        requests.post(f"{API}/booking-fee/deals/{deal['id']}/pay", headers=sa, timeout=30,
                      json={"amount": 5_000_000, "method": "transfer"})
        assert requests.post(f"{API}/deals/{deal['id']}/book", headers=sa, json={}, timeout=30).status_code == 200
        r = requests.post(f"{API}/deals/{deal['id']}/convert", headers=sa, json={"scheme": "kpr"}, timeout=30)
        assert r.status_code == 400 and "dipilih saat reservasi" in r.text, r.text[:300]
        pre = requests.get(f"{API}/deals/{deal['id']}/convert-preview", headers=sa, timeout=30).json()["data"]
        assert pre["deal_scheme"] == "cash_bertahap" and pre["suggested_scheme"] == "cash_bertahap"
    finally:
        _cleanup(sa, deal["id"])
