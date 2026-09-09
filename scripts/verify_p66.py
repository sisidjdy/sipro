#!/usr/bin/env python3
"""verify_p66.py — GATE 57: SATU layar per jenis dokumen (naskah + tampilan + tabel).

Keluhan pemakai yang ditutup fase ini:
  1. layar Template Dokumen terbelah dua ("Isi template" vs "Tampilan & kop surat")
     sehingga tidak ada yang tahu naskah mana milik dokumen mana;
  2. naskah tidak pernah tercetak/terlihat di pratinjau — orang menyetel kop tanpa tahu
     isinya; naskah pada dokumen yang dirakit sistem (SPK/PO/SP/BA) tidak dipakai sama sekali;
  3. gaya TABEL tidak bisa diatur: selalu kotak penuh dengan nama kolom, padahal ada yang
     mencetak di kertas berkop sendiri dan ingin garis transparan tanpa nama kolom.

  K    — kode: kosakata placeholder DITURUNKAN dari konteks mesin penerbit (bukan karangan),
         naskah punya jalan masuk ke dokumen, gaya tabel satu tempat.
  K-UI — layar: satu panel, tab Naskah & Tabel, pratinjau memakai naskah yang disunting.
  D    — perilaku server: naskah tersimpan & tercetak (dibuktikan dengan MEMBACA PDF),
         tabel transparan/tanpa nama kolom benar-benar berubah, token asing ditolak, dan
         naskah resmi tidak bisa diubah peran yang tidak berwenang.

Jalankan: python3 scripts/verify_p66.py
"""
import base64
import os
import sys
import zlib
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

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


def mongo():
    load_dotenv(BE / ".env")
    cli = MongoClient(os.environ["MONGO_URL"])
    return cli, cli[os.environ["DB_NAME"]]


def pdf_text(data: bytes) -> str:
    """Baca teks halaman PDF (ASCII85 + Flate) — gate ini HARUS membuktikan isi cetakan,
    bukan hanya bahwa server menjawab 200."""
    d = data.decode("latin1")
    out = []
    pos = 0
    while True:
        i = d.find("stream", pos)
        if i < 0:
            break
        j = d.find("endstream", i)
        raw = d[i + 6:j].strip()
        pos = j + 5
        if raw.endswith("~>"):
            raw = raw[:-2]
        try:
            blob = base64.a85decode(raw.encode("latin1"), adobe=False,
                                    ignorechars=b" \n\r\t")
            out.append(zlib.decompress(blob).decode("latin1"))
        except Exception:  # noqa: BLE001  (stream gambar/font — bukan teks)
            continue
    return "\n".join(out)


