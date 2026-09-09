"""Iteration 3 audit: WA-09 explicit code, DOC-02 INVOICE layout, CFG-03/04 enum ref_group + option_labels, deletion request status registry."""
import os
import random
import string
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")


def _rand(n=6):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _unwrap(j):
    if isinstance(j, dict) and "data" in j and "total" not in j and set(j.keys()) <= {"data"}:
        return j["data"]
    if isinstance(j, dict) and "data" in j and isinstance(j["data"], (list, dict)):
        # keep both
        return j["data"]
    return j


@pytest.fixture(scope="module")
def s_super():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "superadmin@sipro.co.id", "password": "Sipro#2026"}, timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


# ---------- WA-09 explicit code ----------
class TestWA09ExplicitCode:
    def test_explicit_code_honored_and_duplicate_rejected(self, s_super):
        code = f"tst_x_{_rand(6)}"
        payload = {
            "code": code, "name": "Uji Kode Eksplisit",
            "body": "Halo {{nama}}", "variables": ["nama"],
            "examples": {"nama": "Budi"}, "category": "utility",
        }
        r1 = s_super.post(f"{BASE_URL}/api/wa-templates", json=payload)
        assert r1.status_code == 200, r1.text
        d1 = r1.json().get("data", r1.json())
        assert d1["code"] == code, f"expected code={code} got {d1.get('code')}"
        tid = d1.get("id") or d1.get("_id")

        try:
            r2 = s_super.post(f"{BASE_URL}/api/wa-templates", json=payload)
            assert r2.status_code == 409, r2.text
            assert "sudah" in r2.text.lower() or "dipakai" in r2.text.lower()
        finally:
            if tid:
                s_super.delete(f"{BASE_URL}/api/wa-templates/{tid}")

    def test_no_code_derives_from_name(self, s_super):
        name = f"Uji Otomatis {_rand(4)}"
        r = s_super.post(f"{BASE_URL}/api/wa-templates", json={
            "name": name, "body": "Halo {{nama}}", "variables": ["nama"],
            "examples": {"nama": "Budi"}, "category": "utility",
        })
        assert r.status_code == 200, r.text
        d = r.json().get("data", r.json())
        assert d.get("code"), "code should be derived"
        tid = d.get("id") or d.get("_id")
        if tid:
            s_super.delete(f"{BASE_URL}/api/wa-templates/{tid}")


# ---------- DOC-02 INVOICE ----------
class TestDoc02Invoice:
    def test_invoice_in_doc_layouts(self, s_super):
        r = s_super.get(f"{BASE_URL}/api/doc-layouts")
        assert r.status_code == 200, r.text
        rows = r.json().get("data", r.json())
        if isinstance(rows, dict):
            rows = rows.get("items") or list(rows.values())
        codes = [x.get("code") for x in rows if isinstance(x, dict)]
        assert "INVOICE" in codes, f"INVOICE missing; codes={codes}"
        inv = next(x for x in rows if x.get("code") == "INVOICE")
        assert inv.get("kind") == "table", inv
        assert inv.get("category") == "penagihan", inv

    def test_invoice_get(self, s_super):
        r = s_super.get(f"{BASE_URL}/api/doc-layouts/INVOICE")
        assert r.status_code == 200, r.text
        d = r.json().get("data", r.json())
        assert d.get("kind") == "table", d

    def test_invoice_preview_pdf(self, s_super):
        r = s_super.post(f"{BASE_URL}/api/doc-layouts/INVOICE/preview", json={})
        assert r.status_code == 200, r.text[:300]
        ct = r.headers.get("content-type", "")
        assert "pdf" in ct.lower(), f"content-type={ct}"


