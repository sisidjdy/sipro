#!/usr/bin/env python3
"""verify_late_fee.py — GATE 49 (Fase 58): TOLERANSI keterlambatan yang dijanjikan kontrak
wajib dipakai, dan denda keterlambatan wajib BERJURNAL, tidak dobel, serta hanya bisa
diringankan Manajer Keuangan dengan alasan tertulis.

## Kenapa gate ini ada

Sejak Fase 57A pemakai bisa menyusun toleransi per termin, dan kalimat toleransi itu ikut
TERCETAK pada dokumen SPR yang ditandatangani pembeli. Sampai Fase 57 angka itu tidak dipakai
siapa pun:

  * jadwal tagihan tidak membawa `grace_days` — tenggangnya hilang saat skema diterjemahkan;
  * layar menandai TERLAMBAT pada H+1, lebih cepat menuduh daripada perjanjiannya;
  * denda hanya angka perkiraan worksheet dengan tarif di luar Pusat Konfigurasi, dan bila
    diterapkan TIDAK berjurnal — pembeli ditagih sesuatu yang tidak ada di buku besar;
  * tidak ada jalan resmi untuk meringankan denda, padahal itu keputusan paling sering
    diambil manusia dan paling perlu jejak.

Yang dijaga di sini (dan tidak bisa dijaga uji perilaku biasa):

  * **Satu mesin.** Keadaan termin & nominal denda hanya dihitung `late_fee_engine`; layar,
    portal, daftar penagihan, dan tombol lama "Denda" membaca angka dari fungsi yang sama.
  * **Tenggang milik TERMIN**, bukan angka mati di kode; bawaannya dari Pusat Konfigurasi.
  * **Denda berjurnal & idempoten** per (termin, bulan) — klik dua kali bukan denda kedua.
  * **Keringanan bukan penghapusan jejak**: membalik jurnal, wajib beralasan, hanya Manajer
    Keuangan, dan TIDAK bisa dianulir dengan menagihkan ulang denda yang sama.
  * **Pembeli membaca angka yang sama** tanpa nomor akun GL bocor ke matanya.

Jalankan: python3 scripts/verify_late_fee.py
"""
import os
import pathlib
import re
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
FAIL = []
PASSED = 0
load_dotenv(ROOT / "backend" / ".env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ORG = os.environ.get("DEFAULT_ORG_ID", "org-sipro")
TAG = "GATE49"


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


def read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    return "\n".join(ln for ln in src.split("\n")
                     if not ln.strip().startswith(("//", "#")))


def fungsi(src: str, nama: str) -> str:
    m = re.search(rf"^(?:async )?def {re.escape(nama)}\(", src, re.M)
    if not m:
        return ""
    ekor = src[m.end():]
    m2 = re.search(r"^(?:async def |def |class )", ekor, re.M)
    return src[m.start(): m.end() + (m2.start() if m2 else len(ekor))]


def opsi_kamus(ref_src: str, grup: str) -> set:
    m = re.search(rf'"{grup}":\s*\{{', ref_src)
    if not m:
        return set()
    seg = ref_src[m.end():].split("\n    },")[0]
    return set(re.findall(r'_o\("([a-z_0-9]+)"', seg))


def j(r):
    try:
        return r.json()
    except ValueError:
        return {}


def d(r) -> str:
    return f"HTTP {r.status_code} {str(j(r))[:200]}"


def login(email: str) -> dict:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"login {email} gagal: {d(r)}")
    return {"Authorization": f"Bearer {j(r)['access_token']}"}


