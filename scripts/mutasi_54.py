#!/usr/bin/env python3
"""mutasi_54.py — UJI-MUTASI Fase 54: membuktikan GATE 45 BERGIGI.

Cara kerja: satu per satu aturan Fase 54 dimatikan di kode (mutan), lalu
`scripts/verify_session_resilience.py` dijalankan. Gate yang tetap HIJAU saat aturannya
dimatikan berarti gate itu tidak menguji apa pun — **LOLOS adalah cacat perangkat uji**,
bukan kelulusan produk.

Yang dijaga Fase 54 (dan karena itu dimutasi di sini):
  * urutan kandidat bekal sesi (header DULU) dan "hanya menolak bila SEMUA gagal";
  * jenis token dipaksa dua arah (refresh bukan token kerja, token kerja bukan bekal refresh);
  * sebab penolakan bisa dibedakan mesin (`X-Session-State`) tanpa berhenti menjadi kalimat;
  * `POST /auth/refresh` ada, menyetel ulang cookie, memakai gerbang akun & penyewa, dan
    MEMPERTAHANKAN konteks "bertindak sebagai" penyewa lain;
  * frontend: perpanjangan single-flight, galat tanpa respons bukan sesi mati, React DIBERI
    TAHU saat sesi berakhir, hanya `expired` yang dicoba diperpanjang, dan tempat kerja
    dicatat lalu dipulihkan;
  * kejujuran layar: kalimat sesi tidak membocorkan istilah internal, testId tidak mati,
    dan kamus SSOT tidak bercabang dari konstanta backend.

## Perangkat uji (mewarisi pelajaran mahal dari `mutasi_51.py`/`mutasi_52.py`)

1. **Menunggu reload secara DETERMINISTIK.** `time.sleep()` buta melahirkan dua kebohongan:
   gate berjalan sebelum backend siap (dicatat "TERTANGKAP" tanpa pernah menguji apa pun)
   atau sebelum reload dimulai (dicatat "LOLOS" padahal kodenya masih utuh). PID proses ANAK
   `uvicorn` ditunggu berganti, lalu `/api/health` hidup.
2. **Mutasi FRONTEND tidak perlu menunggu backend.** Gate 45 memeriksa berkas frontend
   secara STATIS, jadi mutan frontend langsung bisa diuji — ini memotong waktu run secara
   nyata, bukan sekadar rapi.
3. **Hasil ditulis SEGERA** ke `memory/gatelogs/mutasi_54_hasil.tsv`; `--ringkas` menyusun
   laporannya walau run dipecah atau dibunuh lingkungan di tengah jalan.
4. **Snapshot kode bersih** di `memory/mutasi54_snapshot/` + `--pulihkan`, supaya kode mutan
   tidak pernah tertinggal di repo.
5. **Jejak DATA dibersihkan** lewat `scripts/_fixture54.py`: gate 45 membuat penyewa & akun
   sementara untuk menguji gerbang perpanjangan. Di bawah mutan M11/M12 gerbang itu
   TIDAK menolak, jadi jalur pembersihan gate bisa terlewat — pembersihan diulang di sini.

Pakai:
    python3 scripts/mutasi_54.py --check           # cepat: pastikan semua pola masih ada
    python3 scripts/mutasi_54.py                   # penuh (~20-30 menit)
    python3 scripts/mutasi_54.py --only=M01,M08    # sebagian
    python3 scripts/mutasi_54.py --from=M15        # lanjutkan run yang terputus
    python3 scripts/mutasi_54.py --ringkas         # laporan kumulatif
    python3 scripts/mutasi_54.py --pulihkan        # kembalikan kode & data bila run terputus
"""
import pathlib
import subprocess
import sys
import time

import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
sys.path.insert(0, str(ROOT / "scripts"))

GATE = "verify_session_resilience.py"        # gate 45
HEALTH = "http://localhost:8001/api/health"

