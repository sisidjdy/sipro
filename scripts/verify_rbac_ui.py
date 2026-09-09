#!/usr/bin/env python3
"""verify_rbac_ui.py — GATE: LAYAR TIDAK BOLEH MENYALIN MATRIKS RBAC.

Cacat NYATA yang dijaga gate ini (ada di repo ini sampai Fase 42):

  1. **Tombol mati.** `FeesPanel` menampilkan "Ajukan Fee" dan `FeePreviewDialog`
     menampilkan "Terbitkan tagihan fee" untuk **finance**, padahal RBAC sengaja memisahkan
     tugas (sales/marketing MENGAJUKAN, finance MENYETUJUI+MEMBAYAR) sehingga server
     SELALU menjawab 403. Pemakai menekan tombol, gagal, dan tidak tahu kenapa.
  2. **Tombol hilang padahal berhak.** `PeriodClosePanel` menyembunyikan "Buka kembali
     periode" dari **Manajer Keuangan** padahal ia punya `gl:manage` (mencakup approve);
     `PermitsPage` menggabungkan "daftarkan izin" dan "ubah status izin" jadi satu izin
     sehingga Pelaksana Lapangan tak pernah melihat tombol ubah status yang ia berhak pakai.
  3. **Matriks bercabang.** Matriks RBAC bisa diubah admin lewat Pusat Konfigurasi
     (`permission_settings.matrix`). Daftar peran yang ditulis ulang di layar TIDAK ikut
     berubah, jadi layar dan server bisa berbeda pendapat tanpa ada yang tahu.

Karena itu layar wajib memakai izin EFEKTIF `can(resource, action)` dari `GET /auth/me`.
Gate ini memaksa tiga hal:

  A. tidak ada lagi `[...].includes(user?.role)` di frontend, kecuali PENGECUALIAN yang
     terdaftar di sini DAN dijelaskan di dalam berkasnya sendiri;
  B. setiap pasangan `can("resource", "action")` di layar benar-benar DIPAKSAKAN oleh
     backend (`require_permission("resource", "action")`) — salah ketik seperti
     `can("partner", "create")` akan membuat tombol hilang selamanya tanpa error;
  C. bukti NYATA lewat API: peran yang izinnya tidak punya aksi itu memang dijawab 403,
     dan peran yang punya izinnya TIDAK dijawab 403 (jadi menyembunyikan tombolnya salah).

Exit !=0 bila ada FAIL. Uji-mutasi: `scripts/mutasi_41_42.py` (M17–M20).
"""
import pathlib
import re
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
FE = ROOT / "frontend" / "src"
BE = ROOT / "backend"
BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
fails = []

# Pengecualian: pemakaian NAMA PERAN yang memang BUKAN gerbang izin. Tiap berkas di sini
# WAJIB menjelaskan alasannya dengan penanda "PENGECUALIAN SAH" supaya tidak ada yang
# menambah pengecualian diam-diam.
ROLE_USE_ALLOWED = {
    # Memilih TAB BAWAAN sesuai cara kerja peran (semua peran boleh membuka kedua tab).
    "pages/ConstructionPage.js",
    # Meniru aturan empat-mata milik backend yang memang ditulis dengan NAMA PERAN:
    # "tidak boleh opname termin yang diajukan sendiri, kecuali owner/super_admin".
    "components/subcon/ClaimOpnameSheet.js",
}
SKIP_DIRS = {"ui", "node_modules"}
ROLE_COPY = re.compile(r"\[[^\]]*\"(?:owner|super_admin|sales|finance|project_manager)\"[^\]]*\]"
                       r"\s*\.includes\(\s*user|[A-Z_]{3,}\s*\.includes\(\s*user\s*\??\.\s*(?:nav_)?role")


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)
    return bool(cond)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def enforced_pairs() -> set:
    """Pasangan (resource, action) yang BENAR-BENAR dipaksakan backend.

    Dua bentuk penegakan dibaca, sebab keduanya sama nyata:
      1. `require_permission("resource", "action")` sebagai dependency endpoint;
      2. `can(<peran>, "resource", "action")` di dalam badan endpoint — dipakai bila SATU
         endpoint punya dua tingkat kewenangan (mis. Fase 49A: siapa pun ber-`gl:update` boleh
         menutup periode, tetapi MENEROBOS daftar periksa menuntut `gl:close_override`).
         Tanpa membaca bentuk kedua, gate ini akan menuduh layar memakai izin "asing" padahal
         backend menolak 403 dengan izin itu juga.
    """
    pairs = set()
    for path in list(BE.glob("*.py")) + list((BE / "routers").glob("*.py")):
        src = path.read_text(encoding="utf-8", errors="ignore")
        for res, act in re.findall(r'require_permission\(\s*"([a-z_]+)"\s*,\s*"([a-z_]+)"\s*\)',
                                   src):
            pairs.add((res, act))
        for res, act in re.findall(
                r'can\((?:[^()]|\([^()]*\))*?"([a-z_]+)"\s*,\s*"([a-z_]+)"\s*\)', src):
            pairs.add((res, act))
    return pairs


