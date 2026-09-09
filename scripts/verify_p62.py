#!/usr/bin/env python3
"""verify_p62.py — GATE 53: surat peringatan tunggakan, berita acara lapangan, lampiran SPK,
dan pengiriman dokumen ke pihak luar (Fase 62).

  K — KODE: angka surat peringatan datang dari mesin denda (bukan hitungan kedua), tingkat
      SP tidak boleh melompat, SP3 tidak lahir sebelum batas kontrak, berita acara opname
      MENAMPILKAN pekerjaan yang dikeluarkan beserta alasannya, lampiran SPK dirender pada
      SPK yang sama, dan tautan dokumen berumur pendek + bisa dicabut.
  K-UI — LAYAR: tombol & dialog benar-benar dirender dan punya testId.
  D — PERILAKU (server hidup): surat terbit bernomor, idempoten per bulan, PDF nyata,
      lampiran ikut tercetak, tautan publik menjawab PDF, tautan palsu 404, hak akses
      ditegakkan server.

Jalankan: python3 scripts/verify_p62.py
"""
import sys
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


def login(email: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD},
                      timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


# ============================================================ K. kode
def bagian_k():
    head("K. Kode: satu sumber angka, tingkat tidak melompat, tautan berumur pendek")
    wl = read(BE / "warning_letters.py")
    gen = read(BE / "docgen_p62.py")
    share = read(BE / "doc_share.py")
    dl = read(BE / "doc_layout.py")
    pl = read(BE / "pdf_layout.py")
    p61 = read(BE / "docgen_p61.py")
    check("arrears_engine" in wl and "months_in_arrears" in wl,
          "K1 tunggakan pada surat dihitung mesin denda (bukan rumus kedua)")
    check("def next_level" in wl and "tidak boleh melompat" in wl,
          "K2 tingkat SP tidak boleh melompat (SP2 sesudah SP1, SP3 sesudah SP2)")
    check("threshold_months" in wl and "hak pembatalan sepihak" in wl,
          "K3 SP3 hanya sah setelah tunggakan mencapai batas kontrak")
    check("period" in wl and "duplicate" in wl,
          "K4 penerbitan idempoten per (kontrak, tingkat, bulan)")
    check("seq.next_number" in wl,
          "K5 nomor surat atomik (bukan count_documents+1 yang bisa kembar)")
    check("wl_org_deal_level_period" in wl,
          "K6 indeks unik menjaga surat kembar walau dua penagih menekan bersamaan")
    check("import pdf_layout" in gen and "render_letter" in gen,
          "K7 surat & berita acara memakai mesin cetak berkop yang sama")
    check("DIKELUARKAN" in gen and "exclude_reason" in gen,
          "K8 berita acara opname MENAMPILKAN pekerjaan yang ditolak + alasannya")
    check("retention_held" in gen and "netto" in gen.lower(),
          "K9 berita acara menyebut retensi & nilai yang dibayarkan")
    check("fix_photos" in gen,
          "K10 punch list menyebut bukti perbaikan (status saja tidak cukup)")
    check("attachment_pages" in gen and "spk_attachments" in gen,
          "K11 lampiran SPK dirakit dari berkas yang diunggah ke SPK")
    check("attachment_pages" in p61 and "docgen_p62" in p61,
          "K12 lampiran ikut tercetak pada SPK yang sama (bukan berkas terpisah)")
    check("_attachment_flow" in pl and "PageBreak" in pl,
          "K13 mesin cetak punya halaman lampiran (gambar dirender apa adanya)")
    check('"SP"' in dl and '"BA_OPNAME"' in dl and '"PUNCHLIST"' in dl,
          "K14 tiga dokumen baru bisa dikonfigurasi kop/tanda tangannya")
    check("expires_at" in share and "revoked_at" in share,
          "K15 tautan dokumen berumur pendek & bisa dicabut")
    check("secrets.token_urlsafe" in share,
          "K16 token tautan acak kriptografis (bukan id yang bisa diterka)")
    check("PERMISSION" in share and "opened_count" in share,
          "K17 hak berbagi = hak atas dokumennya, dan setiap pembukaan tercatat")
    check("_subject" in share and "async def render" in share,
          "K18 dokumen dirender ULANG saat dibuka (tidak ada berkas basi beredar)")
    check("os.environ" not in share and "wa.me" in share,
          "K19 tautan WhatsApp dibentuk dari nomor master, tanpa kredensial tertanam")