SEC = "backend/security.py"
AUTH = "backend/routers/auth_router.py"
SRV = "backend/server.py"
PSEC = "backend/portal_security.py"
REF54 = "backend/reference_p54.py"
API = "frontend/src/services/apiClient.js"
BUS = "frontend/src/services/sessionBus.js"
CTX = "frontend/src/context/AuthContext.js"
APP = "frontend/src/App.js"
LGN = "frontend/src/pages/Login.js"
PCL = "frontend/src/services/portalClient.js"
IDS = "frontend/src/constants/testIds/p54.js"
BANNER = "frontend/src/components/layout/SessionBanner.js"

# Berkas backend memicu reload uvicorn; berkas frontend tidak perlu ditunggu karena gate
# memeriksanya secara statis.
BACKEND_FILES = {SEC, AUTH, SRV, PSEC, REF54}

# (nama, [(berkas, cari, ganti), ...], pemeriksaan yang HARUS jatuh)
MUTATIONS = [
    # ================================================= resolusi token (cacat inti nomor 2)
    ("M01 urutan kandidat dibalik: cookie dibaca sebelum header", [
        (SEC,
         "    out = []\n"
         '    header = request.headers.get("Authorization", "")\n'
         '    if header.startswith("Bearer "):\n'
         "        tok = header[7:].strip()\n"
         "        if tok:\n"
         "            out.append(tok)\n"
         "    cookie = request.cookies.get(cookie_name)\n"
         "    if cookie and cookie not in out:\n"
         "        out.append(cookie)\n"
         "    return out",
         "    out = []\n"
         "    cookie = request.cookies.get(cookie_name)\n"
         "    if cookie:\n"
         "        out.append(cookie)\n"
         '    header = request.headers.get("Authorization", "")\n'
         '    if header.startswith("Bearer "):\n'
         "        tok = header[7:].strip()\n"
         "        if tok and tok not in out:\n"
         "            out.append(tok)\n"
         "    return out")], "K2"),
    ("M02 hanya kandidat PERTAMA yang dicoba (cacat asli kembali sebagian)", [
        (SEC, "    for tok in tokens:", "    for tok in tokens[:1]:")], "D4"),
    ("M03 CACAT ASLI UTUH: cookie dulu DAN hanya satu kandidat", [
        (SEC,
         "    out = []\n"
         '    header = request.headers.get("Authorization", "")\n'
         '    if header.startswith("Bearer "):\n'
         "        tok = header[7:].strip()\n"
         "        if tok:\n"
         "            out.append(tok)\n"
         "    cookie = request.cookies.get(cookie_name)\n"
         "    if cookie and cookie not in out:\n"
         "        out.append(cookie)\n"
         "    return out",
         "    out = []\n"
         "    cookie = request.cookies.get(cookie_name)\n"
         "    if cookie:\n"
         "        out.append(cookie)\n"
         '    header = request.headers.get("Authorization", "")\n'
         '    if header.startswith("Bearer "):\n'
         "        tok = header[7:].strip()\n"
         "        if tok and tok not in out:\n"
         "            out.append(tok)\n"
         "    return out"),
        (SEC, "    for tok in tokens:", "    for tok in tokens[:1]:")], "D2"),
    ("M04 jenis token tidak lagi dipaksa (refresh bisa jadi token kerja)", [
        (SEC,
         "        if payload.get(\"type\") != expected_type:",
         "        if False and payload.get(\"type\") != expected_type:")], "D8"),
    ("M05 kandidat kedaluwarsa langsung mematikan permintaan (tanpa mencoba sisanya)", [
        (SEC,
         "        except jwt.ExpiredSignatureError:\n"
         "            state = SESSION_EXPIRED\n"
         "            continue",
         "        except jwt.ExpiredSignatureError:\n"
         "            return None, SESSION_EXPIRED")], "D4"),
    ("M06 tajuk X-Session-State dilepas (layar kembali harus menebak)", [
        (SEC,
         '                         headers={"X-Session-State": state})',
         "                         )")], "D5"),
    ("M07 sebab kedaluwarsa dilaporkan sebagai 'invalid' (memaksa ketik sandi)", [
        (SEC, "            state = SESSION_EXPIRED\n            continue",
         "            state = SESSION_INVALID\n            continue")], "D6"),
    ("M08 akun nonaktif dilaporkan 'expired' (layar mencoba menghidupkan yang dimatikan)", [
        (SEC,
         "    if not user.get(\"is_active\", True):\n"
         "        raise session_error(SESSION_REVOKED, status_code=403)",
         "    if not user.get(\"is_active\", True):\n"
         "        raise session_error(SESSION_EXPIRED, status_code=403)")], "D17b"),
    ("M09 pembacaan klaim lewat-waktu berhenti memeriksa tanda tangan", [
        (SEC,
         '                                 options={"verify_exp": False})',
         '                                 options={"verify_exp": False,\n'
         '                                          "verify_signature": False})')], "K7"),
    ("M10 pesan 401 menjadi OBJEK (layar mencetak [object Object])", [
        (SEC,
         "    return HTTPException(status_code=status_code,\n"
         "                         detail=detail or SESSION_MESSAGE.get(state, "
         "SESSION_MESSAGE[SESSION_INVALID]),",
         "    return HTTPException(status_code=status_code,\n"
         '                         detail={"state": state, "message": detail or '
         "SESSION_MESSAGE.get(state, SESSION_MESSAGE[SESSION_INVALID])},")], "D5b"),
    ("M11 pesan 401 membocorkan istilah internal ke pemakai", [
        (SEC,
         '    SESSION_EXPIRED: "Sesi Anda sudah berakhir. Silakan masuk kembali.",',
         '    SESSION_EXPIRED: "Token sesi (JWT) Anda kedaluwarsa; cookie access_token '
         'sudah tidak sah.",')], "D6c"),

    # ================================================= endpoint refresh (cacat inti nomor 1)
    ("M12 route /auth/refresh dihapus (kembali ke janji yang tidak ditepati)", [
        (AUTH, '@router.post("/refresh")', '@router.post("/refresh-dimatikan")')], "D10"),
    ("M13 refresh tidak menyetel ulang cookie access_token", [
        (AUTH,
         '    response.set_cookie("access_token", access, httponly=True, secure=COOKIE_SECURE,\n'
         "                        samesite=COOKIE_SAMESITE, max_age=ACCESS_MAX_AGE, path=\"/\")\n"
         '    renewal = "renewed"',
         '    renewal = "renewed"')], "K9"),
    ("M14 refresh MELUPAKAN penyewa aktif (super admin dipulangkan diam-diam)", [
        (AUTH,
         '    active = prev.get("active_org_id") if user.get("role") == "super_admin" else None',
         "    active = None")], "D15"),
    ("M15 refresh melewati gerbang penyewa (penyewa disuspend hidup 7 hari lagi)", [
        (AUTH, "    await _tenant_gate(user)", "    pass  # gerbang penyewa dimatikan")],
     "D16"),
    ("M16 refresh melewati gerbang akun (akun nonaktif hidup 7 hari lagi)", [
        (AUTH,
         "    if not user.get(\"is_active\", True):\n"
         "        raise session_error(SESSION_REVOKED, status_code=403)\n"
         '    user["home_org_id"] = user.get("org_id")',
         '    user["home_org_id"] = user.get("org_id")')], "D17"),
    ("M17 refresh mengembalikan profil ringkas (bentuk sesi bercabang lagi)", [
        (AUTH,
         '    return {"data": await session_payload(user), "access_token": access,\n'
         '            "token_type": "bearer", "renewal": renewal}',
         '    return {"data": {"id": user["id"], "email": user["email"]},\n'
         '            "access_token": access, "token_type": "bearer", "renewal": renewal}')],
     "D11"),
    ("M18 refresh menerima token jenis apa pun (token kerja jadi bekal 7 hari)", [
        (AUTH,
         '    payload, state = decode_session_tokens(tokens, expected_type="refresh")',
         '    payload, state = decode_session_tokens(tokens, expected_type="access")')],
     "D9"),
    ("M19 umur cookie diketik ulang sebagai angka telanjang (dua angka bisa beda)", [
        (AUTH, "ACCESS_MAX_AGE = int(ACCESS_TTL.total_seconds())",
         "ACCESS_MAX_AGE = 86400")], "K13"),
    ("M20 CORS menutup X-Session-State (peramban menyembunyikannya dari layar)", [
        (SRV, '    expose_headers=["X-Session-State"],', "")], "K14"),

    # ================================================= portal pembeli (kelas cacat sama)
    ("M21 portal kembali membaca cookie sebelum header", [
        (PSEC,
         "    out = []\n"
         '    header = request.headers.get("Authorization", "")\n'
         '    if header.startswith("Bearer "):\n'
         "        tok = header[7:].strip()\n"
         "        if tok:\n"
         "            out.append(tok)\n"
         '    for extra in (request.cookies.get("portal_token"), '
         'request.query_params.get("auth")):',
         "    out = []\n"
         '    ck = request.cookies.get("portal_token")\n'
         "    if ck:\n"
         "        out.append(ck)\n"
         '    header = request.headers.get("Authorization", "")\n'
         '    if header.startswith("Bearer "):\n'
         "        tok = header[7:].strip()\n"
         "        if tok:\n"
         "            out.append(tok)\n"
         '    for extra in (request.query_params.get("auth"), None):')], "K25"),
    ("M22 portal berhenti menyebut sebab penolakan", [
        (PSEC, '                            headers={"X-Session-State": "missing"})', ")")],
     "P6"),

    # ================================================= frontend: pemulihan & kejujuran
    ("M23 perpanjangan tidak lagi single-flight (6 panel = 6 perpanjangan)", [
        (API, "  if (renewal) return renewal;", "  // single-flight dimatikan")], "K15"),
    ("M24 galat TANPA respons dianggap sesi mati (mandor tanpa sinyal diusir)", [
        (API, "    if (!e?.response) return true;", "    if (false) return true;")], "K16a"),
    ("M25 React tidak diberi tahu saat sesi berakhir (cacat asli nomor 3 kembali)", [
        (API, "    emitSessionEnded(state || SESSION_STATE.expired);", ""),
        (API, "    emitSessionEnded(sessionState(e) || SESSION_STATE.expired);", "")], "K17"),
    ("M26 setiap 401 dicoba diperpanjang (termasuk yang pasti ditolak)", [
        (API, "    if (state === SESSION_STATE.expired && !cfg.__sudahDiulang) {",
         "    if (!cfg.__sudahDiulang) {")], "K18"),
    ("M27 permintaan diulang tanpa penjaga (gelung tak berujung)", [
        (API, "        cfg.__sudahDiulang = true;", "        cfg.diulangSaja = true;")], "K19"),
    ("M28 AuthContext berhenti berlangganan kabar sesi berakhir", [
        (CTX, "  useEffect(() => onSessionEnded((reason) => {",
         "  useEffect(() => (() => {})((reason) => {")], "K20"),
    ("M29 tempat kerja tidak dicatat (kembali ke Beranda, jejak hilang)", [
        (APP, "    rememberReturnTo(location.pathname + location.search);", "")], "K21"),
    ("M30 pembacaan sekali-pakai tanpa penjaga ref (dimakan render ganda StrictMode)", [
        (APP,
         "  const tujuan = useRef(null);\n"
         "  if (loading) return <Splash />;\n"
         "  if (user) {\n"
         "    if (tujuan.current === null) tujuan.current = takeReturnTo() || \"/\";\n"
         "    return <Navigate to={tujuan.current} replace />;\n"
         "  }",
         "  if (loading) return <Splash />;\n"
         '  if (user) return <Navigate to={takeReturnTo() || "/"} replace />;')], "K22"),
    ("M31 halaman masuk MENGHABISKAN tujuan kembali (janji dilanggar di depan mata)", [
        (LGN, "  const [returnTo] = useState(() => peekReturnTo());",
         "  const [returnTo] = useState(() => takeReturnTo());"),
        (LGN, 'import { SESSION_END_MESSAGE, SESSION_STATE, peekReturnTo } '
              'from "@/services/sessionBus";',
         'import { SESSION_END_MESSAGE, SESSION_STATE, takeReturnTo } '
         'from "@/services/sessionBus";')], "K23"),
    ("M32 portal berhenti mengakhiri sesinya dengan jujur", [
        (PCL, "    if (err?.response?.status === 401 && !auth) {",
         "    if (false) {")], "K24"),
    ("M33 kalimat sesi membocorkan istilah internal ke layar", [
        (BUS,
         '  [SESSION_STATE.invalid]:\n'
         '    "Sesi Anda tidak dikenali lagi. Masuk kembali untuk melanjutkan.",',
         '  [SESSION_STATE.invalid]:\n'
         '    "Token JWT pada localStorage tidak dikenali lagi.",')], "U2"),
    ("M34 kalimat sesi dipotong jadi label (tidak menyebut langkah berikutnya)", [
        (BUS,
         '  [SESSION_STATE.invalid]:\n'
         '    "Sesi Anda tidak dikenali lagi. Masuk kembali untuk melanjutkan.",',
         '  [SESSION_STATE.invalid]: "Sesi tidak sah.",')], "U3"),
    ("M35 testId Fase 54 tidak lagi dipakai layar (uji kehilangan pegangan tanpa suara)", [
        (BANNER, "      <Button data-testid={P54.bannerRenew} size=\"sm\" variant=\"default\"",
         "      <Button size=\"sm\" variant=\"default\"")], "U5"),
    ("M36 keadaan sesi di kode tidak lagi ada di Kamus Data (SSOT bercabang)", [
        (REF54, '            _o("revoked", "Akses dicabut (akun dinonaktifkan atau '
                'organisasi disuspend)"),',
         '            _o("dicabut", "Akses dicabut (akun dinonaktifkan atau '
         'organisasi disuspend)"),')], "U6"),
]


