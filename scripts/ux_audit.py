#!/usr/bin/env python3
"""ux_audit.py — SIPRO UX baseline enforcer (adopsi kn/KN3).

Ubah standar UX dari prosa jadi cek EXECUTABLE. Untuk tiap halaman di pages/:
  E1  Halaman pengambil data (api.get) TANPA loading state   -> ERROR
  E2  Halaman pengambil data TANPA error state               -> ERROR
  E3  Halaman tanpa satupun data-testid                       -> ERROR
  W1  Halaman pengambil data tanpa empty-state eksplisit      -> WARN
  W2  Pemakaian alert() (bukan toast/inline)                  -> WARN
Exit !=0 bila ada ERROR.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "frontend" / "src" / "pages"
errors, warns = [], []


def err(m):
    errors.append(m)
    print(f"  [ERROR] {m}")


def warn(m):
    warns.append(m)
    print(f"  [WARN] {m}")


def ok(m):
    print(f"  [OK] {m}")


def main():
    print("UX baseline audit (halaman di src/pages)\n")
    files = sorted(PAGES.glob("*.js"))
    if not files:
        print("  (tidak ada halaman ditemukan)")
    for f in files:
        t = f.read_text(encoding="utf-8", errors="ignore")
        name = f.name
        if "data-testid" not in t:
            err(f"{name}: tidak ada data-testid (wajib untuk testability)")
        else:
            ok(f"{name}: data-testid ada")
        if "api.get(" in t:
            has_loading = re.search(r"loading|Loading", t) is not None
            has_error = re.search(r"\berror\b|ErrorState", t) is not None
            has_empty = re.search(r"EmptyState|empty|Belum ada|Tidak ada", t) is not None
            if not has_loading:
                err(f"{name}: data-page tanpa LOADING state")
            if not has_error:
                err(f"{name}: data-page tanpa ERROR state")
            if not has_empty:
                warn(f"{name}: data-page tanpa EMPTY state eksplisit (dianjurkan)")
            if has_loading and has_error:
                ok(f"{name}: loading+error state ada")
        if "alert(" in t:
            warn(f"{name}: memakai alert() (hindari; pakai toast/inline)")

    audit_ambiguous_row_actions()
    audit_literal_unicode_escapes()

    print("-" * 50)
    if errors:
        print(f"UX AUDIT FAILED: {len(errors)} error, {len(warns)} warn")
        sys.exit(1)
    print(f"UX AUDIT PASSED ({len(warns)} warn)")


# ---------------------------------------------------------------------------
# E4 — Tombol aksi di dalam .map() wajib punya PEMBEDA BARIS.
#
# Latar belakang (temuan nyata iterasi 29): tombol pensil/hapus per baris memakai
# data-testid STATIS yang sama untuk semua baris (mis. 6 fase -> 6 tombol
# `phase-edit-btn` identik). Akibatnya selector `[data-testid='phase-edit-btn']`
# ambigu: agen uji mengklik baris yang salah lalu MELAPORKAN BUG PALSU (dan
# lebih buruk: mengubah data baris yang salah). Tombol khusus-ikon juga tidak
# punya nama aksesibel sama sekali.
#
# Aturan: elemen dengan data-testid statis di dalam .map() harus punya minimal
# satu pembeda baris pada elemen yang sama: aria-label={`...`} ATAU data-*={...}.
# ---------------------------------------------------------------------------
SRC = ROOT / "frontend" / "src"
TESTID_RE = re.compile(r'data-testid="([a-z0-9-]+)"')
DISCRIMINATOR_RE = re.compile(r'(aria-label=\{|data-[a-z-]+=\{)')


def _jsx_elements_in_maps(text):
    """Yield (line_no, element_source) untuk tiap elemen JSX di dalam blok .map()."""
    lines = text.splitlines()
    in_map = False
    depth = 0
    start_line = -1
    for i, ln in enumerate(lines):
        if ".map(" in ln and not in_map:
            in_map, depth, start_line = True, 0, i
        if not in_map:
            continue
        depth += ln.count("(") - ln.count(")")
        if TESTID_RE.search(ln):
            # kumpulkan elemen: dari '<' terakhir sebelum baris ini s/d '>' pertama sesudahnya
            head = i
            while head > start_line and "<" not in lines[head]:
                head -= 1
            tail = i
            while tail < len(lines) - 1 and ">" not in lines[tail]:
                tail += 1
            yield i + 1, "\n".join(lines[head:tail + 1])
        if depth <= 0 and i >= start_line:
            in_map = False


def audit_ambiguous_row_actions():
    print("\nAksi per-baris di dalam .map() (E4: wajib ada pembeda baris)\n")
    checked = 0
    for f in sorted(SRC.rglob("*.js")):
        if "components/ui/" in f.as_posix():
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        if ".map(" not in text or "data-testid" not in text:
            continue
        for line_no, element in _jsx_elements_in_maps(text):
            checked += 1
            if DISCRIMINATOR_RE.search(element):
                continue
            tid = TESTID_RE.search(element).group(1)
            rel = f.relative_to(ROOT).as_posix()
            err(f"{rel}:{line_no}: data-testid='{tid}' statis di dalam .map() tanpa "
                f"pembeda baris (tambahkan aria-label={{`…${{key}}`}} atau data-*={{key}})")
    if checked:
        ok(f"{checked} elemen data-testid di dalam .map() diperiksa")


# ---------------------------------------------------------------------------
# E5 — Escape unicode literal (\uXXXX) di dalam TEKS JSX.
#
# Latar belakang (temuan nyata): di JSX, teks anak elemen BUKAN string literal
# JavaScript, jadi "\u00b7" TIDAK diterjemahkan menjadi "·" — ia tampil apa adanya
# ke pengguna (mis. "Basis: price \u00b7 Trigger: booked" di tab Konfigurasi
# Keuangan). Di dalam string/template literal escape-nya sah, jadi cek ini hanya
# menyalahkan yang berada di posisi teks JSX.
# ---------------------------------------------------------------------------
UNICODE_ESCAPE_RE = re.compile(r"\\u[0-9a-fA-F]{4}")


def _is_jsx_text_escape(line, idx):
    """True bila escape pada posisi idx berada di TEKS JSX (bukan di dalam string)."""
    before = line[:idx]
    # hitung kutip yang belum ditutup sebelum posisi ini
    for quote in ('"', "'", "`"):
        if before.count(quote) % 2 == 1:
            return False
    # teks JSX selalu berada setelah '>' pembuka pada baris yang sama,
    # atau pada baris teks murni (tanpa tanda '=' atribut sebelum escape)
    return ">" in before or "=" not in before


def audit_literal_unicode_escapes():
    print("\nEscape unicode literal di teks JSX (E5: harus karakter asli)\n")
    hits = 0
    for f in sorted(SRC.rglob("*.js")):
        if "components/ui/" in f.as_posix():
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for m in UNICODE_ESCAPE_RE.finditer(line):
                if _is_jsx_text_escape(line, m.start()):
                    hits += 1
                    err(f"{f.relative_to(ROOT).as_posix()}:{n}: '{m.group(0)}' di TEKS JSX "
                        f"akan tampil apa adanya ke pengguna — pakai karakter aslinya")
    if not hits:
        ok("tidak ada escape unicode literal di teks JSX")


if __name__ == "__main__":
    main()
