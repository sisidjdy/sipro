#!/usr/bin/env python3
"""POC/verifikasi Fase 28c — Bukti kerja BERPASANGAN (sebelum → sesudah).

Menjaga agar fitur tidak bisa mundur:
  A. Foto bukti perbaikan (`fix_photos`) + catatan (`fix_note`) benar-benar tersimpan.
  B. `GET /site-plan/{pid}/unit/{uid}` mengembalikan `construction.repairs` berpasangan
     (before[]/after[]) dengan urutan: yang sudah beres di ATAS.
  C. Setiap foto pada pasangan bisa DIUNDUH (bukan gambar rusak) lewat /api/files/{id}.
  D. Privasi portal: elemen `repairs` pada /portal/progress hanya berisi kunci yang aman.
  E. Kejujuran status: `resolved` hanya true bila temuan ditutup DAN ada foto sesudah.

Jalankan: python3 scripts/verify_28c.py
"""
import io
import os
import sys

import requests
from PIL import Image, ImageDraw

BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PASSWORD = "Sipro#2026"
BUYER_PHONE = "+628121111111"

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  PASS' if cond else '  FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    return cond


def png_bytes(text, color):
    img = Image.new("RGB", (480, 300), color)
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 469, 289], outline=(255, 255, 255), width=4)
    d.text((30, 140), text, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def upload(token, name, text, color):
    files = {"file": (name, png_bytes(text, color), "image/png")}
    r = requests.post(f"{BASE}/files/upload", files=files,
                      headers={"Authorization": f"Bearer {token}"}, timeout=60)
    r.raise_for_status()
    body = r.json()
    return (body.get("data") or body).get("id") or (body.get("data") or body).get("file_id")


def main():
    print("\n=== A. Persiapan data & simpan bukti perbaikan ===")
    tok = login("pm@sipro.co.id")
    H = {"Authorization": f"Bearer {tok}"}

    punch = requests.get(f"{BASE}/field/punchlist", headers=H, timeout=30).json().get("data", [])
    linked = [p for p in punch if p.get("unit_id")]
    check("Ada temuan punch tertaut kavling (seed)", len(linked) >= 1, f"{len(linked)} temuan")
    if not linked:
        return finish()

    # Pilih temuan yang PALING LENGKAP (punya foto temuan) supaya uji tidak bergantung
    # pada urutan data dan tidak "meracuni" temuan uji kejujuran di bawah.
    linked.sort(key=lambda p: (0 if (p.get("photos") or p.get("photo")) else 1,
                               p.get("created_at") or ""))
    target = linked[0]
    unit_id, project_id = target["unit_id"], target["project_id"]

    # pastikan ada foto SEBELUM
    if not (target.get("photos") or target.get("photo")):
        fid = upload(tok, "temuan.png", "TEMUAN (SEBELUM)", (185, 60, 60))
        requests.put(f"{BASE}/field/punchlist/{target['id']}", headers=H,
                     json={"photos": [fid]}, timeout=30).raise_for_status()
    det = requests.get(f"{BASE}/field/punchlist/{target['id']}", headers=H, timeout=30).json()["data"]
    check("Temuan punya foto SEBELUM", bool(det.get("photos") or det.get("photo")))

    # unggah foto SESUDAH + tutup temuan
    after_id = upload(tok, "PERBAIKAN (SESUDAH)", "PERBAIKAN (SESUDAH)", (34, 139, 94))
    note = "Sudah diaci dan dicat ulang"
    r = requests.post(f"{BASE}/field/punchlist/{target['id']}/status", headers=H,
                      json={"status": "closed", "photos": [after_id], "note": note}, timeout=30)
    check("POST punchlist/{id}/status 200", r.status_code == 200, r.text[:200])
    det = requests.get(f"{BASE}/field/punchlist/{target['id']}", headers=H, timeout=30).json()["data"]
    check("fix_photos tersimpan", after_id in (det.get("fix_photos") or []))
    check("fix_note tersimpan", det.get("fix_note") == note, str(det.get("fix_note")))
    check("status closed", det.get("status") == "closed")

    # E1: temuan lain pada kavling yang sama ditutup TANPA foto sesudah
    honest_id = None
    if True:   # SELALU buat temuan uji baru agar hasil tidak dipengaruhi eksekusi sebelumnya
        r = requests.post(f"{BASE}/field/punchlist", headers=H, json={
            "project_id": project_id, "unit_id": unit_id,
            "title": "Uji kejujuran: ditutup tanpa foto", "severity": "low",
            "location": "Teras", "assigned_to": "site@sipro.co.id",
        }, timeout=30)
        check("Buat temuan uji kejujuran", r.status_code in (200, 201), r.text[:200])
        honest_id = (r.json().get("data") or {}).get("id")
        fid = upload(tok, "temuan2.png", "TEMUAN 2 (SEBELUM)", (150, 90, 40))
        r2 = requests.put(f"{BASE}/field/punchlist/{honest_id}", headers=H,
                          json={"photos": [fid]}, timeout=30)
        check("PUT punchlist menerima TAMBAHAN foto temuan (celah lama ditutup)",
              r2.status_code == 200 and fid in ((r2.json().get("data") or {}).get("photos") or []),
              r2.text[:200])
    requests.post(f"{BASE}/field/punchlist/{honest_id}/status", headers=H,
                  json={"status": "closed", "note": "Ditutup tanpa lampiran foto"}, timeout=30)

    print("\n=== B/C. Payload kavling: pasangan + foto termuat ===")
    u = requests.get(f"{BASE}/site-plan/{project_id}/unit/{unit_id}", headers=H, timeout=30)
    check("GET unit detail 200", u.status_code == 200, u.text[:200])
    c = (u.json().get("data") or {}).get("construction") or {}
    repairs = c.get("repairs") or []
    check("construction.repairs ada isinya", len(repairs) >= 1, f"{len(repairs)}")
    mine = next((r_ for r_ in repairs if r_["punch_id"] == target["id"]), None)
    check("Pasangan untuk temuan target ada", mine is not None)
    if mine:
        check("Pasangan punya before[] & after[]", len(mine["before"]) >= 1 and len(mine["after"]) >= 1,
              f"before={len(mine['before'])} after={len(mine['after'])}")
        check("resolved=True (ditutup + ada foto sesudah)", mine["resolved"] is True)
        check("note ikut terkirim", mine.get("note") == note)
        check("fixed_at terisi", bool(mine.get("fixed_at")))
        for side in ("before", "after"):
            for ph in mine[side]:
                check(f"foto {side} punya file_id/inline", bool(ph.get("file_id") or ph.get("inline")))
                check(f"foto {side} punya label & scope", bool(ph.get("label")) and ph.get("scope") == "unit")
    check("Pasangan yang beres ada di URUTAN ATAS", bool(repairs) and repairs[0]["resolved"] is True,
          f"first resolved={repairs[0]['resolved'] if repairs else None}")
    hon = next((r_ for r_ in repairs if r_["punch_id"] == honest_id), None)
    check("E1: ditutup tanpa foto sesudah → resolved=False", hon is not None and hon["resolved"] is False)
    if hon:
        check("E1: pasangan tetap tampil (tidak disembunyikan)", len(hon["before"]) >= 1 and not hon["after"])

    # foto benar-benar bisa diunduh (bukan gambar rusak)
    ok_img = 0
    for r_ in repairs:
        for ph in (r_["before"] + r_["after"]):
            if ph.get("file_id"):
                g = requests.get(f"{BASE}/files/{ph['file_id']}", headers=H, timeout=60)
                good = g.status_code == 200 and g.headers.get("content-type", "").startswith("image") \
                    and len(g.content) > 200
                if good:
                    ok_img += 1
                else:
                    check(f"unduh foto {ph['file_id'][:8]}", False,
                          f"{g.status_code} {g.headers.get('content-type')}")
    check("Semua foto pasangan bisa diunduh sebagai gambar", ok_img >= 2, f"{ok_img} foto OK")

    print("\n=== E2. Kejujuran: status terbuka tidak boleh 'sudah diperbaiki' ===")
    requests.post(f"{BASE}/field/punchlist/{target['id']}/status", headers=H,
                  json={"status": "in_progress"}, timeout=30)
    c2 = ((requests.get(f"{BASE}/site-plan/{project_id}/unit/{unit_id}", headers=H, timeout=30)
           .json().get("data") or {}).get("construction") or {})
    m2 = next((r_ for r_ in (c2.get("repairs") or []) if r_["punch_id"] == target["id"]), None)
    check("Status 'Dikerjakan' + ada foto sesudah → resolved=False", m2 is not None and m2["resolved"] is False)
    # kembalikan ke closed supaya UI punya contoh yang beres
    requests.post(f"{BASE}/field/punchlist/{target['id']}/status", headers=H,
                  json={"status": "closed"}, timeout=30)

    print("\n=== D. Portal pembeli: pasangan + privasi ===")
    ro = requests.post(f"{BASE}/portal/auth/request-otp",
                       json={"identifier": BUYER_PHONE, "channel": "whatsapp"}, timeout=30)
    check("Portal request-otp 200", ro.status_code == 200, ro.text[:200])
    rv = requests.post(f"{BASE}/portal/auth/verify-otp",
                       json={"identifier": BUYER_PHONE, "code": "000000"}, timeout=30)
    check("Portal verify-otp 200", rv.status_code == 200, rv.text[:200])
    ptok = rv.json().get("token") if rv.status_code == 200 else None
    if ptok:
        PH = {"Authorization": f"Bearer {ptok}"}
        pr = requests.get(f"{BASE}/portal/progress", headers=PH, timeout=30)
        check("Portal progress 200", pr.status_code == 200, pr.text[:200])
        pdata = pr.json().get("data") or []
        preps = [r_ for row in pdata for r_ in (row.get("repairs") or [])]
        check("Portal mengirim pasangan perbaikan", len(preps) >= 1, f"{len(preps)}")
        allowed = {"punch_id", "title", "severity", "status", "resolved", "note",
                   "opened_at", "fixed_at", "before", "after"}
        leaked = sorted({k for r_ in preps for k in r_.keys()} - allowed)
        check("Tidak ada kunci internal yang bocor", not leaked, f"bocor: {leaked}")
        pf_ok = 0
        for r_ in preps:
            for ph in (r_.get("before", []) + r_.get("after", [])):
                if ph.get("file_id"):
                    g = requests.get(f"{BASE}/portal/files/{ph['file_id']}", headers=PH, timeout=60)
                    if g.status_code == 200 and g.headers.get("content-type", "").startswith("image"):
                        pf_ok += 1
                    else:
                        check(f"portal unduh {ph['file_id'][:8]}", False, str(g.status_code))
        check("Foto pasangan bisa diunduh via endpoint portal", pf_ok >= 1, f"{pf_ok} foto OK")

    print(f"\n[INFO] project_id={project_id} unit_id={unit_id} punch_target={target['id']}")
    unit = requests.get(f"{BASE}/site-plan/{project_id}/unit/{unit_id}", headers=H, timeout=30).json()
    print(f"[INFO] kode kavling = {(unit.get('data') or {}).get('unit', {}).get('code')}")
    return finish()


def finish():
    print("\n" + "=" * 60)
    print(f"HASIL: {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        for f in FAIL:
            print(f"  - GAGAL: {f}")
        sys.exit(1)
    print("SEMUA ASERSI FASE 28c LULUS")
    sys.exit(0)


if __name__ == "__main__":
    main()
