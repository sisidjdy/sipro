"""Fase 59 — laporan keringanan denda, kandidat tunggakan, utang refund 2-1460."""
import pytest


# ---------- LAPORAN KERINGANAN DENDA ----------
class TestLateFeeWaivers:
    def test_finlead_can_read_waiver_report(self, s_finlead, base_url):
        r = s_finlead.get(f"{base_url}/api/finance/late-fee-waivers")
        assert r.status_code == 200
        d = r.json()["data"]
        for key in ("rows", "by_actor", "by_month", "totals", "filter", "note"):
            assert key in d, f"missing key {key}"
        assert "count" in d["totals"] and "amount" in d["totals"]
        assert d["filter"]["scoped_to"] is None  # finlead not scoped

    def test_finance_can_read_waiver_report(self, s_finance, base_url):
        r = s_finance.get(f"{base_url}/api/finance/late-fee-waivers")
        assert r.status_code == 200

    def test_sales_scoped_to_own_email(self, s_sales, base_url):
        r = s_sales.get(f"{base_url}/api/finance/late-fee-waivers")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["filter"]["scoped_to"] == "sales@sipro.co.id"

    def test_date_filter_applied(self, s_finlead, base_url):
        r = s_finlead.get(
            f"{base_url}/api/finance/late-fee-waivers",
            params={"date_from": "2099-01-01", "date_to": "2099-12-31"},
        )
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["rows"] == []
        assert d["totals"]["count"] == 0
        assert d["filter"]["date_from"] == "2099-01-01"

    def test_pdf_export(self, s_finlead, base_url):
        r = s_finlead.get(f"{base_url}/api/finance/late-fee-waivers/pdf")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"


# ---------- KANDIDAT TUNGGAKAN ----------
class TestArrearsCandidates:
    def test_finance_can_read_candidates(self, s_finance, base_url):
        r = s_finance.get(f"{base_url}/api/finance/arrears/candidates")
        assert r.status_code == 200
        d = r.json()["data"]
        assert "rows" in d and "totals" in d and "threshold_months" in d
        assert d["threshold_months"] >= 1
        # per-row wajib punya stage + rule_note + blocks
        for row in d["rows"]:
            assert row["stage"] in ("aman", "perhatian", "kandidat_batal")
            assert row.get("rule_note")
            assert "blocks" in row
            assert "months_in_arrears" in row

    def test_finlead_can_read_candidates(self, s_finlead, base_url):
        r = s_finlead.get(f"{base_url}/api/finance/arrears/candidates")
        assert r.status_code == 200

    def test_finance_cannot_sweep(self, s_finance, base_url):
        # SoD: hanya Manajer Keuangan (cancellation:approve)
        r = s_finance.post(f"{base_url}/api/finance/arrears/sweep")
        assert r.status_code == 403, f"finance seharusnya 403, dapat {r.status_code}"

    def test_sales_cannot_sweep(self, s_sales, base_url):
        r = s_sales.post(f"{base_url}/api/finance/arrears/sweep")
        assert r.status_code == 403

    def test_finlead_sweep_idempotent(self, s_finlead, base_url):
        r1 = s_finlead.post(f"{base_url}/api/finance/arrears/sweep")
        assert r1.status_code == 200
        d1 = r1.json()["data"]
        assert "created" in d1 and "skipped" in d1
        # sweep kedua harus tidak membuat tugas kembar (idempoten)
        r2 = s_finlead.post(f"{base_url}/api/finance/arrears/sweep")
        assert r2.status_code == 200
        d2 = r2.json()["data"]
        assert len(d2["created"]) == 0, (
            f"sweep idempoten dilanggar: {len(d2['created'])} tugas baru pada sweep ke-2")


# ---------- UTANG REFUND ----------
class TestRefundDebt:
    def test_finance_can_read_refund_debt(self, s_finance, base_url):
        r = s_finance.get(f"{base_url}/api/finance/refund-debt")
        assert r.status_code == 200
        d = r.json()["data"]
        for key in ("rows", "totals", "buckets", "projection", "ledger", "due_days"):
            assert key in d
        assert d["ledger"]["account_code"] == "2-1460"
        assert "matched" in d["ledger"]
        assert "periods" in d["projection"] and "unscheduled" in d["projection"]

    def test_finlead_can_read_refund_debt(self, s_finlead, base_url):
        r = s_finlead.get(f"{base_url}/api/finance/refund-debt")
        assert r.status_code == 200

    def test_owner_can_read_refund_debt(self, s_owner, base_url):
        r = s_owner.get(f"{base_url}/api/finance/refund-debt")
        assert r.status_code == 200

    def test_sales_denied_refund_debt(self, s_sales, base_url):
        r = s_sales.get(f"{base_url}/api/finance/refund-debt")
        assert r.status_code == 403, f"sales harus 403, dapat {r.status_code}"

    def test_projection_horizon(self, s_finlead, base_url):
        r = s_finlead.get(f"{base_url}/api/finance/refund-debt", params={"horizon": 6})
        assert r.status_code == 200
        d = r.json()["data"]
        assert len(d["projection"]["periods"]) == 6

    def test_pdf_export(self, s_finlead, base_url):
        r = s_finlead.get(f"{base_url}/api/finance/refund-debt/pdf")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_ledger_matches_worksheet(self, s_finlead, base_url):
        r = s_finlead.get(f"{base_url}/api/finance/refund-debt")
        assert r.status_code == 200
        led = r.json()["data"]["ledger"]
        # laporan wajib menyandingkan buku besar dengan worksheet secara jujur
        assert isinstance(led["balance"], int)
        assert isinstance(led["worksheet"], int)
        assert led["difference"] == led["balance"] - led["worksheet"]
