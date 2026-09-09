#!/usr/bin/env python3
"""verify_wa_reminders.py — GATE 42 (Fase 51B).

Pengingat otomatis adalah fitur yang paling mudah membusuk tanpa terlihat: ia berjalan di
latar belakang, dan satu-satunya cara mengetahui ia rusak adalah pelanggan berhenti
diingatkan (atau justru diingatkan berkali-kali). Gate ini menjaga enam janjinya:

  W1  setelan dibaca dari Pusat Konfigurasi (bukan angka mati di kode) dan tautan
      "Ubah di Pusat Konfigurasi" di layar BUKAN jalan buntu — grup `pengingat` benar ada.
  W2  kandidat DIHITUNG dari data nyata: garansi hampir habis, termin jatuh tempo, dan
      tunggakan lahir dari BAST & jadwal tagihan, bukan dari daftar penerima yang diketik.
  W3  mengubah ambang MENGUBAH kandidat (buktinya ambang benar-benar dipakai).
  W4  RBAC: melihat boleh untuk peran yang berhubungan dengan pembeli; MENJALANKAN hanya
      peran pengelola — karena menjalankan berarti mengirim pesan sungguhan.
  W5  satu periode satu pengingat: dijalankan dua kali TIDAK mengirim dua kali, dan jalan
      kedua mengaku "dilewati", bukan "terkirim".
  W6  jujur soal mode kirim: tanpa kredensial WhatsApp statusnya `simulasi` + sebabnya
      ditulis; TIDAK PERNAH mengaku `terkirim`.
  W7  penerima tanpa nomor tetap ditampilkan sebagai kandidat beserta sebabnya, dan saat
      dijalankan dicatat `dilewati` dengan `reason_code` — bukan dihitung berhasil.
  W8  yang sudah beres tidak diingatkan lagi (termin lunas, garansi habis).
  W9  riwayat bisa dibaca ulang untuk audit: siapa menjalankan, template apa, isi pesannya.
  W10 keunikan penanda dedup dijaga INDEKS UNIK di database (bukan hanya pemeriksaan
      aplikasi) — dan indeksnya BERGIGI: sisipan kembar langsung ke database ditolak.
  W11 permukaan layar: tab Pengingat Otomatis benar-benar dirender, memakai kamus
      `reminder_kind`/`reminder_status`, dan tidak ada testId 51B yang mati.

Bahan uji dibuat sendiri (`gate51`) lalu dibuang; slot dedup milik data DEMO dipulihkan
(`_fixture51.purge`) supaya manusia tetap punya bahan uji di layar.

Jalankan: python3 scripts/verify_wa_reminders.py
"""
import json
import pathlib
import re
import sys

from pymongo.errors import DuplicateKeyError

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _fixture51 as fx  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
FE = ROOT / "frontend" / "src"
FAIL = []
PASSED = 0


def check(ok: bool, label: str, detail: str = "") -> bool:
    global PASSED
    if ok:
        PASSED += 1
        print(f"  OK    {label}")
    else:
        FAIL.append(label)
        print(f"  MERAH {label} — {detail}")
    return bool(ok)


def head(t: str) -> None:
    print(f"\n{t}")


def mine(headers: dict, phone: str = None) -> list:
    """Kandidat milik pembeli uji saja — gate tidak menilai data demo milik manusia."""
    r = fx.api("GET", "/reminders/candidates", headers)
    r.raise_for_status()
    rows = r.json().get("data") or []
    want = phone or fx.PHONE
    return [c for c in rows if c.get("phone") == want or c.get("unit_code") == fx.UNIT_CODE]


def run(headers: dict, **body):
    return fx.api("POST", "/reminders/run", headers, json=body or {})


