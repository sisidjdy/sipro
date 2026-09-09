#!/usr/bin/env python3
"""verify_panel_resilience.py — GATE 44 (Fase 52): satu panel yang ditolak TIDAK BOLEH
mematikan halaman, dan layar TIDAK BOLEH berbohong tentang sebabnya.

## Cacat nyata yang dijaga gate ini

Dilaporkan pemakai: *"satu 403 dari panel samping mematikan seluruh halaman profil lead dan
menampilkan kalimat yang tidak benar."* Bukti dari container ini (sandi demo, lead milik
`sales@`):

    finance@sipro.co.id   GET /api/leads/{id}             = 200
                          GET /api/appointments?lead_id=  = 403   <-- hanya panel survei

`LeadProfilePage` memuat enam permintaan dengan `Promise.all`, jadi satu penolakan
membatalkan lima lainnya; lalu SATU cabang `catch` menebak sebabnya dari error mana pun yang
menang duluan dan menulis **"Peran Anda tidak diberi akses ke data lead — bukan hanya lead
ini"**. Padahal leadnya baru saja dijawab 200 dan `finance` memang punya `leads:view_all`.
Sepuluh tab hilang, dan kalimat yang tersisa menuduh izin yang salah.

Cacat kedua dari kelas yang sama (juga dilaporkan pemakai, kali ini super admin: *"ada menu
yang tidak bisa saya akses"*): dialog **Peta Menu** menuliskan daftar "BELUM DIBANGUN (TAMPIL
TERKUNCI DI SIDEBAR)" yang ditulis TANGAN, berisi tiga menu yang sudah lama hidup
(`/campaigns`, `/attribution`, `/bi`) beserta nomor fase yang sudah lewat.

## Yang diperiksa (P = kode, D = bukti HTTP, N = peta menu)

  P1..P4   Pemuat tahan-banting ada: `Promise.allSettled`, pesan izin internal DISARING,
           lencana jujur (`undefined`, bukan 0), kartu keadaan panel tersedia.
  P5..P12  Halaman profil memakainya: tidak ada `Promise.all` lagi, kalimat 403 halaman-penuh
           HANYA dari permintaan primer, tab yang ditolak memakai `PanelStateView`, tombol
           yang pasti 403 disembunyikan lewat `can()`, dan panel yang memuat datanya sendiri
           (checklist dokumen, penawaran, percakapan WA) tidak lagi memuntahkan pesan
           penegak izin ke layar.
  D1..D8   Server: `appointments` boleh DIBACA keuangan tetapi tidak dibuat; peran proyek
           tetap ditolak; kalimat 403 "bukan lead Anda" berbeda dari 403 izin peran; dan
           kombinasi berbahaya ("primer 200 + panel 403") dibuktikan MASIH MUNGKIN dengan
           mencabut izin lewat API resmi, lalu DIPULIHKAN.
  N1..N6   Peta menu: daftar terkunci DIDERIVASI dari `navigationConfig` (tidak bisa
           membusuk), tiga menu yang sudah hidup punya baris peta yang rutenya benar-benar
           ada, dan dialog punya cabang "semua menu bisa dibuka".

Gate ini TIDAK meninggalkan jejak: pencabutan izin pada D6..D8 dipulihkan di `finally`,
dan pemulihannya ikut diperiksa (D8) — kalau tidak, gate berikutnya akan menguji dunia yang
sudah dirusak gate ini.

Jalankan: python3 scripts/verify_panel_resilience.py
"""
import copy
import pathlib
import re
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
FE = ROOT / "frontend" / "src"
BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
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


