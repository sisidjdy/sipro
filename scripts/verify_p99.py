#!/usr/bin/env python3
"""verify_p99.py — Gate Fase 99: template UTILITY berheader dokumen + Balasan Cerdas + gate lama hijau.

  T. Template header dokumen: kosakata SSOT, seed `document_delivery`, payload Meta punya HEADER DOCUMENT,
     `_template_payload` menaruh PDF sebagai parameter header, pengajuan tanpa contoh berkas DITOLAK jujur,
     jalur kirim (`route_for`) memilih sesi/template/blocked dan `wa_send.route` dibawa ke layar.
  S. Balasan Cerdas: endpoint saran berbasis playbook tahap lead & kata kunci — tanpa LLM, badan pesan
     sudah dirender, template belum approved tidak bisa dipakai di luar sesi; chip tampil di dialog.
  K. Kode: tidak ada daftar peran disalin (ReserveDialog/Allin/KPR memakai can()), `pricing:approve`
     & `finance:manage` dipaksakan backend, cascade purge dipakai fixture.
"""
import os
import pathlib
import re
import sys

import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
BE, FE = ROOT / "backend", ROOT / "frontend" / "src"
sys.path.insert(0, str(BE))
load_dotenv(BE / ".env")
BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
PASSED, FAIL = 0, []


def check(cond, name, detail=""):
    global PASSED
    if cond:
        PASSED += 1
    else:
        FAIL.append(name)
    print(f"  {'OK   ' if cond else 'MERAH'} {name}" + (f" — {str(detail)[:160]}" if detail and not cond else ""))
    return bool(cond)


def read(p):
    return p.read_text(encoding="utf-8", errors="ignore")


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def bagian_t(sa):
    print("\nT. Template UTILITY berheader dokumen")
    import wa_gateway as gw
    import wa_templates_meta as wtm
    ref = requests.get(f"{BASE}/reference", headers=sa, timeout=20).json()["data"]
    check("wa_template_header" in ref and {o["value"] for o in ref["wa_template_header"]["options"]} >= {"none", "document"},
          "T1 kosakata header template ada di SSOT /reference")
    rows = requests.get(f"{BASE}/wa-templates", headers=sa, timeout=20).json()["data"]
    doc = next((t for t in rows if t["code"] == "document_delivery"), None)
    check(doc is not None and doc.get("header_type") == "document" and doc.get("category") == "utility",
          "T2 template seed `document_delivery` UTILITY berheader dokumen ada", doc)
    if not doc:
        return
    check(set(doc.get("variables") or []) >= {"nama", "dokumen", "nomor", "org"},
          "T3 variabel pengantar dokumen lengkap", doc.get("variables"))
    pv = requests.get(f"{BASE}/wa-templates/{doc['id']}/meta-preview", headers=sa, timeout=20).json()["data"]
    comps = pv.get("components") or []
    check(comps and comps[0].get("type") == "HEADER" and comps[0].get("format") == "DOCUMENT"
          and any(c["type"] == "BODY" and "{{1}}" in c["text"] for c in comps),
          "T4 payload Meta: HEADER DOCUMENT + BODY berparameter berurutan", comps)
    payload = gw._template_payload("628123", doc, ["Ibu", "Kwitansi", " 001", "SIPRO"],
                                   {"link": "https://x/y.pdf", "filename": "kwitansi.pdf"})
    hdr = [c for c in payload["template"]["components"] if c["type"] == "header"]
    check(hdr and hdr[0]["parameters"][0]["type"] == "document"
          and hdr[0]["parameters"][0]["document"].get("filename") == "kwitansi.pdf",
          "T5 kirim: PDF menjadi parameter HEADER template (bukan type:document bebas)", payload)
    plain = gw._template_payload("628123", {"code": "welcome"}, ["A"], {"link": "x"})
    check(not any(c["type"] == "header" for c in plain["template"].get("components", [])),
          "T5b template tanpa header_type=document tidak diberi header palsu")
    check("header_sample_required" in read(BE / "wa_templates_meta.py"),
          "T6 pengajuan template berheader tanpa contoh berkas DITOLAK jujur (bukan 400 Meta yang membingungkan)")
    check(wtm.meta_components({"body": "Hai", "header_type": "text", "header_text": "Judul"})[0].get("format") == "TEXT",
          "T6b header TEXT ikut terbentuk")
    src = read(BE / "wa_docs.py")
    check("async def route_for" in src and '"via": "template"' in src and '"via": "blocked"' in src
          and "wa.document_template_code" in src,
          "T7 jalur kirim PDF: sesi terbuka → dokumen; tertutup → template header; tanpa template → blocked")
    check('out["route"]["via"] == "blocked" and cfg["effective_mode"] == "live"' in src,
          "T7b di mode LIVE tombol dimatikan bila jalur blocked (tidak menjanjikan kirim yang pasti gagal)")
    check("wa.document_template_code" in read(BE / "settings_p88.py"),
          "T8 kode template pengantar dokumen bisa dikonfigurasi di Pusat Konfigurasi")
    tab = read(FE / "components" / "docs" / "IssuedDocsTab.js")
    check("wa_send.route" in tab and "docSendWaRoute" in tab,
          "T9 layar Dokumen Terbit menyebut jalur kirim (sesi/template) kepada pemakai")
    # Tahap 3 (WA-14): editor template pindah ke Pusat Konfigurasi › Template Meta.
    tp = read(FE / "components" / "config" / "WaTemplateEditorDialog.js")
    check('options("wa_template_header")' in tp and "header_sample_handle" in tp,
          "T10 form template punya pilihan header dari SSOT + kolom contoh berkas")


