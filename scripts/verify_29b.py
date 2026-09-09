#!/usr/bin/env python3
"""POC/verifikasi Fase 29b — LEAD LIFECYCLE GERBANG BUKTI + WA TERINTEGRASI.

Menjaga agar cacat yang sudah terbukti TIDAK BISA MUNDUR:
  L-1  stage tidak boleh dipilih seenaknya (nurturing→booking tanpa deal, booking→won).
  L-3  `won` otomatis dari bukti legal; lost/recycle wajib beralasan.
  L-4  kirim WA dari record lead = kontak pertama (waktu respons + tahap + tugas tertutup).
  L-6  chat tidak boleh mengusulkan lompat ke `won`.
  L-7  setiap perpindahan tahap tercatat di `stage_history`.
Plus: playbook WA per tahap (reminder/follow-up/blasting) & penilaian kualitatif respons.

Jalankan: python3 scripts/verify_29b.py
"""
import os
import sys
import uuid

import requests

BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PW = "Sipro#2026"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  PASS' if cond else '  FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    return bool(cond)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def g(h, p, **params):
    return requests.get(f"{BASE}{p}", headers=h, params=params, timeout=40)


def po(h, p, body=None):
    return requests.post(f"{BASE}{p}", headers=h, json=body or {}, timeout=60)