def audit_behaviour(world: dict) -> None:
    owner = fx.login("owner@sipro.co.id")
    finlead = fx.login("finlead@sipro.co.id")
    sales = fx.login("sales@sipro.co.id")
    pm = fx.login("pm@sipro.co.id")

    head("W1 setelan dari Pusat Konfigurasi & mode kirim yang jujur")
    r = fx.api("GET", "/reminders/settings", finlead)
    check(r.ok, "W1a setelan pengingat bisa dibaca", f"{r.status_code} {r.text[:120]}")
    cfg = (r.json().get("data") or {}) if r.ok else {}
    for k in ("warranty_days", "installment_days_before", "overdue_every_days", "enabled"):
        check(k in cfg, f"W1b setelan memuat '{k}'", json.dumps(cfg)[:160])
    check(cfg.get("mode") in ("simulasi", "nyata") and cfg.get("mode_detail"),
          "W1c mode kirim disebut apa adanya beserta sebabnya", json.dumps(cfg)[:200])
    keys = set(cfg.get("setting_keys") or [])
    check({"reminder.warranty_days", "reminder.installment_days_before",
           "reminder.overdue_every_days"} <= keys,
          "W1d ambang batas menunjuk key Pusat Konfigurasi (bukan angka mati)", str(keys))
    r = fx.api("GET", "/settings", owner, params={"group": "pengingat"})
    grup = {row.get("key") for row in ((r.json().get("data") or []) if r.ok else [])}
    check({"reminder.warranty_days", "reminder.installment_days_before"} <= grup,
          "W1e tautan layar ke Pusat Konfigurasi grup 'pengingat' BUKAN jalan buntu",
          str(sorted(grup))[:200])

    head("W2 kandidat dihitung dari data nyata")
    rows = mine(finlead)
    kinds = {c["kind"] for c in rows}
    check("warranty_expiring" in kinds,
          "W2a garansi hampir habis lahir dari BAST + masa garansi per bagian", str(kinds))
    check("installment_due" in kinds,
          "W2b termin jatuh tempo lahir dari jadwal tagihan nyata", str(kinds))
    check("installment_overdue" in kinds,
          "W2c tunggakan lahir dari termin yang lewat jatuh tempo", str(kinds))
    check(all(c.get("reason") and c.get("dedup_key") and c.get("due_date") for c in rows),
          "W2d setiap kandidat menyebut alasan, tanggal, dan penanda dedup yang bisa diperiksa",
          json.dumps(rows[:1], ensure_ascii=False)[:220])
    check(all(c.get("recipient_type") in ("customer", "lead") for c in rows),
          "W2e jenis penerima ditulis benar (pelanggan vs calon pembeli)",
          str({c.get("recipient_type") for c in rows}))
    # W2f ditambahkan setelah uji-mutasi M33 LOLOS: gate lama hanya menguji tagihan yang
    # SELURUHNYA lunas (`status="paid"`), sehingga penyaring per-TERMIN tidak pernah teruji.
    # Padahal keadaan yang sering terjadi justru di tengah: tagihan masih berjalan, tetapi DP
    # sudah dibayar penuh 40 hari lalu. Tanpa penyaring itu, DP tersebut lahir sebagai
    # kandidat tunggakan bernominal Rp 0 — pembeli ditagih untuk yang sudah ia bayar, dan
    # itu jenis pesan yang menghancurkan kepercayaan paling cepat.
    lunas = [it for it in (world["buyer"]["invoice"]["items"] or [])
             if int(it.get("paid") or 0) >= int(it.get("amount") or 0)]
    tgl_lunas = {str(it.get("due_date"))[:10] for it in lunas}
    bocor = [c for c in rows if str(c.get("kind") or "").startswith("installment")
             and (str(c.get("due_date")) in tgl_lunas or int(c.get("amount") or 0) <= 0)]
    check(bool(lunas) and not bocor,
          "W2f termin yang SUDAH LUNAS di tagihan berjalan tidak jadi kandidat "
          "(tidak ada pengingat Rp 0)",
          json.dumps(bocor[:1], ensure_ascii=False)[:200])

    head("W3 ambang batas benar-benar dipakai")
    r = fx.api("PUT", "/settings/reminder.installment_days_before", owner,
               json={"value": 1, "reason": "Gate 42: uji ambang H-1."})
    check(r.ok, "W3a ambang termin bisa diubah dari Pusat Konfigurasi", r.text[:140])
    rows2 = mine(finlead)
    check(not any(c["kind"] == "installment_due" for c in rows2),
          "W3b ambang lebih ketat MENGHILANGKAN kandidat termin (angka benar-benar dipakai)",
          str([c["kind"] for c in rows2]))
    fx.api("PUT", "/settings/reminder.installment_days_before", owner,
           json={"value": 3, "reason": "Gate 42: kembalikan bawaan."})
    check(any(c["kind"] == "installment_due" for c in mine(finlead)),
          "W3c ambang dikembalikan → kandidat termin muncul lagi (tidak ada sisa setelan)")

    head("W4 RBAC menjalankan pengingat")
    r = run(sales)
    check(r.status_code == 403, "W4a sales boleh melihat tetapi TIDAK boleh menjalankan (403)",
          f"got {r.status_code}")
    r = run(pm)
    check(r.status_code == 403, "W4b PM juga tidak boleh menjalankan (403)",
          f"got {r.status_code}")
    r = fx.api("GET", "/reminders", sales)
    check(r.ok, "W4c sales tetap boleh MEMBACA riwayat (pertanyaan kerja harian)",
          f"{r.status_code} {r.text[:120]}")

    head("W5..W6 dedup per periode & kejujuran status")
    if cfg.get("mode") == "nyata":
        check(False, "W5 mode kirim NYATA: gate menolak menjalankan pengingat",
              "kosongkan WHATSAPP_TOKEN/WHATSAPP_PHONE_ID di lingkungan uji")
        return
    r1 = run(finlead)
    check(r1.ok, "W5a Manajer Keuangan boleh menjalankan pengingat", r1.text[:140])
    out1 = (r1.json().get("data") or {}) if r1.ok else {}
    n1 = fx.db.wa_reminders.count_documents({"phone": fx.PHONE})
    check(n1 >= 3, "W5b pengingat untuk pembeli uji benar-benar tercatat",
          f"{n1} baris | {json.dumps(out1, ensure_ascii=False)[:170]}")
    r2 = run(finlead)
    out2 = (r2.json().get("data") or {}) if r2.ok else {}
    n2 = fx.db.wa_reminders.count_documents({"phone": fx.PHONE})
    check(n1 == n2, "W5c dijalankan dua kali TIDAK mengirim dua kali", f"{n1} -> {n2}")
    check(int(out2.get("sent", 0)) == 0 and int(out2.get("skipped", 0)) >= 1,
          "W5d jalan kedua mengaku 'dilewati', bukan 'terkirim'",
          json.dumps(out2, ensure_ascii=False)[:170])
    baris = list(fx.db.wa_reminders.find({"phone": fx.PHONE}, {"_id": 0}))
    status = {b.get("status") for b in baris}
    check("terkirim" not in status,
          "W6a tanpa kredensial WhatsApp TIDAK ADA yang mengaku 'terkirim'", str(status))
    check(all("simulasi" in (b.get("detail") or "").lower()
              or b.get("status") != "simulasi" for b in baris),
          "W6b baris simulasi menjelaskan SEBAB pesannya tidak pergi",
          json.dumps([b.get("detail") for b in baris[:1]], ensure_ascii=False)[:180])
    check(int(out1.get("sent", 0)) == 0 and int(out1.get("simulated", 0)) >= 1,
          "W6c ringkasan jalan pertama memisahkan 'simulasi' dari 'terkirim'",
          json.dumps(out1, ensure_ascii=False)[:170])

    head("W9 riwayat bisa diaudit")
    r = fx.api("GET", "/reminders", finlead, params={"limit": 100})
    hist = (r.json() if r.ok else {})
    ours = [h for h in (hist.get("data") or []) if h.get("phone") == fx.PHONE]
    check(ours, "W9a riwayat pengingat bisa dibaca dari API", r.text[:140])
    check(all(h.get("template_code") for h in ours),
          "W9b riwayat menyebut template yang dipakai (kalimat bukan karangan kode)",
          str({h.get("template_code") for h in ours}))
    check(all(h.get("body") and h.get("reason") for h in ours),
          "W9c riwayat menyimpan ISI pesan + alasan pengingat")
    check(all(h.get("run_by") for h in ours),
          "W9d riwayat menyebut siapa yang menjalankan",
          str({h.get("run_by") for h in ours}))
    check(isinstance(hist.get("by_status"), dict) and hist["by_status"],
          "W9e ringkasan per status ikut dikirim (layar tidak menghitung sendiri)",
          json.dumps(hist.get("by_status"))[:120])

    head("W7 penerima tanpa nomor: dilewati beralasan, bukan dianggap berhasil")
    fx.db.customers.update_one({fx.TAG: True}, {"$set": {"phone": None}})
    fx.db.leads.update_one({fx.TAG: True}, {"$set": {"phone": None}})
    fx.db.wa_reminders.delete_many({"phone": fx.PHONE})
    tanpa = [c for c in (fx.api("GET", "/reminders/candidates", finlead).json().get("data")
                         or []) if c.get("unit_code") == fx.UNIT_CODE]
    check(tanpa and all((c.get("blocked_code") == "no_phone") for c in tanpa),
          "W7a kandidat tanpa nomor TETAP ditampilkan dengan sebabnya",
          json.dumps(tanpa[:1], ensure_ascii=False)[:200])
    run(finlead)
    lewat = fx.db.wa_reminders.count_documents({"status": "dilewati",
                                                "reason_code": "no_phone",
                                                "unit_code": fx.UNIT_CODE})
    check(lewat >= 1, "W7b dijalankan: dicatat 'dilewati' dengan sebab 'tidak ada nomor'",
          f"{lewat} baris")
    fx.db.customers.update_one({fx.TAG: True}, {"$set": {"phone": fx.PHONE}})
    fx.db.leads.update_one({fx.TAG: True}, {"$set": {"phone": fx.PHONE}})

    head("W8 yang sudah beres tidak diingatkan lagi")
    inv = fx.db.ar_invoices.find_one({fx.TAG: True}, {"_id": 0})
    fx.db.ar_invoices.update_one({"id": inv["id"]}, {"$set": {
        "status": "paid", "paid": inv["total"], "outstanding": 0,
        "items": [{**it, "paid": it["amount"], "status": "paid"} for it in inv["items"]]}})
    sisa = [c for c in (fx.api("GET", "/reminders/candidates", finlead).json().get("data")
                        or []) if c.get("entity_id") == inv["id"]]
    check(not sisa, "W8a tagihan lunas tidak lagi jadi kandidat",
          json.dumps(sisa[:1], ensure_ascii=False)[:160])
    ho = fx.db.unit_handovers.find_one({fx.TAG: True}, {"_id": 0, "id": 1, "warranties": 1})
    fx.db.unit_handovers.update_one({"id": ho["id"]}, {"$set": {"warranties": [
        {**w, "expires_at": fx.day(-5)} for w in (ho.get("warranties") or [])]}})
    sisa = [c for c in (fx.api("GET", "/reminders/candidates", finlead).json().get("data")
                        or []) if c.get("entity_id") == ho["id"]]
    check(not sisa, "W8b garansi yang SUDAH habis tidak diingatkan (masanya sudah lewat)",
          json.dumps(sisa[:1], ensure_ascii=False)[:160])

    head("W10 keunikan penanda dijaga DATABASE")
    info = fx.db.wa_reminders.index_information()
    dijaga = [n for n, spec in info.items()
              if spec.get("unique")
              and [k for k, _ in spec.get("key", [])] == ["org_id", "dedup_key"]]
    check(bool(dijaga), "W10a index unik (org_id, dedup_key) ada di database",
          str(sorted(info)))
    kembar = {"org_id": fx.ORG, "dedup_key": "gate42:kembar", "kind": "installment_due",
              "status": "simulasi"}
    fx.db.wa_reminders.delete_many({"dedup_key": kembar["dedup_key"]})
    bergigi = False
    try:
        fx.db.wa_reminders.insert_one(dict(kembar))
        fx.db.wa_reminders.insert_one(dict(kembar))
    except DuplicateKeyError:
        bergigi = True
    finally:
        fx.db.wa_reminders.delete_many({"dedup_key": kembar["dedup_key"]})
    check(bergigi, "W10b database MENOLAK penanda dedup kembar (bukan hanya aplikasi)",
          "sisipan kedua lolos — dedup bergantung pada aplikasi saja")