# --------------------------------------------------------------------------- berkas
def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, src: str) -> None:
    (ROOT / rel).write_text(src, encoding="utf-8")


def apply_patches(patches) -> dict:
    backup = {}
    for path, find, repl in patches:
        src = read(path)
        if path not in backup:
            backup[path] = src
        if find not in src:
            raise RuntimeError(f"pola tidak ditemukan di {path}: {find[:70]}")
        write(path, src.replace(find, repl, 1))
    return backup


def restore(backup: dict) -> None:
    for path, src in backup.items():
        write(path, src)


# ---------------------------------------------- jaring pengaman bila run terputus
SNAP = ROOT / "memory" / "mutasi54_snapshot"


def files_touched() -> list:
    out = []
    for _n, patches, _c in MUTATIONS:
        for path, _f, _r in patches:
            if path not in out:
                out.append(path)
    return out


def snapshot() -> None:
    SNAP.mkdir(parents=True, exist_ok=True)
    for rel in files_touched():
        (SNAP / rel.replace("/", "__")).write_text(read(rel), encoding="utf-8")


def pulihkan() -> int:
    if not SNAP.exists():
        print("Tidak ada snapshot kode — tidak ada berkas yang perlu dipulihkan.")
        return 0
    n = 0
    for rel in files_touched():
        src = SNAP / rel.replace("/", "__")
        if src.exists() and src.read_text(encoding="utf-8") != read(rel):
            write(rel, src.read_text(encoding="utf-8"))
            print(f"  dipulihkan  {rel}")
            n += 1
    print(f"{n} berkas kode dipulihkan dari snapshot.")
    import _fixture54
    print(f"Bahan uji sesi dibuang: {_fixture54.purge()}")
    return 0


