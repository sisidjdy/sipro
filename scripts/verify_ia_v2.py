#!/usr/bin/env python3
"""verify_ia_v2.py — GATE IA & Design System V2 (Fase 40).

Kenapa gate ini ada (cacat NYATA yang sudah pernah terjadi di repo ini):

  1. **Menu dilebur, fitur hilang tanpa sadar.** Fase 40c membuang enam pintu menu
     (`/deals`, `/construction`, `/build-calendar`, `/build-calibration`, `/field`,
     `/permits`) ke dalam hub bertab. Kalau rutenya juga ikut dihapus, semua notifikasi &
     tugas yang SUDAH terbit (menyimpan tautan ke rute itu) menjadi rusak. Gate menuntut:
     hilang dari sidebar, TETAP ADA sebagai route.
  2. **Menu "Segera Hadir" yang punya route** = halaman kosong yang terasa seperti bug.
     Gate menuntut item comingSoon tidak punya `path` sama sekali.
  3. **Daftar yang belum dimigrasikan.** Sebelum Fase 40, tujuh daftar transaksional tidak
     punya filter/sort/ekspor dan sebagian mengurutkan data terpaginasi di browser (bohong).
     Gate menuntut setiap daftar utama memakai `DataTable` + `FilterQuery` (useListQuery) dan
     TIDAK lagi memakai `<Table>` mentah.
  4. **KPI yang tidak bisa ditelusuri.** Blueprint §7.3: "angka KPI wajib bisa di-drill-down;
     tanpa itu dianggap belum selesai". Gate memanggil API sungguhan: setiap KPI Beranda
     harus punya `drill`, rute tujuannya harus ada, dan untuk KPI berbasis hitungan tugas
     jumlah baris hasil filter HARUS SAMA dengan angka KPI-nya (kalau beda, angka bohong).
  5. **Peta menu membusuk.** `navMigrationMap.js` dipakai dialog "menu saya ke mana?"; setiap
     tujuannya harus rute yang benar-benar ada, dan dialognya harus terpasang di Sidebar.
  6. **Batas menu berupa ANGKA MATI ikut membusuk (ditemukan Fase 44).** CHECK 3 dulu hanya
     memeriksa `jumlah pintu ≤ 26` — potret Fase 40c. Begitu Fase 43 membuka dua pintu yang
     MEMANG direncanakan `docs/v2/40_PETA_NAV_V2.md`, gate memerah tanpa ada cacat; gate yang
     memerah karena kadaluwarsa adalah gate yang akan mulai diabaikan orang. Sekarang sidebar
     dibandingkan dengan **ledger pintu resmi** di dokumen itu (§7), sehingga yang tertangkap
     adalah bahaya sebenarnya: pintu **asing** (ditambah tanpa jejak keputusan) dan pintu
     **hilang** (fitur lenyap diam-diam), plus anggaran anti-sprawl `DOOR_BUDGET`.

Exit !=0 bila ada FAIL. Uji-mutasi: `scripts/mutasi_40_ia.py`.
"""
import json
import pathlib
import re
import sys

import requests

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
ROOT = pathlib.Path(__file__).resolve().parent.parent
FE = ROOT / "frontend" / "src"
fails = []

# Menu yang dilebur ke hub: WAJIB hilang dari sidebar, WAJIB tetap punya route (alias).
MERGED = ["/deals", "/construction", "/build-calendar", "/build-calibration", "/field",
          "/permits"]
# Fase 44: dulu di sini ada `MAX_NONADMIN_ITEMS = 26` (potret Fase 40c). Angka mati itu
# MEMBUSUK — Fase 43 membuka 2 pintu yang MEMANG direncanakan dokumen nav (Kampanye & Biaya
# Iklan, Atribusi & CAPI) sehingga gate memerah (28 > 26) tanpa ada yang salah. Sekarang
# sidebar dibandingkan dengan LEDGER PINTU RESMI di `docs/v2/40_PETA_NAV_V2.md` §7 (blok
# json bertanda `<!-- NAV_DOOR_LEDGER -->`), jadi gate menangkap dua hal yang benar-benar
# berbahaya: pintu ASING (tak terdokumentasi) dan pintu HILANG (fitur lenyap diam-diam).
LEDGER_DOC = ROOT / "docs" / "v2" / "40_PETA_NAV_V2.md"
DOOR_BUDGET = 31   # anggaran anti-sprawl (30 + /legal iter149); melewatinya = IA harus dilebur jadi hub bertab
# Daftar transaksional yang WAJIB memakai pola tabel pro.
LISTS = {
    "pages/LeadsPage.js": "lead",
    "components/sales/DealsListTab.js": "deal",
    "components/customers/CustomersListTab.js": "pembeli",
    "components/projects/AllUnitsTab.js": "unit",
    "components/work/TasksListTab.js": "tugas",
    "components/finance/ArPanel.js": "piutang (AR)",
    "components/documents/DocumentsListTab.js": "dokumen",
    "components/complaints/ComplaintsListTab.js": "komplain",
}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)
    return cond


