"""Manual WhatsApp bypass (chat di luar sistem + bukti foto) — POST /api/leads/{id}/wa/manual."""
import io
import os
import time

import pytest
import requests
from dotenv import dotenv_values

_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"
PASS = "Sipro#2026"

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415418d7636060606000000005000105a4a7000000004945"
    "4e44ae426082")
PDF_MIN = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": "superadmin@sipro.co.id", "password": PASS}, timeout=20)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token")
    assert tok, "no access_token in login response"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def _new_lead(sess):
    phone = "+62811" + str(int(time.time() * 1000))[-9:]
    r = sess.post(f"{API}/leads", json={"name": "TEST_WA_Manual", "phone": phone,
                                        "source": "walk_in"}, timeout=20)
    assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
    lead = r.json().get("data") or r.json()
    assert lead.get("stage") == "acquisition", lead.get("stage")
    return lead["id"]


def _upload(sess, lead_id, content, filename, ctype):
    files = {"file": (filename, io.BytesIO(content), ctype)}
    data = {"owner_type": "lead_wa_manual", "owner_id": lead_id, "optimize": "false"}
    r = sess.post(f"{API}/files/upload", files=files, data=data, timeout=30)
    assert r.status_code in (200, 201), f"upload {r.status_code} {r.text[:300]}"
    rec = r.json()["data"]
    return rec["id"], rec.get("content_type")


@pytest.fixture(scope="module")
def created(sess):
    ids = []
    yield ids