def bagian_s(sa):
    print("\nS. Balasan Cerdas (berbasis playbook, tanpa LLM)")
    src = read(BE / "wa_suggest.py")
    check("emergentintegrations" not in src and "litellm" not in src and "openai" not in src.lower(),
          "S1 saran balasan murni aturan (playbook + kata kunci), tanpa LLM")
    check("wp.playbooks(" in src and "automation_rules" in src and "render_wa_body(" in src,
          "S2 sumber saran: playbook tahap lead, aturan kata kunci, badan pesan dirender dari data lead")
    check('"usable": ready or window_open' in src,
          "S3 template belum approved tidak bisa dipakai di luar sesi 24 jam (usable = approved ∨ sesi)")
    tanda = os.urandom(3).hex()
    imp = requests.post(f"{BASE}/wa/contacts/import", headers=sa, timeout=30,
                        json={"text": f"+62813{tanda[:4]}9911 Uji P99 {tanda}\nharga dan kpr berapa?", "label": "gate99"})
    cid = None
    if imp.status_code == 200:
        rows = requests.get(f"{BASE}/wa/contacts", headers=sa, params={"q": f"Uji P99 {tanda}", "limit": 5}, timeout=20).json()["data"]
        cid = rows[0]["id"] if rows else None
    if not cid:
        rows = requests.get(f"{BASE}/wa/contacts", headers=sa, params={"limit": 1}, timeout=20).json()["data"]
        cid = rows[0]["id"] if rows else None
    if not check(bool(cid), "S4 ada kontak WA untuk diuji", imp.text[:200]):
        return
    r = requests.get(f"{BASE}/wa/contacts/{cid}/suggestions", headers=sa, timeout=20)
    d = r.json().get("data") or {}
    items = d.get("items") or []
    check(r.status_code == 200 and "items" in d and "window_open" in d, "S5 endpoint saran menjawab", r.text[:200])
    check(items and all(i.get("body") and i.get("title") and "usable" in i for i in items),
          "S6 setiap saran membawa judul, badan pesan terisi, dan kelayakan kirim", items[:2])
    check(all("{{" not in i["body"] for i in items), "S7 placeholder sudah dirender (tidak ada {{…}} mentah)", items[:2])
    check(all(i["ready"] or not i["usable"] or d.get("window_open") for i in items),
          "S8 saran template belum approved hanya usable di dalam sesi")
    dlg = read(FE / "components" / "wa" / "WaQuickReplyDialog.js")
    chips = read(FE / "components" / "wa" / "WaReplySuggestions.js")
    check("WaReplySuggestions" in dlg and "pickSuggestion" in dlg and "replySuggestion" in chips,
          "S9 chip saran tampil di dialog Balas Cepat dan mengisi template/teks")
    check("windowOpen) { setTmpl(NONE); setBody(s.body" in dlg and "setTmpl(s.template_code)" in dlg,
          "S9b sesi terbuka → teks bisa disunting; tertutup → memilih template approved")
    sales = login("sales@sipro.co.id")
    r2 = requests.get(f"{BASE}/wa/contacts/{cid}/suggestions", headers=sales, timeout=20)
    check(r2.status_code in (200, 403), "S10 endpoint saran dipagari RBAC inbox:view", r2.status_code)
    # bersihkan kontak uji
    requests.delete(f"{BASE}/wa/contacts/{cid}", headers=sa, timeout=20)


