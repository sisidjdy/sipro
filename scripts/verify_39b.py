#!/usr/bin/env python3
"""verify_39b.py — GATE Checklist Dokumen Syarat (Fase 39b).

Fase 39 membuat MASTER dokumen syarat (`doc_requirements`) lengkap dengan mesin
verifikasinya, tetapi tidak ada satu pun layar yang memakainya: `doc/matrix` &
`doc/submissions` nol kemunculan di frontend, sehingga `doc_submissions` mustahil terisi
dari UI dan janji "syarat muncul sebagai checklist" (US-39-3) tidak pernah terbukti.
Gate ini menjaga agar keadaan itu tidak kembali.

Janji bisnis yang dijaga:
  1. Konteks syarat DITURUNKAN BACKEND (frontend tidak menyimpan salinan aturan):
     `GET /doc/matrix` tanpa `contexts` tetap mengembalikan syarat yang relevan.
  2. Bukti harus BENAR ADA: `file_id` fiktif ditolak (tidak bisa mengaku punya berkas).
  3. Bukti KEMBAR tidak boleh masuk dua kali — baik `file_id` sama maupun ISI berkas sama
     (sidik jari `files.sha256`); tetapi berkas berbeda & unggah ulang setelah DITOLAK
     tetap boleh (kalau tidak, satu penolakan keliru mengunci prosesnya).
  4. Verifikasi & penolakan SELALU menyimpan AKTOR + WAKTU + ALASAN, dan hitungan matriks
     serta denormalisasi `doc_progress` ikut berubah (angka di layar tidak boleh bohong).
  5. Wiring UI benar-benar ada: `DocChecklist` terpasang di layar Lead & Pelanggan, punya
     input berkas PER BARIS (bukan satu input bersama yang gagal-senyap), dan label
     konteks/akun GL diambil dari SSOT `/api/reference` — bukan peta hardcode.

Exit !=0 bila ada FAIL.
"""
import os
import pathlib
import re
import sys
import uuid

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
ROOT = pathlib.Path(__file__).resolve().parent.parent
FE = ROOT / "frontend" / "src"
fails = []
created = {"submissions": [], "files": [], "lead_id": None}


def cleanup():
    """Bereskan sisa data uji — gate tidak boleh mengotori data demo.

    Penghapusan baris `doc_submissions` HARUS diikuti perbaikan denormalisasi
    `leads.doc_progress` dengan rumus yang SAMA seperti `doc_registry.refresh_progress`;
    kalau tidak, angka di kartu lead menjadi bohong setelah gate dijalankan.
    """
    if not created["submissions"]:
        return
    load_dotenv(ROOT / "backend/.env")
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    db.doc_submissions.delete_many({"id": {"$in": created["submissions"]}})
    db.files.delete_many({"id": {"$in": created["files"]}})
    lead_id = created["lead_id"]
    if lead_id:
        subs = list(db.doc_submissions.find({"entity_type": "lead", "entity_id": lead_id},
                                            {"_id": 0, "status": 1}))
        db.leads.update_one({"id": lead_id}, {"$set": {"doc_progress": {
            "total": len(subs),
            "verified": sum(1 for s in subs if s["status"] == "verified"),
            "pending": sum(1 for s in subs if s["status"] == "pending"),
            "rejected": sum(1 for s in subs if s["status"] == "rejected"),
            "updated_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc).isoformat(),
        }}})
    print(f"  (bersih) {len(created['submissions'])} penyerahan uji & "
          f"{len(created['files'])} berkas uji dihapus, doc_progress dihitung ulang")


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=15)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def upload(headers, name, content, owner_type, owner_id):
    files = {"file": (name, content, "application/pdf")}
    data = {"owner_type": owner_type, "owner_id": owner_id, "optimize": "false"}
    r = requests.post(f"{BASE}/files/upload", headers=headers, files=files, data=data, timeout=30)
    r.raise_for_status()
    fid = r.json()["data"]["id"]
    created["files"].append(fid)
    return fid


