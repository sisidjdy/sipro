#!/usr/bin/env python3
"""verify_p63.py — GATE 54: agenda kerja lengkap (Fase 63).

  K — KODE: agenda tidak lagi wajib menempel pada lead, jenis agenda non-penjualan masuk
      SSOT, cari/filter/urut dieksekusi SERVER (bukan di browser atas halaman aktif),
      peserta wajib pengguna nyata, agenda selesai tidak bisa diubah, dan staf yang
      DIUNDANG bisa melihat agendanya.
  K-UI — LAYAR: ruang kosong di bawah kalender diisi TABEL agenda (cari, filter, urut,
      paginasi, ekspor) dan agenda bisa dibuat/diubah dari halaman ini.
  D — PERILAKU (server hidup): agenda internal lahir tanpa lead & tanpa menaikkan tahap,
      agenda ber-lead tetap milik peran yang berhak melihat lead, RBAC ditegakkan.

Jalankan: python3 scripts/verify_p63.py
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
API = "http://localhost:8001/api"
PASSWORD = "Sipro#2026"

ok, fails = 0, []


def check(cond, label, detail=None):
    global ok
    if cond:
        ok += 1
        print(f"  OK    {label}")
        return True
    fails.append(label)
    print(f"  GAGAL {label}" + (f" — {detail}" if detail else ""))
    return False


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def hdr(email: str) -> dict:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD},
                      timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def bagian_k():
    head("K. Kode: agenda kerja, bukan hanya janji temu jual")
    rt = read(BE / "routers" / "leads_router.py")
    md = read(BE / "models.py")
    rf = read(BE / "reference_p63.py")
    mx = read(BE / "rbac_matrix.py")
    check("lead_id: Optional[str] = None" in md,
          "K1 agenda TIDAK wajib menempel pada lead (rapat internal punya tempat)")
    check("participants" in md and "AppointmentUpdate" in md,
          "K2 peserta & pengubahan agenda punya model permintaan sendiri")
    check("internal_meeting" in rf and "site_visit" in rf and "vendor_meeting" in rf,
          "K3 jenis agenda non-penjualan masuk SSOT (bukan teks bebas)")
    check("agenda_kind" in rf,
          "K4 golongan agenda (jual vs internal) punya kosakata terkontrol")
    check("APPT_SORTS" in rt and "lst.sort_spec" in rt,
          "K5 urutan dieksekusi DATABASE atas seluruh hasil (bukan halaman terlihat saja)")
    check("lst.apply_search" in rt and '"title", "lead_name", "location"' in rt,
          "K6 pencarian menjangkau judul, lead, lokasi & catatan")
    check("lst.apply_in(base, \"kind\"" in rt and "lst.apply_in(base, \"type\"" in rt,
          "K7 filter golongan & jenis menerima beberapa nilai (koma)")
    check("_appt_scope" in rt and '"participants": own' in rt,
          "K8 staf yang DIUNDANG melihat agendanya (undangan tak terlihat = tak diundang)")
    check("_clean_participants" in rt and "Peserta tidak dikenal" in rt,
          "K9 peserta wajib pengguna nyata — email asing ditolak, bukan disimpan")
    check("leads\", \"view\")" in rt and "kosongkan pilihan lead" in rt,
          "K10 agenda ber-lead hanya untuk peran yang berhak melihat lead (SoD terjaga)")
    check("if internal:" in rt and "return {\"data\": serialize_doc(appt)}" in rt,
          "K11 agenda internal TIDAK menaikkan tahap lead / menerbitkan tugas survei")
    check("sudah selesai/dibatalkan tidak bisa diubah" in rt,
          "K12 agenda yang sudah dilaksanakan adalah catatan sejarah (tidak bisa diubah)")
    check("appointments/staff" in rt and "Sengaja TIDAK memakai `/admin/users`" in rt,
          "K13 pemilih peserta tidak membocorkan data pengguna lewat /admin/users")
    check('"project_manager": ["view_all", "create", "update"]' in mx.split('"appointments"')[1][:2000],
          "K14 peran proyek boleh membuat agendanya sendiri (matriks, bukan tambalan UI)")


def bagian_kui():
    head("K-UI. Layar: ruang kosong diisi tabel + agenda bisa dibuat dari sini")
    page = read(FE / "pages" / "AppointmentsPage.js")
    tab = read(FE / "components" / "appointments" / "AgendaTable.js")
    form = read(FE / "components" / "appointments" / "AgendaFormDialog.js")
    ids = read(FE / "constants" / "testIds" / "appointments.js")
    check("AgendaTable" in page and "AgendaFormDialog" in page,
          "KUI1 halaman memakai tabel agenda & dialog buat agenda")
    check("APPTS.createBtn" in page and "APPTS.dayCreateBtn" in page,
          "KUI2 agenda bisa dibuat dari kepala halaman maupun dari tanggal terpilih")
    check("DataTable" in tab and "FilterBar" in tab,
          "KUI3 tabel memakai pola DataTable+FilterBar (cari, kolom, ekspor, paginasi)")
    check("sortable: true" in tab and "onQueryChange" in tab,
          "KUI4 kolom bisa diurutkan & query dikirim ke server")
    check("next7" in tab and "past" in tab,
          "KUI5 rentang waktu: 7/30 hari ke depan dan riwayat")
    check("APPTS.editBtn" in tab and 'includes(a.status)' in tab,
          "KUI6 agenda bisa diubah, kecuali yang sudah selesai/dibatalkan")
    check("APPTS.formKind" in form and "internal" in form,
          "KUI7 golongan agenda dipilih di layar (jual vs internal)")
    check("APPTS.formParticipants" in form and "appointments/staff" in form,
          "KUI8 peserta dipilih dari daftar staf, bukan diketik")
    check("APPTS.formLeadSearch" in form,
          "KUI9 lead dicari (bukan daftar panjang yang harus digulir)")
    check("Agenda penjualan wajib menyebut leadnya" in form,
          "KUI10 layar menolak agenda jual tanpa lead dengan alasan yang bisa dibaca")
    check("useListQuery" in page,
          "KUI11 cari/filter/urut hidup di URL (bisa dibagikan & tombol Kembali bekerja)")
    check("createBtn" in ids and "tableSearch" in ids and "formSubmit" in ids,
          "KUI12 seluruh elemen baru punya data-testid")
    check("params: { limit: 500 }" in page and "kalender yang menyembunyikan" in page,
          "KUI13 penanda kalender tidak ikut filter tabel (kalender tidak berbohong)")


def bagian_d():
    head("D. Perilaku server: agenda internal, peserta, RBAC, tidak bisa ubah yang selesai")
    adm, pm = hdr("superadmin@sipro.co.id"), hdr("pm@sipro.co.id")
    sales, site = hdr("sales@sipro.co.id"), hdr("site@sipro.co.id")
    when = (datetime.now() + timedelta(days=4)).isoformat()
    judul = "GATE54 rapat internal divisi proyek"

    r = requests.post(f"{API}/appointments", headers=pm, timeout=30, json={
        "title": judul, "scheduled_at": when, "type": "internal_meeting",
        "location": "Ruang rapat", "participants": ["site@sipro.co.id"]})
    doc = (r.json().get("data") or {}) if r.status_code == 200 else {}
    check(r.status_code == 200 and doc.get("kind") == "internal" and not doc.get("lead_id"),
          "D1 agenda internal lahir tanpa lead", f"status {r.status_code} {r.text[:90]}")
    check(doc.get("assigned_to") == "pm@sipro.co.id",
          "D2 pemilik agenda internal = pembuatnya")
    aid = doc.get("id")

    lead = requests.get(f"{API}/leads", headers=adm, params={"limit": 1},
                        timeout=30).json()["data"][0]
    blok = requests.post(f"{API}/appointments", headers=pm, timeout=30, json={
        "lead_id": lead["id"], "title": "GATE54 survey", "scheduled_at": when,
        "type": "survey"})
    check(blok.status_code == 403,
          "D3 peran proyek TIDAK boleh menjadwalkan agenda milik lead (SoD)",
          f"status {blok.status_code}")
    jual = requests.post(f"{API}/appointments", headers=adm, timeout=30, json={
        "lead_id": lead["id"], "title": "GATE54 survey lead", "scheduled_at": when,
        "type": "survey"})
    jd = (jual.json().get("data") or {}) if jual.status_code == 200 else {}
    check(jual.status_code == 200 and jd.get("kind") == "sales" and jd.get("lead_name"),
          "D4 agenda ber-lead tetap bisa dibuat & membawa nama lead",
          f"status {jual.status_code}")

    cari = requests.get(f"{API}/appointments", headers=adm, timeout=30,
                        params={"q": "GATE54 rapat", "kind": "internal"})
    check(cari.status_code == 200 and cari.json()["total"] >= 1,
          "D5 pencarian + filter golongan bekerja di server")
    urut = requests.get(f"{API}/appointments", headers=adm, timeout=30,
                        params={"sort": "title", "direction": "desc", "limit": 5})
    judul_urut = [x["title"] for x in urut.json()["data"]]
    check(urut.status_code == 200 and judul_urut == sorted(judul_urut, reverse=True),
          "D6 sort server-side benar-benar mengurutkan (bukan diabaikan)")
    tipe = requests.get(f"{API}/appointments", headers=adm, timeout=30,
                        params={"type": "internal_meeting,site_visit"})
    check(tipe.status_code == 200
          and all(x["type"] in ("internal_meeting", "site_visit")
                  for x in tipe.json()["data"]),
          "D7 filter jenis menerima beberapa nilai sekaligus")
    ngaco = requests.get(f"{API}/appointments", headers=adm, timeout=30,
                         params={"sort": "org_id", "direction": "desc"})
    check(ngaco.status_code == 200,
          "D8 sort pada kolom di luar whitelist diabaikan (tidak bisa dipaksa lewat URL)")

    staf = requests.get(f"{API}/appointments/staff", headers=pm, timeout=30)
    daftar = (staf.json().get("data") or []) if staf.status_code == 200 else []
    check(staf.status_code == 200 and daftar and all("value" in x for x in daftar),
          "D9 daftar staf untuk pemilih peserta tersedia", f"status {staf.status_code}")

    if aid:
        lihat = requests.get(f"{API}/appointments", headers=site, timeout=30,
                             params={"q": "GATE54 rapat"})
        check(lihat.status_code == 200 and lihat.json()["total"] >= 1,
              "D10 staf yang DIUNDANG melihat agenda itu di daftarnya")
        ubah = requests.put(f"{API}/appointments/{aid}", headers=pm, timeout=30,
                            json={"location": "Ruang rapat lantai 2"})
        check(ubah.status_code == 200
              and ubah.json()["data"]["location"] == "Ruang rapat lantai 2",
              "D11 agenda bisa digeser/diubah", f"status {ubah.status_code}")
        asing = requests.put(f"{API}/appointments/{aid}", headers=pm, timeout=30,
                             json={"participants": ["orang@luar.com"]})
        check(asing.status_code == 400,
              "D12 peserta yang bukan pengguna ditolak 400 (bukan disimpan diam-diam)")
        kosong = requests.put(f"{API}/appointments/{aid}", headers=pm, timeout=30, json={})
        check(kosong.status_code == 400, "D13 permintaan ubah tanpa perubahan ditolak")
        tolak = requests.put(f"{API}/appointments/{aid}", headers=sales, timeout=30,
                             json={"location": "Rumah saya"})
        check(tolak.status_code in (403, 404),
              "D14 sales tidak bisa mengubah agenda internal divisi lain",
              f"status {tolak.status_code}")
        requests.post(f"{API}/appointments/{aid}/status", headers=pm, timeout=30,
                      json={"status": "done"})
        beku = requests.put(f"{API}/appointments/{aid}", headers=pm, timeout=30,
                            json={"location": "X"})
        check(beku.status_code == 400,
              "D15 agenda yang sudah SELESAI tidak bisa diubah lagi")
        check(requests.put(f"{API}/appointments/tidak-ada", headers=pm, timeout=30,
                           json={"location": "X"}).status_code == 404,
              "D16 agenda yang tidak ada = 404")

    # ---- bersihkan bahan uji supaya data demo tidak tercemar
    import os

    from dotenv import load_dotenv
    from pymongo import MongoClient
    load_dotenv(BE / ".env")
    cli = MongoClient(os.environ["MONGO_URL"])
    hapus = cli[os.environ["DB_NAME"]].appointments.delete_many(
        {"title": {"$regex": "^GATE54"}}).deleted_count
    cli.close()
    check(hapus >= 2, "D17 bahan uji dibuang tanpa sisa", f"terhapus {hapus}")


def main():
    print("=" * 78)
    print("GATE 54 — Fase 63: agenda kerja lengkap (tabel, cari/filter/urut, buat agenda)")
    print("=" * 78)
    bagian_k()
    bagian_kui()
    bagian_d()
    print("\n" + "-" * 78)
    if fails:
        print(f"GATE 54 MERAH — {len(fails)} gagal / {ok + len(fails)} pemeriksaan")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"GATE 54 HIJAU — {ok} pemeriksaan")


if __name__ == "__main__":
    main()