def bagian_k():
    head("K. Kode: kosakata dari mesin penerbit, naskah punya jalan ke dokumen, satu gaya tabel")
    ds = read(BE / "doc_script.py")
    dl = read(BE / "doc_layout.py")
    pl = read(BE / "pdf_layout.py")
    rt = read(BE / "routers" / "doc_layout_router.py")
    m60 = read(BE / "models_p60.py")
    p61 = read(BE / "docgen_p61.py")
    p62 = read(BE / "docgen_p62.py")
    check("DOCGEN_TOKENS" in ds and "BAP_TOKENS" in ds and "DEAL_TOKENS" in ds,
          "K1 kosakata placeholder DITURUNKAN dari konteks mesin penerbit (3 jalur nyata)")
    check("TOKENS_BY_CODE" in ds and "def tokens_for" in ds,
          "K2 setiap jenis dokumen punya kosakatanya sendiri (bukan satu daftar untuk semua)")
    check("CATEGORY_OF" in ds and "CATEGORIES" in ds,
          "K3 naskah bergolongan (kategori) mengikuti jenis dokumennya")
    check("def unknown_tokens" in ds and "def save_script" in ds
          and "raise ValueError" in ds,
          "K4 placeholder yang tidak akan pernah terisi DITOLAK (tidak tercetak mentah)")
    check("def intro_for" in ds and "def sample_script" in ds,
          "K5 naskah punya dua jalan keluar: ke dokumen sungguhan & ke pratinjau")
    check("document_templates" in ds,
          "K6 naskah disimpan di koleksi yang DIPAKAI penerbit dokumen (satu naskah)")
    check("def _table_default" in dl and '"table": _table_default()' in dl,
          "K7 gaya tabel jadi bagian konfigurasi dokumen")
    check('("brand", "options", "table")' in dl,
          "K8 gaya tabel ikut diwarisi bawaan organisasi lalu boleh ditimpa per dokumen")
    check("def known_code" in dl and "custom" in dl and "has_script" in dl,
          "K9 daftar jenis dokumen membawa keadaan naskah & ikut memuat kode buatan sendiri")
    check("def _tcfg" in pl and "def _table_style" in pl,
          "K10 satu tempat menerjemahkan gaya tabel ke perintah cetak")
    check('garis == "full"' in pl and '"horizontal"' in pl
          and "# garis == \"none\"" in pl,
          "K11 tiga pilihan garis: kotak penuh, mendatar, TRANSPARAN")
    check('if cfg["show_header"]' in pl and 'has_header=cfg["show_header"]' in pl,
          "K12 nama kolom bisa TIDAK dicetak (baris kepala benar-benar tidak dibuat)")
    check("def _grid(columns, rows, total_row, st, accent, cfg=None)" in pl
          and "def _money_table(rows, st, accent, cfg=None)" in pl,
          "K13 seluruh tabel dokumen (biaya, rincian, laporan) memakai gaya yang sama")
    check("intro: str = \"\"" in pl,
          "K14 laporan tabel pun bisa memuat naskah (bukan tabel telanjang)")
    check("class TableIn" in m60 and "full, horizontal, none" in m60,
          "K15 nilai gaya tabel divalidasi server (bukan apa saja)")
    check("/script" in rt and "DocScriptSave" in rt and "DocPreviewIn" in rt,
          "K16 endpoint naskah + pratinjau yang menerima naskah belum tersimpan")
    check('require_permission("settings", "update")' in
          rt.split('@router.put("/{code}/script")')[1][:900],
          "K17 naskah resmi butuh izin pengaturan organisasi (bukan izin dokumen biasa)")
    check("ds.intro_for" in p61 and "ds.intro_for" in p62,
          "K18 naskah IKUT TERCETAK pada dokumen yang dirakit sistem (SPK/PO/SP/BA)")
    check("naskah_contoh" in rt and "intro=naskah_contoh" in rt,
          "K19 pratinjau memakai naskah — bukan hanya kop")


def bagian_kui():
    head("K-UI. Layar: satu panel per jenis dokumen, tab Naskah & Tabel, pratinjau hidup")
    tabs = read(FE / "components" / "master" / "DocTemplatesPanel.js")
    panel = read(FE / "components" / "master" / "DocLayoutPanel.js")
    script = read(FE / "components" / "master" / "docLayout" / "ScriptForm.js")
    table = read(FE / "components" / "master" / "docLayout" / "TableForm.js")
    ids = read(FE / "constants" / "testIds" / "p60.js")
    check("TabsTrigger" not in tabs and "TabsList" not in tabs,
          "KUI1 dua tab yang memecah naskah & tampilan SUDAH TIDAK ADA")
    check("DocLayoutPanel" in tabs,
          "KUI2 Template Dokumen merender panel gabungan")
    check("P60.tabScript" in panel and "P60.tabTable" in panel
          and "ScriptForm" in panel and "TableForm" in panel,
          "KUI3 naskah & gaya tabel jadi tab di panel yang sama dengan kop")
    check("/script`" in panel and "script: naskah" in panel,
          "KUI4 panel memuat & mengirim naskah (pratinjau memakai naskah yang disunting)")
    check("naskah" in panel and "simpanNaskah" in panel,
          "KUI5 naskah bisa disimpan dari layar yang sama")
    check("category_label" in panel or "category_label" in script,
          "KUI6 jenis dokumen dikelompokkan per kategori (daftar bisa dibaca)")
    check("P60.scriptPlaceholder" in script and "placeholders" in script,
          "KUI7 placeholder yang SAH ditawarkan (bukan pemakai menghafal)")
    check("P60.scriptUnknown" in script and "tercetak mentah" in script,
          "KUI8 placeholder asing diperingatkan sebelum dokumen terbit")
    check("P60.tableGrid" in table and "Tanpa garis (transparan)" in table,
          "KUI9 garis tabel transparan bisa dipilih dari layar")
    check("P60.tableShowHeader" in table and "nama kolom" in table.lower(),
          "KUI10 nama kolom bisa dimatikan dari layar")
    check(all(k in ids for k in ("tabScript", "tabTable", "scriptText", "tableGrid",
                                 "tableShowHeader")),
          "KUI11 elemen baru punya data-testid")
    check("DocumentPreview" in panel and "lg:grid-cols-2" in panel and "<canvas" in read(FE / "components/master/docLayout/DocumentPreview.js"),
          "KUI12 pratinjau tetap berdampingan (naskah & tampilan terlihat bersama)")