# ============================================================ K. tingkat KODE
def bagian_k():
    head("K. Kode: toleransi & denda tidak bisa dilumpuhkan tanpa gate ini merah")
    lf = strip_comments(read(BE / "late_fee_engine.py"))
    fin = strip_comments(read(BE / "finance_engine.py"))
    fr = strip_comments(read(BE / "finance_reports.py"))
    st = read(BE / "settings_store.py")
    gl = read(BE / "gl_engine.py")
    # Matriks izin bawaan tinggal di `rbac_matrix.py` (dipisah agar tiap berkas <= 800
    # baris); RBAC-nya tetap SATU sumber, jadi gate memeriksa keduanya sebagai satu teks.
    rb = read(BE / "rbac.py") + read(BE / "rbac_matrix.py")
    router = read(BE / "routers" / "late_fee_router.py")
    portal = read(BE / "routers" / "portal_router.py")
    ref58 = read(BE / "reference_p58.py")

    hit = fungsi(fin, "compute_scheme_items")
    check('"grace_days": int(i.get("grace_days") or 0)' in hit,
          "K1 toleransi termin IKUT ke jadwal tagihan (tidak hilang saat skema "
          "diterjemahkan)")
    g = fungsi(lf, "grace_of")
    check('item.get("grace_days")' in g and 'pol["grace_days"]' in g,
          "K2 tenggang efektif = milik TERMIN dulu, baru bawaan Pusat Konfigurasi")
    pol = fungsi(lf, "policy")
    check(all(k in pol for k in ("KEY_GRACE", "KEY_RATE", "KEY_CAP", "KEY_MIN"))
          and "cfg.get(" in pol,
          "K3 kebijakan denda dibaca dari Pusat Konfigurasi (bukan angka mati di kode)")
    for key in ("payment.late.grace_days", "payment.late.rate_pct_month",
                "payment.late.max_pct_of_term", "payment.late.min_charge"):
        check(f'"{key}"' in st, f"K3b kunci {key} terdaftar di Pusat Konfigurasi")

    dn = fungsi(lf, "denda_of")
    check('pol["max_pct_of_term"]' in dn and 'pol["min_charge"]' in dn,
          "K4 denda dibatasi ATAS (persen per termin) dan BAWAH (nominal minimum)")
    check('pol["rate_pct_month"] / 100.0' in dn and "/ 30.0" in dn,
          "K4b denda prorata hari sesudah toleransi (bukan sebulan penuh sejak H+1)")
    ai = fungsi(lf, "assess_item")
    check('"dalam_tenggang"' in ai and "grace_until" in ai and "grace_left_days" in ai,
          "K5 ada keadaan DALAM TOLERANSI beserta tanggal batas & sisa harinya")
    check('row["days_late"] = max(0, row["days_past_due"] - grace)' in ai,
          "K5b hari denda dihitung SESUDAH toleransi, bukan sejak jatuh tempo")
    check('ref.label_of("late_state"' in ai,
          "K5c label keadaan diambil dari Kamus Data (layar tidak mengarang label)")

    ap = fungsi(lf, "apply")
    check("gl.post_journal(" in ap and "AKUN_PIUTANG" in ap
          and "AKUN_PENDAPATAN_DENDA" in ap,
          "K6 denda yang ditagihkan BERJURNAL (piutang & pendapatan denda)")
    check('source_event=event' in ap and 'f"late_fee:{deal_id}:{r[\'item_id\']}:{period}"' in ap,
          "K6b jurnal denda idempoten per (termin, bulan) — klik dua kali bukan denda kedua")
    check('r["denda_billable"]' in ap and "denda_running" in strip_comments(fungsi(lf, "assess")),
          "K6c yang ditagihkan adalah SELISIH dengan denda yang sudah pernah ditagihkan")
    wv = fungsi(lf, "waive")
    check("may_waive" in wv and "< 10" in wv,
          "K7 keringanan hanya oleh yang berwenang & wajib beralasan minimal 10 huruf")
    check("gl.post_journal(" in wv
          and re.search(r"AKUN_PENDAPATAN_DENDA.*debit.*nilai", wv, re.S) is not None,
          "K7b keringanan MEMBALIK jurnal dendanya (bukan menghapus jejak)")
    check('int(row.get("paid_amount") or 0) > 0' in wv,
          "K7c denda yang sudah dibayar tidak bisa 'diringankan' (uang tidak lenyap)")
    wm = fungsi(lf, "_waived_days_map")
    check(bool(wm) and "_waived_days_map(items)" in fungsi(lf, "assess"),
          "K8 keringanan tidak bisa dianulir dengan menagihkan denda yang SAMA lagi")

    kode_blk = set(re.findall(r'_blk\("([a-z_0-9]+)"', lf))
    check(bool(kode_blk) and kode_blk <= opsi_kamus(ref58, "late_fee_block"),
          "K9 setiap sebab 'denda belum bisa ditagihkan' terdaftar di Kamus Data",
          f"tak terdaftar: {sorted(kode_blk - opsi_kamus(ref58, 'late_fee_block'))}")
    kode_state = set(re.findall(r'row\["state"\] = "([a-z_]+)"', lf)) | {"lunas"}
    check(kode_state <= opsi_kamus(ref58, "late_state"),
          "K9b setiap keadaan termin terdaftar di Kamus Data",
          f"tak terdaftar: {sorted(kode_state - opsi_kamus(ref58, 'late_state'))}")
    check('("4-1400", "Pendapatan Denda Keterlambatan", "revenue")' in gl,
          "K10 akun pendapatan denda ada di CoA standar (bukan menumpang lain-lain)")

    lf_blok = rb.split('"late_fee": {', 1)[1].split("},", 1)[0] if '"late_fee": {' in rb else ""
    check('"finance": ["view_all", "create"],' in lf_blok
          and '"finance_manager": ["view_all", "create", "override"],' in lf_blok,
          "K11 RBAC: yang MENAGIHKAN denda bukan yang MERINGANKANnya",
          lf_blok.replace("\n", " ")[:160])
    check('"late_fee": ["view_all", "create", "override"]' in rb,
          "K11b izin keringanan dipasang eksplisit (matriks RBAC lama tidak mengunci fitur)")
    check('require_permission("late_fee", "create")' in router
          and 'require_permission("late_fee", "override")' in router,
          "K12 endpoint memakai izin yang benar (menagihkan ≠ meringankan)")
    check('if is_scoped_sales(user) and deal.get("assigned_to") != user.get("email"):' in router
          and 'status_code=403' in router,
          "K12b sales hanya melihat transaksi miliknya (lingkup data dijaga server)")

    fr_apply = fungsi(fr, "apply_late_fee")
    check("lf.apply(" in fr_apply and "is_penalty" not in fr_apply,
          "K13 tombol 'Denda' lama memakai mesin yang SAMA (tidak ada rumus & jurnal kedua)")
    check("lf.denda_of(" in fungsi(fr, "compute_denda"),
          "K13b rumus denda hanya ada di satu tempat")
    wl = fungsi(fr, "collections_worklist")
    check("lf.assess_item(" in wl and 'st["state"] == "terlambat"' in wl,
          "K13c daftar penagihan menghormati toleransi (yang masih tenggang bukan tunggakan)")
    check("lf.policy(" in fungsi(fr, "get_collection_config")
          and "cfg.set_value(" in fungsi(fr, "set_collection_config"),
          "K13d kebijakan penagihan satu sumber dengan Pusat Konfigurasi (berjejak)")

    pr = fungsi(lf, "portal_rows")
    check(bool(pr) and "lf.portal_rows(" in portal,
          "K14 portal pembeli membaca angka dari mesin yang sama")
    check("1-1300" not in pr and "4-1400" not in pr and "AKUN_" not in pr,
          "K14b nomor akun GL tidak pernah dikirim ke mata pembeli")


