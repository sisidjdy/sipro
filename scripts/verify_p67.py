#!/usr/bin/env python3
"""verify_p67.py — GATE 58: kedalaman & konsistensi tampilan (Fase 67).

Keluhan pemakai yang ditutup fase ini: "semua halaman masih sangat flat — kartu, tombol,
search bar warnanya sama dengan latar; aksi penting tidak terlihat penting; ukuran tulisan
tidak konsisten antar halaman."

  T  — TOKEN: kanvas benar-benar berbeda dari kartu, ada token bayangan & permukaan cekung,
       aksen dipertegas (dan mode gelap ikut punya semua token itu).
  P  — PRIMITIF: Button/Input/Select/Card/Tabs/Table membawa kedalaman + keadaan fokus 2px,
       sehingga SELURUH halaman ikut membaik tanpa menyentuh tiap berkas.
  K  — KONSISTENSI: judul halaman memakai satu kelas (`page-title`), keterangan halaman
       dibatasi lebarnya (`page-desc`), dan tidak ada lagi `<h1>` dengan ukuran sendiri.
  A  — AFORDANSI: kotak pencarian punya ikon + latar sendiri, status pill punya titik warna,
       kartu angka punya garis aksen, dan kartu mentah tidak lagi tanpa bayangan.

Jalankan: python3 scripts/verify_p67.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend" / "src"
UI = FE / "components" / "ui"
PAT = FE / "components" / "patterns"

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


def bagian_token():
    head("T. Token: kanvas berlapis, bayangan, aksen dipertegas")
    css = read(FE / "index.css")
    check("--background: 220 20% 96%" in css,
          "T1 kanvas slate dingin (bukan krem yang menyatu dengan kartu putih)")
    check("--surface-sunken" in css and "--surface-raised" in css,
          "T2 ada permukaan CEKUNG & NAIK sebagai token (tiga lapis, bukan satu)")
    check("--shadow-card" in css and "--shadow-raised" in css,
          "T3 bayangan jadi token — satu bahasa kedalaman untuk seluruh aplikasi")
    check("--primary: 194 92% 27%" in css and "--primary-hover" in css,
          "T4 aksen teal/biru dipertegas + punya keadaan hover sendiri")
    check(css.count("--surface-sunken") >= 2 and css.count("--shadow-card") >= 2,
          "T5 mode gelap juga punya token permukaan & bayangan (tidak pincang)")
    check("--border: 215 18% 85%" in css,
          "T6 garis batas benar-benar terlihat di atas kanvas")
    for kelas in ("page-title", "page-desc", "section-title", "eyebrow", "surface-card",
                  "surface-sunken", "toolbar", "search-field", "money", "row-danger"):
        pass
    check(all(f".{k}" in css for k in ("page-title", "page-desc", "section-title", "eyebrow",
                                       "toolbar", "search-field", "money", "row-danger")),
          "T7 resep bersama (judul, keterangan, toolbar, search, uang, baris genting) ada")
    check("font-family" in css and 'Space Grotesk' in css and 'Inter' in css,
          "T8 jenis huruf TIDAK diganti (permintaan pemakai) — hanya ukurannya dirapikan")


def bagian_primitif():
    head("P. Primitif: kedalaman & hierarki aksi di lapisan bersama")
    btn = read(UI / "button.jsx")
    inp = read(UI / "input.jsx")
    sel = read(UI / "select.jsx")
    card = read(UI / "card.jsx")
    tabs = read(UI / "tabs.jsx")
    table = read(UI / "table.jsx")
    check("primary-hover" in btn and "hover:shadow-md" in btn,
          "P1 tombol utama punya keadaan hover yang terasa (warna + bayangan)")
    check("focus-visible:ring-2" in btn and "ring-offset-2" in btn,
          "P2 cincin fokus 2px — pemakai papan tunjuk tidak kehilangan posisi")
    check("bg-card" in btn and "border-input" in btn,
          "P3 tombol outline punya LATAR sendiri (tidak menembus kartu)")
    check("border border-border bg-secondary" in btn,
          "P4 tombol sekunder dibedakan dari latar (garis + permukaan)")
    check("active:translate-y" in btn, "P5 tombol memberi umpan balik saat ditekan")
    check("focus-visible:border-primary" in inp and "focus-visible:ring-2" in inp,
          "P6 kotak isian menandai fokus dengan warna + cincin")
    check("focus:border-primary" in sel and "focus:ring-2" in sel,
          "P7 pemilih (Select) ikut aturan fokus yang sama")
    check("shadow-[var(--shadow-card)]" in card and "border-border" in card,
          "P8 kartu terangkat dari kanvas (bayangan token + garis penuh)")
    check("surface-sunken" in tabs and "data-[state=active]:bg-card" in tabs,
          "P9 tab bergaya segmented: jalur cekung, tab aktif naik")
    check("flex-wrap" in tabs,
          "P10 banyak tab boleh membungkus (dulu saling menimpa di halaman Keuangan)")
    check("surface-sunken" in table and "uppercase" in table,
          "P11 kepala tabel punya permukaan & huruf yang membedakannya dari isi")
    check("even:bg-" in table and "hover:bg-accent" in table,
          "P12 baris tabel belang + hover (baris panjang mudah diikuti)")


def bagian_konsistensi():
    head("K. Konsistensi tulisan antar halaman")
    liar = []
    for f in list((FE / "pages").rglob("*.js")) + list((FE / "components").rglob("*.js")):
        src = read(f)
        for m in re.finditer(r"<h1\b[^>]*className=\"([^\"]*)\"", src):
            cls = m.group(1)
            if "page-title" in cls:
                continue
            if re.search(r"text-(xl|2xl|3xl|4xl)", cls):
                liar.append(f"{f.relative_to(FE)}:{src[:m.start()].count(chr(10)) + 1} → {cls[:48]}")
    check(not liar, "K1 semua judul halaman memakai satu kelas (`page-title`)", liar[:5])
    pakai_title = sum(1 for f in (FE / "pages").rglob("*.js") if "page-title" in read(f))
    check(pakai_title >= 20, "K2 kelas judul dipakai luas di halaman", f"{pakai_title} berkas")
    pakai_desc = sum(1 for f in list((FE / "pages").rglob("*.js"))
                     + list((FE / "components").rglob("*.js")) if "page-desc" in read(f))
    check(pakai_desc >= 10,
          "K3 keterangan halaman dibatasi lebarnya (tidak melebar melintasi layar)",
          f"{pakai_desc} berkas")
    pakai_section = sum(1 for f in list((FE / "pages").rglob("*.js"))
                        + list((FE / "components").rglob("*.js"))
                        if "section-title" in read(f))
    check(pakai_section >= 15, "K4 judul bagian juga satu ukuran", f"{pakai_section} berkas")


def bagian_afordansi():
    head("A. Afordansi: pencarian, status, kartu angka, kartu mentah")
    si = read(PAT / "SearchInput.js")
    toolbar = read(PAT / "DataTableToolbar.js")
    kpi = read(PAT / "KpiCard.js")
    css = read(FE / "index.css")
    empty = read(PAT / "EmptyState.js")
    check("Search" in si and "search-field pl-9" in si,
          "A1 ada komponen pencarian bersama: ikon + latar + ruang untuk ikonnya")
    check("search-field pl-9" in toolbar and "toolbar" in toolbar,
          "A2 baris alat tabel punya permukaannya sendiri (tidak menempel ke latar)")
    tanpa_ikon = []
    for f in list((FE / "pages").rglob("*.js")) + list((FE / "components").rglob("*.js")):
        src = read(f)
        for m in re.finditer(r'<Input\b[^>]*placeholder="Cari[^"]*"', src, re.S):
            blok = src[max(0, m.start() - 400):m.end()]
            if "Search" not in blok and "SearchInput" not in blok:
                tanpa_ikon.append(f"{f.relative_to(FE)}:{src[:m.start()].count(chr(10)) + 1}")
    check(not tanpa_ikon, "A3 tidak ada kotak pencarian tanpa ikon/afordansi", tanpa_ikon[:5])
    check(".status-pill::before" in css,
          "A4 status pill punya titik warna (dikenali dari bentuk+warna, bukan warna saja)")
    check("absolute inset-x-0 top-0" in kpi and "TONE" in kpi,
          "A5 kartu angka punya garis aksen atas sesuai jenis kabarnya")
    check("hover:shadow-[var(--shadow-raised)]" in kpi,
          "A6 kartu angka yang bisa ditelusuri terangkat saat disentuh kursor")
    check("shadow-[var(--shadow-card)]" in empty,
          "A7 keadaan kosong tetap berupa permukaan (bukan bidang kosong yang tampak rusak)")
    mentah = []
    pat = re.compile(r'className="([^"]*\bborder\b[^"]*\bbg-card\b[^"]*)"')
    for f in list((FE / "pages").rglob("*.js")) + list((FE / "components").rglob("*.js")):
        src = read(f)
        for m in pat.finditer(src):
            cls = m.group(1)
            if "shadow" in cls or "border-dashed" in cls or "border-l" in cls:
                continue
            mentah.append(f"{f.relative_to(FE)}:{src[:m.start()].count(chr(10)) + 1}")
    check(len(mentah) <= 5,
          "A8 kartu yang ditulis langsung di halaman tidak lagi tanpa bayangan",
          f"{len(mentah)} sisa: {mentah[:4]}")


def main():
    print("=" * 78)
    print("GATE 58 — Fase 67: kedalaman & konsistensi tampilan (anti-flat)")
    print("=" * 78)
    bagian_token()
    bagian_primitif()
    bagian_konsistensi()
    bagian_afordansi()
    print("\n" + "-" * 78)
    if fails:
        print(f"GATE 58 MERAH — {len(fails)} gagal / {ok + len(fails)} pemeriksaan")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"GATE 58 HIJAU — {ok} pemeriksaan")


if __name__ == "__main__":
    main()
