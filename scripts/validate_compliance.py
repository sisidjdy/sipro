#!/usr/bin/env python3
"""validate_compliance.py — SIPRO compliance gate (diperkuat).

A. Batas ukuran file (Dok 17 NFR): router.py<=800, page/komponen.js<=500,
   util/service.js<=300, css<=400.
B. Tidak ada URL backend HARDCODED di frontend (localhost:800x / emergentagent.com).
C. Tidak ada literal `mongodb://` di kode backend (harus dari os.environ).
D. apiClient memakai process.env.REACT_APP_BACKEND_URL (positive check).
Exit !=0 bila ada pelanggaran.
"""
import os
import re
import sys

ROOT = "/app"
failures = []
warns = []

CSS_LIMIT = 400
UTIL_LIMIT = 300
JS_LIMIT = 500
PY_LIMIT = 800
SKIP = {"node_modules", "components/ui", "build", ".git", "__pycache__"}

HARDCODED_URL_RE = re.compile(r"localhost:80\d\d|\.preview\.emergentagent\.com|emergentagent\.com|localhost:3000")


def lines(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return sum(1 for _ in f)


def fail(m):
    failures.append(m)


def check_sizes():
    for base, _dirs, files in os.walk(os.path.join(ROOT, "frontend/src")):
        if any(s in base for s in SKIP):
            continue
        for fn in files:
            p = os.path.join(base, fn)
            if fn.endswith(".css"):
                n = lines(p)
                if n > CSS_LIMIT:
                    fail(f"{p}: {n} > {CSS_LIMIT} (css)")
            elif fn.endswith(".js"):
                limit = UTIL_LIMIT if ("/utils/" in p or "/services/" in p) else JS_LIMIT
                n = lines(p)
                if n > limit:
                    fail(f"{p}: {n} > {limit}")
    for base, _dirs, files in os.walk(os.path.join(ROOT, "backend")):
        if any(s in base for s in SKIP):
            continue
        for fn in files:
            if fn.endswith(".py"):
                p = os.path.join(base, fn)
                n = lines(p)
                if n > PY_LIMIT:
                    fail(f"{p}: {n} > {PY_LIMIT} (py)")


def check_hardcoded_urls():
    for base, _dirs, files in os.walk(os.path.join(ROOT, "frontend/src")):
        if any(s in base for s in SKIP):
            continue
        for fn in files:
            if not fn.endswith((".js", ".jsx")):
                continue
            p = os.path.join(base, fn)
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    if HARDCODED_URL_RE.search(line):
                        fail(f"{p}:{i}: URL backend HARDCODED -> gunakan process.env.REACT_APP_BACKEND_URL")


def check_backend_secrets():
    for base, _dirs, files in os.walk(os.path.join(ROOT, "backend")):
        if any(s in base for s in SKIP):
            continue
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(base, fn)
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    if "mongodb://" in line or "mongodb+srv://" in line:
                        fail(f"{p}:{i}: literal MongoDB URI — harus dari os.environ['MONGO_URL']")


def check_apiclient_env():
    p = os.path.join(ROOT, "frontend/src/services/apiClient.js")
    if not os.path.exists(p):
        warns.append("apiClient.js tidak ditemukan")
        return
    txt = open(p, encoding="utf-8", errors="ignore").read()
    if "process.env.REACT_APP_BACKEND_URL" not in txt:
        fail("apiClient.js tidak memakai process.env.REACT_APP_BACKEND_URL")


def main():
    check_sizes()
    check_hardcoded_urls()
    check_backend_secrets()
    check_apiclient_env()
    if failures:
        print("COMPLIANCE FAILED:")
        for f in failures:
            print("  ✗", f)
        sys.exit(1)
    print("COMPLIANCE PASSED: ukuran file OK, tidak ada hardcoded URL/secret, apiClient pakai env.")


if __name__ == "__main__":
    main()