# ============================================================ K-UI. layar
def bagian_kui():
    head("K-UI. Layar: janji yang tidak bisa dilihat manusia dianggap tidak ada")
    tab = read(FE / "components" / "customers" / "CustomerPaymentPlanTab.js")
    panel = read(FE / "components" / "finance" / "LateFeePanel.js")
    portal = read(FE / "components" / "portal" / "panels" / "PaymentsPanel.js")
    ids = read(FE / "constants" / "testIds" / "p58.js")
    idx = read(FE / "constants" / "testIds" / "index.js")

    check("belum</b> dibangun: <b>toleransi keterlambatan</b>" not in tab
          and "Yang <b>belum</b> dibangun: <b>toleransi" not in tab,
          "K20 layar tidak lagi mengaku toleransi keterlambatan 'belum dibangun'")
    check("planState(item, late)" in tab and "(late?.rows || []).find" in tab,
          "K20b keadaan termin dibaca dari SERVER (layar tidak menghitung tenggang sendiri)")
    check("row.state_label" in tab and '"Terlambat"' not in tab,
          "K20c label keadaan berasal dari Kamus Data, bukan diketik layar")
    check("<LateFeePanel" in tab and 'from "@/components/finance/LateFeePanel"' in tab,
          "K20d panel denda BENAR-BENAR dirender (bukan komponen mati)")
    check("P58.graceBanner" in tab,
          "K20e termin yang masih di dalam toleransi disebutkan apa adanya di layar")

    check("P58.policy" in panel and "data.policy_sentence" in panel,
          "K21 layar menampilkan kalimat aturan dari SERVER (tidak mengarangnya)")
    check("P58.blockNote" in panel and "data.block.detail" in panel,
          "K21b sebab denda belum bisa ditagihkan DISEBUTKAN (bukan tombol diam)")
    check('(t.denda_billable || 0) > 0' in panel and "perm.apply" in panel,
          "K21c tombol tagihkan hanya muncul bila memang ada denda & pemakai berwenang")
    check("P58.waiveDialog" in panel and "reason.trim().length < 10" in panel,
          "K21d keringanan menuntut alasan di layar (bukan hanya ditolak server)")
    check("wewenang Manajer Keuangan" in panel and "P58.denied" in panel,
          "K21e peran tanpa wewenang membaca SEBABnya, bukan layar kosong")
    check("grace_left_days" in panel and "hari lewat toleransi" in panel,
          "K21f layar menyebut sisa hari toleransi / berapa hari lewat toleransi")

    check("P58.portalCard" in portal and "p.late.policy_sentence" in portal
          and "{p.late && (p.late.rows?.length || p.late.penalties?.length) ? (" in portal,
          "K22 portal pembeli menampilkan toleransi & dendanya sendiri (kartunya HIDUP, "
          "bukan cabang mati)")
    check("state_label" in portal and "1-1300" not in portal,
          "K22b portal memakai label Kamus Data & tanpa nomor akun")

    dipakai = tab + panel + portal
    mati = [k for k in re.findall(r"^\s{2}(\w+):", ids, re.M)
            if f"P58.{k}" not in dipakai]
    check(not mati, "K23 tidak ada testId Fase 58 yang MATI (terdaftar tapi tak dipakai)",
          ", ".join(mati))
    check("./p58" in idx, "K23b testId Fase 58 terdaftar di registry pusat")


