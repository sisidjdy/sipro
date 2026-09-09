#!/usr/bin/env python3
"""verify_field_names — gate Pola B: nama field uang harus sesuai memory/FIELD_MAP.md.

Item termin AR menyimpan `paid_amount`; invoice menyimpan `paid`. Salah baca tidak melempar
galat, hanya angka nol yang diam (WA-02, DOC-01). Gate ini menolak pola akses yang salah.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
# (regex, penjelasan). Variabel `it`/`item`/`term`/`termin` = item termin → dilarang `paid`.
FORBIDDEN = [
    (re.compile(r"\b(it|item|term|termin|row_item)\s*(\.get\(\s*[\"']paid[\"']|\[\s*[\"']paid[\"']\s*\])"),
     "item termin tidak punya field `paid` — pakai `paid_amount` (FIELD_MAP.md)"),
    (re.compile(r"\binv\s*(\.get\(\s*[\"']paid_amount[\"']|\[\s*[\"']paid_amount[\"']\s*\])"),
     "invoice tidak punya field `paid_amount` — pakai `paid` (FIELD_MAP.md)"),
]
SKIP_DIRS = {"tests", "backups", "__pycache__"}


def main() -> int:
    hits = []
    for path in BACKEND.rglob("*.py"):
        if SKIP_DIRS & set(path.relative_to(BACKEND).parts):
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for rx, why in FORBIDDEN:
                if rx.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()[:90]}  <- {why}")
    print("VERIFY FIELD NAMES (memory/FIELD_MAP.md)\n" + "-" * 60)
    for h in hits:
        print("  [ERROR]", h)
    if hits:
        print(f"FIELD NAMES FAILED: {len(hits)} akses field yang bertentangan dengan FIELD_MAP")
        return 1
    print("FIELD NAMES PASSED: tidak ada akses `paid`/`paid_amount` yang salah bentuk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