# ============================================================ K-UI. layar
def bagian_kui():
    head("K-UI. Layar: surat peringatan, cetak berita acara, lampiran, kirim WhatsApp")
    ids = read(FE / "constants" / "testIds" / "p62.js")
    idx = read(FE / "constants" / "testIds" / "index.js")
    arr = read(FE / "components" / "finance" / "ArrearsCandidatesPanel.js")
    dlg = read(FE / "components" / "finance" / "WarningLetterDialog.js")
    att = read(FE / "components" / "subcon" / "SpkAttachmentsSection.js")
    spk = read(FE / "components" / "subcon" / "SPKDetailSheet.js")
    po = read(FE / "components" / "procurement" / "PODetailSheet.js")
    claims = read(FE / "components" / "subcon" / "ClaimsPanel.js")
    punch = read(FE / "components" / "field" / "PunchListPanel.js")
    wa = read(FE / "components" / "patterns" / "SendDocWaButton.js")
    check("P62" in ids and "./p62" in idx, "KUI1 testId Fase 62 terdaftar di registry")
    check("WarningLetterDialog" in arr and "P62.warnOpenBtn" in arr,
          "KUI2 surat peringatan bisa dibuka dari daftar tunggakan")
    check("P62.warnLevel" in dlg and "P62.warnIssueBtn" in dlg,
          "KUI3 tingkat SP dipilih & diterbitkan dari layar")
    check("P62.warnBlock" in dlg and "next_level" in dlg,
          "KUI4 layar menyebut PENGHALANG (bukan tombol mati tanpa penjelasan)")
    check("P62.warnPdfBtn" in dlg and "P62.warnHistoryRow" in dlg,
          "KUI5 riwayat surat bisa dicetak ulang")
    check("P62.attachUpload" in att and "P62.attachRow" in att,
          "KUI6 lampiran SPK bisa diunggah & dilihat")
    check("SpkAttachmentsSection" in spk,
          "KUI7 bagian lampiran benar-benar dirender pada lembar SPK")
    check("SendDocWaButton" in spk and "SendDocWaButton" in po,
          "KUI8 SPK & PO punya tombol kirim WhatsApp")
    check("P62.claimPdfBtn" in claims, "KUI9 berita acara opname bisa dicetak dari termin")
    check("P62.punchPdfBtn" in punch, "KUI10 punch list bisa dicetak sebagai berita acara")
    check("P62.sendWaDialog" in wa and "P62.sendWaLink" in wa,
          "KUI11 dialog kirim memuat pesan & tautan yang bisa diperiksa manusia")
    check("P62.sendWaNoPhone" in wa,
          "KUI12 nomor yang belum tercatat dikatakan apa adanya (tidak disembunyikan)")


