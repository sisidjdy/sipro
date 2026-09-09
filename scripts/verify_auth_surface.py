#!/usr/bin/env python3
"""verify_auth_surface.py — GATE Fase 94: permukaan autentikasi & versi Graph API.

  A1  Tidak ada route yang menulis `db.users` (insert / update field role) tanpa `require_permission`.
  A2  Tidak ada endpoint tanpa autentikasi yang menerima field `role` dari payload.
  A3  `POST /api/auth/register` tidak ada lagi (GET → 404, bukan 405).
  A4  Dokumentasi API dimatikan di produksi (`docs_url/redoc_url/openapi_url=None` bila ENV=production).
  A5  Versi Graph API hanya tertulis di `backend/meta_api.py`.
  A6  Login/refresh/logout tetap hidup (tidak ada regresi).
"""
import pathlib
import re
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _wa_common import BASE, BE, check, finish, hdr  # noqa: E402

ROUTERS = sorted((BE / "routers").glob("*.py"))


def route_blocks(src: str):
    """Potong berkas per dekorator @router.<method> → (dekorator+signature, badan)."""
    parts = re.split(r"(?=^@router\.(?:get|post|put|patch|delete)\()", src, flags=re.M)
    return [p for p in parts if p.startswith("@router.")]


def main():
    print("== A1/A2 statis: tulis users & field role harus berpagar require_permission ==")
    bad_users, bad_role = [], []
    for f in ROUTERS:
        for blk in route_blocks(f.read_text()):
            guarded = any(g in blk for g in ("require_permission(", "require_role(", "require_super_admin(",
                                             "Depends(get_current_user", "Depends(current_user", "Depends(require_auth"))
            writes_users = re.search(r"db\.users\.(insert_one|insert_many|update_one|update_many|replace_one)", blk)
            if writes_users and not guarded and "/auth/" not in blk and 'prefix="/auth"' not in f.read_text()[:800]:
                bad_users.append(f"{f.name}: {blk.splitlines()[0]}")
            takes_role = re.search(r"payload\.role|p\.role|body\.role|\[\"role\"\]", blk)
            if takes_role and not guarded and 'prefix="/auth"' not in f.read_text()[:800]:
                bad_role.append(f"{f.name}: {blk.splitlines()[0]}")
    auth_src = (BE / "routers" / "auth_router.py").read_text()
    for blk in route_blocks(auth_src):
        if re.search(r"db\.users\.(insert_one|update_one)", blk) and re.search(r"role", blk) and "require_permission" not in blk:
            if "refresh" not in blk and "logout" not in blk and "login" not in blk:
                bad_users.append(f"auth_router.py: {blk.splitlines()[0]}")
        if re.search(r"payload\.role|p\.role", blk):
            bad_role.append(f"auth_router.py: {blk.splitlines()[0]}")
    check(not bad_users, "A1 tidak ada route tanpa pagar yang menulis db.users", "; ".join(bad_users))
    check(not bad_role, "A2 tidak ada endpoint tanpa pagar yang menerima field role", "; ".join(bad_role))
    check("RegisterRequest" not in (BE / "models.py").read_text(), "A2b RegisterRequest sudah dihapus dari models.py")

    print("== A3 live: /auth/register hilang ==")
    r = requests.get(f"{BASE}/auth/register", timeout=15)
    check(r.status_code == 404, "A3 GET /api/auth/register → 404", f"status {r.status_code}")
    r = requests.post(f"{BASE}/auth/register", json={"email": "x@x.id", "password": "x", "role": "super_admin"}, timeout=15)
    check(r.status_code in (404, 405), "A3b POST /api/auth/register tidak melayani pendaftaran", f"status {r.status_code}")

    print("== A4 statis: dokumentasi API mati di produksi ==")
    srv = (BE / "server.py").read_text()
    check("docs_url=None if _PROD" in srv and "openapi_url=None if _PROD" in srv and 'os.environ.get("ENV") == "production"' in srv,
          "A4 FastAPI(docs_url/redoc_url/openapi_url=None) saat ENV=production")

    print("== A5 statis: satu konstanta versi Graph ==")
    hits = []
    for f in BE.rglob("*.py"):
        if "tests" in f.parts:
            continue
        for i, line in enumerate(f.read_text().splitlines(), 1):
            if "graph.facebook.com/v" in line or re.search(r"graph\.facebook\.com/\{?\"?v\d", line):
                hits.append(f"{f.relative_to(BE)}:{i}")
    check(not hits, "A5 tidak ada literal graph.facebook.com/vNN di luar meta_api.py", "; ".join(hits))
    check("graph.facebook.com/{GRAPH_VERSION}" in (BE / "meta_api.py").read_text(), "A5a meta_api.py menyusun GRAPH_BASE dari GRAPH_VERSION")
    meta = (BE / "meta_api.py").read_text()
    check('os.environ.get("META_GRAPH_VERSION"' in meta and "GRAPH_BASE" in meta, "A5b meta_api.py membaca META_GRAPH_VERSION")
    for mod in ("wa_gateway.py", "capi.py", "ads_adapters/meta.py", "wa_templates_meta.py"):
        check("from meta_api import GRAPH_BASE" in (BE / mod).read_text(), f"A5c {mod} memakai meta_api.GRAPH_BASE")

    print("== A6 live: login/me/refresh/logout ==")
    try:
        h = hdr()
        me = requests.get(f"{BASE}/auth/me", headers=h, timeout=15)
        check(me.status_code == 200, "A6 login + /auth/me hidup", f"status {me.status_code}")
        # Indikator data uji: sesi menyebut apakah lingkungan memakai akun/transaksi demo,
        # dan TopBar menampilkannya sebagai lencana global (bukan mengira data produksi).
        body = me.json().get("data") or {}
        seed_demo = 'SEED_DEMO_USERS="true"' in (BE / ".env").read_text() or "SEED_DEMO_USERS=true" in (BE / ".env").read_text()
        check(body.get("demo_data") is seed_demo,
              "A7 /auth/me.demo_data = SEED_DEMO_USERS (indikasi data uji jujur)", f"{body.get('demo_data')!r}")
        topbar = (BE.parent / "frontend" / "src" / "components" / "layout" / "TopBar.js").read_text()
        check("user?.demo_data" in topbar and "NAV.demoBadge" in topbar,
              "A7b TopBar menampilkan lencana DATA DEMO dari sesi")
        rf = requests.post(f"{BASE}/auth/refresh", headers=h, json={}, timeout=15)
        check(rf.status_code in (200, 401), "A6b /auth/refresh masih terdaftar", f"status {rf.status_code}")
        lo = requests.post(f"{BASE}/auth/logout", headers=h, timeout=15)
        check(lo.status_code in (200, 204), "A6c /auth/logout hidup", f"status {lo.status_code}")
    except Exception as e:  # noqa: BLE001
        check(False, "A6 login", str(e))
    finish("verify_auth_surface")


if __name__ == "__main__":
    main()
