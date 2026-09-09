#!/usr/bin/env python3
"""verify_35.py — GATE Fase 35: Papan Mandor tahan sinyal hilang (antrean offline).

Melengkapi `poc_35.py` (aturan lewat API) dengan cek yang menahan PEMBUSUKAN DIAM-DIAM —
hal-hal yang dulu benar-benar terjadi dan tidak terlihat sampai dibuka di browser:

  A. Tidak ada `data-testid` Fase 35 yang mati, dan tidak ada modul antrean yatim
     (spanduk, panel antrean, penyimpan foto lokal semuanya terpasang).
  B. Modul yang MEMAKAI antrean benar-benar meng-IMPORT-nya (dulu `PhotoUploader`
     memanggil `sync.*` tanpa import dan `SubmitItemDialog` memakai `online` tanpa
     mengambilnya dari context → layar merah begitu dialog dibuka).
  C. Penjaga kode antrean: bukti tidak dihapus saat server menolak, id foto lokal ditukar
     id server sebelum lanjut (anti unggah dobel), pengiriman tidak tumpang tindih.
  D. Penjaga kode server: `client_ref` diputar ulang, dikunci sebelum item disentuh, dan
     kuncinya DILEPAS bila ditolak (kalau tidak, pekerjaan bisa hilang senyap).
  E. Cadangan di perangkat untuk hal-hal yang bikin papan tidak bisa dipakai saat offline:
     sesi, kamus pilihan (checklist), daftar proyek, dan cuplikan papan.
  F. Service worker menyimpan kerangka aplikasi TAPI tidak pernah men-cache `/api/`
     (data operasional tidak boleh menyamar sebagai data terkini).
  G. Kontrak runtime papan: payload memuat checklist LENGKAP + instruksi + kebijakan,
     grup SSOT antrean terdaftar, indeks idempotensi ada, tidak ada `client_ref` dobel,
     dan kunci pengiriman dilepas saat pengajuan ditolak (diuji tanpa mengubah data).

Jalankan: python3 scripts/verify_35.py
"""
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
PUB = ROOT / "frontend" / "public"
load_dotenv(BE / ".env")
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PW = "Sipro#2026"

ok_n, fail_n = 0, 0


def check(cond, label, detail=""):
    global ok_n, fail_n
    if cond:
        ok_n += 1
        print(f"  PASS  {label}")
    else:
        fail_n += 1
        print(f"  FAIL  {label}" + (f" — {str(detail)[:170]}" if detail else ""))
    return bool(cond)


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ------------------------------------------------------------------ A. testid & modul
def audit_wiring():
    head("A. Tidak ada testid / modul antrean yang mati")
    ids = read(FE / "constants" / "testIds" / "offline.js")
    values = re.findall(r':\s*"([a-z0-9-]+)"', ids)
    check(len(values) >= 10, "daftar testid Fase 35 lengkap", len(values))
    js = "\n".join(read(p) for p in FE.rglob("*.js"))
    keys = re.findall(r"^\s*([a-zA-Z]+):", ids, flags=re.M)
    dead = [k for k in keys if f"OFFLINE.{k}" not in js]
    check(not dead, "setiap testid Fase 35 dipakai di UI", dead)
    check("OfflineProvider" in read(FE / "App.js"), "OfflineProvider terpasang di App")
    shell = read(FE / "components" / "layout" / "AppShell.js")
    check("OfflineBanner" in shell, "spanduk jaringan tampil di seluruh aplikasi")
    banner = read(FE / "components" / "patterns" / "OfflineBanner.js")
    check("OfflineQueuePanel" in banner,
          "antrean bisa dibuka dari halaman mana saja (bukan hanya tab Papan Mandor)")
    board = read(FE / "components" / "construction" / "ForemanBoard.js")
    check("OfflineQueuePanel" in board and "queueStart" in board,
          "Papan Mandor memakai antrean (panel + aksi mulai)")