class TestWaManualHappyPath:
    def test_manual_log_advances_lifecycle(self, sess, created):
        lead_id = _new_lead(sess)
        created.append(lead_id)
        fid, ctype = _upload(sess, lead_id, PNG_1PX, "TEST_wa.png", "image/png")
        assert str(ctype).startswith("image/"), ctype

        r = sess.post(f"{API}/leads/{lead_id}/wa/manual",
                      json={"note": "TEST_ Sudah dihubungi via WA pribadi, minat tipe 45",
                            "evidence_file_ids": [fid]}, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        body = r.json()["data"]
        assert body["mode"] == "manual"
        assert body["message"]["mode"] == "manual"
        assert body["message"]["evidence_file_ids"] == [fid]
        lead = body["lead"]
        assert lead["stage"] == "nurturing", lead["stage"]
        assert lead["first_contact_at"]
        assert lead["first_contact_channel"] == "whatsapp_manual"

        # persistence via GET lead
        g = sess.get(f"{API}/leads/{lead_id}", timeout=20)
        assert g.status_code == 200
        gl = g.json().get("data") or g.json()
        assert gl["stage"] == "nurturing"
        assert gl["first_contact_channel"] == "whatsapp_manual"

        # thread shows manual message
        w = sess.get(f"{API}/leads/{lead_id}/wa", timeout=20)
        assert w.status_code == 200
        msgs = w.json()["data"]["messages"]
        manual = [m for m in msgs if m.get("mode") == "manual"]
        assert len(manual) == 1
        assert fid in manual[0]["evidence_file_ids"]

        # lifecycle requirement first_contact met
        lf = sess.get(f"{API}/leads/{lead_id}/lifecycle", timeout=20)
        assert lf.status_code == 200
        reqs = lf.json()["data"]["requirements"]
        for stg in ("nurturing", "appointment"):
            items = reqs.get(stg) or []
            fc = [i for i in (items.get("items") if isinstance(items, dict) else items)
                  if i.get("key") == "first_contact"]
            assert fc, f"no first_contact requirement in {stg}: {items}"
            assert fc[0].get("met") is True, fc[0]

    def test_second_manual_log_does_not_reset_first_contact(self, sess, created):
        lead_id = created[0]
        before = sess.get(f"{API}/leads/{lead_id}/wa", timeout=20).json()["data"]["first_contact_at"]
        fid, _ = _upload(sess, lead_id, PNG_1PX, "TEST_wa2.png", "image/png")
        time.sleep(1)
        r = sess.post(f"{API}/leads/{lead_id}/wa/manual",
                      json={"note": "TEST_ chat kedua", "evidence_file_ids": [fid]}, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert r.json()["data"]["lead"]["first_contact_at"] == before
        msgs = sess.get(f"{API}/leads/{lead_id}/wa", timeout=20).json()["data"]["messages"]
        assert len([m for m in msgs if m.get("mode") == "manual"]) == 2


class TestWaManualValidation:
    def test_empty_evidence_rejected(self, sess, created):
        """App mengubah 422 pydantic menjadi 400 berpesan ramah (handler global)."""
        lead_id = _new_lead(sess)
        created.append(lead_id)
        r = sess.post(f"{API}/leads/{lead_id}/wa/manual",
                      json={"note": "TEST_ tanpa bukti", "evidence_file_ids": []}, timeout=20)
        assert r.status_code in (400, 422), f"{r.status_code} {r.text[:300]}"
        assert "evidence_file_ids" in r.text

    def test_short_note_rejected(self, sess, created):
        lead_id = created[-1]
        fid, _ = _upload(sess, lead_id, PNG_1PX, "TEST_wa3.png", "image/png")
        r = sess.post(f"{API}/leads/{lead_id}/wa/manual",
                      json={"note": "a", "evidence_file_ids": [fid]}, timeout=20)
        assert r.status_code in (400, 422), f"{r.status_code} {r.text[:300]}"
        assert "note" in r.text

    def test_non_image_evidence_400(self, sess, created):
        lead_id = created[-1]
        fid, ctype = _upload(sess, lead_id, PDF_MIN, "TEST_bukti.pdf", "application/pdf")
        r = sess.post(f"{API}/leads/{lead_id}/wa/manual",
                      json={"note": "TEST_ bukti pdf salah", "evidence_file_ids": [fid]},
                      timeout=20)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]} (ctype={ctype})"
        assert "FOTO" in r.json()["detail"]

    def test_unknown_file_id_404(self, sess, created):
        lead_id = created[-1]
        r = sess.post(f"{API}/leads/{lead_id}/wa/manual",
                      json={"note": "TEST_ file palsu",
                            "evidence_file_ids": ["nonexistent-file-id-xyz"]}, timeout=20)
        assert r.status_code == 404, f"{r.status_code} {r.text[:300]}"

    def test_unknown_lead_404(self, sess):
        fid_lead = None
        r = sess.post(f"{API}/leads/does-not-exist/wa/manual",
                      json={"note": "TEST_ lead palsu", "evidence_file_ids": ["x"]}, timeout=20)
        assert r.status_code == 404, f"{r.status_code} {r.text[:300]} {fid_lead}"

    def test_lead_not_advanced_on_validation_failure(self, sess, created):
        """Lead yang hanya gagal validasi harus tetap di acquisition (tanpa efek samping)."""
        lead_id = created[-1]
        g = sess.get(f"{API}/leads/{lead_id}", timeout=20)
        gl = g.json().get("data") or g.json()
        assert gl["stage"] == "acquisition", gl["stage"]
        assert not gl.get("first_contact_at")


class TestInSystemWaRegression:
    def test_send_wa_without_template_closed_window_400(self, sess, created):
        lead_id = _new_lead(sess)
        created.append(lead_id)
        r = sess.post(f"{API}/leads/{lead_id}/wa", json={"body": "TEST_ halo"}, timeout=20)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"

    def test_send_wa_with_template_ok(self, sess, created):
        lead_id = created[-1]
        w = sess.get(f"{API}/leads/{lead_id}/wa", timeout=20)
        assert w.status_code == 200
        tmpl = w.json()["data"]["templates"]
        if not tmpl:
            pytest.fail("no approved WA templates seeded")
        r = sess.post(f"{API}/leads/{lead_id}/wa",
                      json={"template_code": tmpl[0]["code"], "body": ""}, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        d = r.json()["data"]
        assert d["mode"] == "simulation"
        assert d["lead"]["stage"] == "nurturing"
        assert d["lead"].get("first_contact_channel") == "whatsapp"
