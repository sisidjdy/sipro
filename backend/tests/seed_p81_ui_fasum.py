"""Seed SPK fasum baru (batas fase 35%) untuk uji UI guard termin fasum — Fase 81."""
import os
import random

import requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"email": "superadmin@sipro.co.id", "password": "Sipro#2026"})
r.raise_for_status()
s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})

projects = s.get(f"{BASE}/api/projects").json()
projects = projects if isinstance(projects, list) else projects.get("data", projects.get("items"))
pid = [p for p in projects if "Cluster Asri Blok A" in p["name"]][0]["id"]
tag = random.randint(1000, 9999)

ph = s.post(f"{BASE}/api/construction/phases", json={"project_id": pid, "name": f"TEST81UI_Fase jalan {tag}", "weight": 1, "order": 97})
print("phase", ph.status_code, ph.text[:200])
phase = ph.json().get("data", ph.json())
phid = phase["id"]
pr = s.post(f"{BASE}/api/construction/phases/{phid}/progress", json={"progress": 35})
print("progress", pr.status_code, pr.text[:150])

it = s.post(f"{BASE}/api/boq/items", json={
    "project_id": pid, "cost_code": f"TEST81UI-{tag}", "description": f"TEST81UI Jalan lingkungan {tag}",
    "category": "infrastruktur", "uom": "m", "quantity": 10, "unit_price": 1000000,
    "scope": "fasum", "facility": "jalan", "phase_id": phid})
print("boq item", it.status_code, it.text[:200])
item = it.json().get("data", it.json())

dr = s.post(f"{BASE}/api/rab/spk-draft", json={"project_id": pid, "mode": "fasum", "boq_item_ids": [item["id"]]})
print("draft", dr.status_code, dr.text[:300])
draft = dr.json()["data"]

subs = s.get(f"{BASE}/api/subcon/subcontractors").json()
subs = subs.get("data", subs) if isinstance(subs, dict) else subs
sub_id = (subs["items"] if isinstance(subs, dict) else subs)[0]["id"]

sp = s.post(f"{BASE}/api/subcon/spk/from-rab", json={
    "subcontractor_id": sub_id, "project_id": pid, "title": f"TEST81UI_SPK jalan {tag}",
    "spk_kind": "fasum", "lines": draft["lines"]})
print("spk", sp.status_code, sp.text[:300])
spk = sp.json()["data"]
st = s.post(f"{BASE}/api/subcon/spk/{spk['id']}/status", json={"status": "active"})
print("activate", st.status_code, st.text[:200])
print("SPK_TITLE:", f"TEST81UI_SPK jalan {tag}", "| number:", spk.get("spk_number"))