def read(rel):
    p = FE / rel
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def door_ledger():
    """Daftar pintu menu RESMI dari docs/v2/40 §7 (blok json `<!-- NAV_DOOR_LEDGER -->`).

    Dokumen = SSOT-nya, bukan kode: menambah pintu menu berarti menambah barisnya di dokumen
    nav pada fase yang sama, sehingga keputusan IA selalu punya jejak. Bila blok/JSON-nya
    rusak, fungsi mengembalikan None dan gate GAGAL (bukan lolos diam-diam).
    """
    if not LEDGER_DOC.exists():
        return None
    m = re.search(r"<!-- NAV_DOOR_LEDGER -->\s*```json\s*(.*?)```",
                  LEDGER_DOC.read_text(encoding="utf-8", errors="ignore"), re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) and data else None


def nav_items(nav_src):
    """[(id, path|None, comingSoon, group)] dari NAV_STRUCTURE (regex, KODE menang)."""
    items, group = [], "?"
    body = nav_src.split("export const NAV_STRUCTURE", 1)[-1].split("export function", 1)[0]
    for line in body.splitlines():
        g = re.search(r'groupId:\s*"([^"]+)"', line)
        if g:
            group = g.group(1)
        mid = re.search(r'id:\s*"([^"]+)"', line)
        if not mid or g:
            if not (mid and not g):
                continue
        # item bisa memanjang beberapa baris; ambil blok sampai penutupnya
        items.append({"id": mid.group(1), "line": line, "group": group})
    return items