def read(rel: str) -> str:
    p = FE / rel
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def strip_comments(src: str) -> str:
    """Buang komentar: penjelasan di dalam kode tidak boleh dihitung sebagai pemakaian.

    Pelajaran nyata dari uji-mutasi Fase 51 (C10a): memeriksa kata "DocumentsPanel" saja
    tetap hijau walau panelnya dicabut dari daftar tab, karena BARIS IMPOR sudah memenuhi
    pencarian. Di gate ini pun setiap pemeriksaan harus melihat KODE, bukan cerita.
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def login(email: str) -> dict:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ============================================================ P — pemuat & kartu keadaan
def audit_loader() -> None:
    head("P1..P4  Pemuat tahan-banting + kartu keadaan panel")
    pl = strip_comments(read("utils/panelLoad.js"))
    check(bool(pl), "utils/panelLoad.js ada")
    check("Promise.allSettled(" in pl,
          "pemuat panel memakai Promise.allSettled (satu penolakan tidak membatalkan yang lain)",
          "tidak ada Promise.allSettled — cacat Fase 52 kembali")
    check("Promise.all(" not in pl.replace("Promise.allSettled(", ""),
          "pemuat panel TIDAK memakai Promise.all")
    # Pesan penegak izin backend tidak boleh diteruskan ke layar.
    check(bool(re.search(r"isInternalPermissionMessage\(\s*rawDetail\s*\)\s*\?\s*\"\"", pl)),
          "pesan izin internal DISARING dari `detail` yang ditampilkan",
          "detail mentah bisa bocor ke layar")
    check("tidak memiliki izin" in read("utils/panelLoad.js"),
          "pola pesan penegak izin dikenali pemuat (untuk disaring)")
    # Lencana jujur: undefined, bukan 0.
    check(bool(re.search(r"function honestBadge[\s\S]{0,200}?if\s*\(!panel\s*\|\|\s*!panel\.ok\)"
                         r"\s*return undefined;", pl)),
          "honestBadge() mengembalikan undefined bila panelnya tidak terbaca (bukan 0)",
          "lencana 0 pada tab yang ditolak = pernyataan palsu 'tidak ada datanya'")
    check("export function omittedSources(" in pl,
          "omittedSources() tersedia untuk menyebut sumber yang tidak disertakan")

    sv = read("components/patterns/StateViews.js")
    svc = strip_comments(sv)
    for name in ("PanelDenied", "PanelUnavailable", "PanelStateView"):
        check(f"export function {name}(" in svc, f"StateViews mengekspor {name}")
    check('data-panel-state="denied"' in svc,
          "kartu panel ditolak membawa penanda data-panel-state=\"denied\"")
    check("Ini BUKAN" in sv and "belum ada data" in sv,
          "kartu panel ditolak menegaskan ini BUKAN 'belum ada data'",
          "tanpa kalimat itu pemakai mengira datanya hilang")
    check("panel-denied" in read("constants/testIds/ia.js")
          and "panel-unavailable" in read("constants/testIds/ia.js"),
          "testId keadaan panel terdaftar (panel-denied / panel-unavailable)")


# ============================================================ P — halaman profil
PROFILE_PAGES = {
    "pages/LeadProfilePage.js": "lead",
    "pages/CustomerProfilePage.js": "customer",
}


def audit_profile_pages() -> None:
    head("P5..P9  Halaman profil: hanya permintaan PRIMER yang boleh mematikan halaman")
    for rel in PROFILE_PAGES:
        src = strip_comments(read(rel))
        name = rel.split("/")[-1]
        check("loadPanels(" in src, f"{name} memakai loadPanels()")
        check("Promise.all(" not in src, f"{name} TIDAK lagi memakai Promise.all",
              "satu penolakan akan membatalkan seluruh permintaan halaman")
        # Kalimat halaman-penuh hanya boleh disusun dari error permintaan primer.
        check(bool(re.search(r"const primer = res\.(lead|customer);", src)),
              f"{name} memisahkan permintaan primer secara eksplisit")
        check("primer.status ===" in src,
              f"{name} menyusun kalimat galat dari STATUS permintaan primer")
        check("panelRows(" in src, f"{name} membaca baris panel lewat panelRows()")
        check("honestBadge(" in src, f"{name} memakai honestBadge() untuk lencana tab")
        check(not re.search(r"badge:\s*\w+\.length\s*\|\|\s*undefined", src),
              f"{name} tidak lagi menghitung lencana dari panjang daftar mentah",
              "daftar kosong karena 403 akan tampak seperti 'tidak ada data'")
        check("omittedSources(" in src, f"{name} menyusun daftar panel yang tidak ditampilkan")

    lead = strip_comments(read("pages/LeadProfilePage.js"))
    check("primer.rawDetail" in lead,
          "kalimat 403 profil lead dibaca dari rawDetail PERMINTAAN LEAD (bukan error panel)",
          "inilah sebab layar dulu menuduh izin yang salah")
    check("LEADPROFILE.partial" in lead,
          "profil lead punya spanduk 'sebagian panel tidak ditampilkan'")
    cust = strip_comments(read("pages/CustomerProfilePage.js"))
    check("CUSTPROFILE.partial" in cust,
          "profil pelanggan punya spanduk 'sebagian panel tidak ditampilkan'")
    check("PanelStateView" in cust,
          "profil pelanggan merender kartu keadaan panel (bukan daftar kosong palsu)")
    check(not re.search(r"catch\(\(\)\s*=>\s*\(\{\s*data:\s*\{\s*data:\s*\[\]\s*\}\s*\}\)\)",
                        cust),
          "profil pelanggan tidak lagi mengubah penolakan menjadi daftar kosong",
          "`.catch(() => ({data:{data:[]}}))` menyamakan 403 dengan 'belum ada data'")


def audit_tabs() -> None:
    head("P10..P12  Tab & panel: bercerita jujur, tombol mati disembunyikan")
    survey = strip_comments(read("components/leads/LeadSurveyTab.js"))
    check("PanelStateView" in survey, "tab Survey merender kartu keadaan panel")
    check(bool(re.search(r"if\s*\(panel\s*&&\s*!panel\.ok\)", survey)),
          "tab Survey berhenti menggambar daftar bila panelnya tidak terbaca")
    check('can("appointments", "create")' in survey,
          "tombol 'Jadwalkan Survey' mengikuti izin nyata appointments:create",
          "tanpa ini tombolnya ada tetapi selalu 403 (tombol mati)")
    units = strip_comments(read("components/leads/LeadUnitsTab.js"))
    check("PanelStateView" in units, "tab Unit & SPR merender kartu keadaan panel")
    check('can("deals", "create")' in units,
          "tombol 'Buat Reservasi' mengikuti izin nyata deals:create")
    tl = strip_comments(read("components/leads/LeadTimelineTab.js"))
    check("PANELSTATE.omitted" in tl,
          "tab Timeline menandai jejak yang SEBAGIAN (sumber tidak disertakan)")
    check("SEBAGIAN" in read("components/leads/LeadTimelineTab.js"),
          "tab Timeline mengatakan apa adanya bahwa jejaknya sebagian")

    # Panel yang memuat datanya SENDIRI: 403 tidak boleh muncul sebagai pesan teknis.
    for rel, subject in (("components/patterns/DocChecklist.js", "checklist dokumen"),
                         ("components/quotations/QuotationsTab.js", "penawaran"),
                         ("components/sales/LeadWaPanel.js", "percakapan WA")):
        src = strip_comments(read(rel))
        check("classifyRequestError(" in src,
              f"panel {subject} mengklasifikasikan galat (403 vs gagal vs offline)")
        check("PanelStateView" in src,
              f"panel {subject} merender kartu keadaan panel, bukan pesan backend mentah")
        check("setError(e?.response?.data?.detail" not in src,
              f"panel {subject} tidak lagi menampilkan detail galat backend apa adanya",
              "pesan itu menyebut nama izin internal")


# ============================================================ N — peta menu
def audit_nav_map() -> None:
    head("N1..N6  Peta menu tidak boleh mengaku menu HIDUP itu terkunci")
    nav = read("config/navigationConfig.js")
    mig = read("config/navMigrationMap.js")
    dlg = strip_comments(read("components/layout/NavMigrationDialog.js"))
    check("export function comingSoonItems(" in nav,
          "navigationConfig mengekspor comingSoonItems() sebagai satu sumber menu terkunci")
    check("export const NAV_SOON = comingSoonItems()" in mig,
          "daftar 'belum dibangun' DIDERIVASI, bukan ditulis tangan",
          "daftar tangan membusuk tanpa ada yang tahu — itu cacat yang dilaporkan")
    check(not re.search(r"NAV_SOON\s*=\s*\[", mig),
          "tidak ada lagi daftar 'belum dibangun' berbentuk array tangan")
    check("navSoonFor(" in dlg and "soon.length ?" in dlg,
          "dialog peta menu hanya memasang kotak terkunci bila memang ADA yang terkunci")
    check("navMapAllOpen" in dlg,
          "dialog peta menu punya kalimat jujur 'semua menu bisa dibuka'")
    # Tiga menu yang dulu diumumkan terkunci sekarang harus jadi baris peta yang rutenya ada.
    app_js = (FE / "App.js").read_text(encoding="utf-8", errors="ignore")
    routes = set(re.findall(r'path="([^"]+)"', app_js))
    for path, nama in (("/campaigns", "Kampanye & Biaya Iklan"),
                       ("/attribution", "Atribusi & CAPI"),
                       ("/bi", "Analitik & BI")):
        check(f'to: "{path}"' in mig, f"peta menu menautkan '{nama}' ke {path}")
        check(path in routes, f"rute {path} benar-benar ada di App.js")
    # Semua tujuan peta harus punya route (dijaga juga gate IA V2; diulang di sini karena
    # Fase 52 MENAMBAH baris baru dan baris baru itulah yang paling mudah salah).
    bad = [t for t in re.findall(r'to:\s*"([^"]+)"', mig) if t.split("?")[0] not in routes]
    check(not bad, "semua tujuan peta menu punya route", ", ".join(bad[:4]))


# ============================================================ D — bukti HTTP
def audit_server() -> None:
    head("D1..D5  Server: keuangan boleh MEMBACA jadwal survei, tidak menjadwalkan")
    sa = login("superadmin@sipro.co.id")
    matrix = requests.get(f"{BASE}/admin/permissions", headers=sa, timeout=30).json()["data"]["matrix"]
    appt = matrix.get("appointments") or {}
    for role in ("finance", "finance_manager"):
        perms = appt.get(role) or []
        check("view_all" in perms, f"matriks memberi {role} izin BACA appointments", str(perms))
        check(not ({"create", "update"} & set(perms)),
              f"{role} TIDAK diberi create/update appointments (pemisahan tugas)", str(perms))

    lead_id = None
    for email in ("finance@sipro.co.id", "finlead@sipro.co.id"):
        h = login(email)
        if lead_id is None:
            rows = requests.get(f"{BASE}/leads", headers=h, params={"limit": 50}, timeout=30)
            data = rows.json().get("data") or []
            # Bahan uji lingkup baris: lead yang BUKAN milik sales2 (dipakai D5 di bawah).
            asing = [x for x in data if x.get("assigned_to") != "sales2@sipro.co.id"]
            lead_id = (asing or data)[0]["id"] if data else None
        g = requests.get(f"{BASE}/appointments", headers=h, params={"lead_id": lead_id}, timeout=30)
        check(g.status_code == 200, f"{email} boleh GET /appointments", str(g.status_code))
        p = requests.post(f"{BASE}/appointments", headers=h,
                          json={"lead_id": lead_id or "x", "title": "gate44",
                                "scheduled_at": "2099-01-01T09:00:00Z", "type": "survey"},
                          timeout=30)
        check(p.status_code == 403, f"{email} TIDAK boleh POST /appointments", str(p.status_code))
    check(bool(lead_id), "ada lead yang bisa dipakai sebagai bahan uji")

    # Fase 63 — peran PROYEK kini boleh melihat & membuat agendanya sendiri (rapat internal,
    # kunjungan proyek, rapat vendor), karena halaman Agenda tidak lagi hanya berisi janji
    # temu jual. Yang TIDAK melebar: agenda yang MENYEBUT LEAD tetap ditolak untuk peran
    # tanpa `leads:view` (dibuktikan di bawah), dan keuangan tetap hanya membaca.
    for email in ("pm@sipro.co.id", "site@sipro.co.id"):
        h = login(email)
        g = requests.get(f"{BASE}/appointments", headers=h, timeout=30)
        check(g.status_code == 200,
              f"{email} boleh melihat agenda kerjanya (Fase 63)", str(g.status_code))
        p = requests.post(f"{BASE}/appointments", headers=h,
                          json={"lead_id": lead_id or "x", "title": "gate44-lead",
                                "scheduled_at": "2099-01-01T09:00:00Z", "type": "survey"},
                          timeout=30)
        check(p.status_code == 403,
              f"{email} TIDAK boleh menjadwalkan agenda milik LEAD (SoD tetap)",
              str(p.status_code))

    # Dua sebab 403 yang BERBEDA harus tetap bisa dibedakan layar.
    h2 = login("sales2@sipro.co.id")
    r2 = requests.get(f"{BASE}/leads/{lead_id}", headers=h2, timeout=30)
    detail2 = str((r2.json() or {}).get("detail", "")) if r2.status_code == 403 else ""
    check(r2.status_code == 403 and "bukan lead anda" in detail2.lower(),
          "403 lingkup baris menyebut 'bukan lead Anda' (kalimat 'milik rekan lain' di layar)",
          f"{r2.status_code} {detail2[:80]}")
    hp = login("pm@sipro.co.id")
    rp = requests.get(f"{BASE}/leads/{lead_id}", headers=hp, timeout=30)
    detailp = str((rp.json() or {}).get("detail", "")) if rp.status_code == 403 else ""
    check(rp.status_code == 403 and "bukan lead anda" not in detailp.lower(),
          "403 izin peran BUKAN kalimat yang sama dengan 403 lingkup baris",
          f"{rp.status_code} {detailp[:80]}")
    return sa, lead_id


def audit_dangerous_combo(sa: dict, lead_id: str) -> None:
    """D6..D8 — buktikan kombinasi 'primer 200 + panel 403' MASIH MUNGKIN, lalu pulihkan.

    Kenapa perlu: sesudah izin baca diberikan ke keuangan, tidak ada lagi peran demo yang
    menghasilkan kombinasi itu. Tetapi admin BOLEH mencabut izin apa pun dari layar Hak
    Akses, jadi kombinasinya tetap nyata — dan ketahanan halaman harus dijaga untuk itu,
    bukan untuk keadaan hari ini saja.
    """
    head("D6..D8  Kombinasi berbahaya 'primer 200 + panel 403' + pemulihan izin")
    before = requests.get(f"{BASE}/admin/permissions", headers=sa, timeout=30).json()["data"]["matrix"]
    asli = copy.deepcopy((before.get("appointments") or {}).get("finance") or [])
    draft = copy.deepcopy(before)
    draft.setdefault("appointments", {})["finance"] = []
    try:
        put = requests.put(f"{BASE}/admin/permissions", headers=sa, json={"matrix": draft},
                           timeout=30)
        check(put.status_code == 200, "izin appointments finance bisa dicabut lewat API resmi",
              str(put.status_code))
        h = login("finance@sipro.co.id")
        primer = requests.get(f"{BASE}/leads/{lead_id}", headers=h, timeout=30).status_code
        panel = requests.get(f"{BASE}/appointments", headers=h, params={"lead_id": lead_id},
                             timeout=30).status_code
        check(primer == 200 and panel == 403,
              "kombinasi 'primer 200 + panel 403' terbukti MASIH MUNGKIN (harus tahan-banting)",
              f"primer={primer} panel={panel}")
    finally:
        draft2 = copy.deepcopy(before)
        draft2.setdefault("appointments", {})["finance"] = asli or ["view_all"]
        requests.put(f"{BASE}/admin/permissions", headers=sa, json={"matrix": draft2}, timeout=30)
    h = login("finance@sipro.co.id")
    ulang = requests.get(f"{BASE}/appointments", headers=h, params={"lead_id": lead_id},
                         timeout=30).status_code
    check(ulang == 200, "izin DIPULIHKAN setelah pengujian (gate tidak meninggalkan jejak)",
          str(ulang))


def main() -> None:
    print("verify_panel_resilience — GATE 44 (Fase 52): satu 403 panel tidak boleh "
          "mematikan halaman, dan layar tidak boleh berbohong")
    audit_loader()
    audit_profile_pages()
    audit_tabs()
    audit_nav_map()
    sa, lead_id = audit_server()
    if lead_id:
        audit_dangerous_combo(sa, lead_id)
    print("\n" + "-" * 62)
    print(f"HASIL verify_panel_resilience: {PASSED} PASS, {len(FAIL)} FAIL")
    if FAIL:
        print("GATE KETAHANAN PANEL GAGAL:")
        for x in FAIL:
            print(f"  - {x}")
        sys.exit(1)
    print("GATE KETAHANAN PANEL PASSED")


if __name__ == "__main__":
    main()