def main():
    files = [p for p in FE.rglob("*.js") if not any(s in p.parts for s in SKIP_DIRS)]

    print("\n1. Tidak ada lagi matriks RBAC yang disalin ke layar")
    offenders, exceptions_seen = [], set()
    for p in sorted(files):
        rel = str(p.relative_to(FE)).replace("\\", "/")
        src = p.read_text(encoding="utf-8", errors="ignore")
        if not ROLE_COPY.search(src):
            continue
        if rel in ROLE_USE_ALLOWED:
            exceptions_seen.add(rel)
            check(f"pengecualian '{rel}' menjelaskan alasannya di berkasnya",
                  "PENGECUALIAN SAH" in src)
            continue
        offenders.append(rel)
    check("tidak ada layar yang menyalin daftar peran RBAC", not offenders,
          ", ".join(offenders[:6]))
    stale = ROLE_USE_ALLOWED - exceptions_seen
    check("daftar pengecualian tidak menyimpan sisa yang sudah bersih", not stale,
          f"sudah tidak memakai nama peran: {', '.join(sorted(stale))}")

    print("\n2. Setiap izin yang dipakai layar BENAR-BENAR dipaksakan backend")
    enforced = enforced_pairs()
    check("daftar izin backend terbaca", len(enforced) > 50, f"{len(enforced)} pasangan")
    used = {}
    for p in sorted(files):
        rel = str(p.relative_to(FE)).replace("\\", "/")
        for res, act in re.findall(r'can\(\s*"([a-z_]+)"\s*,\s*"([a-z_]+)"\s*\)',
                                   p.read_text(encoding="utf-8", errors="ignore")):
            used.setdefault((res, act), []).append(rel)
    check("layar memang memakai izin efektif can()", len(used) >= 20, f"{len(used)} pasangan")
    unknown = {pair: who for pair, who in used.items()
               if pair not in enforced and pair[1] != "view"}
    # `view` diperlakukan longgar: backend memaksakannya sebagai `view_all`/`view_own`
    # (lihat `rbac._permitted`), jadi pasangan ("x", "view") sah walau tidak tertulis apa adanya.
    for pair, who in sorted(unknown.items()):
        check(f"izin can(\"{pair[0]}\", \"{pair[1]}\") dipaksakan backend", False,
              f"tidak ada require_permission-nya; dipakai di {who[0]}")
    check("tidak ada izin layar yang tidak dikenal backend", not unknown,
          f"{len(unknown)} pasangan asing")
    for (res, act), who in sorted(used.items()):
        if act == "view" and not any(r == res for r, _a in enforced):
            check(f"resource '{res}' dikenal backend", False, f"dipakai di {who[0]}")

    # CATATAN (bukan kegagalan): resource yang ADA di matriks RBAC tetapi tidak dipaksakan
    # endpoint mana pun. Admin bisa memberi/mencabut izin itu di Pusat Konfigurasi dan
    # TIDAK ADA yang berubah — rasa kendali yang palsu. Dicetak supaya terlihat, bukan
    # memerahkan gate, karena membetulkannya berarti mengubah izin endpoint yang sudah lulus
    # gate lain (keputusan pemilik, bukan pembersihan sepihak).
    try:
        sys.path.insert(0, str(BE))
        import rbac  # noqa: PLC0415
        declared = set(rbac.DEFAULT_PERMISSIONS)
        idle = sorted(declared - {r for r, _a in enforced})
        if idle:
            print(f"  CATATAN  resource di matriks tapi tidak dipaksakan endpoint: "
                  f"{', '.join(idle)}")
    except Exception as exc:  # noqa: BLE001
        print(f"  CATATAN  tidak bisa membaca DEFAULT_PERMISSIONS ({exc})")

    print("\n3. Bukti NYATA: jawaban server sama dengan yang diputuskan layar")
    admin = login("superadmin@sipro.co.id")
    # (peran, metode, path, payload, harus 403?, alasan)
    probes = [
        ("sales", "post", "/projects", {}, True,
         "sales hanya view_all pada projects"),
        ("sales", "post", "/boq/items", {}, True,
         "sales tidak ada di matriks boq"),
        ("site", "post", "/build/templates/clone",
         {"clone_from": "tidak-ada-gate-rbac-ui", "code": "GATE", "name": "Gate RBAC UI"}, True,
         "hanya SUPERVISOR_ROLES (= pemegang construction:approve)"),
        ("site", "post", "/permits", {}, True,
         "site engineer hanya permits:update, bukan create"),
        ("finance", "post", "/gl/periods/reopen", {"period": "1900-01"}, True,
         "reopen menuntut gl:approve"),
        # Sisi sebaliknya — menyembunyikan tombol dari peran ini justru SALAH:
        ("finlead", "post", "/gl/periods/reopen", {"period": "1900-01"}, False,
         "Manajer Keuangan punya gl:manage (mencakup approve)"),
        ("pm", "post", "/permits", {}, False, "Manajer Proyek punya permits:create"),
    ]
    emails = {"sales": "sales@sipro.co.id", "site": "site@sipro.co.id",
              "finance": "finance@sipro.co.id", "finlead": "finlead@sipro.co.id",
              "pm": "pm@sipro.co.id"}
    tokens = {k: login(v) for k, v in emails.items()}
    for role, method, path, body, want_403, why in probes:
        r = getattr(requests, method)(f"{BASE}{path}", headers=tokens[role], json=body,
                                      timeout=30)
        if want_403:
            check(f"{role} -> {method.upper()} {path} = 403 ({why})",
                  r.status_code == 403, f"got {r.status_code}")
        else:
            # Payload sengaja kosong/mustahil: yang dibuktikan hanyalah "tidak ditolak IZIN".
            check(f"{role} -> {method.upper()} {path} BUKAN 403 ({why})",
                  r.status_code != 403, f"got {r.status_code}")

    print("\n4. `GET /auth/me` benar-benar mengirim izin efektif (bahan baku can())")
    me = requests.get(f"{BASE}/auth/me", headers=tokens["sales"], timeout=20)
    perms = (me.json().get("data") or {}).get("permissions") or {}
    check("peran biasa menerima peta izin", me.status_code == 200 and len(perms) >= 5,
          f"{len(perms)} resource")
    check("izin sales tidak mengaku boleh mendaftarkan mitra",
          "create" not in (perms.get("partners") or []), str(perms.get("partners")))
    me_admin = requests.get(f"{BASE}/auth/me", headers=admin, timeout=20)
    padmin = (me_admin.json().get("data") or {}).get("permissions") or {}
    check("peran FULL_ACCESS ditandai '*' (bukan daftar panjang yang bisa lapuk)",
          padmin.get("*") == ["*"], str(padmin)[:80])

    print("-" * 60)
    if fails:
        print(f"GATE RBAC UI FAILED: {len(fails)} temuan — {fails[:6]}")
        sys.exit(1)
    print("GATE RBAC UI PASSED: layar memakai izin efektif, izinnya dikenal backend, "
          "dan jawaban server cocok dengan keputusan layar")


if __name__ == "__main__":
    main()