# --------------------------------------------------- B. import yang benar-benar ada
def audit_imports():
    head("B. Modul pemakai antrean benar-benar meng-import yang dipakainya")
    targets = {
        "components/patterns/PhotoUploader.js": ["offlineSync", "OFFLINE"],
        "components/construction/BuildItemDialogs.js": ["offlineSync", "OfflineContext", "OFFLINE"],
        "components/construction/ForemanBoard.js": ["offlineSync", "OfflineContext"],
        "components/construction/OfflineQueuePanel.js": ["OfflineContext", "ReferenceContext"],
        "components/patterns/OfflineBanner.js": ["OfflineContext"],
    }
    for rel, needs in targets.items():
        src = read(FE / rel)
        imports = "\n".join(l for l in src.splitlines() if l.startswith("import"))
        miss = [n for n in needs if n not in imports]
        check(not miss, f"{rel} meng-import modul yang dipakai", miss)
    dlg = read(FE / "components" / "construction" / "BuildItemDialogs.js")
    check(re.search(r"const\s*\{\s*online\s*\}\s*=\s*useOffline\(\)", dlg),
          "dialog ajukan mengambil status jaringan dari context (bukan variabel bebas)")
    check(dlg.count("const refRef = useRef") == 1,
          "penanda idempoten dideklarasikan tepat sekali", dlg.count("const refRef = useRef"))
    up = read(FE / "components" / "patterns" / "PhotoUploader.js")
    check("sync.storePhoto" in up and "isLocalPhoto" in up,
          "foto disimpan di perangkat saat offline & ditandai di pratinjau")


# ------------------------------------------------------------------ C. penjaga antrean
def audit_queue_guards():
    head("C. Penjaga antrean di perangkat")
    s = read(FE / "services" / "offlineSync.js")
    check('status: "rejected"' in s and "deleteJob" in s,
          "server menolak → status 'ditolak' + alasan asli, pekerjaan TIDAK dihapus diam-diam")
    check(re.search(r"status\s*>=\s*400\s*&&\s*status\s*<\s*500", s),
          "hanya penolakan 4xx yang dianggap final; galat jaringan tetap menunggu")
    check("await odb.putJob({ ...job, photos: swapped })" in s,
          "id foto lokal ditukar id server SEBELUM lanjut (anti unggah dobel)")
    check("if (flushing" in s and "flushing = true" in s,
          "pengiriman antrean tidak tumpang tindih")
    check("client_ref: job.client_ref" in s, "setiap pekerjaan antrean membawa penanda idempoten")
    db = read(FE / "utils" / "offlineDb.js")
    check("indexedDB" in db and "BLOBS" in db,
          "foto disimpan sebagai Blob di IndexedDB (bukan localStorage yang cuma teks)")
    ctx = read(FE / "context" / "OfflineContext.js")
    check('addEventListener("online"' in ctx and "setInterval" in ctx,
          "antrean dikirim saat sinyal kembali + dicoba ulang berkala")


# ------------------------------------------------------------------ D. penjaga server
def audit_server_guards():
    head("D. Penjaga idempotensi di server")
    a = read(BE / "build_actions.py")
    check('return {"item": fresh, "warning": None, "replay": True}' in a,
          "pengiriman ulang dengan penanda sama diputar ulang (tidak membuat pengajuan kedua)")
    check("_claim_ref" in a and "build_submit_claims" in a,
          "penanda dikunci SEBELUM item disentuh (dua tab tidak bisa mengirim dobel)")
    check(re.search(r"except Exception:\s*\n\s*#[^\n]*\n\s*#[^\n]*\n\s*await db\.build_submit_claims"
                    r"\.delete_one", a)
          or ("delete_one({\"org_id\": org, \"client_ref\": ref})" in a),
          "kunci DILEPAS bila pengajuan ditolak (mandor bisa memperbaiki & kirim ulang)")
    check("STALE_CLAIM_SECONDS" in a,
          "kunci basi bisa diambil ulang (proses mati di tengah jalan ≠ pekerjaan terkirim)")
    check(re.search(r"if ref:\s*\n\s*audit\[\"client_ref\"\] = ref", a),
          "penanda hanya DITULIS bila ada — `client_ref: null` bentrok dengan indeks unik sparse "
          "dan dulu membuat pengajuan kedua dari layar biasa gagal 500")
    idx = read(BE / "seed_phase31.py")
    check("build_item_submissions.create_index" in idx and "client_ref" in idx,
          "indeks unik penanda pengajuan disemai")
    check("build_submit_claims.create_index" in idx, "indeks unik kunci pengiriman disemai")
    r = read(BE / "routers" / "build_router.py")
    check('"replay": bool(out.get("replay"))' in r,
          "API memberi tahu klien bahwa kiriman adalah pemutaran ulang")
    bi = read(BE / "build_instruction.py")
    check('"checklist": [{"code"' in bi,
          "payload kartu memuat checklist lengkap (bisa diisi tanpa jaringan)")