# ============================================================ D. perilaku
def bahan_uji() -> dict:
    """Satu transaksi uji dengan DUA termin: satu lewat toleransi, satu masih tenggang."""
    import uuid
    now = datetime.now(timezone.utc)
    lead_id, deal_id, inv_id = (str(uuid.uuid4()) for _ in range(3))
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    db.leads.insert_one({"id": lead_id, "org_id": ORG, "name": f"{TAG} Pembeli Denda",
                         "phone": "+628999000049", "status": "new",
                         "assigned_to": "sales2@sipro.co.id",
                         "created_at": now.isoformat(), "updated_at": now.isoformat()})
    db.deals.insert_one({"id": deal_id, "org_id": ORG, "lead_id": lead_id,
                         "lead_name": f"{TAG} Pembeli Denda", "unit_code": f"{TAG}-01",
                         "status": "booked", "assigned_to": "sales2@sipro.co.id",
                         "price": 100_000_000, "created_at": now.isoformat(),
                         "updated_at": now.isoformat()})
    db.ar_invoices.insert_one({
        "id": inv_id, "org_id": ORG, "deal_id": deal_id, "unit_code": f"{TAG}-01",
        "lead_name": f"{TAG} Pembeli Denda", "assigned_to": "sales2@sipro.co.id",
        "scheme_name": f"{TAG} Skema Uji", "status": "unpaid",
        "total": 100_000_000, "paid": 0, "outstanding": 100_000_000,
        "items": [
            {"id": t1, "label": "Termin lewat toleransi", "basis": "amount",
             "value": 60_000_000, "amount": 60_000_000, "paid_amount": 0,
             "status": "unpaid", "grace_days": 7,
             "due_date": (now - timedelta(days=37)).isoformat()},
            {"id": t2, "label": "Termin masih tenggang", "basis": "amount",
             "value": 40_000_000, "amount": 40_000_000, "paid_amount": 0,
             "status": "unpaid", "grace_days": 20,
             "due_date": (now - timedelta(days=5)).isoformat()},
        ],
        "created_at": now.isoformat(), "updated_at": now.isoformat()})
    return {"lead_id": lead_id, "deal_id": deal_id, "inv_id": inv_id, "t1": t1, "t2": t2}


def jurnal(deal_id: str, prefix: str) -> list:
    return list(db.journal_entries.find(
        {"org_id": ORG, "source_event": {"$regex": f"^{prefix}"},
         "$or": [{"source_id": deal_id}, {"source_deal_id": deal_id}]}, {"_id": 0}))