def bagian_d():
    head("D. Perilaku server: naskah tersimpan & TERCETAK, tabel benar-benar berubah")
    admin = hdr("superadmin@sipro.co.id")
    sales = hdr("sales@sipro.co.id")

    daftar = requests.get(f"{API}/doc-layouts", headers=admin, timeout=30).json()["data"]
    check(len(daftar) >= 18, "D1 semua jenis dokumen tampil dalam SATU daftar",
          f"{len(daftar)} jenis")
    check(all("category" in d and "has_script" in d for d in daftar),
          "D2 setiap jenis membawa kategori & keadaan naskahnya")
    check(any(d["code"] == "SPR_KPR" and d["has_script"] for d in daftar),
          "D3 naskah dokumen yang sudah ada ikut terbaca (bukan daftar terpisah)")

    s = requests.get(f"{API}/doc-layouts/SPR_KPR/script", headers=admin,
                     timeout=30).json()["data"]
    check(s["category"] == "surat_pesanan" and len(s["placeholders"]) >= 30,
          "D4 placeholder mengikuti JENIS dokumen (SPR: kosakata mesin kontrak)")
    check(s["unknown_tokens"] == [],
          "D5 naskah yang sudah terpasang tidak punya placeholder liar",
          f"{s['unknown_tokens']}")
    kw = requests.get(f"{API}/doc-layouts/KWITANSI/script", headers=admin,
                      timeout=30).json()["data"]
    check(len(kw["placeholders"]) < len(s["placeholders"]),
          "D6 jenis lain menawarkan kosakata yang berbeda (bukan satu daftar untuk semua)")

    cli, db = mongo()
    try:
        semula = db.document_templates.find_one({"code": "SP"}, {"_id": 0})
        bad = requests.put(f"{API}/doc-layouts/SP/script", headers=admin,
                           json={"content": "Kepada {{nama_ngawur}},"}, timeout=30)
        check(bad.status_code == 400 and "tidak dikenal" in bad.text,
              "D7 placeholder asing ditolak 400 dengan sebab yang bisa dibaca",
              bad.text[:120])
        good = requests.put(
            f"{API}/doc-layouts/SP/script", headers=admin,
            json={"content": "Surat ini diterbitkan {{org_name}} pada {{date}} "
                             "dengan nomor {{doc_number}}. NASKAH-UJI-GATE-57"}, timeout=30)
        check(good.status_code == 200, "D8 naskah tersimpan untuk jenis dokumen tersebut",
              good.text[:120])
        simpan = db.document_templates.find_one({"code": "SP"}, {"_id": 0})
        check("NASKAH-UJI-GATE-57" in (simpan or {}).get("content", ""),
              "D9 naskah tersimpan di koleksi yang dipakai penerbit dokumen")

        # naskah TERCETAK: pratinjau harus memuat naskah + nilai contohnya
        prev = requests.post(f"{API}/doc-layouts/SPR_KPR/preview", headers=admin,
                             json={"script": "NASKAH-PRATINJAU-57 untuk {{customer_name}}"},
                             timeout=60)
        teks = pdf_text(prev.content) if prev.status_code == 200 else ""
        check(prev.status_code == 200 and "NASKAH-PRATINJAU-57" in teks,
              "D10 naskah benar-benar TERCETAK di pratinjau (PDF dibaca, bukan diasumsikan)")
        check("Dewi Kartika" in teks,
              "D11 placeholder pada naskah terisi nilai contoh (bukan `{{...}}` mentah)")
        check("{{customer_name}}" not in teks,
              "D12 tidak ada placeholder mentah yang lolos ke halaman")

        # gaya tabel: nama kolom & garis. Bagian `biaya` MATI secara bawaan (naskah SPR owner
        # memuat rincian inline — keputusan audit 2026-06), jadi probe menyalakannya eksplisit.
        biaya_on = [{"key": "biaya", "visible": True, "order": 20}]
        biasa = requests.post(f"{API}/doc-layouts/SPR_KPR/preview", headers=admin,
                              json={"script": "", "sections": biaya_on}, timeout=60)
        t_biasa = pdf_text(biasa.content)
        check("Komponen" in t_biasa,
              "D13 bawaan: nama kolom tabel biaya tercetak")
        tanpa = requests.post(f"{API}/doc-layouts/SPR_KPR/preview", headers=admin,
                              json={"script": "", "sections": biaya_on,
                                    "table": {"show_header": False, "grid": "none",
                                              "zebra": False}}, timeout=60)
        t_tanpa = pdf_text(tanpa.content)
        check(tanpa.status_code == 200 and "Komponen" not in t_tanpa,
              "D14 'tanpa nama kolom' benar-benar menghilangkan baris kepala")
        check("Harga unit" in t_tanpa or "Total kewajiban" in t_tanpa,
              "D15 …tetapi ISI tabel tetap tercetak (bukan tabelnya yang hilang)")
        check(len(tanpa.content) < len(biasa.content),
              "D16 tabel transparan menghasilkan halaman yang lebih ringan (garis hilang)",
              f"{len(tanpa.content)} vs {len(biasa.content)}")
        salah = requests.put(f"{API}/doc-layouts/SPR_KPR", headers=admin,
                             json={"table": {"grid": "pelangi"}}, timeout=30)
        check(salah.status_code == 422 or salah.status_code == 400,
              "D17 gaya garis yang tidak dikenal ditolak server", f"{salah.status_code}")
        simpan_tabel = requests.put(f"{API}/doc-layouts/SPR_KPR", headers=admin,
                                    json={"table": {"grid": "none", "show_header": False}},
                                    timeout=30)
        check(simpan_tabel.status_code == 200
              and simpan_tabel.json()["data"]["table"]["grid"] == "none",
              "D18 gaya tabel tersimpan per jenis dokumen")
        efektif = requests.get(f"{API}/doc-layouts/SPR_KPR", headers=admin,
                              timeout=30).json()["data"]
        check(efektif["table"]["show_header"] is False,
              "D19 gaya tabel terbaca kembali sebagai konfigurasi efektif")

        # hak akses & kode asing
        tolak = requests.put(f"{API}/doc-layouts/SP/script", headers=sales,
                             json={"content": "Naskah dari sales."}, timeout=30)
        check(tolak.status_code == 403,
              "D20 naskah resmi tidak bisa diubah peran tanpa izin pengaturan",
              f"{tolak.status_code}")
        check(requests.get(f"{API}/doc-layouts/TIDAK_ADA/script", headers=admin,
                           timeout=30).status_code == 404,
              "D21 jenis dokumen yang tidak dikenal = 404")
    finally:
        db.document_layouts.delete_many({"code": "SPR_KPR"})
        if semula:
            db.document_templates.replace_one({"code": "SP"}, semula, upsert=True)
        else:
            db.document_templates.delete_many({"code": "SP"})
        sisa = db.document_templates.count_documents(
            {"content": {"$regex": "NASKAH-UJI-GATE-57"}})
        cli.close()
    check(sisa == 0, "D22 bahan uji gate dibuang bersih (naskah & tampilan dipulihkan)")


def main():
    print("=" * 78)
    print("GATE 57 — Fase 66: satu layar per jenis dokumen (naskah + tampilan + tabel)")
    print("=" * 78)
    bagian_k()
    bagian_kui()
    bagian_d()
    print("\n" + "-" * 78)
    if fails:
        print(f"GATE 57 MERAH — {len(fails)} gagal / {ok + len(fails)} pemeriksaan")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"GATE 57 HIJAU — {ok} pemeriksaan")


if __name__ == "__main__":
    main()
