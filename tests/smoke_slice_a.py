"""Smoke test Slice A backend flow against the running server (localhost:8001)."""
import requests, sys, time

BASE = "http://localhost:8001/api"
results = []
def rec(name, ok, detail=""):
    results.append(bool(ok)); print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

def login(email, pw="Sipro#2026"):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    return r.json()["access_token"]

def H(t): return {"Authorization": f"Bearer {t}"}

sales = login("sales@sipro.co.id")
sales2 = login("sales2@sipro.co.id")
manager = login("manager@sipro.co.id")

# 1. Leads list (scoped)
r = requests.get(f"{BASE}/leads", headers=H(sales))
d = r.json()
rec("1. Sales list leads (scoped, scored)", r.status_code==200 and d["total"]>=2 and all("score" in x for x in d["data"]),
    f"total={d.get('total')}, counts={d.get('counts')}")

# 2. Webhook capture -> lead + 5min task
ph = f"+62899{int(time.time())%100000}"
r = requests.post(f"{BASE}/webhooks/meta-lead", json={"name":"Test Meta Lead","phone":ph,"campaign":"c-a","message":"berapa harga unitnya?"})
cap = r.json()["data"]; lead_id = cap["lead_id"]
rec("2. Meta webhook capture (simulation)", r.status_code==200 and not cap["duplicate"] and lead_id, f"lead={lead_id}")

# 2b. dedup
r2 = requests.post(f"{BASE}/webhooks/meta-lead", json={"name":"Test Meta Lead","phone":ph})
rec("2b. Webhook dedup", r2.json()["data"]["duplicate"] is True)

# 3. Task 'Hubungi <=5 menit' created for assignee — check via that lead's assignee
time.sleep(1)
# find who owns it: check as manager (view_all)
r = requests.get(f"{BASE}/leads/{lead_id}", headers=H(manager))
assignee = r.json()["data"].get("assigned_to")
tok = sales if assignee=="sales@sipro.co.id" else sales2
r = requests.get(f"{BASE}/work/tasks", headers=H(tok), params={"filter":"mine"})
tasks = r.json()["data"]
contact_task = [t for t in tasks if t.get("related_entity_id")==lead_id and t["type"]=="contact"]
rec("3. Guided task 'Hubungi <=5 menit' created", len(contact_task)==1 and contact_task[0].get("sla_due_at"),
    f"assignee={assignee}, tasks_for_lead={len(contact_task)}")

# 4. RBAC: sales2 cannot see sales-owned lead detail
sales_lead = requests.get(f"{BASE}/leads", headers=H(sales)).json()["data"][0]["id"]
r = requests.get(f"{BASE}/leads/{sales_lead}", headers=H(sales2))
rec("4. RBAC row-scope (sales2 denied sales lead)", r.status_code==403, f"status={r.status_code}")

# 5. Inbox: list + send inbound (trigger automation)
convs = requests.get(f"{BASE}/inbox", headers=H(sales)).json()["data"]
rec("5. Inbox conversations listed", len(convs)>=1, f"count={len(convs)}")
conv_id = convs[0]["id"]
r = requests.post(f"{BASE}/inbox/{conv_id}/messages", headers=H(sales), json={"body":"mau tanya soal KPR dan cicilan","direction":"in"})
time.sleep(1)
tks = requests.get(f"{BASE}/work/tasks", headers=H(sales)).json()["data"]
auto = [t for t in tks if t.get("related_entity_id")==conv_id]
rec("5b. Automation keyword -> suggestion task", r.status_code==200 and len(auto)>=1, f"auto_tasks={len(auto)}")

# 6. Units + atomic booking
units = requests.get(f"{BASE}/units", headers=H(sales)).json()
avail = [u for u in units["data"] if u["status"]=="available"]
rec("6. Units listed", units["total"]>=6 and len(avail)>=1, f"avail={len(avail)}, counts={units.get('counts')}")
unit_id = avail[0]["id"]
# reserve using sales' own lead
r = requests.post(f"{BASE}/deals/reserve", headers=H(sales), json={"unit_id":unit_id,"lead_id":sales_lead,"booking_fee":5000000})
deal = r.json().get("data",{}); deal_id = deal.get("id")
rec("6b. Reserve unit (atomic hold)", r.status_code==200 and deal.get("status")=="reserved", f"status={r.status_code}")
# double reserve -> 409
r2 = requests.post(f"{BASE}/deals/reserve", headers=H(sales), json={"unit_id":unit_id,"lead_id":sales_lead})
rec("6c. Double booking blocked (409)", r2.status_code==409, f"status={r2.status_code}")
# book
r = requests.post(f"{BASE}/deals/{deal_id}/book", headers=H(sales), json={})
rec("6d. Book deal (reserved->booked)", r.status_code==200 and r.json()["data"]["status"]=="booked")

# 7. Document SPR: create -> finalize -> sign -> pdf
r = requests.post(f"{BASE}/documents", headers=H(sales), json={"template_code":"SPR","deal_id":deal_id})
doc = r.json().get("data",{}); doc_id = doc.get("id")
rec("7. Create SPR document (draft)", r.status_code==200 and doc.get("status")=="draft", f"num={doc.get('doc_number')}")
requests.post(f"{BASE}/documents/{doc_id}/finalize", headers=H(sales))
r = requests.post(f"{BASE}/documents/{doc_id}/sign", headers=H(sales), json={"role":"buyer","name":"Ibu Dewi Kartika"})
rec("7b. Finalize + sign SPR", r.status_code==200 and r.json()["data"]["status"]=="signed")
r = requests.get(f"{BASE}/documents/{doc_id}/pdf", headers=H(sales))
rec("7c. Download SPR PDF", r.status_code==200 and r.headers.get("content-type")=="application/pdf" and len(r.content)>800,
    f"bytes={len(r.content)}")

# 8. first-contact response_time
r = requests.post(f"{BASE}/leads/{lead_id}/first-contact", headers=H(tok))
rt = r.json()["data"].get("response_time_minutes")
rec("8. First contact sets response_time_minutes", r.status_code==200 and rt is not None, f"rt={rt}")

print("="*60)
print(f"RINGKASAN: {sum(results)}/{len(results)} PASS")
sys.exit(0 if all(results) else 1)