def bagian_d(bahan: dict):
    head("D. Perilaku: toleransi dihormati, denda berjurnal, keringanan tidak bisa dianulir")
    fin = login("finance@sipro.co.id")
    lead = login("finlead@sipro.co.id")
    sales = login("sales@sipro.co.id")
    deal_id, t1, t2 = bahan["deal_id"], bahan["t1"], bahan["t2"]

    r = requests.get(f"{BASE}/finance/late-fees/{deal_id}", headers=fin, timeout=30)
    a = j(r).get("data") or {}
    rows = {x["item_id"]: x for x in a.get("rows") or []}
    check(r.status_code == 200 and a.get("policy_sentence"),
          "D1 keadaan keterlambatan bisa dibaca beserta kalimat aturannya", d(r))
    check(rows.get(t2, {}).get("state") == "dalam_tenggang",
          "D2 termin lewat tanggal TAPI masih di dalam toleransi = belum menunggak",
          str(rows.get(t2, {}).get("state")))
    check(int(rows.get(t2, {}).get("grace_left_days") or 0) > 0,
          "D2b layar/API menyebutkan sisa hari toleransi",
          str(rows.get(t2, {}).get("grace_left_days")))
    check(rows.get(t1, {}).get("state") == "terlambat"
          and int(rows.get(t1, {}).get("days_late") or 0) == 30,
          "D3 termin lewat toleransi = terlambat, dihitung SESUDAH tenggang (37-7=30 hari)",
          str(rows.get(t1, {})))
    pol = a.get("policy") or {}
    harap = min(round(60_000_000 * pol.get("rate_pct_month", 0) / 100 * 30 / 30),
                round(60_000_000 * pol.get("max_pct_of_term", 0) / 100))
    check(int(rows.get(t1, {}).get("denda_running") or 0) == harap,
          "D3b denda berjalan = tarif prorata, dibatasi persen per termin",
          f"{rows.get(t1, {}).get('denda_running')} vs {harap}")
    check(int(a.get("totals", {}).get("in_grace_outstanding") or 0) == 40_000_000,
          "D3c yang masih di dalam toleransi TIDAK dihitung sebagai tunggakan",
          str(a.get("totals")))

    r = requests.get(f"{BASE}/finance/late-fees/{deal_id}", headers=sales, timeout=30)
    check(r.status_code == 403,
          "D4 sales yang bukan pemegang transaksi tidak bisa membacanya", d(r))

    r = requests.post(f"{BASE}/finance/late-fees/{deal_id}/apply", headers=fin, json={},
                      timeout=60)
    dibuat = j(r).get("created") or []
    check(r.status_code == 200 and len(dibuat) == 1 and dibuat[0]["amount"] == harap,
          "D5 Keuangan bisa menagihkan denda yang berlaku", d(r))
    jr = jurnal(deal_id, "late_fee:")
    lines = {ln["account_code"]: (ln.get("debit", 0), ln.get("credit", 0))
             for e in jr for ln in e.get("lines") or []}
    check(len(jr) == 1 and lines.get("1-1300", (0, 0))[0] == harap
          and lines.get("4-1400", (0, 0))[1] == harap,
          "D5b jurnal denda: Dr Piutang Usaha / Cr Pendapatan Denda — berimbang", str(lines))
    inv = db.ar_invoices.find_one({"deal_id": deal_id}, {"_id": 0})
    denda_item = [i for i in inv["items"] if i.get("is_penalty")]
    check(len(denda_item) == 1 and int(inv["total"]) == 100_000_000 + harap
          and denda_item[0].get("penalty_for") == t1,
          "D5c denda menjadi baris tagihan yang menunjuk terminnya", str(inv["total"]))

    r = requests.post(f"{BASE}/finance/late-fees/{deal_id}/apply", headers=fin, json={},
                      timeout=60)
    check(r.status_code == 400 and "sudah ditagihkan" in str(j(r)).lower(),
          "D6 penekanan kedua BUKAN denda kedua (dan sebabnya disebutkan)", d(r))
    check(len(jurnal(deal_id, "late_fee:")) == 1,
          "D6b tidak ada jurnal denda kedua untuk termin & bulan yang sama")

    pid = denda_item[0]["id"]
    r = requests.post(f"{BASE}/finance/late-fees/{deal_id}/waive/{pid}", headers=fin,
                      json={"reason": "Pembeli terkena musibah kebakaran rumah"}, timeout=30)
    check(r.status_code == 403,
          "D7 Keuangan (yang menagihkan) TIDAK boleh meringankan dendanya sendiri", d(r))
    r = requests.post(f"{BASE}/finance/late-fees/{deal_id}/waive/{pid}", headers=lead,
                      json={"reason": "telat"}, timeout=30)
    check(r.status_code in (400, 422),
          "D7b keringanan tanpa alasan yang layak ditolak", d(r))
    r = requests.post(f"{BASE}/finance/late-fees/{deal_id}/waive/{pid}", headers=lead,
                      json={"reason": "Pembeli terkena musibah kebakaran, disetujui direksi"},
                      timeout=60)
    check(r.status_code == 200 and int(j(r).get("waived", {}).get("waived_amount") or 0) == harap,
          "D8 Manajer Keuangan bisa memberi keringanan beralasan", d(r))
    jw = jurnal(pid, "late_fee_waive:") or list(db.journal_entries.find(
        {"org_id": ORG, "source_event": f"late_fee_waive:{pid}"}, {"_id": 0}))
    lw = {ln["account_code"]: (ln.get("debit", 0), ln.get("credit", 0))
          for e in jw for ln in e.get("lines") or []}
    check(len(jw) == 1 and lw.get("4-1400", (0, 0))[0] == harap
          and lw.get("1-1300", (0, 0))[1] == harap,
          "D8b keringanan MEMBALIK jurnalnya (pendapatan denda didebit kembali)", str(lw))
    inv = db.ar_invoices.find_one({"deal_id": deal_id}, {"_id": 0})
    check(int(inv["total"]) == 100_000_000 and int(inv["outstanding"]) == 100_000_000,
          "D8c tagihan pembeli kembali seperti sebelum denda", str(inv["total"]))

    r = requests.post(f"{BASE}/finance/late-fees/{deal_id}/apply", headers=fin, json={},
                      timeout=60)
    check(r.status_code == 400 and "diringankan" in str(j(r)).lower(),
          "D9 keringanan tidak bisa dianulir dengan menagihkan denda yang sama lagi", d(r))

    r = requests.get(f"{BASE}/finance/collections", headers=fin, timeout=60)
    baris = [x for x in (j(r).get("data") or {}).get("rows") or []
             if x.get("deal_id") == deal_id]
    check(bool(baris) and int(baris[0].get("overdue_amount") or 0) == 60_000_000
          and int(baris[0].get("in_grace_amount") or 0) == 40_000_000,
          "D10 daftar penagihan memisahkan tunggakan dari yang masih di dalam toleransi",
          str(baris[:1]))
    return True


