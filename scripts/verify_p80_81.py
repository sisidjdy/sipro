#!/usr/bin/env python3
"""verify_p80_81.py — GATE 61: RAB terstruktur (Fase 80) + versi/salin/impor RAB & kendali fasum vs fase (Fase 81).

  K — KODE: RAB unit hidup di TIPE (bukan proyek), SPK dari RAB menyimpan jejak `rab_lines` + override
      beralasan, item fasum/umum tidak dikontrakkan 2×, versi lama tersimpan saat Simpan mengubah baris,
      pulihkan = simpan ulang lewat jalur yang sama, termin fasum dibatasi progres fase, UI memakai testid.
  D — PERILAKU (server hidup): versi naik hanya bila baris berubah, salin × faktor menghitung benar dan
      tidak menyimpan, template Excel bisa diunduh & diimpor sebagai pratinjau, batas termin fasum = progres fase.

Jalankan: python3 scripts/verify_p80_81.py
"""
import io
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
API = "http://localhost:8001/api"
PASSWORD = "Sipro#2026"
ok, fails = 0, []


def check(cond, label, detail=None):
    global ok
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fails.append(label)
        print(f"  GAGAL {label}" + (f" — {detail}" if detail else ""))
    return cond


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def read(p):
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


head("K — kode")
eng = read(BE / "rab_engine.py")
ext = read(BE / "rab_templates_ext.py")
rr = read(BE / "routers" / "rab_router.py")
sr = read(BE / "routers" / "subcon_router.py")
cr = read(BE / "routers" / "subcon_claims_router.py")
check('"kind": "unit_type"' in eng and "rab_templates" in eng and "def list_templates" in eng, "RAB unit tertempel pada tipe (rab_templates kind=unit_type)")
check("rab_lines" in sr and "assert_boq_not_contracted" in sr and "validate_lines" in sr, "SPK dari RAB: jejak rab_lines + guard kontrak ganda + validasi override")
check("wajib diberi alasan override" in eng, "override nilai RAB wajib alasan")
check("rab_template_versions.insert_one" in eng and 'prev["items"] != norm' in eng, "versi lama disimpan hanya bila baris berubah")
check("async def restore_version" in ext and "re_.save_template" in ext, "pulihkan versi = save_template (tercatat sebagai versi baru)")
check("def copy_items" in ext and "MAX_FACTOR" in ext and "source_ref == ref_code" in ext, "salin dari tipe lain: faktor dibatasi, sumber ≠ tujuan")
check("def parse_import" in ext and "def import_workbook" in ext and "work_category" in ext, "impor Excel: template + pratinjau tervalidasi (kategori dari SSOT)")
check("/copy-from" in rr and "/import" in rr and "/versions/{vid}/restore" in rr and "import-template.xlsx" in rr, "endpoint versi/salin/impor terdaftar")
check('require_permission("boq", "update")' in rr, "ubah RAB butuh boq:update")
check("async def fasum_phase_cap" in eng and "construction_phases" in eng, "batas termin fasum dihitung dari progres fase konstruksi tertaut")
check("assert_fasum_claim_within_phase" in cr and 'spk_kind") == "fasum"' in cr, "pengajuan termin SPK fasum lump-sum ditolak bila melampaui progres fase")
check('"fasum_control"' in eng, "ringkasan proyek membawa kendali fasum per SPK")
for f in ("RabTemplateTools.js", "RabVersionHistory.js", "RabFasumControl.js"):
    check((FE / "components" / "boq" / f).exists(), f"komponen UI {f} ada")
check("P81" in read(FE / "components" / "boq" / "RabTemplateDialog.js") and "RabTemplateTools" in read(FE / "components" / "boq" / "RabTemplateDialog.js"),
      "editor RAB memuat alat salin/impor + riwayat versi")
check("claim-fasum-cap" in read(FE / "components" / "subcon" / "SubmitClaimDialog.js"), "dialog termin menampilkan batas fase untuk SPK fasum")
check("export * from './p81'" in read(FE / "constants" / "testIds" / "index.js"), "testid P81 terekspor")

