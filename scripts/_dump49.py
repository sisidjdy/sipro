"""Dump bentuk jawaban endpoint Fase 49 (dipakai saat membangun UI)."""
import json
import sys

import requests

BASE = "http://localhost:8001/api"


def login(email, pw="Sipro#2026"):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def get(path, tok, **params):
    r = requests.get(f"{BASE}{path}", headers={"Authorization": f"Bearer {tok}"},
                     params=params, timeout=60)
    return r.status_code, (r.json() if "json" in r.headers.get("content-type", "") else
                           f"<{r.headers.get('content-type')} {len(r.content)}b>")


def shape(v, depth=0):
    pad = "  " * depth
    if isinstance(v, dict):
        out = []
        for k, val in list(v.items())[:40]:
            if isinstance(val, (dict, list)) and depth < 2:
                out.append(f"{pad}{k}:\n{shape(val, depth + 1)}")
            else:
                s = json.dumps(val, ensure_ascii=False, default=str)
                out.append(f"{pad}{k} = {s[:130]}")
        return "\n".join(out)
    if isinstance(v, list):
        if not v:
            return f"{pad}[] (kosong)"
        return f"{pad}[{len(v)} baris] contoh:\n" + shape(v[0], depth + 1)
    return f"{pad}{json.dumps(v, ensure_ascii=False, default=str)[:130]}"


def main():
    fin = login("finance@sipro.co.id")
    owner = login("owner@sipro.co.id")
    period = "2026-08"
    calls = [
        ("GET /gl/periods", "/gl/periods", owner, {}),
        ("GET /gl/periods/close-check", "/gl/periods/close-check", owner, {"period": period}),
        ("GET /gl/year", "/gl/year", owner, {}),
        ("GET /gl/year/check", "/gl/year/check", owner, {"year": "2026"}),
        ("GET /gl/reports/cash-flow-projects", "/gl/reports/cash-flow-projects", owner,
         {"date_from": "2026-01-01", "date_to": "2026-12-31"}),
        ("GET /gl/reports/owner-pack", "/gl/reports/owner-pack", owner, {"period": period}),
        ("GET /gl/reports/closing-history", "/gl/reports/closing-history", owner, {"limit": 6}),
        ("GET /tax/compliance/periods", "/tax/compliance/periods", fin, {}),
        ("GET /tax/compliance/faktur", "/tax/compliance/faktur", fin, {"period": period}),
        ("GET /tax/compliance/faktur-export/check", "/tax/compliance/faktur-export/check", fin,
         {"period": period}),
        ("GET /tax/compliance/vat-return", "/tax/compliance/vat-return", fin, {"period": period}),
        ("GET /tax/compliance/withholding", "/tax/compliance/withholding", fin, {"period": period}),
        ("GET /tax/compliance/withholding/summary", "/tax/compliance/withholding/summary", fin,
         {"period": period}),
        ("GET /tax/compliance/withholding/candidates", "/tax/compliance/withholding/candidates",
         fin, {"period": period}),
        ("GET /tax/compliance/withholding/config", "/tax/compliance/withholding/config", fin, {}),
        ("GET /tax/compliance/withholding-export/check", "/tax/compliance/withholding-export/check",
         fin, {"period": period}),
        ("GET /ap/bills", "/ap/bills", fin, {}),
        ("GET /tax/faktur-candidates", "/tax/faktur-candidates", fin, {}),
    ]
    for label, path, tok, params in calls:
        code, body = get(path, tok, **params)
        print("=" * 100)
        print(f"{label}  -> {code}")
        print(shape(body) if isinstance(body, (dict, list)) else body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
