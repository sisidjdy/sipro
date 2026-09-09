#!/usr/bin/env python3
"""verify_api_contract.py — SIPRO FE<->BE contract gate (adopsi pola kn/KN3).

CHECK A — Duplicate route: FastAPI diam-diam pakai definisi TERAKHIR bila ada
           dua (method, path) sama → handler pertama mati senyap.
CHECK B — FE call → BE route exists: setiap `api.<method>('/path')` di frontend
           harus cocok dengan route backend terdaftar (cegah 404 senyap/typo path).

FE base = `${REACT_APP_BACKEND_URL}/api`, jadi path FE relatif (tanpa /api).
Exit 0 = lulus, !=0 = ada ERROR (blokir).
"""
import os
import re
import sys
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:
    pass
sys.path.insert(0, str(ROOT / "backend"))
SRC = ROOT / "frontend" / "src"

errors = 0


def err(msg, detail=""):
    global errors
    errors += 1
    print(f"  [ERROR] {msg}" + (f"\n          {detail}" if detail else ""))


def ok(msg):
    print(f"  [OK] {msg}")


def norm(path):
    """Normalisasi path: ${...} (FE) & {param} (BE) -> '*', buang trailing slash."""
    p = re.sub(r"\$\{[^}]*\}", "*", path)   # FE template literal segments
    p = re.sub(r"\{[^}]*\}", "*", p)        # BE path params
    if len(p) > 1:
        p = p.rstrip("/")
    return p


def load_app():
    import server
    return server.app


def check_duplicates(app):
    print("\nCHECK A — Duplicate route")
    seen = Counter()
    names = defaultdict(list)
    for r in app.routes:
        for m in (getattr(r, "methods", set()) or set()):
            if m in ("HEAD", "OPTIONS"):
                continue
            key = (m, getattr(r, "path", ""))
            seen[key] += 1
            names[key].append(getattr(r, "name", "?"))
    dups = [(k, v) for k, v in seen.items() if v > 1]
    if dups:
        for (m, p), c in dups:
            err(f"Duplicate {m} {p} (x{c}) handlers={names[(m, p)]}",
                "Definisi pertama tidak pernah dipanggil.")
    else:
        ok(f"Tidak ada duplicate route ({len(seen)} route unik).")


def backend_set(app):
    s = set()
    for r in app.routes:
        path = getattr(r, "path", "")
        if not path.startswith("/api"):
            continue
        rel = path[4:] or "/"
        for m in (getattr(r, "methods", set()) or set()):
            if m in ("HEAD", "OPTIONS"):
                continue
            s.add((m, norm(rel)))
    return s


FE_CALL_RE = re.compile(r"""\bapi\.(get|post|put|patch|delete)\(\s*([`'\"])([^`'\"]+?)\2""")


def fe_calls():
    calls = []
    for f in SRC.rglob("*.js"):
        if "components/ui" in str(f):
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in FE_CALL_RE.finditer(text):
            method = m.group(1).upper()
            raw = m.group(3).split("?")[0]
            calls.append((method, norm(raw), f.name, raw))
    return calls


def _match(fe: str, be: str) -> bool:
    """Cocok per segmen: '*' (param FE `${…}` / BE `{…}`) mewakili SATU segmen apa pun."""
    a, b = fe.split("/"), be.split("/")
    return len(a) == len(b) and all(x == y or x == "*" or y == "*" for x, y in zip(a, b))


def check_fe_be(app):
    print("\nCHECK B — FE call -> BE route exists")
    be = backend_set(app)
    fe = fe_calls()
    bad = 0
    for method, npath, fname, raw in fe:
        if not any(m == method and _match(npath, p) for m, p in be):
            err(f"FE {method} '{raw}' ({fname}) tidak cocok route backend manapun.")
            bad += 1
    if not bad:
        ok(f"Semua {len(fe)} panggilan FE cocok dengan route backend.")


def main():
    app = load_app()
    check_duplicates(app)
    check_fe_be(app)
    print("-" * 50)
    if errors:
        print(f"API CONTRACT FAILED: {errors} error")
        sys.exit(1)
    print("API CONTRACT PASSED")


if __name__ == "__main__":
    main()