def main():
    sales = login("sales@sipro.co.id")
    mgr = login("manager@sipro.co.id")
    dmlead = login("dmlead@sipro.co.id")

    print("\n=== A. Lead baru: tahap awal & gerbang bukti ===")
    phone = f"+62812{uuid.uuid4().int % 10**8:08d}"
    r = po(sales, "/leads", {"name": "Uji Lifecycle 29b", "phone": phone,
                             "source": "walk_in", "interest_unit_type": "Tipe 45/90"})
    check("Buat lead 200", r.status_code == 200, r.text[:200])
    lead = r.json()["data"]
    lid = lead["id"]
    check("Tahap awal 'acquisition'", lead["stage"] == "acquisition", lead["stage"])

    lf = g(sales, f"/leads/{lid}/lifecycle")
    check("GET lifecycle 200", lf.status_code == 200, lf.text[:200])
    life = lf.json()["data"]
    check("Syarat 'nurturing' = kontak pertama (belum terpenuhi)",
          life["requirements"]["nurturing"][0]["met"] is False)
    check("Belum boleh naik tahap", life["can_advance"] is False, str(life["can_advance"]))
    check("Ada penjelasan syarat yang kurang", bool(life["blocked_reason"]))
    check("Ada langkah berikutnya (NBA) di record lead", len(life["next_actions"]) >= 1)

    r = po(sales, f"/leads/{lid}/stage", {"stage": "appointment"})
    check("acquisition→appointment DITOLAK (tidak berurutan)", r.status_code == 400, r.text[:150])
    r = po(sales, f"/leads/{lid}/stage", {"stage": "won"})
    check("won manual DITOLAK di tahap mana pun", r.status_code == 400
          and "tidak bisa dipilih manual" in r.text, r.text[:200])
    r = po(sales, f"/leads/{lid}/stage", {"stage": "lost"})
    check("lost tanpa alasan DITOLAK", r.status_code == 400 and "Alasan wajib" in r.text,
          r.text[:200])

    print("\n=== B. WA di record lead = kontak pertama nyata ===")
    w = g(sales, f"/leads/{lid}/wa")
    check("GET /leads/{id}/wa 200", w.status_code == 200, w.text[:150])
    wa = w.json()["data"]
    check("Sesi 24 jam tertutup untuk lead baru", wa["window_open"] is False)
    check("Template pra-approved tersedia", len(wa["templates"]) >= 3, str(len(wa["templates"])))
    check("Ditandai mode simulasi (jujur)", wa["mode"] == "simulation")

    r = po(sales, f"/leads/{lid}/wa", {"body": "Halo pak", "direction": "out"})
    check("Kirim teks bebas saat sesi tertutup DITOLAK", r.status_code == 400, r.text[:180])

    r = po(sales, f"/leads/{lid}/wa", {"body": "", "direction": "out",
                                       "template_code": "welcome"})
    check("Kirim template 200", r.status_code == 200, r.text[:200])
    body = r.json().get("data", {})
    fresh = body.get("lead", {})
    check("Kontak pertama tercatat", bool(fresh.get("first_contact_at")))
    check("Waktu respons dihitung", fresh.get("response_time_minutes") is not None)
    check("Tahap naik ke nurturing lewat aksi WA", fresh.get("stage") == "nurturing",
          str(fresh.get("stage")))
    check("Riwayat tahap tercatat", len(fresh.get("stage_history") or []) >= 1)
    hist = (fresh.get("stage_history") or [{}])[-1]
    check("Riwayat menyebut sumber aksi", "contact" in str(hist.get("source")), str(hist))

    acts = g(sales, "/activities", entity_type="lead", entity_id=lid).json().get("data", [])
    check("Pesan WA muncul di timeline LEAD",
          any("WhatsApp" in (a.get("body") or "") for a in acts),
          str([a.get("body") for a in acts][:3]))
    tasks = g(sales, "/work/tasks", scope="mine", limit=100).json().get("data", [])
    contact_open = [t for t in tasks if t.get("related_entity_id") == lid
                    and t.get("type") == "contact"]
    check("Tugas 'hubungi lead' otomatis tertutup oleh bukti WA", not contact_open,
          str([t.get("status") for t in contact_open]))

    r = po(sales, f"/leads/{lid}/wa/inbound-demo", {"body": "Berapa harga tipe 45? mau survey",
                                                    "direction": "in"})
    check("Simulasi balasan pelanggan 200", r.status_code == 200, r.text[:150])
    wa2 = g(sales, f"/leads/{lid}/wa").json()["data"]
    check("Sesi 24 jam terbuka setelah balasan", wa2["window_open"] is True)
    r = po(sales, f"/leads/{lid}/wa", {"body": "Harga mulai 850jt pak", "direction": "out"})
    check("Teks bebas boleh saat sesi terbuka", r.status_code == 200, r.text[:150])

    print("\n=== C. Penilaian kualitatif respons lead ===")
    r = po(sales, f"/leads/{lid}/disposition", {"disposition": "ngawur"})
    check("Nilai respons ngawur DITOLAK", r.status_code == 400, r.text[:150])
    r = po(sales, f"/leads/{lid}/disposition",
           {"disposition": "positive", "note": "Minat kuat, minta survey Sabtu",
            "intent_tags": ["survey", "harga"]})
    check("Set respons positif 200", r.status_code == 200, r.text[:200])
    d = r.json()
    check("Disposition tersimpan", d["data"]["disposition"] == "positive")
    check("Catatan kualitatif tersimpan", "Minat kuat" in (d["data"].get("disposition_note") or ""))
    check("Langkah berikutnya menyesuaikan", len(d.get("next_actions") or []) >= 1)

    print("\n=== D. Naik tahap hanya dengan bukti ===")
    r = po(sales, f"/leads/{lid}/stage", {"stage": "booking"})
    check("nurturing→booking DITOLAK tanpa reservasi", r.status_code == 400
          and "SPR" in r.text, r.text[:220])
    r = po(sales, "/appointments", {"lead_id": lid, "title": "Survey unit",
                                    "scheduled_at": "2026-12-01T03:00:00+00:00",
                                    "type": "survey", "location": "Kantor pemasaran"})
    check("Buat appointment 200", r.status_code == 200, r.text[:200])
    st = g(sales, f"/leads/{lid}").json()["data"]["stage"]
    check("Tahap otomatis jadi 'appointment' karena survey dijadwalkan", st == "appointment", st)
    life2 = g(sales, f"/leads/{lid}/lifecycle").json()["data"]
    check("Syarat booking menyebut reservasi belum ada",
          any(not x["met"] for x in life2["requirements"]["booking"]))

    print("\n=== E. 'won' hanya dari bukti legal (otomatis) ===")
    units = g(sales, "/units", status="available").json().get("data", [])
    unit = units[0] if units else None
    check("Ada unit tersedia untuk uji", bool(unit), str(len(units)))
    if unit:
        r = po(sales, "/deals/reserve", {"lead_id": lid, "unit_id": unit["id"],
                                         "booking_fee": 5000000})
        check("Reservasi unit 200", r.status_code == 200, r.text[:250])
        deal_id = (r.json().get("data") or {}).get("id")
        st = g(sales, f"/leads/{lid}").json()["data"]["stage"]
        check("Tahap otomatis 'booking' karena reservasi (bukti transaksi)", st == "booking", st)
        po(login("finance@sipro.co.id"), f"/booking-fee/deals/{deal_id}/pay",
           {"amount": 5000000, "method": "transfer"})
        r = po(mgr, f"/deals/{deal_id}/book", {})
        check("Booking deal 200", r.status_code == 200, r.text[:200])
        r = po(mgr, f"/deals/{deal_id}/ppjb", {"note": "uji"})
        check("Tanda tangan PPJB 200", r.status_code == 200, r.text[:250])
        r = po(mgr, f"/deals/{deal_id}/ajb", {"notary": "Notaris Uji"})
        check("Tanda tangan AJB 200", r.status_code == 200, r.text[:250])
        import time
        lead_after = {}
        for _ in range(12):   # dispatcher outbox berjalan tiap ~8 detik
            time.sleep(2)
            lead_after = g(mgr, f"/leads/{lid}").json()["data"]
            if lead_after.get("stage") == "won":
                break
        check("Lead OTOMATIS jadi 'won' setelah AJB (tanpa klik manual)",
              lead_after["stage"] == "won", lead_after["stage"])
        won_hist = [h for h in (lead_after.get("stage_history") or []) if h["to"] == "won"]
        check("Riwayat 'won' bersumber dari deal", bool(won_hist)
              and won_hist[-1].get("source") == "deal", str(won_hist[-1:]))

    print("\n=== F. Override hanya supervisor + wajib alasan ===")
    r = po(sales, "/leads", {"name": "Uji Override", "phone": f"+62813{uuid.uuid4().int % 10**8:08d}",
                             "source": "walk_in"})
    lid2 = r.json()["data"]["id"]
    r = po(sales, f"/leads/{lid2}/stage/override", {"stage": "booking", "reason": "maksa"})
    check("Staf sales DILARANG override", r.status_code == 403, r.text[:150])
    r = po(mgr, f"/leads/{lid2}/stage/override", {"stage": "booking", "reason": "abc"})
    check("Override tanpa alasan memadai DITOLAK", r.status_code in (400, 422),
          str(r.status_code))
    r = po(mgr, f"/leads/{lid2}/stage/override",
           {"stage": "booking", "reason": "Migrasi data lama: SPR fisik sudah ada"})
    check("Supervisor boleh override dengan alasan", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        h = (r.json()["data"].get("stage_history") or [{}])[-1]
        check("Override ditandai di riwayat", h.get("override") is True and bool(h.get("reason")),
              str(h))

    print("\n=== G. Chat tidak boleh mengusulkan 'won' ===")
    convs = g(mgr, "/inbox", limit=10).json().get("data", [])
    checked = False
    for c in convs:
        nba = g(mgr, f"/inbox/{c['id']}/nba")
        if nba.status_code != 200:
            continue
        stages = [s.get("stage") for s in nba.json()["data"]["suggestions"]
                  if s.get("type") == "advance_stage"]
        if "won" in stages:
            check("Usulan chat tidak menawarkan 'won'", False, str(stages))
            checked = True
            break
    if not checked:
        check("Usulan chat tidak menawarkan 'won'", True)

    print("\n=== H. Playbook WA per tahap (reminder/follow-up/blasting) ===")
    p = g(dmlead, "/wa-playbooks")
    check("GET playbook 200", p.status_code == 200, p.text[:200])
    rows = p.json().get("data", []) if p.status_code == 200 else []
    keys = {x["key"] for x in rows}
    check("5 playbook tersedia (sapaan/follow-up/survey/bayar/promo)",
          {"first_touch", "followup_nurturing", "survey_reminder", "payment_reminder",
           "promo_blast"}.issubset(keys), str(keys))
    check("Semua playbook punya template siap",
          all(x.get("template_ready") for x in rows),
          str([(x["key"], x.get("template_code")) for x in rows if not x.get("template_ready")]))
    r = requests.put(f"{BASE}/wa-playbooks/promo_blast", headers=dmlead,
                     json={"cooldown_days": 7}, timeout=30)
    check("Ubah jeda kirim 200", r.status_code == 200, r.text[:200])
    r = requests.put(f"{BASE}/wa-playbooks/promo_blast", headers=dmlead,
                     json={"cooldown_days": 999}, timeout=30)
    check("Jeda kirim tidak masuk akal DITOLAK", r.status_code == 400, str(r.status_code))
    # Sasaran SEGAR supaya uji tidak terpengaruh jeda kirim dari eksekusi sebelumnya.
    po(sales, "/leads", {"name": "Uji Target Promo", "source": "walk_in",
                         "phone": f"+62815{uuid.uuid4().int % 10**8:08d}"})
    r = po(dmlead, "/wa-playbooks/promo_blast/run", {"send": True, "limit": 10})
    check("Jalankan blasting promo 200", r.status_code == 200, r.text[:250])
    res = r.json().get("data", {}) if r.status_code == 200 else {}
    check("Blasting mengirim pesan (simulasi) & membuat tugas",
          (res.get("sent", 0) + res.get("tasks", 0)) >= 1, str(res))
    check("Hasil blasting ditandai simulasi", res.get("mode") == "simulation", str(res))
    r2 = po(dmlead, "/wa-playbooks/promo_blast/run", {"send": True, "limit": 10})
    res2 = r2.json().get("data", {}) if r2.status_code == 200 else {}
    check("Jeda kirim mencegah spam pada lead yang sama",
          res2.get("sent", 0) < max(res.get("sent", 0), 1), f"{res} -> {res2}")
    r = po(sales, "/wa-playbooks/promo_blast/run", {"send": True})
    check("Staf sales tidak boleh menjalankan blasting", r.status_code == 403, str(r.status_code))
    return finish()


def finish():
    print("\n" + "=" * 62)
    print(f"HASIL: {len(PASS)} PASS / {len(FAIL)} FAIL")
    for f in FAIL:
        print(f"  - GAGAL: {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
