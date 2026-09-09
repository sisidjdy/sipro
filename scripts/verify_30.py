#!/usr/bin/env python3
"""POC/verifikasi Fase 30 — SLIK BERBUKTI + FOTO HEMAT KUOTA + LEAD GAGAL MASUK.

Satu skrip untuk tiga hal yang ditambahkan pada Fase 30, semuanya diuji lewat API NYATA
(bukan unit test terisolasi) supaya cacat tidak bisa mundur:

  30a  Pra-skrining BI/SLIK sebagai GERBANG BERBUKTI:
       * hasil clear/flagged DITOLAK tanpa lampiran iDeb; id berkas fiktif ditolak
       * hasil rejected wajib beralasan, menahan lead, melahirkan tugas SM-12 + usul tutup
       * riwayat pemeriksaan bertambah (hasil lama tidak tertimpa diam-diam)
       * pra-skrining mengalir ke pengajuan KPR TANPA memalsukan hasil resmi bank
  30b  Kompresi + watermark + thumbnail foto:
       * foto besar turun >=60%, sisi maks 1600 px, EXIF/GPS dibuang, watermark tercap
       * `?variant=thumb` melayani berkas jauh lebih kecil; PDF tidak diubah
  30c  Antrean lead gagal masuk (capture.failed):
       * payload cacat TIDAK hilang (202 + antrean), tugas DM-02 + notifikasi supervisor
       * retry dengan koreksi menyelamatkan lead; discard wajib beralasan
       * payload benar tetap masuk normal (tidak ada regresi)

Jalankan: python3 scripts/verify_30.py
"""
import io
import os
import random
import sys
import uuid

import requests

BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PW = "Sipro#2026"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  PASS' if cond else '  FAIL'}  {name}"
          + (f" — {detail}" if detail else ""))
    return bool(cond)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def g(h, p, **params):
    return requests.get(f"{BASE}{p}", headers=h, params=params, timeout=60)


def po(h, p, body=None):
    return requests.post(f"{BASE}{p}", headers=h, json=body or {}, timeout=90)


def upload(h, name, data, ctype, owner_type="lead", owner_id=None, watermark=None,
           optimize=True):
    files = {"file": (name, data, ctype)}
    form = {"owner_type": owner_type, "optimize": str(optimize).lower()}
    if owner_id:
        form["owner_id"] = owner_id
    if watermark:
        form["watermark"] = watermark
    return requests.post(f"{BASE}/files/upload", headers=h, files=files, data=form, timeout=120)


def camera_jpeg(w=2400, h=1600) -> bytes:
    """Foto ala kamera HP (derau + gradien) lengkap dengan EXIF orientation & GPS."""
    from PIL import Image
    img = Image.new("RGB", (w, h))
    px = img.load()
    random.seed(11)
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            col = (int(x * 255 / w), int(y * 255 / h), random.randint(50, 205))
            for dy in range(4):
                for dx in range(4):
                    px[x + dx, y + dy] = col
    exif = img.getexif()
    exif[274] = 1
    exif[271] = "SIPRO-CAM"
    gps = exif.get_ifd(0x8825)
    gps[1] = "S"
    gps[2] = (6.0, 12.0, 15.0)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95, exif=exif.tobytes())
    return buf.getvalue()