# ------------------------------------------------------------------ E. cadangan perangkat
def audit_offline_fallbacks():
    head("E. Cadangan di perangkat supaya papan tetap bisa dipakai tanpa sinyal")
    auth = read(FE / "context" / "AuthContext.js")
    check("!e?.response && cached" in auth,
          "tanpa sinyal sesi dipertahankan; hanya penolakan server yang mengeluarkan pengguna")
    api = read(FE / "services" / "apiClient.js")
    check("401" in api and "removeItem" in api,
          "sesi yang benar-benar ditolak server (401) dibersihkan")
    ref = read(FE / "context" / "ReferenceContext.js")
    check("localStorage.setItem(CACHE_KEY" in ref,
          "kamus pilihan (checklist mutu) punya cadangan — dropdown tidak kosong saat offline")
    proj = read(FE / "components" / "construction" / "ProjectSelect.js")
    check("localStorage" in proj,
          "daftar proyek punya cadangan — papan tidak terjebak di 'Pilih proyek'")
    board = read(FE / "components" / "construction" / "ForemanBoard.js")
    check("snapKey(" in board and "snapshotAt" in board,
          "cuplikan papan per proyek + waktunya ditampilkan (tidak menyamar sebagai data kini)")


# ------------------------------------------------------------------ F. service worker
def audit_pwa():
    head("F. Kerangka aplikasi tersimpan, data operasional tidak dipalsukan")
    sw = read(PUB / "service-worker.js")
    check(bool(sw), "service worker ada")
    check('url.pathname.startsWith("/api/")' in sw and "return true" in sw,
          "permintaan /api/ TIDAK PERNAH di-cache (tidak ada data basi yang mengaku terkini)")
    check("hot-update" in sw, "aset dev-server dilewati (tidak mengganggu pengembangan)")
    check('request.mode === "navigate"' in sw,
          "membuka/menyegarkan aplikasi saat offline tetap menampilkan aplikasi")
    check("manifest.json" in read(PUB / "index.html") and (PUB / "manifest.json").exists(),
          "manifest PWA terpasang (bisa dipasang di layar utama HP)")
    check("serviceWorker" in read(FE / "index.js"), "service worker didaftarkan aplikasi")