head("D — perilaku (server hidup)")
try:
    tok = requests.post(f"{API}/auth/login", json={"email": "superadmin@sipro.co.id", "password": PASSWORD}, timeout=15).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    T = "TIPE-36-72"
    items = [{"code": "G61", "description": "GATE61_Struktur", "category": "struktur", "qty": 1, "unit_price": 111_000_000}]
    a = requests.put(f"{API}/rab/templates/unit_type/{T}", headers=H, json={"items": items}, timeout=15).json()["data"]
    b = requests.put(f"{API}/rab/templates/unit_type/{T}", headers=H, json={"items": items}, timeout=15).json()["data"]
    check(a["version"] == b["version"], "simpan identik tidak menaikkan versi")
    c = requests.put(f"{API}/rab/templates/unit_type/{T}", headers=H, json={"items": [{**items[0], "unit_price": 122_000_000}], "note": "gate"}, timeout=15).json()["data"]
    check(c["version"] == a["version"] + 1 and c["note"] == "gate", "perubahan harga → versi baru + catatan")
    vs = requests.get(f"{API}/rab/templates/unit_type/{T}/versions", headers=H, timeout=15).json()["data"]["versions"]
    old = next((v for v in vs if v["version"] == a["version"]), None)
    check(old is not None and old["total"] == 111_000_000 and vs[0]["delta"] == 11_000_000, "riwayat versi memuat total lama & selisih")
    r = requests.post(f"{API}/rab/templates/unit_type/{T}/versions/{old['id']}/restore", headers=H, timeout=15).json()["data"]
    check(r["total"] == 111_000_000 and r["version"] == c["version"] + 1, "pulihkan versi → total lama, versi naik")
    cp = requests.post(f"{API}/rab/templates/unit_type/TIPE-45-90/copy-from", headers=H, json={"source_ref_code": T, "factor": 2}, timeout=15).json()["data"]
    check(cp["total"] == 222_000_000, "salin × faktor 2 menghitung benar")
    cur = requests.get(f"{API}/rab/templates/unit_type/TIPE-45-90", headers=H, timeout=15).json()["data"]
    check(cur.get("total", 0) != 222_000_000 or cur.get("items") != cp["items"], "salin hanya pratinjau (tidak menyimpan)")
    check(requests.post(f"{API}/rab/templates/unit_type/TIPE-45-90/copy-from", headers=H, json={"source_ref_code": T, "factor": 0}, timeout=15).status_code == 400,
          "faktor 0 ditolak")
    x = requests.get(f"{API}/rab/import-template.xlsx", headers=H, params={"kind": "unit_type"}, timeout=15)
    check(x.status_code == 200 and x.content[:2] == b"PK", "template Excel RAB terunduh")
    imp = requests.post(f"{API}/rab/templates/unit_type/{T}/import", headers=H, files={"file": ("t.xlsx", x.content)}, timeout=15).json()["data"]
    check(imp["rows"] == 1 and imp["items"][0]["description"] == "Struktur & pondasi", "impor template contoh → 1 baris pratinjau")
    check(requests.post(f"{API}/rab/templates/unit_type/{T}/import", headers=H, files={"file": ("t.csv", b"x")}, timeout=15).status_code == 400, "impor non-xlsx ditolak")
    # fasum vs fase
    proj = requests.get(f"{API}/projects", headers=H, params={"limit": 1}, timeout=15).json()["data"][0]
    sub = requests.get(f"{API}/subcon/subcontractors", headers=H, params={"active": "true"}, timeout=15).json()["data"][0]
    ph = requests.post(f"{API}/construction/phases", headers=H, json={"project_id": proj["id"], "name": f"GATE61_fase {int(time.time()) % 10000}", "weight": 1, "order": 98}, timeout=15).json()["data"]
    requests.post(f"{API}/construction/phases/{ph['id']}/progress", headers=H, json={"progress": 30}, timeout=15)
    bi = requests.post(f"{API}/boq/items", headers=H, json={"project_id": proj["id"], "cost_code": f"G61-{int(time.time()) % 100000}", "description": "GATE61_fasum", "category": "infrastruktur",
                                                              "uom": "m", "quantity": 10, "unit_price": 1_000_000, "scope": "fasum", "facility": "jalan", "phase_id": ph["id"]}, timeout=15).json()["data"]
    d = requests.post(f"{API}/rab/spk-draft", headers=H, json={"project_id": proj["id"], "mode": "fasum", "boq_item_ids": [bi["id"]]}, timeout=15).json()["data"]
    spk = requests.post(f"{API}/subcon/spk/from-rab", headers=H, json={"subcontractor_id": sub["id"], "project_id": proj["id"], "title": "GATE61_SPK", "spk_kind": "fasum", "lines": d["lines"]}, timeout=15).json()["data"]
    requests.post(f"{API}/subcon/spk/{spk['id']}/status", headers=H, json={"status": "active"}, timeout=15)
    dup = requests.post(f"{API}/subcon/spk/from-rab", headers=H, json={"subcontractor_id": sub["id"], "project_id": proj["id"], "title": "GATE61_SPK2", "spk_kind": "fasum", "lines": d["lines"]}, timeout=15)
    check(dup.status_code == 400, "item fasum tidak bisa dikontrakkan 2×")
    over = requests.post(f"{API}/subcon/claims", headers=H, json={"spk_id": spk["id"], "progress_pct": 50}, timeout=15)
    check(over.status_code == 400 and "30%" in over.text, "termin 50% ditolak saat fase 30%")
    okc = requests.post(f"{API}/subcon/claims", headers=H, json={"spk_id": spk["id"], "progress_pct": 30}, timeout=15)
    check(okc.status_code == 200, "termin 30% diterima saat fase 30%")
    fc = requests.get(f"{API}/rab/projects/{proj['id']}/summary", headers=H, timeout=15).json()["data"]["fasum_control"]
    check(any(r["spk_id"] == spk["id"] and r["cap_pct"] == 30 for r in fc), "kendali fasum di ringkasan proyek")
    requests.post(f"{API}/subcon/spk/{spk['id']}/status", headers=H, json={"status": "cancelled", "note": "gate selesai"}, timeout=15)
except Exception as e:  # noqa: BLE001
    check(False, "server hidup", str(e))

print(f"\n{ok} OK, {len(fails)} GAGAL")
print("PASSED" if not fails else "FAILED")
sys.exit(1 if fails else 0)
