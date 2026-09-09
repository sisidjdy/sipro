#!/usr/bin/env python3
"""verify_ui_surfaces.py — GATE permukaan tampilan (Fase 38).

Menjaga empat cacat yang NYATA dikeluhkan pemakai ("tidak ada background", "kartu rusak",
"tulisan samar", "label tidak bisa diklik") tidak kembali lagi setelah diperbaiki:

  S1  Kotak isian punya LATAR SENDIRI. shadcn mengirim Input/Textarea/SelectTrigger dengan
      `bg-transparent`; begitu field itu berada di atas panel berwarna (bg-secondary,
      bg-sky-50, kartu peringatan, dialog bertingkat) ia tampak "tanpa background".
  S2  Permukaan mengapung (dialog, sheet, popover, dropdown, isi select, command) memakai
      latar PADAT — bukan transparan/semi — supaya isi halaman di belakangnya tidak menembus.
  S3  Pembungkus tabel berbingkai (`overflow-x-auto` + `border` + `rounded`) menyebut `bg-`.
      Satu pembungkus tanpa latar sudah cukup membuat satu halaman terlihat rusak
      (terbukti pada layar Kalibrasi: panel 698x1826 tanpa latar).
  S4  Setiap `<Label>` yang berdiri tepat sebelum `<Input>/<Textarea>` TERTAUT (htmlFor/id).
      Tanpa itu: klik label tidak memindahkan kursor, pembaca layar tidak menyebut nama
      field, dan penguji hanya bisa berpegang pada urutan DOM.
  S5  Legenda grafik Recharts memakai `formatter` (warna tulisan legenda bawaan Recharts =
      warna garis; untuk seri amber hanya 2.1:1 terhadap latar putih).

Semua aturan lahir dari pengukuran, bukan selera: lihat `scripts/ui_audit_shots.py`
(kartu tanpa latar) dan `scripts/ui_audit_dialogs.py` (temuan D1/D2/D5/D6).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend" / "src"
UI = FE / "components" / "ui"

ok_count = 0
fails: list = []


def check(cond: bool, label: str, detail=None) -> bool:
    global ok_count
    if cond:
        ok_count += 1
        print(f"  PASS  {label}")
        return True
    fails.append(label)
    print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))
    return False


def head(t: str):
    print(f"\n{t}\n" + "-" * len(t))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def strip_comments(src: str) -> str:
    """Buang komentar supaya penjelasan di dalam kode tidak ikut terbaca sebagai class."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def class_with(src: str, needle: str) -> str:
    """String className yang MEMUAT penanda tertentu (mis. 'flex h-9 w-full').

    Dicari dari posisi penanda lalu dilebarkan sampai batas kutip terdekat — bukan dengan
    memasangkan kutip dari awal berkas (cara itu salah bila ada kutip lain di atasnya,
    dan pernah membuat gate ini lolos padahal class-nya tidak terbaca sama sekali).
    """
    s = strip_comments(src)
    i = s.find(needle)
    if i < 0:
        return ""
    start = max(s.rfind('"', 0, i), s.rfind("'", 0, i), s.rfind("`", 0, i))
    q = s[start] if start >= 0 else '"'
    end = s.find(q, i)
    if start < 0 or end < 0:
        return ""
    return s[start + 1:end]


# ------------------------------------------------------------------ S1 field punya latar
def audit_fields():
    head("S1. Kotak isian punya latar sendiri (bukan bg-transparent bawaan shadcn)")
    inp = read(UI / "input.jsx")
    cls = class_with(inp, "flex h-9 w-full rounded-md border")
    check("bg-background" in cls, "Input memakai bg-background", cls[:80])
    # `file:bg-transparent` sah (itu tombol pilih berkas di dalam field, bukan field-nya).
    check(bool(cls) and not re.search(r"(?<!file:)bg-transparent", cls),
          "Input tidak memakai bg-transparent untuk permukaan field")
    ta = class_with(read(UI / "textarea.jsx"), "flex min-h-")
    check("bg-background" in ta, "Textarea memakai bg-background", ta[:80])
    check(bool(ta) and "bg-transparent" not in ta, "Textarea tidak memakai bg-transparent")
    sel = read(UI / "select.jsx")
    trig = class_with(sel, "items-center justify-between")
    check("bg-background" in trig, "SelectTrigger memakai bg-background", trig[:80])
    check(bool(trig) and "bg-transparent" not in trig,
          "SelectTrigger tidak memakai bg-transparent")