# ------------------------------------------------------- menunggu backend memuat ulang
def server_pids() -> tuple:
    """PID proses PEKERJA (anak) `uvicorn server:app --reload`.

    Induknya TIDAK pernah berganti PID saat reload; yang berganti adalah anaknya.
    """
    induk = subprocess.run(["pgrep", "-f", "uvicorn server:app"],
                           capture_output=True, text=True)
    pids = []
    for p in induk.stdout.split():
        if not p.strip().isdigit():
            continue
        anak = subprocess.run(["pgrep", "-P", p.strip()], capture_output=True, text=True)
        pids += [int(x) for x in anak.stdout.split() if x.strip().isdigit()]
    return tuple(sorted(pids))


def health_ok(timeout: float = 3.0) -> bool:
    try:
        return requests.get(HEALTH, timeout=timeout).status_code == 200
    except requests.RequestException:
        return False


def wait_reload(before: tuple, batas_ganti: int = 40, batas_sehat: int = 240) -> str:
    mulai = time.time()
    ganti = False
    while time.time() - mulai < batas_ganti:
        now = server_pids()
        if now and now != before:
            ganti = True
            break
        time.sleep(0.4)
    while time.time() - mulai < batas_sehat:
        if health_ok():
            time.sleep(1.2)     # beri jeda agar router selesai terpasang
            return (f"reload {time.time() - mulai:.0f}s" if ganti else
                    f"TANPA reload terdeteksi ({time.time() - mulai:.0f}s)")
        time.sleep(0.5)
    return "backend TIDAK sehat setelah menunggu"


