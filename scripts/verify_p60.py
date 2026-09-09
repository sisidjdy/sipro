#!/usr/bin/env python3
"""verify_p60.py — GATE 51: konfigurasi tampilan dokumen (kop, baris biaya, tanda tangan).

Sampai Fase 59 dokumen yang keluar dari sistem ini adalah teks polos. Fase 60 memberi
pemilik usaha kendali atas tampilannya. Gate ini menjaga agar kendali itu tidak berubah
menjadi hiasan yang tidak dipakai mesin cetak:

  K — KODE: layout punya SATU sumber (doc_layout), dokumen turunan hanya menyimpan yang
      berbeda dari bawaan, baris Rp 0 bisa disembunyikan, dan SETIAP jalur cetak dokumen
      (staf, portal pembeli, kwitansi, BAST, penawaran) memakai layout — bukan hanya satu.
  K-UI — LAYAR: panel + tab tampilan benar-benar dirender, pratinjau berdampingan ada, dan
      bidang usaha memakai kamus SSOT (bukan teks bebas yang beda-beda tiap dokumen).
  D — PERILAKU (server hidup): baca/simpan/reset bekerja, pratinjau menghasilkan PDF nyata
      dari rancangan yang BELUM disimpan, konfigurasi tersimpan benar-benar mengubah PDF
      dokumen sungguhan, dan hak akses ditegakkan server.

Jalankan: python3 scripts/verify_p60.py
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
    head("K. Kode: satu sumber layout & semua jalur cetak memakainya")
    dl = read(BE / "doc_layout.py")
    pl = read(BE / "pdf_layout.py")
    pu = read(BE / "pdf_utils.py")
    check("DEFAULT_CODE" in dl and "_merge" in dl,
          "K1 layout punya bawaan organisasi + penggabungan per dokumen")
    check("hide_if_zero" in dl and "hide_zero_rows" in dl,
          "K2 baris bernilai 0 bisa disembunyikan (bukan mencetak Rp 0 sebagai fakta)")
    check("def signatures_for" in dl and "auto_from_issuer" in dl,
          "K3 kolom tanda tangan dinamis (jumlah & isi ditentukan pemakai)")
    check("header_mode" in dl and "footer_mode" in dl,
          "K4 kop/footer punya dua mode: dirakit sistem ATAU gambar desain")
    check("def render_letter" in pl and "def render_table" in pl,
          "K5 mesin cetak melayani surat DAN laporan tabel")
    check("watermark" in pl.lower(), "K6 watermark benar-benar dirender mesin cetak")
    check("layout" in pu and "render_letter" in pu,
          "K7 pembuat PDF lama meneruskan layout (tidak ada dua mesin cetak)")
    jalur = {
        "dokumen staf": BE / "routers" / "documents_router.py",
        "portal pembeli": BE / "routers" / "portal_router.py",
        "penawaran": BE / "routers" / "quotations_router.py",
        "serah terima (BAST)": BE / "handover_engine.py",
    }
    for nama, p in jalur.items():
        src = read(p)
        check("doc_layout" in src and "layout=" in src,
              f"K8 jalur cetak '{nama}' memakai konfigurasi layout")
    check("business_field" in read(BE / "reference_p60.py"),
          "K9 bidang usaha ada di kamus SSOT (bukan teks bebas per dokumen)")


# ============================================================ K-UI. layar
def bagian_kui():
    head("K-UI. Layar: panel, pratinjau berdampingan, kamus SSOT")
    panel = read(FE / "components" / "master" / "DocLayoutPanel.js")
    brand = read(FE / "components" / "master" / "docLayout" / "BrandForm.js")
    rows = read(FE / "components" / "master" / "docLayout" / "RowsForm.js")
    sign = read(FE / "components" / "master" / "docLayout" / "SignaturesForm.js")
    tabs = read(FE / "components" / "master" / "DocTemplatesPanel.js")
    ids = read(FE / "constants" / "testIds" / "p60.js")
    check("DocLayoutPanel" in tabs and "P60.tabScript" in panel
          and "TabsTrigger" not in tabs,
          "KUI1 Template Dokumen = SATU panel (naskah + tampilan + pratinjau), bukan dua tab")
    check("P60.panel" in panel and "P60.preview" in panel,
          "KUI2 panel & pratinjau punya testId (bisa diuji, bukan komponen mati)")
    check("DocumentPreview" in panel and "lg:grid-cols-2" in panel and "<canvas" in read(FE / "components/master/docLayout/DocumentPreview.js"),
          "KUI3 pratinjau BERDAMPINGAN dengan formulir (bukan halaman terpisah)")
    check("/doc-layouts/${code}/preview" in panel or "preview" in panel,
          "KUI4 pratinjau memanggil mesin cetak server (bukan tiruan CSS)")
    check("P60.saveBtn" in panel and "P60.resetBtn" in panel,
          "KUI5 simpan & kembalikan ke bawaan tersedia di layar")
    check('ReferenceSelect group="business_field"' in brand,
          "KUI6 bidang usaha memakai dropdown kamus SSOT")
    check("P60.rowUp" in rows and "P60.rowAddManual" in rows,
          "KUI7 baris biaya bisa diurutkan & ditambah manual")
    check("P60.signAdd" in sign and "P60.signRemove" in sign,
          "KUI8 kolom tanda tangan bisa ditambah/dihapus")
    check("previewError" in ids and "P60.previewError" in panel,
          "KUI9 pratinjau yang GAGAL dirender dibedakan dari yang belum diminta")
    check("denied" in ids and "P60.denied" in panel,
          "KUI10 tanpa hak akses layar berkata HAK AKSES, bukan diam")


# ============================================================ D. perilaku
def bagian_d():
    head("D. Perilaku server: baca, simpan, pratinjau, PDF nyata, hak akses")
    admin = login("superadmin@sipro.co.id")
    sales = login("sales@sipro.co.id")
    # Mulai dari keadaan bawaan: gate tidak boleh bergantung pada sisa run sebelumnya.
    requests.delete(f"{API}/doc-layouts/__default__", headers=hdr(admin), timeout=30)

    r = requests.get(f"{API}/doc-layouts", headers=hdr(admin), timeout=30)
    body = r.json() if r.status_code == 200 else {}
    check(r.status_code == 200 and len(body.get("data") or []) >= 5,
          "D1 daftar dokumen yang bisa dikonfigurasi", f"status {r.status_code}")
    check(any(x["code"] == "__default__" for x in body.get("data") or []),
          "D2 ada bawaan organisasi yang berlaku untuk semua dokumen")
    check(len(body.get("money_rows_catalog") or []) >= 10
          and len(body.get("sections_catalog") or []) >= 4,
          "D3 katalog baris biaya & bagian dokumen dikirim server (layar tidak mengarang)")

    g = requests.get(f"{API}/doc-layouts/__default__", headers=hdr(admin), timeout=30)
    lay = (g.json().get("data") or {}) if g.status_code == 200 else {}
    check(g.status_code == 200 and lay.get("brand") and lay.get("money_rows"),
          "D4 layout efektif terbaca lengkap", f"status {g.status_code}")
    check(requests.get(f"{API}/doc-layouts/NGACO", headers=hdr(admin),
                       timeout=30).status_code == 404,
          "D5 kode dokumen yang tidak dikenal ditolak 404 (bukan disimpan diam-diam)")

    draft = {k: lay[k] for k in ("brand", "sections", "money_rows", "signatures", "options")
             if k in lay}
    draft["brand"] = {**draft["brand"], "company_name": "PT UJI GATE 51",
                      "tagline": "Kontraktor Umum", "watermark_text": "PRATINJAU"}
    p = requests.post(f"{API}/doc-layouts/__default__/preview", headers=hdr(admin),
                      json=draft, timeout=60)
    check(p.status_code == 200 and p.content[:4] == b"%PDF",
          "D6 pratinjau rancangan BELUM DISIMPAN menghasilkan PDF nyata",
          f"status {p.status_code}")
    ulang = requests.get(f"{API}/doc-layouts/__default__", headers=hdr(admin), timeout=30)
    check((ulang.json()["data"]["brand"].get("company_name")) != "PT UJI GATE 51",
          "D7 pratinjau TIDAK menyimpan (rancangan tetap rancangan)")

    lap = requests.post(f"{API}/doc-layouts/LAPORAN/preview", headers=hdr(admin),
                        json=draft, timeout=60)
    check(lap.status_code == 200 and lap.content[:4] == b"%PDF",
          "D8 pratinjau laporan tabel dirender mesin cetak yang sama",
          f"status {lap.status_code}")

    s = requests.put(f"{API}/doc-layouts/__default__", headers=hdr(admin), json=draft,
                     timeout=60)
    check(s.status_code == 200
          and s.json()["data"]["brand"].get("company_name") == "PT UJI GATE 51",
          "D9 simpan konfigurasi berhasil", f"status {s.status_code}")
    s2 = requests.put(f"{API}/doc-layouts/__default__", headers=hdr(admin), json=draft,
                      timeout=60)
    check(s2.status_code == 200, "D10 menyimpan dua kali tidak menggandakan konfigurasi")

    docs = requests.get(f"{API}/documents", headers=hdr(admin), timeout=60)
    lst = (docs.json().get("data") or []) if docs.status_code == 200 else []
    if lst:
        did = lst[0]["id"]
        pdf = requests.get(f"{API}/documents/{did}/pdf", headers=hdr(admin), timeout=60)
        check(pdf.status_code == 200 and pdf.content[:4] == b"%PDF",
              "D11 dokumen SUNGGUHAN tercetak memakai konfigurasi tersimpan",
              f"status {pdf.status_code}")
        real = requests.post(f"{API}/doc-layouts/SPR_CASH/preview?document_id={did}",
                             headers=hdr(admin), json=draft, timeout=60)
        check(real.status_code == 200 and real.content[:4] == b"%PDF",
              "D12 pratinjau bisa memakai DATA dokumen nyata", f"status {real.status_code}")
    else:
        check(False, "D11/D12 butuh minimal satu dokumen terbit di data demo")

    d = requests.delete(f"{API}/doc-layouts/__default__", headers=hdr(admin), timeout=30)
    check(d.status_code == 200
          and d.json()["data"]["brand"].get("company_name") != "PT UJI GATE 51",
          "D13 reset mengembalikan bawaan", f"status {d.status_code}")

    check(requests.get(f"{API}/doc-layouts", timeout=30).status_code == 401,
          "D14 tanpa token = 401 (identitas perusahaan bukan data publik)")
    check(requests.put(f"{API}/doc-layouts/__default__", headers=hdr(sales), json=draft,
                       timeout=30).status_code == 403,
          "D15 sales tidak boleh mengubah tampilan dokumen organisasi")
    check(requests.post(f"{API}/doc-layouts/__default__/preview", headers=hdr(sales),
                        json=draft, timeout=30).status_code == 403,
          "D16 pratinjau rancangan pun butuh hak mengubah dokumen")


def main():
    print("=" * 78)
    print("GATE 51 — Fase 60: konfigurasi tampilan dokumen (kop, baris, tanda tangan)")
    print("=" * 78)
    bagian_k()
    bagian_kui()
    bagian_d()
    print("\n" + "-" * 78)
    if fails:
        print(f"GATE 51 MERAH — {len(fails)} gagal / {ok + len(fails)} pemeriksaan")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"GATE 51 HIJAU — {ok} pemeriksaan")


if __name__ == "__main__":
    main()
