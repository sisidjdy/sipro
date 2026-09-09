#!/usr/bin/env python3
"""_patch_label_ids.py — TAUTKAN <Label> ke kotak isiannya (satu kali jalan, Fase 38).

Masalah yang ditutup (temuan D5 `scripts/ui_audit_dialogs.py`): pola yang dipakai hampir
di semua formulir SIPRO adalah

    <div className="space-y-1.5"><Label>Nama</Label><Input value=… /></div>

Label-nya TIDAK tertaut ke kotak isian: mengklik tulisan "Nama" tidak memindahkan kursor ke
kotaknya, pembaca layar hanya menyebut "kotak teks" tanpa nama, dan penguji otomatis tidak
punya pegangan selain urutan DOM. Pada field yang juga tidak punya placeholder, kotak itu
benar-benar bisu.

Skrip ini melakukan transformasi mekanis yang aman:
  * hanya untuk `<Label>` TANPA atribut apa pun (jadi tidak menimpa htmlFor yang sudah ada),
  * yang PERSIS diikuti `<Input …>` / `<Textarea …>` TANPA `id=` dan tanpa `aria-label`,
  * `id` dibentuk dari nama berkas + teks label (di-slug), dijamin unik per berkas,
  * tidak menyentuh baris lain, tidak mengubah urutan atribut lain.

Jalankan: python3 scripts/_patch_label_ids.py [--dry]
Setelah jalan, `scripts/verify_ui_surfaces.py` menjaga pola ini tidak kembali.
"""
import re
import sys
import unicodedata
from pathlib import Path

FE = Path(__file__).resolve().parent.parent / "frontend" / "src"
PAT = re.compile(
    r"<Label>([^<>{}]{1,60})</Label>(\s*)<(Input|Textarea)\b([^>]*?)(/?)>",
    re.S,
)


def slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return re.sub(r"-{2,}", "-", t)[:34] or "field"


def patch(path: Path, dry: bool) -> int:
    src = path.read_text(encoding="utf-8")
    used = set(re.findall(r'\bid="([^"]+)"', src))
    base = slug(path.stem)
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        text, gap, tag, attrs, closing = m.groups()
        if re.search(r"\bid=", attrs) or "aria-label" in attrs:
            return m.group(0)
        ident = f"{base}-{slug(text)}"
        n = 2
        while ident in used:
            ident = f"{base}-{slug(text)}-{n}"
            n += 1
        used.add(ident)
        count += 1
        return (f'<Label htmlFor="{ident}">{text}</Label>{gap}'
                f'<{tag} id="{ident}"{attrs}{closing}>')

    out = PAT.sub(repl, src)
    if count and not dry:
        path.write_text(out, encoding="utf-8")
    return count


def main():
    dry = "--dry" in sys.argv
    total, files = 0, 0
    for f in sorted(FE.rglob("*.js")):
        if "components/ui/" in str(f):
            continue
        n = patch(f, dry)
        if n:
            files += 1
            total += n
            print(f"  {n:3d}  {f.relative_to(FE)}")
    print(f"\n{'(dry) ' if dry else ''}{total} label ditautkan pada {files} berkas.")


if __name__ == "__main__":
    main()
