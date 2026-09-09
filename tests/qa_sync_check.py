import json, sys, urllib.request

API = "http://localhost:8001"
def login():
    req = urllib.request.Request(API + "/api/auth/login", method="POST",
        data=json.dumps({"email": "superadmin@sipro.co.id", "password": "Sipro#2026"}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "curl/8"})
    d = json.load(urllib.request.urlopen(req))
    return d.get("token") or d.get("access_token") or d.get("data", {}).get("token")
TOK = login()
def call(m, p, body=None):
    req = urllib.request.Request(API + p, method=m, data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + TOK, "Content-Type": "application/json", "User-Agent": "curl/8"})
    try: return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e: return {"err": e.code, "detail": e.read().decode()[:300]}

t = call("GET", "/api/construction/phase-templates")["data"][0]
rows = [{"name": p["name"], "weight": p["weight"], "planned_pct": p.get("planned_pct", 0), "work_category": c}
        for p, c in zip(t["phases"], ["persiapan", "struktur", "struktur", "arsitektur", "mep", "finishing"])]
r = call("PUT", f"/api/construction/phase-templates/{t['id']}", {"code": t["code"], "name": t["name"], "description": t.get("description"), "phases": rows})
print("tpl", [(p["name"], p.get("work_category")) for p in r.get("data", {}).get("phases", [])] or r)

ar = call("GET", "/api/finance/ar/3266be54-0961-4105-b543-9d7dae616bd6")["data"]
t1 = [i for i in ar["items"] if i["label"].startswith("Termin I ")][0]
if t1.get("paid_amount", 0) == 0:
    r = call("POST", "/api/finance/ar/receipts", {"deal_id": ar["deal_id"], "amount": 50000000, "method": "transfer", "allocations": [{"item_id": t1["id"], "amount": 50000000}]})
    inv = r.get("data", {}).get("invoice", {})
    print("alloc", r.get("data", {}).get("receipt", {}).get("allocations"), [(i["label"], i.get("paid_amount")) for i in inv.get("items", [])] or r)
r = call("POST", "/api/finance/ar/receipts", {"deal_id": ar["deal_id"], "amount": 10000000, "method": "transfer", "allocations": [{"item_id": t1["id"], "amount": 999999999}]})
print("overalloc", r.get("err"), r.get("detail", "")[:140])

tp = call("GET", "/api/build/templates").get("data", [])
src = [x for x in tp if x.get("unit_types")]
if src:
    src = src[0]
    r = call("POST", "/api/build/templates/clone", {"clone_from": src["id"], "code": "QA-OVERLAP", "name": "QA overlap", "unit_types": src["unit_types"]})
    print("overlap", r.get("err"), r.get("detail", "")[:160])
print("layout", str(call("GET", "/api/doc-layouts/INVOICE_BF"))[:160])
# project phases sync check
projs = call("GET", "/api/projects?limit=1").get("data", [])
if projs:
    pid = projs[0]["id"]
    ph = call("GET", f"/api/construction/project/{pid}/phases")
    cats = {"Persiapan Lahan": "persiapan", "Pondasi": "struktur", "Struktur": "struktur", "Dinding & Atap": "arsitektur", "MEP (Listrik/Air)": "mep", "Finishing": "finishing"}
    for p in ph.get("data", []):
        if not p.get("work_category") and cats.get(p["name"]):
            print("set", p["name"], str(call("PUT", f"/api/construction/phases/{p['id']}", {"work_category": cats[p["name"]]}))[:80])
    ph = call("GET", f"/api/construction/project/{pid}/phases")
    r = call("POST", f"/api/construction/phases/{ph['data'][0]['id']}/progress", {"progress": 50}); print("manual-on-synced", r.get("err"), r.get("detail", "")[:100])
    print("phases", [(p["name"], p.get("work_category"), p.get("progress"), p.get("progress_source")) for p in ph.get("data", [])])