def read(rel):
    p = FE / rel
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def main():
    admin = login("superadmin@sipro.co.id")
    tag = uuid.uuid4().hex[:8]

    print("\n1. Master syarat & konteks diturunkan backend")
    r = requests.get(f"{BASE}/doc/requirements", headers=admin, timeout=20)
    reqs = r.json().get("data") or [] if r.status_code == 200 else []
    check("GET /doc/requirements = 200", r.status_code == 200, f"got {r.status_code}")
    check("master syarat terisi (>=10)", len(reqs) >= 10, f"{len(reqs)} syarat")
    check("setiap syarat menyebut konteks berlakunya",
          all(x.get("applies_to") for x in reqs))

    leads = requests.get(f"{BASE}/leads?limit=50", headers=admin, timeout=20).json().get("data") or []
    booking = next((x for x in leads if x.get("stage") == "booking"), None)
    check("ada lead tahap booking untuk diuji", bool(booking))
    if not booking:
        print("GATE 39b FAILED: tidak ada lead booking")
        sys.exit(1)

    r = requests.get(f"{BASE}/doc/matrix", headers=admin, timeout=20,
                     params={"entity_type": "lead", "entity_id": booking["id"]})
    m = r.json().get("data") or {} if r.status_code == 200 else {}
    check("GET /doc/matrix TANPA contexts = 200", r.status_code == 200, f"got {r.status_code}")
    check("backend menurunkan konteks sendiri", len(m.get("contexts") or []) >= 2,
          str(m.get("contexts")))
    check("matriks berisi baris syarat", len(m.get("rows") or []) >= 1,
          f"{len(m.get('rows') or [])} baris")
    check("ada syarat WAJIB yang dihitung", (m.get("counts") or {}).get("required", 0) >= 1,
          str(m.get("counts")))
    row0 = (m.get("rows") or [{}])[0]
    check("tiap baris membawa syarat + status + label status",
          bool(row0.get("requirement")) and row0.get("status") and row0.get("status_label"))

    custs = requests.get(f"{BASE}/customers?limit=5", headers=admin, timeout=20).json().get("data") or []
    if custs:
        r = requests.get(f"{BASE}/doc/matrix", headers=admin, timeout=20,
                         params={"entity_type": "customer", "entity_id": custs[0]["id"]})
        ctx = (r.json().get("data") or {}).get("contexts") or []
        check("konteks pelanggan diturunkan (customer:legal)", "customer:legal" in ctx, str(ctx))

    print("\n2. Bukti harus benar ada")
    r = requests.post(f"{BASE}/doc/submissions", headers=admin, timeout=20, json={
        "requirement_code": reqs[0]["code"], "entity_type": "lead",
        "entity_id": booking["id"], "file_id": f"palsu-{tag}"})
    check("berkas fiktif ditolak 400", r.status_code == 400, f"got {r.status_code}")
    check("pesannya menjelaskan berkas tidak ada",
          "tidak ditemukan di penyimpanan" in r.text, r.text[:120])

    print("\n3. Bukti kembar ditolak, bukti berbeda boleh")
    code = next((x["code"] for x in reqs
                 if any(str(c).startswith("lead_stage") for c in x.get("applies_to", []))),
                reqs[0]["code"])
    body = f"%PDF-1.4 gate39b {tag}\n%%EOF\n".encode()
    f1 = upload(admin, f"gate_{tag}_a.pdf", body, "lead", booking["id"])
    payload = {"requirement_code": code, "entity_type": "lead", "entity_id": booking["id"]}
    r = requests.post(f"{BASE}/doc/submissions", headers=admin, timeout=20,
                      json={**payload, "file_id": f1})
    sub = (r.json().get("data") or {}) if r.status_code == 200 else {}
    check("unggah bukti pertama = 200 & status pending",
          r.status_code == 200 and sub.get("status") == "pending", r.text[:140])
    if sub.get("id"):
        created["submissions"].append(sub["id"])
        created["lead_id"] = booking["id"]
    r = requests.post(f"{BASE}/doc/submissions", headers=admin, timeout=20,
                      json={**payload, "file_id": f1})
    check("file_id yang SAMA ditolak 400 (bukan 500)", r.status_code == 400,
          f"got {r.status_code}: {r.text[:120]}")
    f2 = upload(admin, f"gate_{tag}_copy.pdf", body, "lead", booking["id"])
    r = requests.post(f"{BASE}/doc/submissions", headers=admin, timeout=20,
                      json={**payload, "file_id": f2})
    check("ISI berkas yang sama ditolak 400", r.status_code == 400,
          f"got {r.status_code}: {r.text[:120]}")
    check("pesannya menyebut sudah pernah diserahkan",
          "sudah pernah diserahkan" in r.text, r.text[:140])
    f3 = upload(admin, f"gate_{tag}_b.pdf", f"%PDF-1.4 lain {tag}\n%%EOF\n".encode(),
                "lead", booking["id"])
    r = requests.post(f"{BASE}/doc/submissions", headers=admin, timeout=20,
                      json={**payload, "file_id": f3})
    check("bukti dengan isi BERBEDA tetap boleh", r.status_code == 200,
          f"got {r.status_code}: {r.text[:120]}")
    other = (r.json().get("data") or {}).get("id")
    if other:
        created["submissions"].append(other)

    print("\n4. Verifikasi & penolakan menyimpan aktor + waktu + alasan")
    r = requests.post(f"{BASE}/doc/submissions/{sub['id']}/verify", headers=admin,
                      timeout=20, json={"note": "gate 39b"})
    v = (r.json().get("data") or {}) if r.status_code == 200 else {}
    check("verifikasi = 200", r.status_code == 200, f"got {r.status_code}")
    check("status verified + aktor + waktu tercatat",
          v.get("status") == "verified" and v.get("verified_by") and v.get("verified_at"),
          str({k: v.get(k) for k in ("status", "verified_by", "verified_at")})[:160])
    r = requests.post(f"{BASE}/doc/submissions/{other}/reject", headers=admin, timeout=20,
                      json={"reason": f"gate 39b {tag}"})
    j = (r.json().get("data") or {}) if r.status_code == 200 else {}
    check("penolakan = 200 & menyimpan alasan",
          r.status_code == 200 and j.get("status") == "rejected"
          and tag in str(j.get("reject_reason")), r.text[:140])
    hist = j.get("history") or []
    check("riwayat penolakan menyimpan aktor",
          any(h.get("action") == "rejected" and h.get("actor") for h in hist), str(hist)[:160])
    r = requests.post(f"{BASE}/doc/submissions/{other}/reject", headers=admin, timeout=20,
                      json={"reason": ""})
    check("penolakan tanpa alasan ditolak (400/422)", r.status_code in (400, 422),
          f"got {r.status_code}")

    m2 = requests.get(f"{BASE}/doc/matrix", headers=admin, timeout=20, params={
        "entity_type": "lead", "entity_id": booking["id"]}).json()["data"]
    check("hitungan matriks ikut berubah (>=1 terverifikasi)",
          (m2.get("counts") or {}).get("verified", 0) >= 1, str(m2.get("counts")))
    lead = requests.get(f"{BASE}/leads/{booking['id']}", headers=admin, timeout=20).json()["data"]
    prog = lead.get("doc_progress") or {}
    check("doc_progress lead ter-denormalisasi", prog.get("verified", 0) >= 1, str(prog))

    print("\n5. RBAC — pengunggah tidak boleh memverifikasi berkasnya sendiri")
    # `docs/v2/24_CRM_LEAD_SPEC.md` §13: verifikasi dokumen = sales ✖, sales_manager ✔,
    # marketing_admin ✔, finance ✔, owner/super_admin ✔. Sebelum Fase 39b aksi verifikasi
    # memakai izin `documents.update` yang JUGA dimiliki sales — artinya sales bisa
    # meloloskan berkasnya sendiri dan "gerbang bukti" kehilangan artinya.
    sales = login("sales@sipro.co.id")
    manager = login("manager@sipro.co.id")
    me_sales = requests.get(f"{BASE}/auth/me", headers=sales, timeout=15).json()["data"]
    perms = (me_sales.get("permissions") or {}).get("documents") or []
    check("/auth/me mengirim izin efektif", bool(me_sales.get("permissions")))
    check("sales boleh mengunggah (create) tapi TIDAK boleh verify",
          "create" in perms and "verify" not in perms, str(perms))
    me_mgr = requests.get(f"{BASE}/auth/me", headers=manager, timeout=15).json()["data"]
    check("sales_manager punya izin verify",
          "verify" in ((me_mgr.get("permissions") or {}).get("documents") or []))
    f5 = upload(sales, f"gate_{tag}_rbac.pdf", f"%PDF rbac {tag}\n%%EOF\n".encode(),
                "lead", booking["id"])
    r = requests.post(f"{BASE}/doc/submissions", headers=sales, timeout=20,
                      json={**payload, "file_id": f5})
    sub5 = (r.json().get("data") or {}) if r.status_code == 200 else {}
    check("sales berhasil mengunggah bukti", r.status_code == 200, r.text[:120])
    if sub5.get("id"):
        created["submissions"].append(sub5["id"])
        r = requests.post(f"{BASE}/doc/submissions/{sub5['id']}/verify", headers=sales,
                          timeout=20, json={"note": "verifikasi sendiri"})
        check("sales DITOLAK saat memverifikasi berkasnya sendiri (403)",
              r.status_code == 403, f"got {r.status_code}")
        r = requests.post(f"{BASE}/doc/submissions/{sub5['id']}/reject", headers=sales,
                          timeout=20, json={"reason": "coba tolak"})
        check("sales DITOLAK saat menolak dokumen (403)", r.status_code == 403,
              f"got {r.status_code}")
        r = requests.post(f"{BASE}/doc/submissions/{sub5['id']}/verify", headers=manager,
                          timeout=20, json={"note": "verifikasi manajer"})
        check("sales_manager BOLEH memverifikasi", r.status_code == 200,
              f"got {r.status_code}: {r.text[:120]}")

    print("\n6. SSOT label (bukan peta hardcode di frontend)")
    ref = requests.get(f"{BASE}/reference", headers=admin, timeout=20).json()["data"]
    for grp in ("doc_context", "gl_account", "setting_origin", "setting_source",
                "doc_submission_status"):
        check(f"grup referensi '{grp}' ada", grp in ref)
    gl = (ref.get("gl_account") or {}).get("options") or []
    check("akun GL diambil dari bagan akun (>=10 opsi)", len(gl) >= 10, f"{len(gl)} opsi")
    check("label akun GL memuat kode DAN nama",
          any(" — " in (o.get("label") or "") for o in gl), str(gl[:2])[:160])
    check("akun GL tidak menawarkan nilai baru",
          (ref.get("gl_account") or {}).get("allow_new") is False)
    check("maps lama (channel_to_source/source_score) tidak hilang",
          {"channel_to_source", "source_score"} <= set(
              requests.get(f"{BASE}/reference", headers=admin, timeout=20).json()
              .get("maps", {}).keys()))

    print("\n7. Wiring UI (statis) — checklist benar-benar dipakai")
    chk = read("components/patterns/DocChecklist.js")
    check("komponen DocChecklist ada", bool(chk))
    check("checklist memanggil /doc/matrix", "/doc/matrix" in chk)
    check("checklist bisa mengunggah (/doc/submissions)", "/doc/submissions" in chk)
    # Diperiksa PADA ELEMEN input-nya, bukan sekadar "ada string data-requirement di berkas":
    # atribut itu juga muncul di baris/tombol lain, sehingga pemeriksaan longgar tetap hijau
    # walau input berkasnya kembali dipakai bersama (cacat gagal-senyap). Ditemukan oleh
    # uji-mutasi M8 di `scripts/mutasi_39b.py`.
    file_inputs = [e for e in re.findall(r"<input\b.*?/>", chk, re.S) if 'type="file"' in e]
    check("input berkas PER BARIS (setiap input file membawa data-requirement)",
          bool(file_inputs) and all("data-requirement" in e for e in file_inputs),
          f"{len(file_inputs)} input file diperiksa")
    check("aksi verifikasi & tolak tersedia di checklist",
          "/verify" in chk and "/reject" in chk)
    check("label konteks dari SSOT", 'labelOf("doc_context"' in chk)
    check("tombol verifikasi mengikuti izin nyata, bukan tebakan peran",
          'can("documents", "verify")' in chk and "mayVerify" in chk)
    check("badge tidak mengaku 'lengkap' saat belum ada syarat",
          "Belum ada syarat pada tahap ini" in chk)
    # Fase 40 memindahkan checklist dari drawer ke HALAMAN kanonik (`/leads/:id`,
    # `/customers/:id`) — gate ini memeriksa NIAT-nya ("checklist bisa dicapai dari layar
    # Lead / Pelanggan"), bukan satu nama berkas. Kandidat berkas dipindai; bila TIDAK ADA
    # satu pun yang memasang DocChecklist dengan entityType yang benar, gate GAGAL.
    LEAD_SCREENS = ("pages/LeadProfilePage.js", "components/leads/LeadSummaryTab.js",
                    "components/leads/LeadTimelineTab.js", "components/sales/LeadDetail.js")
    CUST_SCREENS = ("pages/CustomerProfilePage.js", "components/customers/CustomerSummaryTab.js",
                    "components/customers/CustomerRelatedTabs.js",
                    "components/customers/CustomerDetailSheet.js")

    def mounted(screens, entity):
        hits = [rel for rel in screens
                if "DocChecklist" in read(rel) and f'entityType="{entity}"' in read(rel)]
        return hits

    lead_hits = mounted(LEAD_SCREENS, "lead")
    cust_hits = mounted(CUST_SCREENS, "customer")
    check("checklist terpasang di layar Lead", bool(lead_hits), ", ".join(lead_hits) or "TIDAK ADA")
    check("checklist terpasang di layar Pelanggan", bool(cust_hits),
          ", ".join(cust_hits) or "TIDAK ADA")
    # Halaman kanonik wajib benar-benar punya route (kalau tidak, checklist tak terjangkau).
    app_js = read("App.js")
    check("route halaman kanonik lead & pelanggan terdaftar",
          '/leads/:id' in app_js and '/customers/:id' in app_js)
    for panel in ("components/config/AddonPanel.js", "components/config/PriceComponentPanel.js"):
        src = read(panel)
        check(f"{pathlib.Path(panel).name}: akun GL memakai dropdown SSOT",
              'group="gl_account"' in src, "masih input bebas?")
    docs_panel = read("components/config/DocRequirementsPanel.js")
    check("DocRequirementsPanel memakai grup doc_context dari SSOT",
          'options("doc_context")' in docs_panel or "doc_context" in docs_panel)
    check("tidak ada lagi daftar konteks hardcode CONTEXT_OPTIONS",
          "const CONTEXT_OPTIONS = [" not in docs_panel)
    settings_panel = read("components/config/SettingsPanel.js")
    check("SettingsPanel memakai label SSOT untuk asal nilai",
          'labelOf("setting_origin"' in settings_panel)
    check("tidak ada lagi peta ORIGIN_LABEL hardcode",
          "const ORIGIN_LABEL = {" not in settings_panel)
    mig = read("components/master/MigrationRunsPanel.js")
    check("riwayat migrasi punya layar (US-39-5)",
          "/admin/migrations" in mig and "MigrationRunsPanel" in read("pages/AuditLogsPage.js"))

    print("-" * 60)
    cleanup()
    if fails:
        print(f"GATE 39b FAILED: {len(fails)} temuan — {fails}")
        sys.exit(1)
    print("GATE 39b PASSED: checklist dokumen terpakai nyata, bukti jujur, label dari SSOT")


if __name__ == "__main__":
    main()
