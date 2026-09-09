"""EPIC 1.7 backend functional test (SIMULATION)."""
import requests

API = "http://localhost:8001/api"
PW = "Sipro#2026"
R = []


def check(name, cond, detail=""):
    R.append(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PW}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def h(t):
    return {"Authorization": f"Bearer {t}"}


def main():
    mgr = login("manager@sipro.co.id")
    sales = login("sales@sipro.co.id")

    # 1) Seeded config
    rules = requests.get(f"{API}/automation-rules", headers=h(mgr)).json()
    check("automation-rules seeded (>=3)", rules.get("total", 0) >= 3, f"total={rules.get('total')}")
    events = {r["trigger"]["event"] for r in rules["data"]}
    check("rules cover message.received/lead.captured/no_response",
          {"message.received", "lead.captured", "no_response"} <= events, str(events))

    tmpls = requests.get(f"{API}/wa-templates", headers=h(mgr)).json()
    check("wa-templates seeded (>=4)", tmpls.get("total", 0) >= 4, f"total={tmpls.get('total')}")

    chans = requests.get(f"{API}/channels", headers=h(mgr)).json()
    check("channels seeded (>=5, simulation)", chans.get("total", 0) >= 5
          and all(c["mode"] == "simulation" for c in chans["data"]))

    # 2) Attribution + capture events
    attr = requests.get(f"{API}/capture-events/attribution", headers=h(mgr)).json()["data"]
    check("attribution has rows + totals", bool(attr["rows"]) and attr["totals"]["leads"] > 0,
          f"totals={attr['totals']}")
    ce = requests.get(f"{API}/capture-events", headers=h(mgr)).json()
    check("capture-events audit list non-empty", ce.get("total", 0) >= 1, f"total={ce.get('total')}")

    # 3) Inbox window + filters
    convs = requests.get(f"{API}/inbox", headers=h(sales), params={"filter": "unanswered"}).json()
    stale = next((c for c in convs["data"] if "Pasif" in (c.get("contact_name") or "")), None)
    check("unanswered filter returns stale conv", stale is not None)
    if stale:
        check("stale conv window_open=false", stale.get("window_open") is False,
              f"window_open={stale.get('window_open')}")

    # 4) Template-gated outbound send on closed window
    if stale:
        cid = stale["id"]
        r1 = requests.post(f"{API}/inbox/{cid}/messages", headers=h(sales),
                           json={"body": "halo, masih tersedia", "direction": "out"})
        check("free-form reply on CLOSED window -> 400", r1.status_code == 400, f"code={r1.status_code}")
        r2 = requests.post(f"{API}/inbox/{cid}/messages", headers=h(sales),
                           json={"body": "", "direction": "out", "template_code": "reengage"})
        check("template send on closed window -> 200", r2.status_code == 200,
              f"code={r2.status_code} {r2.text[:120]}")
        check("template message flagged is_template",
              r2.status_code == 200 and r2.json()["data"].get("is_template") is True)

    # 5) Inbound keyword -> automation (send_template + suggest_stage + create_task)
    allconv = requests.get(f"{API}/inbox", headers=h(sales)).json()["data"]
    answered = next((c for c in allconv if c.get("lead_id") and "Pasif" not in (c.get("contact_name") or "")), None)
    if answered:
        cid = answered["id"]
        before = requests.get(f"{API}/inbox/{cid}", headers=h(sales)).json()["data"]["messages"]
        requests.post(f"{API}/inbox/{cid}/messages", headers=h(sales),
                      json={"body": "berapa harga dan cicilan KPR nya?", "direction": "in"})
        import time
        time.sleep(1.5)
        after = requests.get(f"{API}/inbox/{cid}", headers=h(sales)).json()["data"]["messages"]
        tmpl_sent = [m for m in after if m.get("is_template")]
        check("inbound keyword triggered auto template reply", len(after) > len(before) and len(tmpl_sent) >= 1,
              f"before={len(before)} after={len(after)} templates={len(tmpl_sent)}")
        # suggestion task created for the lead
        tasks = requests.get(f"{API}/work/tasks", headers=h(sales)).json()
        titles = " ".join(t.get("title", "") for t in tasks.get("data", []))
        check("automation created NBA/suggestion task", "Usulan" in titles or "intent" in titles.lower(),
              titles[:160])

    # 6) Rule CRUD lifecycle
    created = requests.post(f"{API}/automation-rules", headers=h(mgr), json={
        "name": "Uji Rule", "trigger_event": "message.received", "keywords": ["promo"],
        "actions": [{"type": "create_task", "title": "cek promo"}]}).json()["data"]
    rid = created["id"]
    check("rule create", bool(rid))
    tog = requests.post(f"{API}/automation-rules/{rid}/toggle", headers=h(mgr)).json()["data"]
    check("rule toggle -> inactive", tog["is_active"] is False)
    upd = requests.put(f"{API}/automation-rules/{rid}", headers=h(mgr),
                       json={"keywords": ["promo", "diskon"]}).json()["data"]
    check("rule update keywords", "diskon" in upd["trigger"]["keywords"])
    dele = requests.delete(f"{API}/automation-rules/{rid}", headers=h(mgr)).json()["data"]
    check("rule delete", dele.get("deleted") is True)

    # 7) Multi-provider webhook capture w/ attribution
    r = requests.post(f"{API}/webhooks/google-lead", json={
        "name": "Uji Google", "phone": "+628129998887", "campaign": "gads-brand",
        "adset_id": "g-as1", "creative_id": "g-cr1", "form_id": "g-lf1"}).json()["data"]
    check("google-lead webhook capture", bool(r.get("lead_id")) and r.get("provider") == "google_lead")

    print("-" * 55)
    print(f"RESULT: {sum(R)}/{len(R)} checks passed")
    raise SystemExit(0 if all(R) else 1)


if __name__ == "__main__":
    main()