# ============================== 30a — SLIK berbukti ==============================
def part_slik(sales, mgr):
    print("\n=== 30a. Pra-skrining BI/SLIK sebagai gerbang BERBUKTI ===")
    phone = f"+62813{uuid.uuid4().int % 10**8:08d}"
    r = po(sales, "/leads", {"name": "Uji SLIK Fase 30", "phone": phone, "source": "walk_in"})
    check("Buat lead 200", r.status_code == 200, r.text[:150])
    lid = r.json()["data"]["id"]

    life = g(sales, f"/leads/{lid}/lifecycle").json()["data"]
    keys = [q["key"] for q in life["requirements"]["booking"]]
    check("Syarat booking memuat gerbang 'slik'", "slik" in keys, str(keys))
    check("Gerbang slik belum terpenuhi",
          [q for q in life["requirements"]["booking"] if q["key"] == "slik"][0]["met"] is False)
    check("Opsi hasil tanpa 'pending'",
          [o["value"] for o in life["slik_options"]] == ["clear", "flagged", "rejected"],
          str([o["value"] for o in life["slik_options"]]))
    check("Mode ditandai simulasi", life.get("slik_mode") == "simulation", str(life.get("slik_mode")))

    r = po(sales, f"/leads/{lid}/slik-prescreen", {"status": "ngawur"})
    check("Hasil tidak dikenal ditolak", r.status_code == 400, r.text[:120])
    r = po(sales, f"/leads/{lid}/slik-prescreen", {"status": "clear"})
    check("clear TANPA bukti ditolak", r.status_code == 400 and "bukti" in r.text.lower(),
          r.text[:140])
    r = po(sales, f"/leads/{lid}/slik-prescreen",
           {"status": "clear", "evidence_file_ids": ["berkas-fiktif-123"]})
    check("Bukti dengan id fiktif ditolak", r.status_code == 400, r.text[:140])
    r = po(sales, f"/leads/{lid}/slik-prescreen", {"status": "rejected"})
    check("rejected tanpa alasan ditolak", r.status_code == 400, r.text[:140])

    ev = upload(sales, "ideb.pdf", b"%PDF-1.4 iDeb SLIK simulasi\n", "application/pdf",
                owner_type="lead", owner_id=lid, optimize=False)
    check("Unggah bukti iDeb (PDF) 200", ev.status_code == 200, ev.text[:150])
    fid = ev.json()["data"]["id"]
    check("Bukti PDF tidak dikompres/di-watermark",
          ev.json()["data"]["optimized"] is False, str(ev.json()["data"]["optimized"]))

    r = po(sales, f"/leads/{lid}/slik-prescreen",
           {"status": "clear", "note": "Kolektibilitas 1", "evidence_file_ids": [fid]})
    check("clear DENGAN bukti tersimpan", r.status_code == 200, r.text[:150])
    body = r.json()
    check("Bukti tercatat pada hasil", body["slik"]["evidence_count"] == 1,
          str(body["slik"]))
    check("Gerbang booking terbuka",
          [q for q in body["requirements"] if q["key"] == "slik"][0]["met"] is True)
    check("Riwayat pemeriksaan = 1", len(body["history"]) == 1, str(len(body["history"])))

    r = po(sales, f"/leads/{lid}/slik-prescreen",
           {"status": "rejected", "note": "Kol-4 di 2 bank"})
    check("rejected + alasan tersimpan", r.status_code == 200, r.text[:150])
    body = r.json()
    check("Riwayat bertambah jadi 2 (hasil lama tidak hilang)", len(body["history"]) == 2,
          str(len(body["history"])))
    check("Gerbang booking tertutup kembali",
          [q for q in body["requirements"] if q["key"] == "slik"][0]["met"] is False)
    sug = body.get("suggest_close") or {}
    check("Ada usul tutup lead beralasan SSOT",
          sug.get("stage") == "lost" and sug.get("reason") == "financing", str(sug))
    task = body.get("followup_task") or {}
    check("Tugas tindak lanjut SM-12 lahir untuk pemilik lead",
          bool(task) and task.get("assigned_to") == "sales@sipro.co.id", str(task)[:150])

    r = po(sales, f"/leads/{lid}/first-contact")
    check("Catat kontak pertama (naik ke nurturing)", r.status_code == 200, r.text[:120])
    check("Tahap jadi nurturing", (r.json()["data"] or {}).get("stage") == "nurturing",
          str((r.json()["data"] or {}).get("stage")))
    r = po(sales, f"/leads/{lid}/stage", {"stage": "booking"})
    check("nurturing→booking DITOLAK karena SLIK ditolak",
          r.status_code == 400 and "SLIK" in r.text, r.text[:170])

    # Hasil yang tidak menahan menutup tugas tindak lanjut (bukan menggantung selamanya).
    ev2 = upload(sales, "ideb2.png", b"\x89PNG\r\n\x1a\n" + b"0" * 50, "image/png",
                 owner_type="lead", owner_id=lid)
    fid2 = ev2.json()["data"]["id"] if ev2.status_code == 200 else fid
    r = po(sales, f"/leads/{lid}/slik-prescreen",
           {"status": "flagged", "note": "Skema tunai bertahap disetujui",
            "evidence_file_ids": [fid2]})
    check("Pemeriksaan ulang (flagged) tersimpan", r.status_code == 200, r.text[:150])
    check("Tugas tindak lanjut ditutup otomatis",
          (r.json().get("closed_followups") or 0) >= 1, str(r.json().get("closed_followups")))
    check("Riwayat = 3", len(r.json()["history"]) == 3, str(len(r.json()["history"])))

    life = g(sales, f"/leads/{lid}/lifecycle").json()["data"]
    check("Lifecycle mengembalikan riwayat SLIK", len(life.get("slik_history") or []) == 3)
    check("Lifecycle menandai hasil meloloskan", life["slik"]["passing"] is True)

    # Pra-skrining mengalir ke pengajuan KPR tanpa memalsukan hasil resmi bank.
    units = g(mgr, "/units", status="available").json().get("data") or []
    if not units:
        check("Ada unit tersedia untuk uji KPR", False, "tidak ada unit available")
        return
    r = po(mgr, "/deals/reserve", {"lead_id": lid, "unit_id": units[0]["id"],
                                   "booking_fee": 5000000})
    check("Buat reservasi untuk lead 200", r.status_code == 200, r.text[:150])
    deal_id = r.json()["data"]["id"]
    fin = po(mgr, "/financing", {"deal_id": deal_id, "bank_name": "BTN", "plafon": 400000000,
                                 "dp_amount": 40000000, "tenor_months": 180,
                                 "interest_rate_pct": 8.5})
    check("Buat pengajuan KPR 200", fin.status_code == 200, fin.text[:170])
    fb = fin.json()
    pre = fb.get("prescreen") or {}
    check("Pengajuan KPR mewarisi pra-skrining lead", pre.get("status") == "flagged", str(pre)[:140])
    check("Bukti pra-skrining ikut menempel", len(pre.get("evidence") or []) >= 1)
    check("Status SLIK RESMI tetap 'pending' (tidak dipalsukan)",
          fb["data"]["slik_status"] == "pending", fb["data"]["slik_status"])
    check("Status pengajuan tetap 'submitted' (tidak auto-approve)",
          fb["data"]["status"] == "submitted", fb["data"]["status"])
    check("Catatan KPR menyebut simulasi & menunggu bank",
          "SIMULASI" in (fb["data"]["slik_note"] or "")
          and "RESMI" in (fb["data"]["slik_note"] or ""), str(fb["data"]["slik_note"])[:140])
    check("Ada peringatan karena pra-skrining belum 'clear'",
          bool(fb.get("prescreen_warning")), str(fb.get("prescreen_warning"))[:100])