# --------------------------------------------------------------------------- gate
def run_gate(tag: str) -> tuple:
    logdir = ROOT / "memory" / "gatelogs"
    logdir.mkdir(parents=True, exist_ok=True)
    log = logdir / f"mut54_{tag}.log"
    with log.open("w", encoding="utf-8") as fh:
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / GATE)],
                           stdout=fh, stderr=subprocess.STDOUT, cwd=str(ROOT))
    isi = log.read_text(encoding="utf-8", errors="ignore")
    jatuh = [ln.strip()[6:].split()[0] for ln in isi.splitlines()
             if ln.strip().startswith("MERAH")]
    return p.returncode == 0, jatuh


HASIL = ROOT / "memory" / "gatelogs" / "mutasi_54_hasil.tsv"


def catat_hasil(nama: str, hasil: str, catatan: str = "") -> None:
    HASIL.parent.mkdir(parents=True, exist_ok=True)
    with HASIL.open("a", encoding="utf-8") as fh:
        fh.write(f"{nama.split()[0]}\t{hasil}\t{nama}\t{catatan}\n")


def baca_hasil() -> dict:
    if not HASIL.exists():
        return {}
    out = {}
    for line in HASIL.read_text(encoding="utf-8").splitlines():
        b = line.split("\t")
        if len(b) >= 3:
            out[b[0]] = (b[1], b[2], b[3] if len(b) > 3 else "")
    return out