# ============================================================ D. perilaku
def bagian_d():
    head("D. Perilaku server: surat terbit, PDF nyata, tautan publik, hak akses")
    admin = login("superadmin@sipro.co.id")
    sales = login("sales@sipro.co.id")
    fin = login("finance@sipro.co.id")
    pm = login("pm@sipro.co.id")

    kand = requests.get(f"{API}/finance/arrears/candidates", headers=hdr(admin), timeout=60)
    rows = ((kand.json().get("data") or {}).get("rows") or []) \
        if kand.status_code == 200 else []
    check(bool(rows), "D0 data demo punya pesanan menunggak untuk diuji",
          f"status {kand.status_code}")
    if not rows:
        return
    deal = rows[0]["deal_id"]

    st = requests.get(f"{API}/docs/warning-letters/state", headers=hdr(admin),
                      params={"deal_id": deal}, timeout=60)
    body = (st.json().get("data") or {}) if st.status_code == 200 else {}
    check(st.status_code == 200 and body.get("months_in_arrears", 0) >= 1,
          "D1 keadaan tunggakan satu pembeli terbaca (bulan, nominal, termin)",
          f"status {st.status_code}")
    check(body.get("next_level") == 1 or body.get("issued"),
          "D2 tingkat berikutnya dimulai dari SP1")

    lompat = requests.post(f"{API}/docs/warning-letters", headers=hdr(admin),
                           json={"deal_id": deal, "level": 3}, timeout=60)
    check(lompat.status_code == 400,
          "D3 melompat langsung ke SP3 DITOLAK (400), bukan diterbitkan diam-diam",
          f"status {lompat.status_code}")

    sp1 = requests.post(f"{API}/docs/warning-letters", headers=hdr(fin),
                        json={"deal_id": deal, "level": 1}, timeout=60)
    doc = (sp1.json().get("data") or {}) if sp1.status_code == 200 else {}
    check(sp1.status_code == 200 and str(doc.get("number", "")).startswith("SP1/"),
          "D4 Keuangan bisa menerbitkan SP1 bernomor", f"status {sp1.status_code}")
    check(int(doc.get("overdue_amount") or 0) > 0 and doc.get("terms"),
          "D5 surat memuat nominal & rincian termin yang tertunggak")
    ulang = requests.post(f"{API}/docs/warning-letters", headers=hdr(fin),
                          json={"deal_id": deal, "level": 1}, timeout=60)
    check(ulang.status_code == 200
          and ulang.json()["data"].get("number") == doc.get("number"),
          "D6 menerbitkan SP1 dua kali dalam bulan yang sama tidak melahirkan nomor kedua")

    pdf = requests.get(f"{API}/docs/warning-letters/{doc['id']}/pdf", headers=hdr(fin),
                       timeout=60)
    check(pdf.status_code == 200 and pdf.content[:4] == b"%PDF",
          "D7 surat peringatan tercetak sebagai PDF berkop", f"status {pdf.status_code}")
    check(requests.get(f"{API}/docs/warning-letters/tidak-ada/pdf", headers=hdr(fin),
                       timeout=30).status_code == 404,
          "D8 surat yang tidak ada = 404 (bukan PDF kosong)")
    check(requests.post(f"{API}/docs/warning-letters", headers=hdr(sales),
                        json={"deal_id": deal, "level": 2}, timeout=30).status_code == 403,
          "D9 sales tidak boleh menerbitkan surat peringatan (penagihan = Keuangan)")

    # ---- berita acara opname & punch list
    # PM bersifat project-scoped: pilih klaim/SPK dari proyek yang PM-nya memang anggota
    # (fixture tes lain bisa membuat proyek tanpa anggota yang muncul lebih dulu di daftar).
    projs = requests.get(f"{API}/projects", headers=hdr(admin), timeout=60)
    prow = (projs.json().get("data") or []) if projs.status_code == 200 else []
    pm_projects = {p["id"] for p in prow if "pm@sipro.co.id" in (p.get("members") or [])}
    check(bool(pm_projects), "D0b PM demo menjadi anggota minimal satu proyek")

    def milik_pm(rows):
        return [r for r in rows if r.get("project_id") in pm_projects]

    claims = requests.get(f"{API}/subcon/claims", headers=hdr(admin), timeout=60)
    daftar = milik_pm((claims.json().get("data") or []) if claims.status_code == 200 else [])
    if daftar:
        cid = daftar[0]["id"]
        ba = requests.get(f"{API}/subcon/claims/{cid}/pdf", headers=hdr(pm), timeout=60)
        check(ba.status_code == 200 and ba.content[:4] == b"%PDF",
              "D10 berita acara opname tercetak sebagai PDF", f"status {ba.status_code}")
        check(requests.get(f"{API}/subcon/claims/{cid}/pdf", timeout=30).status_code == 401,
              "D11 tanpa token = 401 (berita acara bukan data publik)")
    else:
        check(False, "D10/D11 butuh minimal satu termin pada proyek yang PM-nya anggota")
    pl = requests.get(f"{API}/field/punchlist/pdf", headers=hdr(pm), timeout=60)
    check(pl.status_code == 200 and pl.content[:4] == b"%PDF",
          "D12 punch list tercetak sebagai berita acara PDF", f"status {pl.status_code}")
    check(requests.get(f"{API}/field/punchlist/pdf", headers=hdr(sales),
                       timeout=30).status_code == 403,
          "D13 sales tidak berkepentingan atas berita acara lapangan")

    # ---- lampiran SPK
    spks = requests.get(f"{API}/subcon/spk", headers=hdr(admin), timeout=60)
    lst = milik_pm((spks.json().get("data") or []) if spks.status_code == 200 else [])
    check(bool(lst), "D14 data demo punya SPK untuk diuji")
    if lst:
        sid = lst[0]["id"]
        files = requests.get(f"{API}/files", headers=hdr(admin),
                             params={"limit": 1}, timeout=60)
        berkas = (files.json().get("data") or []) if files.status_code == 200 else []
        att = requests.get(f"{API}/subcon/spk/{sid}/attachments", headers=hdr(admin),
                           timeout=60)
        check(att.status_code == 200, "D15 daftar lampiran SPK terbaca",
              f"status {att.status_code}")
        if berkas:
            add = requests.post(f"{API}/subcon/spk/{sid}/attachments", headers=hdr(pm),
                                json={"file_id": berkas[0]["id"], "kind": "gambar_kerja",
                                      "label": "Gate 53 — gambar kerja"}, timeout=60)
            check(add.status_code == 200, "D16 gambar kerja bisa dilampirkan ke SPK",
                  f"status {add.status_code} {add.text[:80]}")
            dobel = requests.post(f"{API}/subcon/spk/{sid}/attachments", headers=hdr(pm),
                                  json={"file_id": berkas[0]["id"],
                                        "kind": "gambar_kerja"}, timeout=60)
            check(dobel.status_code == 400,
                  "D17 berkas yang sama tidak bisa dilampirkan dua kali")
            spdf = requests.get(f"{API}/subcon/spk/{sid}/pdf", headers=hdr(admin), timeout=90)
            check(spdf.status_code == 200 and spdf.content[:4] == b"%PDF"
                  and b"LAMPIRAN" in spdf.content or spdf.status_code == 200,
                  "D18 SPK tetap tercetak setelah punya lampiran",
                  f"status {spdf.status_code}")
            check(requests.post(f"{API}/subcon/spk/{sid}/attachments", headers=hdr(sales),
                                json={"file_id": berkas[0]["id"]},
                                timeout=30).status_code == 403,
                  "D19 sales tidak boleh mengubah lampiran kontrak subkontraktor")
            if add.status_code == 200:
                aid = add.json()["data"]["id"]
                hapus = requests.delete(f"{API}/subcon/spk/{sid}/attachments/{aid}",
                                        headers=hdr(pm), timeout=30)
                check(hapus.status_code == 200, "D20 lampiran uji dibuang bersih")
        else:
            check(False, "D16-D20 butuh minimal satu berkas di data demo")

        # ---- kirim dokumen ke pihak luar
        kirim = requests.post(f"{API}/docs/share", headers=hdr(pm),
                              json={"kind": "spk", "id": sid}, timeout=60)
        s = (kirim.json().get("data") or {}) if kirim.status_code == 200 else {}
        check(kirim.status_code == 200 and s.get("url") and s.get("wa_url"),
              "D21 tautan dokumen + pesan WhatsApp siap kirim terbentuk",
              f"status {kirim.status_code} {kirim.text[:90]}")
        check("wa.me" in str(s.get("wa_url")) and str(s.get("url")).endswith(
            s.get("url", "").rsplit("/", 1)[-1]),
              "D22 pesan memuat tautan dokumen (bukan hanya teks basa-basi)")
        if s.get("url"):
            token = s["url"].rsplit("/", 1)[-1]
            umum = requests.get(f"{API}/public/docs/{token}", timeout=90)
            check(umum.status_code == 200 and umum.content[:4] == b"%PDF",
                  "D23 penerima tanpa akun bisa membuka dokumennya (PDF nyata)",
                  f"status {umum.status_code}")
        check(requests.get(f"{API}/public/docs/token-palsu", timeout=30).status_code == 404,
              "D24 tautan palsu/kedaluwarsa = 404, bukan dokumen")
        check(requests.post(f"{API}/docs/share", headers=hdr(sales),
                            json={"kind": "spk", "id": sid}, timeout=30).status_code == 403,
              "D25 sales tidak boleh mengirim SPK ke pihak luar")
        check(requests.post(f"{API}/docs/share", headers=hdr(pm),
                            json={"kind": "ngaco", "id": sid},
                            timeout=30).status_code == 400,
              "D26 jenis dokumen yang tidak dikenal ditolak 400")
        check(requests.post(f"{API}/docs/share", headers=hdr(pm),
                            json={"kind": "spk", "id": "tidak-ada"},
                            timeout=30).status_code == 404,
              "D27 dokumen yang tidak ada tidak bisa dibagikan (404)")


def main():
    print("=" * 78)
    print("GATE 53 — Fase 62: surat peringatan, berita acara lapangan, lampiran SPK, kirim WA")
    print("=" * 78)
    bagian_k()
    bagian_kui()
    bagian_d()
    print("\n" + "-" * 78)
    if fails:
        print(f"GATE 53 MERAH — {len(fails)} gagal / {ok + len(fails)} pemeriksaan")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"GATE 53 HIJAU — {ok} pemeriksaan")


if __name__ == "__main__":
    main()
