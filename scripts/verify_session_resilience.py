#!/usr/bin/env python3
"""verify_session_resilience.py — GATE 45 (Fase 54): sesi TIDAK BOLEH mati mendadak, dan
kalau memang berakhir ia harus berakhir dengan JUJUR.

## Cacat nyata yang dijaga gate ini

Laporan uji terakhir Fase 53 (`test_reports/iteration_85.json`, prioritas MEDIUM):
*"Login sessions expire frequently during testing. Users need to re-login multiple times
during extended use."* Empat sebabnya, semuanya terbukti di kode:

  1. **`POST /api/auth/refresh` tidak pernah ada.** Baris pertama `auth_router.py` menulis
     "…, logout, refresh", `create_refresh_token()` dipanggil di login DAN register, cookie
     `refresh_token` disetel 7 hari — dan tidak ada satu baris pun yang membacanya. Sesi mati
     keras di jam ke-24, di tengah orang mengisi rincian biaya kontrak.
  2. **Cookie kedaluwarsa mengalahkan Bearer yang sah.** `security._extract_token` membaca
     cookie dulu, header hanya bila cookie KOSONG. Cookie yang ADA tapi BASI → 401 walau
     header membawa token sempurna. Ini juga penghalang keras bagi (1): sesi yang baru
     diperpanjang justru 401 selamanya karena peramban masih mengirim cookie lama.
  3. **Penyimpanan dibersihkan tanpa memberi tahu React.** `apiClient` menghapus
     `sipro_token` pada 401 tetapi `AuthContext` tetap memegang `user`, jadi aplikasi
     tergambar utuh sementara SEMUA permintaannya gagal — tanpa pesan, tanpa diantar ke
     halaman masuk, dan isian yang sedang dikerjakan hilang.
  4. **Perpanjangan bisa menjadi pintu belakang** (akun/penyewa yang dimatikan hidup 7 hari
     lagi) atau **memindahkan penyewa diam-diam** (`super_admin` yang sedang "bertindak
     sebagai" org lain dipulangkan tanpa pesan; layar menyebut penyewa lama, datanya milik
     penyewa lain).

## Yang diperiksa (K = kode, D = bukti HTTP, P = portal, U = kejujuran layar)

  K1..K12   Backend: urutan kandidat token (header DULU), penolakan hanya bila SEMUA gagal,
            `/auth/refresh` ada + menyetel ulang cookie + gerbang penyewa + mempertahankan
            `active_org_id`, umur cookie dibaca dari satu sumber, tajuk `X-Session-State`
            dibuka lewat CORS.
  K13..K22  Frontend: perpanjangan single-flight (bukan 6 panggilan barengan), 401 tanpa
            respons TIDAK dianggap sesi mati (aturan offline Fase 35), React DIBERI TAHU saat
            sesi berakhir, hanya `expired` yang dicoba diperpanjang, tempat kerja dicatat &
            dipulihkan, dan halaman masuk memakai pembacaan TIDAK merusak.
  D1..D18   Bukti HTTP: perpanjangan bekerja, cookie basi + Bearer sah = 200, sebab 401
            dibedakan mesin, token salah jenis ditolak dua arah, penyewa dipertahankan,
            akun/penyewa yang dicabut tidak bisa memperpanjang, umur cookie = umur token.
  P1..P5    Portal pembeli: kelas cacat yang sama ikut ditutup, dan dua dunia sesi (staf vs
            pembeli) tidak bisa saling menyusup.
  U1..U6    Kejujuran layar: kalimat sesi tidak membocorkan istilah internal, tidak ada
            testId Fase 54 yang mati, dan kamus SSOT cocok dengan konstanta backend.

Gate ini TIDAK meninggalkan jejak: penyewa & akun sementara dibuang lewat
`scripts/_fixture54.py`, dan kebersihannya ikut diperiksa (D18).

Jalankan: python3 scripts/verify_session_resilience.py
"""
import os
import pathlib
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import jwt
import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(BE / ".env")

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
SECRET = os.environ["JWT_SECRET"]
ALG = "HS256"
FAIL = []
PASSED = 0


