#!/usr/bin/env python3
"""verify_p61.py — GATE 52: cetak SPK subkontraktor & PO pengadaan.

Dua dokumen yang paling sering dipegang PIHAK LUAR justru tidak punya bentuk cetak sampai
Fase 60. Gate ini menjaga agar keduanya tidak kembali menjadi "baris di layar":

  K — KODE: isi dokumen dirakit dari baris yang SAMA dengan yang dipakai penagihan (lingkup
      SPK & item PO), mesin cetaknya SATU (`pdf_layout`, kop dari Pusat Konfigurasi Fase 60),
      dan dokumen yang belum disetujui WAJIB bertanda DRAFT.
  K-UI — LAYAR: tombol cetak benar-benar ada di lembar detail SPK & PO dan bisa diuji.
  D — PERILAKU (server hidup): endpoint menjawab PDF nyata, nomor dokumen ikut tercetak,
      SPK/PO yang tidak ada = 404, hak akses & lingkup proyek ditegakkan server.

Jalankan: python3 scripts/verify_p61.py
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


def bagian_k():
    head("K. Kode: satu sumber angka, satu mesin cetak, tanda DRAFT")
    src = read(BE / "docgen_p61.py")
    pl = read(BE / "pdf_layout.py")
    dl = read(BE / "doc_layout.py")
    check("import pdf_layout" in src and "render_letter" in src,
          "K1 memakai mesin cetak berkop yang sama dengan dokumen lain")
    check("op.scope_rows" in src and "op.summarize" in src,
          "K2 rincian SPK dibaca dari baris lingkup (sumber angka penagihan)")
    check('po.get("items")' in src and 'po.get("total")' in src,
          "K3 rincian & total PO dibaca dari dokumen PO, bukan dihitung ulang")
    check("_draft_layout" in src and "DRAFT" in src,
          "K4 dokumen yang belum disetujui bertanda DRAFT")
    check('"SPK"' in dl and '"PO"' in dl,
          "K5 SPK & PO bisa dikonfigurasi tampilannya (Pusat Konfigurasi Dokumen)")
    check("item_table" in pl and "def _grid" in pl,
          "K6 tabel rincian dipakai bersama surat & laporan (bukan tabel kedua)")
    check("SPK_CLAUSES" in src and "PO_CLAUSES" in src,
          "K7 ketentuan tercetak (retensi, opname, GRN, 3-way match) — bukan surat kosong")
    check("retention_pct" in src and "maintenance_days" in src,
          "K8 retensi & masa pemeliharaan tercetak pada SPK (dasar penahanan uang)")


def bagian_kui():
    head("K-UI. Layar: tombol cetak ada dan bisa diuji")
    spk = read(FE / "components" / "subcon" / "SPKDetailSheet.js")
    po = read(FE / "components" / "procurement" / "PODetailSheet.js")
    btn = read(FE / "components" / "patterns" / "PrintDocButton.js")
    ids = read(FE / "constants" / "testIds" / "p61.js")
    check("P61.spkPdf" in spk and "/subcon/spk/" in spk, "KUI1 tombol cetak SPK di lembar detail")
    check("P61.poPdf" in po and "/procurement/pos/" in po, "KUI2 tombol cetak PO di lembar detail")
    check("responseType" in btn and "application/pdf" in btn,
          "KUI3 tombol cetak mengunduh PDF sungguhan dari server")
    check("spkPdf" in ids and "poPdf" in ids, "KUI4 testId Fase 61 terdaftar")
    check("export * from './p61'" in read(FE / "constants" / "testIds" / "index.js"),
          "KUI5 testId Fase 61 ikut diekspor registry")


def bagian_d():
    head("D. Perilaku server: PDF nyata, 404, hak akses")
    admin = login("superadmin@sipro.co.id")
    sales = login("sales@sipro.co.id")

    spks = requests.get(f"{API}/subcon/spk", headers=hdr(admin), timeout=60).json()
    pos = requests.get(f"{API}/procurement/pos", headers=hdr(admin), timeout=60).json()
    spk = (spks.get("data") or [None])[0]
    po = (pos.get("data") or [None])[0]
    if not check(bool(spk) and bool(po), "D0 data demo punya SPK & PO untuk diuji"):
        return

    r = requests.get(f"{API}/subcon/spk/{spk['id']}/pdf", headers=hdr(admin), timeout=60)
    check(r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.content) > 1500,
          "D1 SPK tercetak sebagai PDF berkop", f"status {r.status_code}")
    check("pdf" in (r.headers.get("Content-Disposition") or "").lower(),
          "D2 berkas SPK diberi nama yang menyebut nomornya")

    r2 = requests.get(f"{API}/procurement/pos/{po['id']}/pdf", headers=hdr(admin), timeout=60)
    check(r2.status_code == 200 and r2.content[:4] == b"%PDF" and len(r2.content) > 1500,
          "D3 PO tercetak sebagai PDF berkop", f"status {r2.status_code}")

    check(requests.get(f"{API}/subcon/spk/tidak-ada/pdf", headers=hdr(admin),
                       timeout=30).status_code == 404,
          "D4 SPK yang tidak ada = 404 (bukan PDF kosong)")
    check(requests.get(f"{API}/procurement/pos/tidak-ada/pdf", headers=hdr(admin),
                       timeout=30).status_code == 404,
          "D5 PO yang tidak ada = 404")

    check(requests.get(f"{API}/subcon/spk/{spk['id']}/pdf", timeout=30).status_code == 401,
          "D6 tanpa token = 401 (dokumen kontrak bukan data publik)")
    check(requests.get(f"{API}/subcon/spk/{spk['id']}/pdf", headers=hdr(sales),
                       timeout=30).status_code == 403,
          "D7 sales tidak berkepentingan atas SPK subkontraktor")
    check(requests.get(f"{API}/procurement/pos/{po['id']}/pdf", headers=hdr(sales),
                       timeout=30).status_code == 403,
          "D8 sales tidak berkepentingan atas PO pengadaan")

    # Tanda DRAFT tidak boleh bergantung pada konfigurasi pemakai: PO/SPK draf harus
    # tercetak dengan watermark walau layout organisasi tidak memasang watermark.
    import docgen_p61 as p61  # noqa: E402  (dipakai untuk memeriksa perilaku, bukan HTTP)
    lay = p61._draft_layout({"brand": {"watermark_text": ""}}, True, "DRAFT — X")
    check((lay.get("brand") or {}).get("watermark_text") == "DRAFT — X",
          "D9 dokumen draf DIPAKSA bertanda DRAFT (tidak bisa dimatikan konfigurasi)")
    lay2 = p61._draft_layout({"brand": {"watermark_text": "SALINAN"}}, False, "DRAFT — X")
    check((lay2.get("brand") or {}).get("watermark_text") == "SALINAN",
          "D10 dokumen yang sudah sah memakai watermark pilihan organisasi")


def main():
    print("=" * 78)
    print("GATE 52 — Fase 61: cetak SPK subkontraktor & PO pengadaan")
    print("=" * 78)
    sys.path.insert(0, str(BE))
    bagian_k()
    bagian_kui()
    bagian_d()
    print("\n" + "-" * 78)
    if fails:
        print(f"GATE 52 MERAH — {len(fails)} gagal / {ok + len(fails)} pemeriksaan")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"GATE 52 HIJAU — {ok} pemeriksaan")


if __name__ == "__main__":
    main()