def ringkas() -> int:
    hasil = baca_hasil()
    print("=" * 78)
    print("RINGKASAN UJI-MUTASI FASE 54 (kumulatif) — gate 45 verify_session_resilience.py")
    print("=" * 78)
    tertangkap, lolos, lewat, belum = [], [], [], []
    for nama, _p, _c in MUTATIONS:
        kode = nama.split()[0]
        row = hasil.get(kode)
        if not row:
            belum.append(nama)
            print(f"  BELUM      {nama}")
            continue
        status, _n, catatan = row
        print(f"  {status:<10} {nama}" + (f"  [{catatan}]" if catatan else ""))
        {"TERTANGKAP": tertangkap, "LOLOS": lolos,
         "LEWAT": lewat}.get(status, belum).append(nama)
    print("-" * 78)
    print(f"TERTANGKAP: {len(tertangkap)} · LOLOS: {len(lolos)} · LEWAT: {len(lewat)} · "
          f"BELUM DIJALANKAN: {len(belum)} · TOTAL: {len(MUTATIONS)}")
    if lolos:
        print("\nMutasi yang LOLOS (gate harus diperkuat, bukan diabaikan):")
        for e in lolos:
            print(f"   - {e}")
    print("=" * 78)
    return 0 if (not lolos and not lewat and not belum) else 1