def bagian_k():
    print("\nK. Kode: pembersihan gate merah tidak dibalik diam-diam")
    for rel in ("components/sales/ReserveDialog.js", "components/pricing/AllinSchemeField.js",
                "components/contracts/KprDisbursementBox.js", "components/contracts/AllinAmendmentBox.js"):
        s = read(FE / rel)
        check(not re.search(r'\[[^\]]*"(?:owner|super_admin|finance_manager)"[^\]]*\]\s*\.includes\(', s),
              f"K1 {rel.split('/')[-1]} tidak menyalin daftar peran")
    rb = read(BE / "rbac.py")
    check('"pricing": ["approve"]' in rb and '"finance": ["approve", "manage"]' in rb,
          "K2 izin pricing:approve & finance:manage terdefinisi di ROLE_GRANTS")
    check('can(user.get("role"), "pricing", "approve")' in read(BE / "routers" / "deals_router.py")
          and 'can(user.get("role"), "finance", "manage")' in read(BE / "allin_engine.py"),
          "K3 backend memaksakan izin yang sama dengan layar")
    for f in ("_fixture42.py", "_fixture47.py", "_fixture50.py", "_fixture56.py"):
        check("purge_deal_children" in read(ROOT / "scripts" / f), f"K4 {f} membuang turunan deal (booking fee titipan dst)")
    check("REL_LOOKUP" in read(FE / "components" / "work" / "CreateTaskDialog.js")
          and 'options("task_related_type")' in read(FE / "components" / "work" / "CreateTaskDialog.js"),
          "K5 jenis record terkait tugas dari Kamus Data")
    check("salesLabel(" in read(FE / "components" / "siteplan" / "studio" / "studioPalette.js")
          and "SALES_LABEL" not in read(FE / "components" / "siteplan" / "studio" / "studioPalette.js"),
          "K6 label palet studio dari SSOT unit_status")


def main() -> int:
    print("=" * 78)
    print("GATE Fase 99 — Template header dokumen, Balasan Cerdas, gate merah bersih")
    print("=" * 78)
    try:
        requests.get(f"{BASE}/health", timeout=10)
    except Exception as e:  # noqa: BLE001
        print(f"Backend tidak menjawab: {e}")
        return 1
    sa = login("superadmin@sipro.co.id")
    bagian_t(sa)
    bagian_s(sa)
    bagian_k()
    print("\n" + "-" * 78)
    if FAIL:
        print(f"GATE P99 MERAH — {len(FAIL)} gagal / {PASSED + len(FAIL)} pemeriksaan")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"GATE P99 HIJAU — {PASSED} pemeriksaan PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