# ------------------------------------------------------------------ S2 permukaan mengapung
def audit_overlays():
    head("S2. Permukaan mengapung memakai latar padat")
    for f, token in (("dialog.jsx", "bg-background"), ("sheet.jsx", "bg-background"),
                     ("popover.jsx", "bg-popover"), ("dropdown-menu.jsx", "bg-popover"),
                     ("select.jsx", "bg-popover"), ("command.jsx", "bg-popover"),
                     ("alert-dialog.jsx", "bg-background")):
        src = read(UI / f)
        check(token in src, f"{f} memakai {token}")
    # Latar padat: tidak boleh memakai transparansi pada panel utamanya (mis. bg-card/80).
    for f in ("dialog.jsx", "sheet.jsx", "popover.jsx", "dropdown-menu.jsx"):
        src = read(UI / f)
        bad = re.findall(r"bg-(?:background|popover|card)/\d{1,2}\b", src)
        check(not bad, f"{f} tidak memakai latar semi-transparan", bad[:3])


# ------------------------------------------------------------------ S3 pembungkus tabel
def audit_table_wrappers():
    head("S3. Pembungkus tabel berbingkai menyebut latar")
    bad = []
    for f in sorted(FE.rglob("*.js")):
        if "components/ui/" in str(f):
            continue
        src = read(f)
        for m in re.finditer(r'className=(?:\{)?["\'`]([^"\'`]{10,300})["\'`]', src):
            cls = m.group(1)
            if "overflow-x-auto" not in cls or "border" not in cls or "rounded" not in cls:
                continue
            if re.search(r"\bbg-[a-z]", cls):
                continue
            bad.append(f"{f.relative_to(FE)}:{src[:m.start()].count(chr(10)) + 1} → {cls[:70]}")
    check(not bad, "semua pembungkus tabel berbingkai punya latar", bad[:5])


# ------------------------------------------------------------------ S4 label tertaut
def audit_label_links():
    head("S4. Label tertaut ke kotak isiannya")
    pat = re.compile(r"<Label>([^<>{}]{1,60})</Label>\s*(?:\{[^}]*\}\s*)?"
                     r"<(Input|Textarea)\b([^>]*?)/?>", re.S)
    bad = []
    for f in sorted(FE.rglob("*.js")):
        if "components/ui/" in str(f):
            continue
        src = read(f)
        for m in pat.finditer(src):
            text, tag, attrs = m.groups()
            if re.search(r"\bid=", attrs) or "aria-label" in attrs:
                continue
            bad.append(f"{f.relative_to(FE)}:{src[:m.start()].count(chr(10)) + 1} "
                       f"<Label>{text.strip()[:24]}</Label> → <{tag}> tanpa id")
    check(not bad, "tidak ada Label yang menggantung tanpa tautan ke field", bad[:6])


# ------------------------------------------------------------------ S5 legenda grafik
def audit_chart_legend():
    head("S5. Legenda grafik tidak memakai warna garis untuk tulisannya")
    bad = []
    for f in sorted(FE.rglob("*.js")):
        src = read(f)
        for m in re.finditer(r"<Legend\b([^>]*)>", src):
            if "formatter" not in m.group(1):
                bad.append(f"{f.relative_to(FE)}:{src[:m.start()].count(chr(10)) + 1}")
    check(not bad, "setiap <Legend> memakai formatter warna teks yang terbaca", bad[:5])


def main():
    print("verify_ui_surfaces — gate permukaan tampilan (latar, permukaan mengapung, "
          "label, legenda)")
    audit_fields()
    audit_overlays()
    audit_table_wrappers()
    audit_label_links()
    audit_chart_legend()
    print("\n" + "-" * 58)
    print(f"HASIL verify_ui_surfaces: {ok_count} PASS, {len(fails)} FAIL")
    if fails:
        print("GATE PERMUKAAN TAMPILAN GAGAL:")
        for x in fails:
            print(f"  - {x}")
        sys.exit(1)
    print("GATE PERMUKAAN TAMPILAN PASSED")


if __name__ == "__main__":
    main()