def bersihkan(bahan: dict) -> int:
    if not bahan:
        return 0
    deal_id = bahan["deal_id"]
    db.journal_entries.delete_many({"source_event": {"$regex": f"late_fee.*{deal_id}"}})
    inv = db.ar_invoices.find_one({"deal_id": deal_id}, {"_id": 0}) or {}
    pids = [i["id"] for i in inv.get("items") or [] if i.get("is_penalty")]
    for pid in pids:
        db.journal_entries.delete_many({"source_event": f"late_fee_waive:{pid}"})
    db.ar_invoices.delete_many({"deal_id": deal_id})
    db.deals.delete_many({"id": deal_id})
    db.leads.delete_many({"id": bahan["lead_id"]})
    db.activities.delete_many({"entity_id": {"$in": [deal_id, bahan["lead_id"]]}})
    db.notifications.delete_many({"related_entity_id": deal_id})
    db.tasks.delete_many({"related_entity_id": deal_id})
    db.audit_logs.delete_many({"entity_id": {"$in": [deal_id] + pids}})
    db.events.delete_many({"entity_id": deal_id})
    return (db.ar_invoices.count_documents({"deal_id": deal_id})
            + db.deals.count_documents({"id": deal_id})
            + db.leads.count_documents({"name": {"$regex": f"^{TAG}"}})
            + db.journal_entries.count_documents(
                {"source_event": {"$regex": f"late_fee.*{deal_id}"}}))


def main() -> int:
    print("=" * 78)
    print("GATE 49 — TOLERANSI KETERLAMBATAN & DENDA BERJURNAL (Fase 58)")
    print("=" * 78)
    try:
        requests.get(f"{BASE}/health", timeout=10)
    except requests.RequestException as e:
        print(f"Backend tidak menjawab: {e}")
        return 1
    bagian_k()
    bagian_kui()
    bahan = None
    try:
        bahan = bahan_uji()
        bagian_d(bahan)
    finally:
        head("Bahan uji dibuang tanpa sisa")
        sisa = bersihkan(bahan)
        check(sisa == 0, "D11 bahan uji gate dibuang bersih (termasuk jurnalnya)",
              f"sisa={sisa}")

    print("\n" + "-" * 78)
    if FAIL:
        print(f"GATE 49 MERAH — {len(FAIL)} gagal / {PASSED + len(FAIL)} pemeriksaan")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"GATE 49 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