# ====================== 30b — kompresi + watermark + thumbnail ======================
def part_photo(site):
    print("\n=== 30b. Kompresi + watermark + thumbnail foto lapangan ===")
    raw = camera_jpeg()
    r = upload(site, "progres.jpg", raw, "image/jpeg", owner_type="site_diary",
               watermark="Cluster Asri Blok A · Kavling A-01")
    check("Unggah foto 200", r.status_code == 200, r.text[:150])
    rec = r.json()["data"]
    check("Ditandai teroptimasi", rec["optimized"] is True)
    check("Hemat ukuran >= 60%", (rec["saving_pct"] or 0) >= 60,
          f'{round(rec["original_size"] / 1024)}KB -> {round(rec["size"] / 1024)}KB '
          f'({rec["saving_pct"]}%)')
    check("Sisi terpanjang <= 1600 px", max(rec["width"], rec["height"]) <= 1600,
          f'{rec["width"]}x{rec["height"]}')
    check("Watermark memuat konteks + organisasi + WIB",
          "A-01" in (rec["watermark"] or "") and "WIB" in (rec["watermark"] or "")
          and "SIPRO" in (rec["watermark"] or ""), str(rec["watermark"]))
    check("Thumbnail dibuat", bool(rec.get("thumb_path")) and (rec.get("thumb_size") or 0) > 0,
          f'{round((rec.get("thumb_size") or 0) / 1024)}KB')
    fid = rec["id"]

    token = site["Authorization"].split(" ", 1)[1]
    full = requests.get(f"{BASE}/files/{fid}", params={"auth": token}, timeout=60)
    th = requests.get(f"{BASE}/files/{fid}", params={"auth": token, "variant": "thumb"},
                      timeout=60)
    check("Unduh foto penuh 200", full.status_code == 200, str(full.status_code))
    check("Unduh thumbnail 200", th.status_code == 200, str(th.status_code))
    check("Thumbnail jauh lebih kecil dari foto penuh",
          len(th.content) * 3 < len(full.content),
          f"{len(th.content)}B vs {len(full.content)}B")
    check("Respons foto boleh di-cache browser",
          "max-age" in (full.headers.get("Cache-Control") or ""),
          str(full.headers.get("Cache-Control")))
    from PIL import Image
    out = Image.open(io.BytesIO(full.content))
    check("Metadata EXIF/GPS dibuang", not dict(out.getexif()),
          str(list(dict(out.getexif()).keys())))
    thumb_img = Image.open(io.BytesIO(th.content))
    check("Thumbnail <= 480 px", max(thumb_img.size) <= 480, str(thumb_img.size))
    px = out.convert("RGB").load()
    bar = sum(sum(px[x, out.height - 12]) / 3 for x in range(0, out.width, 60))
    mid = sum(sum(px[x, out.height // 2]) / 3 for x in range(0, out.width, 60))
    n = len(range(0, out.width, 60))
    check("Bilah watermark benar-benar tercetak", (mid / n) - (bar / n) > 20,
          f"tengah={mid / n:.0f} bilah={bar / n:.0f}")

    r = upload(site, "kontrak.pdf", b"%PDF-1.4 dokumen\n", "application/pdf",
               owner_type="generic")
    check("PDF tidak diubah (bukan gambar)", r.json()["data"]["optimized"] is False)
    r = upload(site, "asli.jpg", raw, "image/jpeg", owner_type="generic", optimize=False)
    check("optimize=false menyimpan berkas apa adanya",
          r.json()["data"]["optimized"] is False
          and r.json()["data"]["size"] == len(raw), str(r.json()["data"]["size"]))
    r = upload(site, "rusak.jpg", b"ini-bukan-gambar-sama-sekali", "image/jpeg",
               owner_type="generic")
    check("Berkas gambar rusak tetap tersimpan (unggahan tidak gagal)",
          r.status_code == 200 and r.json()["data"]["optimized"] is False, r.text[:120])


# ====================== 30c — antrean lead gagal masuk ======================
def part_capture(dmlead):
    print("\n=== 30c. Antrean lead gagal masuk (capture.failed) ===")
    tag = uuid.uuid4().hex[:6]
    r = requests.post(f"{BASE}/webhooks/meta-lead", timeout=60,
                      json={"name": f"Tanpa Nomor {tag}", "campaign": "Promo Agustus"})
    check("Payload tanpa nomor -> 202 (bukan 422 lalu hilang)", r.status_code == 202,
          str(r.status_code))
    d = r.json()["data"]
    check("Ditandai tidak tertangkap + ada id antrean",
          d["captured"] is False and bool(d["failure_id"]), str(d)[:120])
    fid_missing = d["failure_id"]

    r = requests.post(f"{BASE}/webhooks/web", timeout=60,
                      data='{"name":"rusak", "phone":',
                      headers={"Content-Type": "application/json"})
    check("JSON rusak masuk antrean (202)", r.status_code == 202, str(r.status_code))
    check("Alasan menyebut JSON tidak valid",
          "JSON" in r.json()["data"]["reason"], r.json()["data"]["reason"][:80])

    r = requests.post(f"{BASE}/webhooks/tiktok-lead", timeout=60,
                      json={"name": "Nomor Pendek", "phone": "0812"})
    check("Nomor terlalu pendek masuk antrean",
          r.status_code == 202 and "pendek" in r.json()["data"]["reason"].lower(),
          r.json()["data"]["reason"][:80])

    phone_ok = f"+62815{uuid.uuid4().int % 10**8:08d}"
    r = requests.post(f"{BASE}/webhooks/google-lead", timeout=60,
                      json={"name": f"Lead Bersih {tag}", "phone": phone_ok,
                            "campaign": "Google Search"})
    check("Payload benar tetap masuk normal (tanpa regresi)",
          r.status_code == 200 and r.json()["data"]["captured"] is True, r.text[:120])

    lst = g(dmlead, "/capture/failures", status="open", limit=50)
    check("GET /capture/failures 200 (supervisor DM)", lst.status_code == 200, lst.text[:120])
    body = lst.json()
    check("Antrean memuat kegagalan tadi", body["total"] >= 3, str(body["total"]))
    check("Ringkasan memuat hitungan per provider",
          bool(body["summary"]["by_provider"]), str(body["summary"])[:120])
    check("Semua kegagalan data ditandai perlu koreksi",
          body["summary"]["needs_fix"] >= 3, str(body["summary"]["needs_fix"]))

    tasks = g(dmlead, "/work/tasks", scope="division", limit=100).json().get("data") or []
    dm02 = [t for t in tasks if t.get("jobdesk_code") == "DM-02"]
    check("Tugas DM-02 lahir dari event capture.failed", len(dm02) >= 1, str(len(dm02)))
    check("Tugas DM-02 punya pemilik (staf divisi digital marketing)",
          bool(dm02 and dm02[0].get("assigned_to")), str(dm02[:1])[:120])

    notif = g(dmlead, "/notifications", limit=20).json().get("data") or []
    check("Supervisor DM diberi notifikasi",
          any("gagal masuk" in (n.get("title") or "").lower() for n in notif),
          str([n.get("title") for n in notif[:3]]))

    r = po(dmlead, f"/capture/failures/{fid_missing}/retry", {"fixes": {}})
    check("Retry tanpa koreksi ditolak dengan alasan jelas",
          r.status_code == 400 and "nomor" in r.text.lower(), r.text[:130])
    fixed = f"+62816{uuid.uuid4().int % 10**8:08d}"
    r = po(dmlead, f"/capture/failures/{fid_missing}/retry",
           {"fixes": {"phone": fixed, "name": f"Bu Rina {tag}"}})
    check("Retry dengan koreksi menyelamatkan lead", r.status_code == 200, r.text[:150])
    rb = r.json()
    check("Lead nyata terbentuk", bool(rb.get("lead_id")), str(rb)[:100])
    check("Antrean jadi 'resolved' + jejak pengoreksi",
          rb["data"]["status"] == "resolved" and rb["data"]["resolved_by"] == "dmlead@sipro.co.id",
          str(rb["data"]["status"]))
    lead = g(dmlead, f"/leads/{rb['lead_id']}")
    check("Lead hasil penyelamatan bisa dibuka & bernomor benar",
          lead.status_code == 200 and lead.json()["data"]["phone"] == fixed,
          lead.text[:120])
    check("Campaign iklan asli tidak hilang saat diselamatkan",
          lead.json()["data"].get("campaign") == "Promo Agustus",
          str(lead.json()["data"].get("campaign")))

    tasks2 = g(dmlead, "/work/tasks", scope="division", status="done",
               limit=100).json().get("data") or []
    closed = [t for t in tasks2 if t.get("jobdesk_code") == "DM-02"
              and t.get("related_entity_id") == fid_missing and t.get("status") == "done"]
    check("Tugas DM-02 untuk antrean itu ikut tertutup", len(closed) >= 1, str(len(closed)))
    check("Hasil tugas menyebut lead yang diselamatkan",
          bool(closed) and "diselamatkan" in (closed[0].get("outcome") or ""),
          str(closed[:1])[:120])
    r = po(dmlead, f"/capture/failures/{fid_missing}/retry", {"fixes": {}})
    check("Retry ulang antrean yang sudah selesai ditolak", r.status_code == 400, r.text[:120])

    opens = [x for x in g(dmlead, "/capture/failures", status="open", limit=50).json()["data"]]
    check("Masih ada antrean terbuka untuk uji discard", len(opens) >= 1, str(len(opens)))
    fid2 = opens[0]["id"]
    r = po(dmlead, f"/capture/failures/{fid2}/discard", {"reason": "x"})
    check("Discard dengan alasan terlalu pendek ditolak", r.status_code in (400, 422),
          str(r.status_code))
    r = po(dmlead, f"/capture/failures/{fid2}/discard",
           {"reason": "Payload uji coba tim iklan"})
    check("Discard beralasan tersimpan",
          r.status_code == 200 and r.json()["data"]["status"] == "discarded", r.text[:130])
    check("Alasan discard tersimpan untuk audit",
          "uji coba" in (r.json()["data"].get("discard_reason") or ""),
          str(r.json()["data"].get("discard_reason")))
    r = po(dmlead, f"/capture/failures/{fid2}/retry", {"fixes": {"phone": "081999888777"}})
    check("Antrean yang sudah dibuang tidak bisa diulang", r.status_code == 400, r.text[:120])

    sales = login("sales@sipro.co.id")
    r = g(sales, "/capture/failures")
    check("Sales biasa TIDAK boleh membuka antrean lintas lead (RBAC)",
          r.status_code == 403, str(r.status_code))


def main():
    sales = login("sales@sipro.co.id")
    mgr = login("manager@sipro.co.id")
    site = login("site@sipro.co.id")
    dmlead = login("dmlead@sipro.co.id")

    part_slik(sales, mgr)
    part_photo(site)
    part_capture(dmlead)

    print(f"\n=== HASIL FASE 30: {len(PASS)} PASS, {len(FAIL)} FAIL ===")
    if FAIL:
        for f in FAIL:
            print(f"  - GAGAL: {f}")
        sys.exit(1)
    print("SEMUA VERIFIKASI FASE 30 LULUS")


if __name__ == "__main__":
    main()