def check_patterns() -> int:
    print("=" * 78)
    print("PERIKSA POLA MUTASI FASE 54 (cepat, tanpa menjalankan gate)")
    print("=" * 78)
    bad = []
    for nama, patches, _c in MUTATIONS:
        missing = [f"{p} :: {find[:60]}" for p, find, _r in patches if find not in read(p)]
        print(f"  {'OK    ' if not missing else 'HILANG'} {nama}")
        for m in missing:
            print(f"        - {m}")
        bad += missing
    print("-" * 78)
    print(f"{len(MUTATIONS)} mutasi · {len(bad)} pola hilang")
    return 1 if bad else 0


def selected():
    only, start = None, None
    for arg in sys.argv[1:]:
        if arg.startswith("--only="):
            only = {x.strip().upper() for x in arg.split("=", 1)[1].split(",") if x.strip()}
        elif arg.startswith("--from="):
            start = arg.split("=", 1)[1].strip().upper()
    rows = list(MUTATIONS)
    if only:
        rows = [m for m in rows if m[0].split()[0].upper() in only]
    if start:
        idx = next((i for i, m in enumerate(rows) if m[0].split()[0].upper() == start), 0)
        rows = rows[idx:]
    return rows


def main() -> int:
    if "--check" in sys.argv:
        return check_patterns()
    if "--pulihkan" in sys.argv:
        return pulihkan()
    if "--ringkas" in sys.argv:
        return ringkas()

    rows = selected()
    snapshot()
    print("=" * 78)
    print(f"UJI-MUTASI FASE 54 — {len(rows)} mutan · gate 45 {GATE}")
    print(f"Snapshot kode bersih: {SNAP.relative_to(ROOT)}")
    print("=" * 78)

    if "--tanpa-baseline" not in sys.argv:
        print("\nBASELINE (kode bersih): gate harus HIJAU sebelum mutasi apa pun.")
        ok, _ = run_gate("baseline")
        print(f"  baseline gate: {'HIJAU' if ok else 'MERAH'}")
        if not ok:
            print("  Baseline MERAH — mutasi dihentikan (hasilnya tidak akan berarti).")
            return 1

    import _fixture54
    for nama, patches, harus_jatuh in rows:
        kode = nama.split()[0]
        print(f"\n--- {nama}")
        butuh_reload = any(p in BACKEND_FILES for p, _f, _r in patches)
        before = server_pids() if butuh_reload else ()
        try:
            backup = apply_patches(patches)
        except RuntimeError as e:
            print(f"  LEWAT — {e}")
            catat_hasil(nama, "LEWAT", str(e)[:80])
            continue
        try:
            if butuh_reload:
                print(f"  {wait_reload(before)}")
            ok, jatuh = run_gate(kode)
            if ok:
                print("  LOLOS — gate tetap HIJAU walau aturannya dimatikan (GATE LEMAH)")
                catat_hasil(nama, "LOLOS", "")
            else:
                tepat = harus_jatuh in jatuh
                print(f"  TERTANGKAP — gate MERAH; jatuh: {','.join(jatuh[:6])}")
                if not tepat:
                    print(f"  (catatan: pemeriksaan {harus_jatuh} yang diharapkan TIDAK "
                          f"jatuh — gate menangkapnya lewat jalan lain)")
                catat_hasil(nama, "TERTANGKAP",
                            f"{harus_jatuh}{'' if tepat else ' (lewat jalan lain)'}: "
                            f"{','.join(jatuh[:6])}")
        finally:
            restore(backup)
            if butuh_reload:
                wait_reload(server_pids())
            _fixture54.purge()

    print()
    return ringkas()


if __name__ == "__main__":
    sys.exit(main())