def check(ok: bool, label: str, detail: str = "") -> bool:
    global PASSED
    if ok:
        PASSED += 1
        print(f"  OK    {label}")
    else:
        FAIL.append(label)
        print(f"  MERAH {label} — {detail}")
    return bool(ok)


def head(t: str) -> None:
    print(f"\n{t}\n" + "-" * len(t))


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def strip_comments(src: str) -> str:
    """Buang komentar: penjelasan di dalam kode tidak boleh dihitung sebagai pemakaian.

    Pelajaran uji-mutasi Fase 51: mencari sebuah nama saja tetap hijau walau kodenya dicabut,
    karena BARIS KOMENTAR/IMPOR sudah memenuhi pencarian. Gate harus melihat KODE.
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    out = []
    for line in src.split("\n"):
        s = line.strip()
        if s.startswith("//") or s.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


def strip_imports(src: str) -> str:
    """Buang baris impor. WAJIB sebelum memeriksa "apakah fungsi ini DIPAKAI".

    Pelajaran mahal `mutasi_51.py` (C10a) yang TERULANG saat membangun gate ini: uji-mutasi
    Fase 54 menemukan lima pemeriksaan gate ini LOLOS — `emitSessionEnded` dicabut dari
    interceptor tetapi gate tetap hijau, karena BARIS IMPOR di puncak berkas sudah memenuhi
    pencarian `"emitSessionEnded" in src`. Sebuah nama yang hanya diimpor dan tidak pernah
    dipanggil adalah kode mati, bukan bukti perilaku.
    """
    return "\n".join(ln for ln in src.split("\n")
                     if not ln.strip().startswith("import ")
                     and not re.match(r"^\s*}\s*from\s+[\"']", ln))


def body(src: str, awal: str, akhir: str = None) -> str:
    """Potongan kode dari penanda `awal` sampai `akhir` (atau akhir berkas).

    Pemeriksaan harus melihat KODE DI TEMPAT YANG BENAR. Contoh nyata dari uji-mutasi gate
    ini: penjaga "galat tanpa respons bukan sesi mati" ada di DUA tempat (perpanjangan
    proaktif dan interceptor). Memeriksa berkas secara utuh membuat pencabutan salah satunya
    tidak terdeteksi — satu penjaga yang tersisa sudah memenuhi pencarian.
    """
    i = src.find(awal)
    if i == -1:
        return ""
    j = src.find(akhir, i + len(awal)) if akhir else -1
    return src[i:j] if j != -1 else src[i:]


def detail(r) -> str:
    try:
        return f"HTTP {r.status_code} {str(r.json())[:180]}"
    except Exception:
        return f"HTTP {r.status_code} {r.text[:180]}"


def j(r):
    try:
        return r.json()
    except Exception:
        return {}


def bearer(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def state(r) -> str:
    return r.headers.get("X-Session-State", "")


def login(email: str, pw: str = PW):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=30)
    if r.status_code != 200:
        return None, None, r
    return j(r).get("access_token"), r.cookies, r


def mint(sub: str, email: str = "", role: str = "", *, typ: str = "access",
         ttl: int = 3600, active_org_id: str = None) -> str:
    p = {"sub": sub, "type": typ,
         "exp": datetime.now(timezone.utc) + timedelta(seconds=ttl)}
    if typ == "access":
        p.update({"email": email, "role": role})
        if active_org_id:
            p["active_org_id"] = active_org_id
    return jwt.encode(p, SECRET, algorithm=ALG)


# ============================================================== K. penjaga di tingkat KODE
def bagian_k():
    head("K. Kode: perbaikan Fase 54 tidak boleh bisa dibatalkan tanpa gate ini merah")
    sec = read(BE / "security.py")
    sec_code = strip_comments(sec)
    auth = read(BE / "routers" / "auth_router.py")
    auth_code = strip_comments(auth)
    srv = strip_comments(read(BE / "server.py"))

    # --- urutan kandidat: header DULU, cookie kemudian (inti cacat 2)
    m = re.search(r"def candidate_tokens\(.*?\n(?=\ndef |\Z)", sec_code, flags=re.S)
    fn = m.group(0) if m else ""
    check(bool(fn), "K1 `candidate_tokens()` ada di security.py")
    i_hdr = fn.find("Authorization")
    i_ck = fn.find("cookies")
    check(i_hdr != -1 and i_ck != -1 and i_hdr < i_ck,
          "K2 header Authorization dibaca SEBELUM cookie (cookie basi tidak menang)",
          f"posisi header={i_hdr} cookie={i_ck}")

    m = re.search(r"def decode_session_tokens\(.*?\n(?=\ndef |\Z)", sec_code, flags=re.S)
    dec = m.group(0) if m else ""
    check("for " in dec and "tokens" in dec,
          "K3 semua kandidat dicoba (bukan hanya satu)")
    check("ExpiredSignatureError" in dec and "continue" in dec,
          "K4 kandidat kedaluwarsa tidak langsung mematikan permintaan (lanjut ke kandidat lain)")
    check('expected_type' in dec,
          "K5 jenis token dipaksa (refresh tidak boleh dipakai sebagai token kerja)")
    check("X-Session-State" in sec_code,
          "K6 sebab penolakan dikirim sebagai tajuk yang bisa dibaca mesin")
    # `claims_ignoring_expiry` HANYA boleh melonggarkan waktu, bukan tanda tangan.
    m = re.search(r"def claims_ignoring_expiry\(.*?\n(?=\ndef |\Z)", sec_code, flags=re.S)
    cig = m.group(0) if m else ""
    check("verify_exp" in cig and "verify_signature" not in cig,
          "K7 pembacaan klaim lewat-waktu tetap MEMERIKSA tanda tangan", cig[:120])

    # --- endpoint refresh
    check('@router.post("/refresh")' in auth,
          "K8 route POST /auth/refresh benar-benar terdaftar")
    m = re.search(r'@router\.post\("/refresh"\).*\Z', auth_code, flags=re.S)
    rf = m.group(0) if m else ""
    check('set_cookie("access_token"' in rf,
          "K9 refresh MENYETEL ULANG cookie access_token (jebakan cookie basi tidak kembali)")
    check("active_org_id" in rf and "claims_ignoring_expiry" in rf,
          "K10 refresh MEMPERTAHANKAN konteks 'bertindak sebagai' penyewa lain")
    check("_tenant_gate" in rf and "is_active" in rf,
          "K11 refresh memakai gerbang akun & penyewa (bukan pintu belakang)")
    check("session_payload" in rf,
          "K12 jawaban refresh memakai profil sesi yang SAMA dengan /login & /me")
    check("86400" not in auth_code and "604800" not in auth_code,
          "K13 umur cookie tidak diketik ulang sebagai angka telanjang (satu sumber)")
    check("expose_headers" in srv and "X-Session-State" in srv,
          "K14 CORS membuka X-Session-State (kalau tidak, layar kembali harus menebak)")

    # --- frontend
    # `strip_imports` WAJIB: uji-mutasi menemukan lima pemeriksaan di bawah ini pernah LOLOS
    # karena baris impor sudah memenuhi pencarian nama, walau pemanggilannya dicabut.
    api = strip_imports(strip_comments(read(FE / "services" / "apiClient.js")))
    ctx = strip_imports(strip_comments(read(FE / "context" / "AuthContext.js")))
    app = strip_imports(strip_comments(read(FE / "App.js")))
    lgn = strip_comments(read(FE / "pages" / "Login.js"))
    pcl = strip_imports(strip_comments(read(FE / "services" / "portalClient.js")))
    psec = strip_comments(read(BE / "portal_security.py"))

    check("renewal" in api and re.search(r"if \(renewal\) return renewal", api) is not None,
          "K15 perpanjangan SINGLE-FLIGHT (6 panel yang 401 barengan = 1 perpanjangan)")

    # Penjaga "tanpa respons ≠ sesi mati" ada di DUA tempat dan keduanya harus utuh:
    # perpanjangan proaktif (pengatur waktu) dan interceptor (jalur 401).
    proaktif = body(api, "export async function renewIfExpiringSoon", "api.interceptors.response")
    inter = body(api, "api.interceptors.response.use(")
    check(re.search(r"if \(!\w+\??\.response\)", proaktif) is not None,
          "K16a perpanjangan proaktif: galat tanpa respons tidak membunuh sesi (Fase 35)")
    check(re.search(r"if \(!\w+\??\.response\)", inter) is not None,
          "K16b jalur 401: galat tanpa respons tidak membunuh sesi (Fase 35)")
    check("emitSessionEnded(" in inter,
          "K17 React DIBERI TAHU dari jalur 401 (cacat 3: dulu hanya storage dibersihkan)")
    check("emitSessionEnded(" in proaktif,
          "K17b React juga diberi tahu bila perpanjangan proaktif gagal")

    # Syarat pemicu perpanjangan dibaca dari KODE, bukan dari ada-tidaknya nama di berkas:
    # mutan yang menghapus `SESSION_STATE.expired` dari SYARAT tetap meninggalkan nama itu di
    # tempat lain, dan gate versi pertama tertipu.
    m = re.search(r"if \(([^)]*)\)\s*\{\s*try\s*\{\s*await renewSession\(\)", inter, flags=re.S)
    cond = m.group(1) if m else ""
    check("SESSION_STATE.expired" in cond,
          "K18 hanya `expired` yang dicoba diperpanjang (syaratnya, bukan sekadar namanya)",
          repr(cond[:80]))
    g = re.search(r"!\w+\.(\w+)", cond)
    penjaga = g.group(1) if g else ""
    check(bool(penjaga) and re.search(r"\." + penjaga + r"\s*=\s*true", inter) is not None,
          "K19 penanda 'sudah diulang' yang DIPERIKSA sama dengan yang DISETEL (tidak ada "
          "gelung tak berujung)", f"penjaga={penjaga!r}")

    check("onSessionEnded(" in ctx,
          "K20 AuthContext benar-benar MEMANGGIL onSessionEnded (bukan hanya mengimpornya)")
    check("rememberReturnTo(" in app,
          "K21 tempat kerja dicatat sebelum pengguna diantar ke halaman masuk")
    # Regresi NYATA yang terjadi saat fase ini dibangun: `takeReturnTo()` dipanggil langsung
    # di dalam render, dan React.StrictMode memanggil render DUA KALI sehingga pemanggilan
    # pertama MEMAKAN tujuannya. Pengguna dijanjikan kembali ke tempat kerjanya lalu tetap
    # didaratkan di Beranda. Penjaganya adalah ref — dan yang diperiksa harus PEMAKAIANNYA.
    check("takeReturnTo(" in app and "useRef(" in app,
          "K22 pembacaan sekali-pakai dijaga ref (aman terhadap render ganda StrictMode)")
    check("peekReturnTo(" in lgn and "takeReturnTo" not in lgn,
          "K23 halaman masuk hanya MELIHAT tujuan kembali (tidak menghabiskannya)")
    check("401" in pcl and ("onPortalSessionEnded" in pcl or "listeners" in pcl),
          "K24 portal pembeli juga mengakhiri sesinya dengan jujur")
    psec_c = re.search(r"def _candidates\(.*?\n(?=\ndef |\Z)", psec, flags=re.S)
    pc = psec_c.group(0) if psec_c else ""
    ip_h = pc.find("Authorization")
    ip_c = pc.find("portal_token")
    check(bool(pc) and ip_h != -1 and ip_c != -1 and ip_h < ip_c,
          "K25 portal juga membaca header SEBELUM cookie (kelas cacat sama)",
          f"header={ip_h} cookie={ip_c}")


# ============================================================== D. bukti HTTP
def bagian_d():
    head("D. Bukti HTTP: sesi bisa diperpanjang, dan penolakannya menyebut sebab yang benar")
    tok, ck, r = login("superadmin@sipro.co.id")
    if not check(tok is not None, "D0 super admin bisa masuk", detail(r)):
        return None
    me = j(requests.get(f"{BASE}/auth/me", headers=bearer(tok), timeout=30)).get("data") or {}
    uid, email, role = me.get("id"), me.get("email"), me.get("role")

    # --- umur cookie tidak boleh melebihi umur token di dalamnya
    setck = r.headers.get("Set-Cookie", "") or ""
    m = re.search(r"access_token=[^;]+;[^,]*?Max-Age=(\d+)", setck, flags=re.I)
    exp = jwt.decode(tok, SECRET, algorithms=[ALG], options={"verify_exp": False})["exp"]
    sisa = exp - int(time.time())
    check(bool(m) and abs(int(m.group(1)) - sisa) <= 10,
          "D1 umur cookie access = umur token di dalamnya (tidak ada dua angka yang bisa beda)",
          f"cookie={m.group(1) if m else '?'} token={sisa}")

    # --- INTI CACAT 2
    basi = mint(uid, email, role, ttl=-60)
    rr = requests.get(f"{BASE}/auth/me", cookies={"access_token": basi},
                      headers=bearer(tok), timeout=30)
    check(rr.status_code == 200,
          "D2 cookie KEDALUWARSA + Bearer SAH = 200 (header menang)", detail(rr))
    rr = requests.get(f"{BASE}/auth/me", cookies={"access_token": "bukan.jwt"},
                      headers=bearer(tok), timeout=30)
    check(rr.status_code == 200, "D3 cookie SAMPAH + Bearer SAH = 200", detail(rr))
    rr = requests.get(f"{BASE}/auth/me", cookies={"access_token": tok},
                      headers=bearer(basi), timeout=30)
    check(rr.status_code == 200, "D4 Bearer basi + cookie SAH = 200 (kandidat lain dicoba)",
          detail(rr))

    # --- sebab 401 dibedakan mesin
    for kirim, harap, label in (
        ({}, "missing", "D5 tanpa bekal apa pun -> missing"),
        ({"headers": bearer(basi)}, "expired", "D6 token kedaluwarsa -> expired"),
        ({"headers": bearer("bukan.jwt")}, "invalid", "D7 token cacat -> invalid"),
    ):
        rr = requests.get(f"{BASE}/auth/me", timeout=30, **kirim)
        check(rr.status_code == 401 and state(rr) == harap, label,
              f"{rr.status_code}/{state(rr)}")
        d = j(rr).get("detail")
        check(isinstance(d, str), f"{label[:2]}b pesannya KALIMAT (bukan objek → [object Object])",
              repr(d))
        low = str(d).lower()
        check(not any(k in low for k in ("token", "jwt", "cookie", "bearer")),
              f"{label[:2]}c pesannya tidak membocorkan istilah internal", repr(d))

    # --- token salah jenis, dua arah
    rfk = mint(uid, typ="refresh", ttl=3600)
    rr = requests.get(f"{BASE}/auth/me", headers=bearer(rfk), timeout=30)
    check(rr.status_code == 401, "D8 token refresh ditolak sebagai token kerja", detail(rr))
    rr = requests.post(f"{BASE}/auth/refresh", cookies={"refresh_token": tok}, timeout=30)
    check(rr.status_code == 401, "D9 token kerja ditolak sebagai bekal perpanjangan",
          detail(rr))

    # --- perpanjangan
    time.sleep(1.2)
    rr = requests.post(f"{BASE}/auth/refresh", cookies=ck, timeout=30)
    check(rr.status_code == 200, "D10 /auth/refresh bekerja", detail(rr))
    body = j(rr)
    baru = body.get("access_token")
    kurang = [k for k in ("permissions", "active_org", "home_org_id", "is_switched", "role")
              if k not in (body.get("data") or {})]
    check(not kurang, "D11 profil sesi hasil refresh LENGKAP (satu bentuk)", str(kurang))
    exp2 = jwt.decode(baru, SECRET, algorithms=[ALG],
                      options={"verify_exp": False})["exp"] if baru else 0
    check(exp2 > exp, "D12 batas waktu benar-benar bergeser ke depan", f"{exp} -> {exp2}")
    kerja = requests.get(f"{BASE}/leads", headers=bearer(baru), params={"limit": 1}, timeout=30)
    check(kerja.status_code == 200, "D13 pekerjaan bisa dilanjutkan dengan token baru",
          detail(kerja))
    mati = mint(uid, typ="refresh", ttl=-30)
    rr = requests.post(f"{BASE}/auth/refresh", cookies={"refresh_token": mati}, timeout=30)
    check(rr.status_code == 401 and state(rr) == "expired",
          "D14 bekal yang kedaluwarsa tidak bisa dibangkitkan (batas 7 hari nyata)",
          f"{rr.status_code}/{state(rr)}")

    # --- penyewa dipertahankan
    sw = requests.post(f"{BASE}/admin/orgs/org-nusa/switch", headers=bearer(baru), timeout=30)
    if sw.status_code == 200:
        tsw = j(sw).get("access_token")
        rr = requests.post(f"{BASE}/auth/refresh",
                           cookies={"refresh_token": ck.get("refresh_token"),
                                    "access_token": tsw}, timeout=30)
        prof = j(rr).get("data") or {}
        check(rr.status_code == 200 and (prof.get("active_org") or {}).get("id") == "org-nusa",
              "D15 refresh MEMPERTAHANKAN penyewa aktif (tidak memulangkan diam-diam)",
              f"{rr.status_code}/{(prof.get('active_org') or {}).get('id')}")
        requests.post(f"{BASE}/admin/orgs/org-sipro/switch",
                      headers=bearer(j(rr).get("access_token") or tsw), timeout=30)
    else:
        check(False, "D15 refresh MEMPERTAHANKAN penyewa aktif", detail(sw))

    # --- gerbang: yang dicabut tidak boleh diperpanjang
    sa = baru
    nama = "ZZ Uji Sesi F54 Gate"
    surel = "gate.f54@ujisesif54.co.id"
    cr = requests.post(f"{BASE}/admin/orgs", headers=bearer(sa), timeout=30,
                       json={"name": nama, "owner_name": "Owner Gate F54",
                             "owner_email": surel, "owner_password": PW})
    org_id = (j(cr).get("data") or {}).get("id")
    if check(bool(org_id), "D16a penyewa sementara dibuat untuk uji gerbang", detail(cr)):
        _, ck2, _ = login(surel)
        requests.put(f"{BASE}/admin/orgs/{org_id}", headers=bearer(sa),
                     json={"status": "suspended"}, timeout=30)
        rr = requests.post(f"{BASE}/auth/refresh", cookies=ck2, timeout=30)
        check(rr.status_code in (401, 403) and state(rr) == "revoked",
              "D16 penyewa disuspend TIDAK bisa memperpanjang sesi (sebab: revoked)",
              f"{rr.status_code}/{state(rr)}")
        requests.put(f"{BASE}/admin/orgs/{org_id}", headers=bearer(sa),
                     json={"status": "active"}, timeout=30)

    # Akun dinonaktifkan: dibuat DI ORGANISASI SENDIRI. `GET /admin/users` ber-scope
    # organisasi, jadi owner penyewa sementara di atas TIDAK akan pernah muncul di daftar
    # super admin — memakainya membuat pemeriksaan ini diam-diam terlewat (dan gate
    # melaporkan hijau untuk sesuatu yang tidak pernah diuji).
    surel_u = "staf.f54@ujisesif54.co.id"
    cu = requests.post(f"{BASE}/admin/users", headers=bearer(sa), timeout=30,
                       json={"name": "ZZ Uji Sesi F54 Staf", "email": surel_u,
                             "password": PW, "role": "sales"})
    tid = (j(cu).get("data") or {}).get("id")
    if check(bool(tid), "D17a akun sementara dibuat untuk uji gerbang akun", detail(cu)):
        _, ck3, _ = login(surel_u)
        requests.put(f"{BASE}/admin/users/{tid}", headers=bearer(sa),
                     json={"is_active": False}, timeout=30)
        rr = requests.post(f"{BASE}/auth/refresh", cookies=ck3, timeout=30)
        check(rr.status_code in (401, 403) and state(rr) == "revoked",
              "D17 akun dinonaktifkan TIDAK bisa memperpanjang sesi (sebab: revoked)",
              f"{rr.status_code}/{state(rr)}")
        # Token kerja yang MASIH SAH pun harus berhenti bekerja begitu akunnya dimatikan —
        # kalau tidak, "menonaktifkan akun" hanya berlaku pada sesi baru.
        rr = requests.get(f"{BASE}/auth/me", cookies=ck3, timeout=30)
        check(rr.status_code == 403 and state(rr) == "revoked",
              "D17b token yang masih sah pun berhenti bekerja saat akun dimatikan",
              f"{rr.status_code}/{state(rr)}")

    # --- perpanjangan bukan celah naik pangkat
    stok, sck, _ = login("sales@sipro.co.id")
    if stok:
        rr = requests.post(f"{BASE}/auth/refresh", cookies=sck, timeout=30)
        sbaru = j(rr).get("access_token")
        pajak = requests.get(f"{BASE}/tax/records", headers=bearer(sbaru), timeout=30)
        check(pajak.status_code == 403,
              "D18 peran terbatas tetap terbatas memakai token hasil refresh", detail(pajak))
    return sa


# ============================================================== P. portal pembeli
def bagian_p(sa: str):
    head("P. Portal pembeli: kelas cacat sama ikut ditutup, dua dunia sesi tetap terpisah")
    r = requests.post(f"{BASE}/portal/auth/request-otp",
                      json={"identifier": "+6281250000502"}, timeout=30)
    if not check(r.status_code == 200, "P1 permintaan OTP portal berjalan", detail(r)):
        return
    v = requests.post(f"{BASE}/portal/auth/verify-otp",
                      json={"identifier": "+6281250000502", "code": "000000"}, timeout=30)
    ptok = j(v).get("token")
    if not check(bool(ptok), "P2 OTP master portal berlaku", detail(v)):
        return
    basi = jwt.encode({"sub": "x", "type": "portal",
                       "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                      SECRET, algorithm=ALG)
    rr = requests.get(f"{BASE}/portal/me", cookies={"portal_token": basi},
                      headers=bearer(ptok), timeout=30)
    check(rr.status_code == 200,
          "P3 cookie portal basi + Bearer portal sah = 200 (header menang di portal juga)",
          detail(rr))
    rr = requests.get(f"{BASE}/auth/me", headers=bearer(ptok), timeout=30)
    check(rr.status_code == 401, "P4 token portal tidak bisa masuk sesi staf", detail(rr))
    rr = requests.get(f"{BASE}/portal/me", headers=bearer(sa), timeout=30)
    check(rr.status_code in (401, 403), "P5 token staf tidak bisa menyusup ke portal",
          detail(rr))
    rr = requests.get(f"{BASE}/portal/me", timeout=30)
    check(rr.status_code == 401 and state(rr) == "missing",
          "P6 portal juga menyebut sebab penolakan lewat X-Session-State",
          f"{rr.status_code}/{state(rr)}")


# ============================================================== U. kejujuran layar
def bagian_u():
    head("U. Kejujuran layar: kalimat sesi tidak boleh membocorkan istilah internal")
    bus = read(FE / "services" / "sessionBus.js")
    pctx = read(FE / "context" / "PortalAuthContext.js")

    # Hanya NILAI kamus pesan yang diperiksa (bukan komentar): itulah yang dibaca pengguna.
    def pesan_pengguna(src: str, nama: str) -> list:
        m = re.search(nama + r"\s*=\s*\{(.*?)\n\};", src, flags=re.S)
        if not m:
            return []
        return re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))

    kalimat = pesan_pengguna(bus, "SESSION_END_MESSAGE") + \
        pesan_pengguna(pctx, "PORTAL_END_MESSAGE")
    check(len(kalimat) >= 6, "U1 kamus kalimat sesi terisi (staf + portal)", str(len(kalimat)))
    bocor = [k for k in kalimat
             if any(x in k.lower() for x in ("token", "jwt", "cookie", "localstorage", "401"))]
    check(not bocor, "U2 tidak ada kalimat sesi yang menyebut istilah internal", str(bocor[:2]))
    pendek = [k for k in kalimat if len(k) < 25]
    check(not pendek, "U3 setiap kalimat menjelaskan langkah berikutnya (bukan potongan)",
          str(pendek[:2]))

    # testId Fase 54 tidak boleh mati (pola repo)
    p54 = read(FE / "constants" / "testIds" / "p54.js")
    ids = dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", p54))
    check(len(ids) >= 6, "U4 testId Fase 54 terdaftar", str(len(ids)))
    semua = ""
    for p in list(FE.rglob("*.js")):
        if "constants/testIds" in str(p):
            continue
        semua += read(p)
    mati = [k for k, v in ids.items()
            if f"P54.{k}" not in semua and v not in semua]
    check(not mati, "U5 tidak ada testId Fase 54 yang MATI (tiap id dipakai layar)", str(mati))

    # Kamus SSOT harus cocok dengan konstanta backend — dua daftar yang bisa berbeda diam-diam
    ref = read(BE / "reference_p54.py")
    opts = set(re.findall(r'_o\("([a-z_]+)"', ref))
    sec = read(BE / "security.py")
    konst = set(re.findall(r'SESSION_[A-Z]+ = "([a-z]+)"', sec))
    check(konst and konst.issubset(opts),
          "U6 setiap keadaan sesi di kode ADA di Kamus Data (SSOT tidak bercabang)",
          f"kode={sorted(konst)} kamus={sorted(opts)}")


def main() -> int:
    print("=" * 78)
    print("GATE 45 — KETAHANAN SESI (Fase 54)")
    print("=" * 78)
    try:
        requests.get(f"{BASE}/health", timeout=10)
    except Exception as e:
        print(f"Backend tidak menjawab: {e}")
        return 1
    bagian_k()
    sa = bagian_d()
    if sa:
        bagian_p(sa)
    bagian_u()

    head("Bahan uji dibersihkan tanpa sisa")
    import _fixture54
    hasil = _fixture54.purge()
    sisa = _fixture54.purge(dry=True)
    check(sisa == {"orgs": 0, "users": 0},
          "D19 bahan uji gate dibuang bersih (termasuk koleksi turunan seperti bagan akun)",
          f"dibuang={hasil} sisa={sisa}")

    print("\n" + "-" * 78)
    if FAIL:
        print(f"GATE 45 MERAH — {len(FAIL)} gagal / {PASSED + len(FAIL)} pemeriksaan")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"GATE 45 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