# ------------------------------------------------------------------ G. kontrak runtime
def audit_runtime():
    head("G. Kontrak runtime (tanpa mengubah data)")
    site = login("site@sipro.co.id")
    sales = login("sales@sipro.co.id")
    reg = requests.get(f"{BASE}/reference", headers=site, timeout=60).json().get("data") or {}
    check({"offline_queue_status", "offline_queue_kind"} <= set(reg),
          "grup SSOT antrean terdaftar di /api/reference")
    bd = (requests.get(f"{BASE}/build/board/today", headers=site, timeout=90)
          .json() or {}).get("data") or {}
    rows = [r for k in ("overdue", "today", "in_progress", "rework", "scheduled_later")
            for r in ((bd.get("groups") or {}).get(k) or [])]
    check(bool(rows), "papan mandor memberi pekerjaan siap kerja", len(rows))
    if rows:
        check(all(len(r.get("checklist") or []) == int(r.get("checklist_total") or 0)
                  for r in rows), "checklist di payload = jumlah yang ditampilkan kartu")
        check(all(r.get("instruction") for r in rows), "instruksi kerja ikut di payload")
    check("min_note_chars" in (bd.get("policy") or {}), "kebijakan bukti ikut di payload")

    names = mdb.build_item_submissions.index_information()
    uniq = [v for v in names.values()
            if v.get("unique") and any(k[0] == "client_ref" for k in v.get("key", []))]
    check(bool(uniq), "indeks UNIK client_ref aktif pada jejak pengajuan", list(names))
    check(all(v.get("partialFilterExpression") for v in uniq),
          "indeks client_ref berupa PARTIAL (bukan sparse) — pengajuan tanpa penanda tidak "
          "bentrok 'null'", [v.get("partialFilterExpression") for v in uniq])
    cnames = mdb.build_submit_claims.index_information()
    check(any(v.get("unique") and any(k[0] == "client_ref" for k in v.get("key", []))
              for v in cnames.values()),
          "indeks UNIK kunci pengiriman aktif", list(cnames))
    check(any(v.get("expireAfterSeconds") for v in cnames.values()),
          "kunci pengiriman punya TTL (koleksi bersih sendiri)", list(cnames))
    bulk = mdb.build_bulk_runs.index_information()
    check(all(v.get("partialFilterExpression")
              for v in bulk.values()
              if v.get("unique") and any(k[0] == "client_ref" for k in v.get("key", []))),
          "indeks client_ref operasi massal (Fase 34) juga PARTIAL", list(bulk))
    refs = [d["client_ref"] for d in mdb.build_item_submissions.find(
        {"client_ref": {"$ne": None}}, {"client_ref": 1})]
    check(len(refs) == len(set(refs)), "tidak ada client_ref dobel pada data hidup",
          f"{len(refs)} jejak berpenanda")
    # Catatan: query `{"client_ref": None}` juga cocok untuk dokumen yang FIELD-nya tidak ada,
    # jadi harus memakai $type agar benar-benar menguji nilai null.
    nulls = mdb.build_item_submissions.count_documents({"client_ref": {"$type": "null"}})
    check(nulls == 0,
          "tidak ada jejak pengajuan berpenanda null (bentrok indeks unik)", nulls)

    if rows:
        item = rows[0]
        ref = "verify35-claim-probe"
        mdb.build_submit_claims.delete_many({"client_ref": ref})
        body = {"note": "Uji kunci antrean: sengaja tanpa foto agar ditolak server.",
                "photo_file_ids": [], "checklist": [], "client_ref": ref}
        r1 = requests.post(f"{BASE}/build/items/{item['id']}/submit", headers=site,
                           json=body, timeout=90)
        r2 = requests.post(f"{BASE}/build/items/{item['id']}/submit", headers=site,
                           json=body, timeout=90)
        check(r1.status_code == 400 and r2.status_code == 400,
              "pengajuan ditolak dua kali dengan alasan (kunci tidak menelan percobaan kedua)",
              f"{r1.status_code}/{r2.status_code}")
        check(mdb.build_submit_claims.count_documents({"client_ref": ref}) == 0,
              "kunci dilepas setelah penolakan (pekerjaan tidak hilang senyap)")
        check(mdb.build_item_submissions.count_documents({"client_ref": ref}) == 0,
              "penolakan tidak meninggalkan jejak pengajuan palsu")
        rs = requests.post(f"{BASE}/build/items/{item['id']}/submit", headers=sales,
                           json=dict(body, client_ref="verify35-rbac"), timeout=60)
        check(rs.status_code == 403, "sales tetap tidak boleh mengajukan hasil kerja",
              rs.status_code)


def main():
    audit_wiring()
    audit_imports()
    audit_queue_guards()
    audit_server_guards()
    audit_offline_fallbacks()
    audit_pwa()
    audit_runtime()
    print("\n" + "-" * 58)
    print(f"HASIL verify_35: {ok_n} PASS, {fail_n} FAIL")
    if fail_n:
        print("GATE FASE 35 GAGAL")
        sys.exit(1)
    print("GATE FASE 35 PASSED")


if __name__ == "__main__":
    main()