def audit_surface() -> None:
    head("W11 permukaan layar Fase 51B")
    panel = (FE / "components" / "omni" / "RemindersPanel.js").read_text(encoding="utf-8")
    page = (FE / "pages" / "OmnichannelPage.js").read_text(encoding="utf-8")
    check("RemindersPanel" in page and "reminders" in page,
          "W11a tab Pengingat Otomatis terpasang di halaman Automasi & Channel")
    check("P51.remindersTab" in page or "t.tid" in page,
          "W11b tab pengingat punya testId")
    check('params.get("tab")' in page,
          "W11c tab bisa ditautkan & bertahan saat muat ulang (?tab=)",
          "tanpa ini tautan 'buka pengingat' selalu mendarat di tab lain")
    check('can(t.res' in page or "can(t.res, t.act" in page,
          "W11d tab tanpa izin tidak dirender (halaman tidak tampak rusak bagi peran lain)")
    for needle, label in (("T.remindersMode", "banner mode kirim"),
                          ("T.remindersSettings", "kartu ambang batas"),
                          ("T.remindersRunBtn", "tombol jalankan sekarang"),
                          ("T.remindersRunDenied", "kalimat penjelas bagi peran tanpa izin"),
                          ("T.remindersCandidateRow", "baris kandidat"),
                          ("T.remindersCandidateBlocked", "sebab kandidat tertahan"),
                          ("T.remindersHistoryRow", "baris riwayat"),
                          ("T.remindersHistoryBody", "isi pesan pada riwayat")):
        check(needle in panel, f"W11e {label} punya testId", needle)
    check('group="reminder_kind"' in panel and 'group="reminder_status"' in panel,
          "W11f label jenis & status dibaca dari Kamus Data, bukan diketik di layar")
    check("simulasi" in panel.lower(),
          "W11g layar menyebut mode simulasi apa adanya")
    src = (FE / "constants" / "testIds" / "p51.js").read_text(encoding="utf-8")
    keys = re.findall(r"^\s{2}(reminders\w+):", src, flags=re.M)
    all_fe = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                       for p in FE.rglob("*.js") if "components/ui/" not in p.as_posix())
    mati = [k for k in keys if f"T.{k}" not in all_fe and f"P51.{k}" not in all_fe]
    check(not mati, "W11h tidak ada testId pengingat Fase 51B yang MATI", str(mati))


def main() -> int:
    print("=" * 78)
    print("GATE 42 — PENGINGAT WHATSAPP OTOMATIS: DIHITUNG, TIDAK DOBEL, JUJUR (Fase 51B)")
    print("=" * 78)
    world = fx.make(with_active_claim=False)
    try:
        audit_behaviour(world)
        audit_surface()
    finally:
        buang = fx.purge()
        print(f"\n  info  bahan uji dibuang: {json.dumps(buang, ensure_ascii=False)}")
        sisa = {k: v for k, v in fx.orphans().items() if v}
        check(not sisa, "bahan uji gate dibuang bersih (termasuk slot dedup demo)",
              json.dumps(sisa, ensure_ascii=False))
    print("-" * 78)
    if FAIL:
        print(f"GATE 42 MERAH — {len(FAIL)} pemeriksaan gagal:")
        for f in FAIL:
            print(f"   - {f}")
        return 1
    print(f"GATE 42 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
