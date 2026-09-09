"""Smoke test Slice B (Construction) against running server (localhost:8001)."""
import requests, sys

BASE = "http://localhost:8001/api"
results = []
def rec(name, ok, detail=""):
    results.append(bool(ok)); print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
def login(email, pw="Sipro#2026"):
    return requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}).json()["access_token"]
def H(t): return {"Authorization": f"Bearer {t}"}

pm = login("pm@sipro.co.id")
site = login("site@sipro.co.id")
owner = login("owner@sipro.co.id")
sales = login("sales@sipro.co.id")

# B1: projects scoped for pm (member)
r = requests.get(f"{BASE}/projects", headers=H(pm))
d = r.json()
rec("B1. PM lists member projects", r.status_code == 200 and d["total"] >= 1, f"total={d.get('total')}")
pid = d["data"][0]["id"]

# B1b: project detail (units + phases + curve)
r = requests.get(f"{BASE}/projects/{pid}", headers=H(pm)).json()["data"]
curve0 = r["curve"]
rec("B1b. Project detail units+phases+curve", len(r["units"]) == 6 and len(r["phases"]) == 6 and "overall_actual" in curve0,
    f"units={len(r['units'])}, phases={len(r['phases'])}, actual={curve0['overall_actual']}, planned={curve0['overall_planned']}, behind={curve0['behind']}")
rec("B1c. Kurva-S baseline behind schedule", curve0["behind"] is True and curve0["overall_actual"] < curve0["overall_planned"],
    f"dev={curve0['deviation']}")

# B2: update phase progress -> overall recompute
struktur = [p for p in r["phases"] if p["name"] == "Struktur"][0]
res = requests.post(f"{BASE}/construction/phases/{struktur['id']}/progress", headers=H(site),
                    json={"progress": 70, "note": "cor kolom lantai 2"})
rj = res.json()
rec("B2. Site updates progress -> overall recompute", res.status_code == 200 and rj["overall"] > curve0["overall_actual"],
    f"new_overall={rj.get('overall')}")

# B3: QC fail -> phase qc_hold + corrective task
pondasi = [p for p in r["phases"] if p["name"] == "Pondasi"][0]
res = requests.post(f"{BASE}/construction/qc", headers=H(site),
                    json={"project_id": pid, "phase_id": pondasi["id"], "result": "fail", "notes": "retak halus terdeteksi"})
rec("B3. QC fail logged", res.status_code == 200 and res.json()["data"]["result"] == "fail")
ph = requests.get(f"{BASE}/construction/project/{pid}/phases", headers=H(pm)).json()["data"]
pond = [p for p in ph if p["name"] == "Pondasi"][0]
rec("B3b. Failed phase -> qc_hold", pond["status"] == "qc_hold", f"status={pond['status']}")
tasks = requests.get(f"{BASE}/work/tasks", headers=H(pm)).json()["data"]
qc_task = [t for t in tasks if t.get("related_entity_id") == pid and "QC" in t.get("title", "")]
rec("B3c. Corrective QC task created for PM", len(qc_task) >= 1, f"qc_tasks={len(qc_task)}")

# B4: materials stock + txn + opname
mats = requests.get(f"{BASE}/materials/project/{pid}", headers=H(site)).json()["data"]
rec("B4. Materials listed w/ stock", len(mats) == 4 and all("stock" in m for m in mats),
    f"count={len(mats)}, stocks={[(m['code'], m['stock']) for m in mats]}")
semen = [m for m in mats if m["code"] == "SMN"][0]
before = semen["stock"]
res = requests.post(f"{BASE}/materials/txn", headers=H(site),
                    json={"project_id": pid, "material_id": semen["id"], "type": "out", "qty": 50, "note": "pengecoran"})
rec("B4b. Issue material (out) reduces stock", res.status_code == 200 and res.json()["stock"] == before - 50,
    f"stock={res.json().get('stock')}")
# over-issue guard
res = requests.post(f"{BASE}/materials/txn", headers=H(site),
                    json={"project_id": pid, "material_id": semen["id"], "type": "out", "qty": 999999})
rec("B4c. Over-issue blocked (400)", res.status_code == 400, f"status={res.status_code}")
# opname variance
book_now = requests.get(f"{BASE}/materials/project/{pid}", headers=H(site)).json()["data"]
semen2 = [m for m in book_now if m["code"] == "SMN"][0]["stock"]
res = requests.post(f"{BASE}/materials/opname", headers=H(site),
                    json={"project_id": pid, "material_id": semen["id"], "physical_qty": semen2 - 10, "note": "opname bulanan"})
oj = res.json()["data"]
rec("B4d. Opname variance computed", res.status_code == 200 and oj["variance"] == -10 and oj["new_stock"] == semen2 - 10,
    f"book={oj['book_qty']}, variance={oj['variance']}")

# B5: RBAC — sales denied materials; project scope for site on non-member project
r = requests.get(f"{BASE}/materials/project/{pid}", headers=H(sales))
rec("B5. Sales denied materials (403)", r.status_code == 403, f"status={r.status_code}")
# owner creates a project without site as member
res = requests.post(f"{BASE}/projects", headers=H(owner),
                    json={"name": "Cluster Baru Blok B", "code": "CBB", "members": []})
pid2 = res.json()["data"]["id"]
r = requests.get(f"{BASE}/projects/{pid2}", headers=H(site))
rec("B5b. Project-scope: site denied non-member project (403)", r.status_code == 403, f"status={r.status_code}")

# X1: 3-way sync — booked unit carries construction_progress + payment_status
units = requests.get(f"{BASE}/units", headers=H(sales), params={"project_id": pid}).json()["data"]
avail = [u for u in units if u["status"] == "available"][0]
lead = requests.get(f"{BASE}/leads", headers=H(sales)).json()["data"][0]["id"]
dr = requests.post(f"{BASE}/deals/reserve", headers=H(sales),
                   json={"unit_id": avail["id"], "lead_id": lead, "booking_fee": 5000000}).json()["data"]
requests.post(f"{BASE}/deals/{dr['id']}/book", headers=H(sales), json={})
u = requests.get(f"{BASE}/units", headers=H(sales), params={"project_id": pid}).json()["data"]
booked = [x for x in u if x["id"] == avail["id"]][0]
rec("X1. 3-way sync: booked unit has construction_progress + payment_status",
    booked["status"] == "booked" and booked.get("construction_progress", 0) > 0 and booked.get("payment_status") == "booking_fee",
    f"status={booked['status']}, progress={booked.get('construction_progress')}, pay={booked.get('payment_status')}")

print("=" * 60)
print(f"RINGKASAN SLICE B: {sum(results)}/{len(results)} PASS")
sys.exit(0 if all(results) else 1)