def main():
    nav = read("config/navigationConfig.js")
    app = read("App.js")
    routes = set(re.findall(r'<Route\s+path="([^"]+)"', app))

    print("\n1. Peleburan menu (fitur tidak boleh hilang)")
    body = nav.split("export const NAV_STRUCTURE", 1)[-1].split("export function", 1)[0]
    nav_paths = set(re.findall(r'path:\s*"([^"]+)"', body))
    for p in MERGED:
        check(f"menu lama '{p}' tidak lagi di sidebar", p not in nav_paths)
        check(f"rute alias '{p}' TETAP hidup", p in routes)
    check("hub Pembangunan '/build' ada di sidebar", "/build" in nav_paths)
    check("hub Pembangunan '/build' punya route", "/build" in routes)
    meta = nav.split("PAGE_META", 1)[-1].split("const ALL", 1)[0]
    check("'/build' punya PAGE_META (judul TopBar resolve)", '"/build"' in meta)

    print("\n2. Item 'Segera Hadir' tidak boleh bisa diklik")
    soon_blocks = [b for b in re.split(r"\n\s{4,6}\{", body) if "comingSoon: true" in b]
    # Fase 44: dulu gate MEWAJIBKAN minimal satu item "Segera Hadir" sebagai bukti peta jalan
    # jujur. Aturan itu berbalik arah begitu peta jalan menu SELESAI (Analitik & BI dibuka):
    # ia menuntut aplikasi menyimpan satu menu yang sengaja tidak berfungsi selamanya. Yang
    # benar-benar penting bukan ADANYA item itu, melainkan bahwa item semacam itu TIDAK BISA
    # DIKLIK dan menjelaskan kapan datangnya — itu yang diperiksa di bawah.
    check("jumlah item comingSoon dilaporkan (0 = seluruh peta jalan menu sudah dibuka)",
          True, f"{len(soon_blocks)} item")
    for b in soon_blocks:
        label = (re.search(r'label:\s*"([^"]+)"', b) or [None, "?"])[1]
        check(f"comingSoon '{label}' tanpa path", "path:" not in b)
        check(f"comingSoon '{label}' menjelaskan kapan (note)", "note:" in b)

    print("\n3. Pintu menu non-admin = LEDGER RESMI (docs/v2/40 §7) + anggaran anti-sprawl")
    admin = {p for p in nav_paths if p.startswith("/admin")}
    non_admin = nav_paths - admin
    ledger = door_ledger()
    check("ledger pintu resmi terbaca dari docs/v2/40_PETA_NAV_V2.md §7", ledger is not None)
    if ledger is not None:
        ledger_routes = {d.get("route") for d in ledger}
        asing = sorted(non_admin - ledger_routes)
        hilang = sorted(ledger_routes - non_admin)
        check("tidak ada pintu sidebar di luar ledger (pintu asing)", not asing,
              f"asing: {asing}" if asing else f"{len(non_admin)} pintu")
        check("semua pintu ledger benar-benar ada di sidebar (fitur tidak hilang)", not hilang,
              f"hilang: {hilang}" if hilang else f"{len(ledger_routes)} pintu")
        check(f"jumlah pintu ledger ≤ anggaran {DOOR_BUDGET}", len(ledger) <= DOOR_BUDGET,
              f"{len(ledger)} pintu")
        tanpa_fase = [d.get("route") for d in ledger if not str(d.get("phase") or "").strip()]
        check("setiap pintu ledger menyebut fase pembukaannya", not tanpa_fase,
              f"tanpa fase: {tanpa_fase}" if tanpa_fase else "")
        tanpa_route = [d["route"] for d in ledger if d.get("route") not in routes]
        check("setiap pintu ledger punya <Route> di App.js", not tanpa_route,
              f"tanpa route: {tanpa_route}" if tanpa_route else "")
        tanpa_meta = [d["route"] for d in ledger if f'"{d.get("route")}"' not in meta]
        check("setiap pintu ledger punya PAGE_META (judul TopBar resolve)", not tanpa_meta,
              f"tanpa meta: {tanpa_meta}" if tanpa_meta else "")
    check("buildNavGroups menyembunyikan grup kosong",
          "if (roleItems.length) result.push" in nav)
    check("countNavItems tersedia untuk audit", "export function countNavItems" in nav)

    print("\n4. Hub bertab memakai penanda ?hub= (tidak bentrok dengan ?tab= di dalamnya)")
    for page, testid in (("pages/BuildHubPage.js", "HUB.build"),
                         ("pages/CustomersPage.js", "CUSTOMERS.page"),
                         ("pages/DocumentsPage.js", "DOCS.page")):
        src = read(page)
        check(f"{pathlib.Path(page).name} memakai TabPage paramKey=\"hub\"",
              'paramKey="hub"' in src and "TabPage" in src)
        check(f"{pathlib.Path(page).name} punya data-testid halaman", testid.split(".")[0] in src)

    print("\n5. Semua daftar utama = tabel pro (cari + filter + sort + ekspor + paginasi)")
    toolbar = read("components/patterns/DataTableToolbar.js")
    check("toolbar tabel punya kotak cari ber-testid",
          "data-testid={testIds.search || DT.search}" in toolbar)
    check("toolbar tabel punya ekspor CSV", "testIds.export || DT.export" in toolbar)
    check("toolbar tabel punya pemilih kolom", "testIds.columns || DT.columns" in toolbar)
    check("tabel punya sort per kolom ber-testid", "${DT.sort}-${key}" in read("components/patterns/DataTable.js"))
    for rel, label in LISTS.items():
        src = read(rel)
        name = pathlib.Path(rel).name
        if not check(f"{name} ada", bool(src)):
            continue
        check(f"{name} memakai DataTable", "DataTable" in src)
        check(f"{name} memakai FilterBar", "FilterBar" in src)
        check(f"{name} query hidup di URL (useListQuery)", "useListQuery" in src)
        check(f"{name} tidak lagi memakai <Table> mentah",
              "@/components/ui/table" not in src, label)

    print("\n6. Halaman yang dipakai GANDA (rute lama + tab hub) tidak boleh menendang pemakai")
    # Cacat NYATA yang ditemukan lewat uji browser sesi ini: halaman yang disematkan di hub
    # menulis keadaannya ke URL dengan pathname HARDCODE, sehingga `/build?hub=kalender`
    # langsung terpental ke `/build-calendar` (tab yang baru diklik hilang).
    for rel, legacy in (("pages/BuildCalendarPage.js", "/build-calendar"),
                        ("pages/ConstructionPage.js", "/construction")):
        src = read(rel)
        name = pathlib.Path(rel).name
        check(f"{name} tidak menulis pathname hardcode",
              f'pathname: "{legacy}"' not in src, legacy)
        check(f"{name} memakai selfPath(loc.pathname, …)", "selfPath(loc.pathname" in src)
    tabpage = read("components/patterns/TabPage.js")
    # Cacat kedua: filter satu tab bocor ke tab lain (mis. `project_id` dari tab Kalender
    # terbaca tab Papan Unit sebagai filter proyek yang tidak pernah dipilih pemakai).
    check("TabPage memulai query BERSIH saat pindah tab",
          "const next = new URLSearchParams();" in tabpage)
    check("TabPage tetap menjaga penanda tab yang lebih luar (hub)",
          "TAB_MARKERS" in tabpage and 'if (marker === paramKey) break;' in tabpage)

    print("\n7. Peta menu lama→baru bisa dicapai DARI DALAM aplikasi")
    mig = read("config/navMigrationMap.js")
    sidebar = read("components/layout/Sidebar.js")
    check("navMigrationMap.js ada", bool(mig))
    # Diperiksa pada PEMAKAIANNYA (JSX), bukan sekadar ada string namanya: uji-mutasi M8
    # membuktikan komponennya bisa dicabut dari tampilan sementara `import`-nya tertinggal,
    # dan pemeriksaan longgar tetap hijau padahal peta menu sudah tak bisa dibuka pemakai.
    check("dialog peta menu terpasang di Sidebar", "<NavMigrationDialog" in sidebar)
    check("dokumen peta nav ada", (ROOT / "docs/v2/40_PETA_NAV_V2.md").exists())
    targets = re.findall(r'to:\s*"([^"]+)"', mig)
    check("peta menu punya minimal 12 baris", len(targets) >= 12, f"{len(targets)} baris")
    for t in targets:
        base = t.split("?")[0]
        check(f"tujuan peta '{t}' punya route", base in routes)

    print("\n8. KPI Beranda WAJIB bisa di-drill-down (bukti API, bukan bacaan kode)")
    home_js = read("pages/Home.js")
    check("Home.js meneruskan drill ke KpiCard", "to={k.drill}" in home_js)
    check("KpiCard mendukung tautan drill", 'data-drill={to}' in read("components/patterns/KpiCard.js"))
    for email in ("superadmin@sipro.co.id", "sales@sipro.co.id", "finance@sipro.co.id",
                  "pm@sipro.co.id", "manager@sipro.co.id"):
        h = login(email)
        data = requests.get(f"{BASE}/work/home", headers=h, timeout=30).json()["data"]
        kpis = data.get("kpis") or []
        check(f"{email}: ada KPI", len(kpis) >= 3, f"{len(kpis)} kartu")
        for k in kpis:
            drill = k.get("drill") or ""
            if not check(f"{email}: KPI '{k['label']}' punya drill", bool(drill)):
                continue
            path, _, qs = drill.partition("?")
            check(f"{email}: drill '{drill}' menuju route yang ada", path in routes)
            # KPI tugas: jumlah baris hasil filter harus SAMA dengan angka KPI-nya.
            if path == "/tasks" and "bucket=" in qs:
                params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
                params.pop("tab", None)
                r = requests.get(f"{BASE}/work/tasks", headers=h,
                                 params={**params, "limit": 1}, timeout=30)
                total = r.json().get("total") if r.ok else f"HTTP {r.status_code}"
                check(f"{email}: angka '{k['label']}'={k['value']} sama dengan hasil filter",
                      total == k["value"], f"daftar mengembalikan {total}")
        team = data.get("team")
        if team:
            check(f"{email}: angka tim punya drill", bool(team.get("drills")))

    print("-" * 60)
    if fails:
        print(f"GATE IA V2 FAILED: {len(fails)} temuan — {fails[:8]}")
        sys.exit(1)
    print("GATE IA V2 PASSED: menu dilebur tanpa fitur hilang, daftar seragam, KPI bisa "
          "ditelusuri sampai barisnya")


if __name__ == "__main__":
    main()