# ---------- CFG-03/04 enum ref_group + option_labels ----------
class TestCfgEnumRegistry:
    def test_all_enum_settings_have_ref_group_and_labels(self, s_super):
        r = s_super.get(f"{BASE_URL}/api/settings")
        assert r.status_code == 200, r.text
        rows = r.json().get("data", [])
        enums = [x for x in rows if x.get("type") == "enum"]
        assert enums, "no enum settings found"
        problems = []
        for row in enums:
            key = row.get("key")
            rg = row.get("ref_group")
            opts = row.get("options") or []
            labels = row.get("option_labels") or {}
            if not rg:
                problems.append(f"{key}: missing ref_group")
                continue
            if not opts:
                problems.append(f"{key}: no options")
                continue
            for opt in opts:
                if opt not in labels:
                    problems.append(f"{key}: option {opt} missing label")
                elif labels[opt] == opt:
                    problems.append(f"{key}: option {opt} label equals code")
        assert not problems, "issues: " + "; ".join(problems[:20])

    def test_specific_labels(self, s_super):
        rows = s_super.get(f"{BASE_URL}/api/settings").json().get("data", [])
        by_key = {x.get("key"): x for x in rows}
        s = by_key.get("docnum.scope")
        assert s, "docnum.scope missing"
        assert s.get("option_labels", {}).get("per_project", "").lower().startswith("per proyek"), s
        h = by_key.get("handover.settlement_policy")
        assert h, "handover.settlement_policy missing"
        lbl = h.get("option_labels", {}).get("wajib_lunas", "")
        assert "wajib lunas" in lbl.lower(), f"got '{lbl}'"


class TestReferenceGroups:
    def test_registry_new_groups(self, s_super):
        r = s_super.get(f"{BASE_URL}/api/reference")
        assert r.status_code == 200, r.text
        groups = r.json().get("data", {})
        needed = ["lead_won_trigger", "slik_gate", "attribution_model",
                  "docnum_scope", "docnum_reset_policy", "deletion_request_status"]
        missing = []
        for g in needed:
            entry = groups.get(g)
            if not entry or not entry.get("options"):
                missing.append(g)
        assert not missing, f"missing/empty: {missing}"


# ---------- Setting PUT ----------
class TestSettingsPut:
    def _get_val(self, s, key):
        r = s.get(f"{BASE_URL}/api/settings")
        rows = r.json().get("data", [])
        for x in rows:
            if x.get("key") == key:
                return x.get("value")
        return None

    def test_docnum_reset_policy(self, s_super):
        original = self._get_val(s_super, "docnum.reset_policy") or "yearly"

        r = s_super.put(f"{BASE_URL}/api/settings/docnum.reset_policy",
                        json={"value": "monthly", "reason": "uji iterasi 3"})
        assert r.status_code == 200, r.text

        r_bad = s_super.put(f"{BASE_URL}/api/settings/docnum.reset_policy",
                            json={"value": "xyz", "reason": "uji bad"})
        assert r_bad.status_code == 400, r_bad.text

        s_super.put(f"{BASE_URL}/api/settings/docnum.reset_policy",
                    json={"value": original, "reason": "kembalikan"})

    def test_docnum_scope(self, s_super):
        original = self._get_val(s_super, "docnum.scope") or "per_project"

        r = s_super.put(f"{BASE_URL}/api/settings/docnum.scope",
                        json={"value": "global", "reason": "uji iterasi 3"})
        assert r.status_code == 200, r.text
        s_super.put(f"{BASE_URL}/api/settings/docnum.scope",
                    json={"value": original, "reason": "kembalikan"})


# ---------- Legal deletion requests ----------
class TestLegalDeletionRequests:
    def test_deletion_request_patch_status(self, s_super):
        payload = {"name": "Uji Hapus", "email": f"del_{_rand(5)}@x.co",
                   "phone": "081200000000", "reason": "Uji",
                   "message": "Iterasi 3", "context": "Iterasi 3"}
        rc = requests.post(f"{BASE_URL}/api/legal/public/deletion-requests",
                           json=payload, timeout=15)
        tid = None
        if rc.status_code in (200, 201):
            body = rc.json().get("data", rc.json())
            tid = body.get("id") or body.get("_id")
        if not tid:
            rl = s_super.get(f"{BASE_URL}/api/legal/deletion-requests")
            if rl.status_code == 200:
                rows = rl.json().get("data", rl.json())
                if isinstance(rows, dict):
                    rows = rows.get("items") or []
                if rows:
                    tid = rows[0].get("id") or rows[0].get("_id")
        if not tid:
            pytest.skip(f"cannot create/find ticket; public={rc.status_code} {rc.text[:200]}")

        rbad = s_super.patch(f"{BASE_URL}/api/legal/deletion-requests/{tid}",
                             json={"status": "ngawur"})
        assert rbad.status_code == 400, rbad.text

        rok = s_super.patch(f"{BASE_URL}/api/legal/deletion-requests/{tid}",
                            json={"status": "in_progress"})
        assert rok.status_code == 200, rok.text
