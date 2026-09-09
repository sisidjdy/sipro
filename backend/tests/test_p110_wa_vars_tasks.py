"""Fase 110 — (1) substitusi variabel template WA, (2) WA manual menutup tugas via task_id,
(3) validasi POST /api/work/tasks (jobdesk_code + related_entity)."""
import io
import os
import time
from datetime import datetime, timedelta, timezone

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


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": "superadmin@sipro.co.id", "password": PASS}, timeout=20)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token")
    assert tok, "no access_token"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def _new_lead(sess, name="TEST_P110_Lead"):
    phone = "+62812" + str(int(time.time() * 1000000))[-9:]
    r = sess.post(f"{API}/leads", json={"name": name, "phone": phone,
                                        "source": "walk_in"}, timeout=20)
    assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
    return (r.json().get("data") or r.json())["id"]


def _upload(sess, owner_id, content=PNG_1PX, filename="TEST_p110.png", ctype="image/png"):
    files = {"file": (filename, io.BytesIO(content), ctype)}
    data = {"owner_type": "lead_wa_manual", "owner_id": owner_id, "optimize": "false"}
    r = sess.post(f"{API}/files/upload", files=files, data=data, timeout=30)
    assert r.status_code in (200, 201), f"upload {r.status_code} {r.text[:300]}"
    return r.json()["data"]["id"]


