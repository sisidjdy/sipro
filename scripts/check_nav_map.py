#!/usr/bin/env python3
"""check_nav_map.py — SIPRO (adopsi pola kn/KN3, config-driven & truthful).

Memvalidasi navigasi NYATA (navigationConfig.js) vs route NYATA (App.js):
  CHECK 1 — setiap item nav LIVE (bukan comingSoon) punya <Route path> di App.js.
  CHECK 2 — item comingSoon TIDAK punya route (jangan pura-pura navigable).
  CHECK 3 — setiap key PAGE_META punya route (agar judul TopBar resolve).
  CHECK 4 — ROLE_HOME_REGISTRY path punya route.
  CHECK 5 — route App.js tercakup nav/PAGE_META/Role-Home (deteksi 'dead page').

KODE MENANG atas DOKUMEN. Exit !=0 bila ada ERROR.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAVFILE = ROOT / "frontend/src/config/navigationConfig.js"
APPFILE = ROOT / "frontend/src/App.js"
errors = []
warns = []


def err(m):
    errors.append(m)
    print(f"  [ERROR] {m}")


def warn(m):
    warns.append(m)
    print(f"  [WARN] {m}")


def ok(m):
    print(f"  [OK] {m}")


def main():
    nav = NAVFILE.read_text(encoding="utf-8", errors="ignore")
    app = APPFILE.read_text(encoding="utf-8", errors="ignore")

    routes = set(re.findall(r'<Route\s+path="([^"]+)"', app))
    concrete = {r for r in routes if r != "*"}

    live_paths, soon_paths = set(), set()
    # PARSING PER-BLOK, bukan per-baris. Ditemukan oleh uji-mutasi M2
    # (`scripts/mutasi_40_ia.py`): item nav boleh memanjang beberapa baris, sehingga
    #     { id: "bi", label: "Analitik & BI", roles: ALL, comingSoon: true,
    #       path: "/analytics", note: "..." },
    # dulu terbaca sebagai DUA hal berbeda — baris `comingSoon` tanpa path dan baris `path`
    # tanpa comingSoon — sehingga item "Segera Hadir" yang PUNYA route lolos gate (CHECK 2
    # tidak pernah melihatnya). Item nav tidak punya kurung kurawal bersarang, jadi pola
    # `{...}` tanpa `{` di dalamnya tepat mengambil satu item.
    nav_body = nav.split("export const NAV_STRUCTURE", 1)[-1].split("export function", 1)[0]
    for block in re.findall(r"\{[^{}]*\}", nav_body, re.S):
        mp = re.search(r'path:\s*"([^"]+)"', block)
        if not mp:
            continue
        path = mp.group(1)
        if re.search(r"comingSoon:\s*true", block):
            soon_paths.add(path)
        else:
            live_paths.add(path)

    meta_block = re.search(r"PAGE_META\s*=\s*\{(.*?)\};", nav, re.S)
    meta_keys = set(re.findall(r'"([^"]+)":\s*\{', meta_block.group(1))) if meta_block else set()

    home_block = re.search(r"ROLE_HOME_REGISTRY\s*=\s*\{(.*?)\};", nav, re.S)
    home_paths = set(re.findall(r'path:\s*"([^"]+)"', home_block.group(1))) if home_block else set()

    print("\nCHECK 1 — nav LIVE path punya route App.js")
    for p in sorted(live_paths):
        ok(f"nav '{p}' -> route ada") if p in concrete else err(f"nav LIVE '{p}' TIDAK punya <Route> di App.js")

    print("\nCHECK 2 — comingSoon TIDAK punya route")
    if not soon_paths:
        ok("tidak ada item comingSoon.")
    for p in sorted(soon_paths):
        err(f"comingSoon '{p}' punya route (harus disabled)") if p in concrete else ok(f"comingSoon '{p}' benar tanpa route")

    print("\nCHECK 3 — PAGE_META key punya route")
    for p in sorted(meta_keys):
        ok(f"PAGE_META '{p}' -> route ada") if p in concrete else err(f"PAGE_META '{p}' tidak punya route")

    print("\nCHECK 4 — ROLE_HOME path punya route")
    for p in sorted(home_paths):
        ok(f"Role-Home '{p}' -> route ada") if p in concrete else err(f"Role-Home '{p}' tidak punya route")

    print("\nCHECK 5 — route App.js tercakup nav (deteksi dead page)")
    nav_all = live_paths | home_paths | meta_keys
    for p in sorted(concrete):
        if p == "/login":
            continue
        if p not in nav_all:
            warn(f"route '{p}' tidak ada di nav/PAGE_META/Role-Home (kemungkinan dead page)")
    if all(p in nav_all or p == "/login" for p in concrete):
        ok("semua route tercakup nav.")

    print("-" * 50)
    if errors:
        print(f"NAV MAP FAILED: {len(errors)} error, {len(warns)} warn")
        sys.exit(1)
    print(f"NAV MAP PASSED ({len(warns)} warn)")


if __name__ == "__main__":
    main()