def _get_task(sess, task_id, status=None):
    # cari lewat kata kunci judul: daftar dibatasi 200 baris dan tugas menumpuk seiring run tes
    params = {"scope": "all", "limit": 200, "q": "TEST_P110"}
    if status:
        params["status"] = status
    r = sess.get(f"{API}/work/tasks", params=params, timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    payload = r.json().get("data")
    rows = payload if isinstance(payload, list) else (payload or {}).get("items") or []
    hit = [t for t in rows if t.get("id") == task_id]
    assert hit, f"task {task_id} not found in list of {len(rows)}"
    return hit[0]


# ---------------------------------------------------------------- template vars
class TestWaTemplateVariables:
    def test_template_send_fills_name_and_fallback_date(self, sess):
        lead_id = _new_lead(sess, "TEST_P110_Placeholder")
        w = sess.get(f"{API}/leads/{lead_id}/wa", timeout=20).json()["data"]
        codes = [t["code"] for t in w["templates"]]
        assert codes, "no approved templates seeded"
        code = "appointment_reminder" if "appointment_reminder" in codes else codes[0]
        tpl_body = [t["body"] for t in w["templates"] if t["code"] == code][0]

        r = sess.post(f"{API}/leads/{lead_id}/wa",
                      json={"template_code": code, "body": ""}, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        body = r.json()["data"]["message"]["body"]
        assert "{{" not in body, f"raw placeholder left: {body}"
        if "{{nama}}" in tpl_body or "{{name}}" in tpl_body:
            assert "TEST_P110_Placeholder" in body, body
        if "{{date}}" in tpl_body:
            assert "(waktu akan dikonfirmasi)" in body, body

    def test_template_send_uses_appointment_date_after_scheduling(self, sess):
        lead_id = _new_lead(sess, "TEST_P110_Appt")
        w = sess.get(f"{API}/leads/{lead_id}/wa", timeout=20).json()["data"]
        tpls = {t["code"]: t for t in w["templates"]}
        code = "appointment_reminder" if "appointment_reminder" in tpls else None
        if not code or "{{date}}" not in tpls[code]["body"]:
            pytest.fail(f"appointment_reminder template with date var missing: "
                        f"{list(tpls)}")
        when = (datetime.now(timezone.utc) + timedelta(days=3)).replace(
            microsecond=0).isoformat()
        a = sess.post(f"{API}/appointments", json={
            "lead_id": lead_id, "title": "TEST_P110 Survey", "scheduled_at": when,
            "type": "survey", "location": "Kantor Marketing"}, timeout=30)
        assert a.status_code in (200, 201), f"{a.status_code} {a.text[:400]}"

        r = sess.post(f"{API}/leads/{lead_id}/wa",
                      json={"template_code": code, "body": ""}, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        body = r.json()["data"]["message"]["body"]
        assert "{{" not in body, body
        assert "WIB" in body, body
        assert "(waktu akan dikonfirmasi)" not in body, body
        # tanggal Indonesia: nama bulan lokal harus muncul
        months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
                  "Agustus", "September", "Oktober", "November", "Desember"]
        assert any(m in body for m in months), body

    def test_inbox_template_send_substitutes(self, sess):
        lead_id = _new_lead(sess, "TEST_P110_Inbox")
        # buat percakapan lewat kirim template dari record lead
        w = sess.get(f"{API}/leads/{lead_id}/wa", timeout=20).json()["data"]
        code = w["templates"][0]["code"]
        first = sess.post(f"{API}/leads/{lead_id}/wa",
                          json={"template_code": code, "body": ""}, timeout=30)
        assert first.status_code == 200, first.text[:300]
        conv_id = first.json()["data"]["conversation_id"]

        r = sess.post(f"{API}/inbox/{conv_id}/messages",
                      json={"template_code": code, "body": "", "direction": "out"},
                      timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        msgs = sess.get(f"{API}/leads/{lead_id}/wa", timeout=20).json()["data"]["messages"]
        assert msgs, "no messages"
        for m in msgs:
            assert "{{" not in (m.get("body") or ""), m


# ------------------------------------------------------- create task validation
class TestCreateTaskValidation:
    def test_create_task_inherits_jobdesk_and_links_lead(self, sess):
        lead_id = _new_lead(sess, "TEST_P110_TaskLead")
        cat = sess.get(f"{API}/work/jobdesks", timeout=20)
        assert cat.status_code == 200, f"{cat.status_code} {cat.text[:300]}"
        items = cat.json().get("data")
        rows = items if isinstance(items, list) else (items or {}).get("items") or []
        jd = next((j for j in rows if j.get("code") == "SM-10"), None)
        assert jd, f"SM-10 not in catalog: {[j.get('code') for j in rows][:20]}"

        r = sess.post(f"{API}/work/tasks", json={
            "title": "TEST_P110 follow up lead", "type": "follow_up",
            "priority": "medium", "jobdesk_code": "SM-10",
            "related_entity_type": "lead", "related_entity_id": lead_id}, timeout=30)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:400]}"
        t = r.json()["data"]
        assert t["jobdesk_code"] == "SM-10"
        assert t["related_entity_id"] == lead_id
        assert t["proof_kind"] == jd.get("proof_kind"), (t["proof_kind"], jd)
        assert t["verify_mode"] == jd.get("verify_mode"), (t["verify_mode"], jd)
        assert t["division"] == jd.get("division"), (t["division"], jd)
        if jd.get("sla_hours"):
            assert t["due_date"], "due_date not auto-filled from SLA"
        # persistence via list
        gt = _get_task(sess, t["id"])
        assert gt["jobdesk_code"] == "SM-10"
        assert gt["related_entity_id"] == lead_id

    def test_fake_related_id_404(self, sess):
        r = sess.post(f"{API}/work/tasks", json={
            "title": "TEST_P110 fake lead", "type": "follow_up", "priority": "medium",
            "related_entity_type": "lead", "related_entity_id": "does-not-exist"},
            timeout=20)
        assert r.status_code == 404, f"{r.status_code} {r.text[:300]}"

    def test_unknown_entity_type_400(self, sess):
        r = sess.post(f"{API}/work/tasks", json={
            "title": "TEST_P110 banana", "type": "follow_up", "priority": "medium",
            "related_entity_type": "banana", "related_entity_id": "x"}, timeout=20)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"

    def test_type_without_id_400(self, sess):
        r = sess.post(f"{API}/work/tasks", json={
            "title": "TEST_P110 no id", "type": "follow_up", "priority": "medium",
            "related_entity_type": "lead"}, timeout=20)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"

    def test_unknown_jobdesk_400(self, sess):
        r = sess.post(f"{API}/work/tasks", json={
            "title": "TEST_P110 jobdesk palsu", "type": "follow_up",
            "priority": "medium", "jobdesk_code": "XX-99"}, timeout=20)
        assert r.status_code == 400, (
            f"unknown jobdesk accepted: {r.status_code} "
            f"jobdesk_code={r.json().get('data', {}).get('jobdesk_code')!r} "
            f"division={r.json().get('data', {}).get('division')!r} {r.text[:200]}")


# ------------------------------------------------- WA manual closing a task
class TestWaManualClosesTask:
    @pytest.fixture(scope="class")
    def lead_task(self, sess):
        lead_id = _new_lead(sess, "TEST_P110_ManualTask")
        r = sess.post(f"{API}/work/tasks", json={
            "title": "TEST_P110 follow up WA", "type": "follow_up",
            "priority": "medium", "jobdesk_code": "SM-10",
            "related_entity_type": "lead", "related_entity_id": lead_id}, timeout=30)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:400]}"
        return lead_id, r.json()["data"]["id"]

    def test_manual_with_task_id_closes_task(self, sess, lead_task):
        lead_id, task_id = lead_task
        fid = _upload(sess, lead_id)
        r = sess.post(f"{API}/leads/{lead_id}/wa/manual", json={
            "note": "TEST_P110 chat lewat WA pribadi, sudah follow up",
            "evidence_file_ids": [fid], "task_id": task_id}, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        data = r.json()["data"]
        assert data["lead"]["stage"] == "nurturing"
        t = data["task"]
        assert t and t["id"] == task_id
        assert t["status"] == "done", t["status"]
        assert t["review"] == "approved", t["review"]
        assert t["verified_by"] == "system", t.get("verified_by")
        kinds = {p.get("kind") for p in (t.get("proof") or [])}
        assert {"note", "photo"} <= kinds, t.get("proof")
        assert any(p.get("value") == fid for p in t["proof"] if p.get("kind") == "photo")
        # persistence via list
        g = _get_task(sess, task_id, status="done")
        assert g["status"] == "done"
        assert g["review"] == "approved"

    def test_manual_with_closed_task_400(self, sess, lead_task):
        lead_id, task_id = lead_task
        fid = _upload(sess, lead_id)
        r = sess.post(f"{API}/leads/{lead_id}/wa/manual", json={
            "note": "TEST_P110 tugas sudah ditutup", "evidence_file_ids": [fid],
            "task_id": task_id}, timeout=30)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
        assert "ditutup" in r.text

    def test_manual_with_nonexistent_task_404(self, sess, lead_task):
        lead_id, _ = lead_task
        fid = _upload(sess, lead_id)
        r = sess.post(f"{API}/leads/{lead_id}/wa/manual", json={
            "note": "TEST_P110 tugas palsu", "evidence_file_ids": [fid],
            "task_id": "nope-nope"}, timeout=30)
        assert r.status_code == 404, f"{r.status_code} {r.text[:300]}"

    def test_manual_with_task_of_other_lead_404(self, sess, lead_task):
        lead_id, task_id = lead_task
        other = _new_lead(sess, "TEST_P110_OtherLead")
        fid = _upload(sess, other)
        r = sess.post(f"{API}/leads/{other}/wa/manual", json={
            "note": "TEST_P110 tugas lead lain", "evidence_file_ids": [fid],
            "task_id": task_id}, timeout=30)
        assert r.status_code == 404, f"{r.status_code} {r.text[:300]}"
