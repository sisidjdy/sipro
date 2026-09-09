"""Patch backend hasil audit forensik (idempoten). Jalankan: python scripts/_patch_backend.py"""
import pathlib
import sys

B = pathlib.Path("/app/backend")

# (file, old, new, label)
PATCHES = [
    # ---------------- 1. Nomor dokumen atomik ----------------
    ("routers/subcon_router.py",
     'async def _next_number(prefix: str, coll) -> str:\n'
     '    year = now_iso()[:4]\n'
     '    n = await coll.count_documents({"org_id": ORG_ID}) + 1\n'
     '    return f"{prefix}/{year}/{n:04d}"',
     'SCOPE_BY_PREFIX = {"SPK": "spk"}\n\n\n'
     'async def _next_number(prefix: str, coll, org_id: str = None) -> str:\n'
     '    """Nomor atomik per org+tahun. Dulu `count_documents+1`: dua request bersamaan\n'
     '    menghasilkan nomor identik, dan hitungannya memakai org default (bocor antar tenant)."""\n'
     '    return await seq.next_number(SCOPE_BY_PREFIX.get(prefix, prefix.lower()),\n'
     '                                 org_id or ORG_ID, prefix=prefix)',
     "subcon: nomor atomik"),
    ("routers/subcon_router.py",
     'await _next_number("SPK", db.spk)', 'await _next_number("SPK", db.spk, org)',
     "subcon: SPK pakai org user"),

    ("routers/procurement_router.py",
     'async def _next_number(prefix: str, coll) -> str:\n'
     '    year = now_iso()[:4]\n'
     '    n = await coll.count_documents({"org_id": ORG_ID}) + 1\n'
     '    return f"{prefix}/{year}/{n:04d}"',
     'SCOPE_BY_PREFIX = {"PO": "po", "GRN": "grn"}\n\n\n'
     'async def _next_number(prefix: str, coll, org_id: str = None) -> str:\n'
     '    """Nomor atomik per org+tahun (lihat sequences.py)."""\n'
     '    return await seq.next_number(SCOPE_BY_PREFIX.get(prefix, prefix.lower()),\n'
     '                                 org_id or ORG_ID, prefix=prefix)',
     "procurement: nomor atomik"),
    ("routers/procurement_router.py",
     'await _next_number("PO", db.purchase_orders)',
     'await _next_number("PO", db.purchase_orders, org)', "procurement: PO org"),
    ("routers/procurement_router.py",
     'await _next_number("GRN", db.grns)', 'await _next_number("GRN", db.grns, org)',
     "procurement: GRN org"),

    ("routers/subcon_claims_router.py",
     'async def _next_number(prefix: str, coll) -> str:\n'
     '    year = now_iso()[:4]\n'
     '    n = await coll.count_documents({"org_id": ORG_ID}) + 1\n'
     '    return f"{prefix}/{year}/{n:04d}"',
     'SCOPE_BY_PREFIX = {"TRM": "claim", "CO": "change_order"}\n\n\n'
     'async def _next_number(prefix: str, coll, org_id: str = None) -> str:\n'
     '    """Nomor atomik per org+tahun (lihat sequences.py)."""\n'
     '    return await seq.next_number(SCOPE_BY_PREFIX.get(prefix, prefix.lower()),\n'
     '                                 org_id or ORG_ID, prefix=prefix)',
     "claims: nomor atomik"),
    ("routers/subcon_claims_router.py",
     'await _next_number("TRM", db.progress_claims)',
     'await _next_number("TRM", db.progress_claims, org)', "claims: TRM org"),
    ("routers/subcon_claims_router.py",
     'await _next_number("CO", db.change_orders)',
     'await _next_number("CO", db.change_orders, org)', "claims: CO org"),

    ("routers/materials_router.py",
     'async def _req_number(org: str) -> str:\n'
     '    n = await db.material_requisitions.count_documents({"org_id": org}) + 1\n'
     '    return f"PR/{now_iso()[:4]}/{n:04d}"',
     'async def _req_number(org: str) -> str:\n'
     '    """Nomor atomik (dulu count_documents+1 -> bisa duplikat)."""\n'
     '    return await seq.next_number("requisition", org, prefix="PR")',
     "materials: nomor atomik"),

    ("routers/inspection_router.py",
     '    n = await db.inspections.count_documents({"org_id": org}) + 1\n'
     '    ts = now_iso()\n'
     '    doc = {\n'
     '        "id": new_id(), "org_id": org, "inspection_number": f"QC/{ts[:4]}/{n:04d}",',
     '    ts = now_iso()\n'
     '    doc = {\n'
     '        "id": new_id(), "org_id": org,\n'
     '        "inspection_number": await seq.next_number("inspection", org, prefix="QC"),',
     "inspection: nomor atomik"),

    ("gl_engine.py",
     '    n = await db.journal_entries.count_documents({"org_id": org_id}) + 1\n'
     '    doc = {\n'
     '        "id": new_id(), "org_id": org_id, "entry_no": f"JV/{ts[:4]}/{n:05d}", "date": d,',
     '    entry_no = await seq.next_number("journal", org_id, prefix="JV", width=5, year=ts[:4])\n'
     '    doc = {\n'
     '        "id": new_id(), "org_id": org_id, "entry_no": entry_no, "date": d,',
     "GL: nomor jurnal atomik"),

    ("tax_engine.py",
     '    n = await db.faktur_pajak.count_documents({"org_id": org_id}) + 1\n'
     '    return f"{transaction_code}.000-{yy}.{str(n).zfill(8)}"',
     '    n = await seq.next_seq("faktur", org_id)\n'
     '    return f"{transaction_code}.000-{yy}.{str(n).zfill(8)}"',
     "pajak: nomor faktur atomik"),

    ("routers/documents_router.py",
     '    seq = await db.documents.count_documents({"org_id": org, "template_code": payload.template_code}) + 1\n'
     '    doc_number = f"{payload.template_code}/{year}/{seq:04d}"',
     '    doc_number = await sequences.next_number(f"document:{payload.template_code}", org,\n'
     '                                             prefix=payload.template_code, year=year)',
     "dokumen: nomor atomik"),

    ("routers/deals_router.py",
     '    n = await db.deals.count_documents({"org_id": org, f"{field}.number": {"$exists": True}}) + 1\n'
     '    return f"{prefix}/{now_iso()[:4]}/{n:04d}"',
     '    return await seq.next_number(f"legal:{field}", org, prefix=prefix)',
     "PPJB/AJB: nomor atomik"),

    # ---------------- 2. SSOT skor sumber lead ----------------
    ("engine.py",
     'SCORE_SOURCE = {"meta_ads": 25, "whatsapp": 20, "walk_in": 25, "referral": 20,\n'
     '                "website": 15, "manual": 10, "import": 10}',
     '# SSOT di reference.SOURCE_SCORE. Dulu google_lead & tiktok_ads TIDAK terdaftar di sini,\n'
     '# sehingga lead dari iklan Google/TikTok selalu mendapat skor terendah (10) seperti import.\n'
     'SCORE_SOURCE = ref.SOURCE_SCORE',
     "lead scoring: SSOT + Google/TikTok tidak lagi diskor terendah"),

    # ---------------- 3. SSOT tahap lead ----------------
    ("routers/leads_router.py",
     'STAGES = ["acquisition", "nurturing", "appointment", "booking", "won", "recycle", "lost"]',
     'STAGES = list(ref.values("lead_stage"))  # SSOT: reference.GROUPS["lead_stage"]',
     "leads: STAGES dari reference"),

    # ---------------- 4. Dedup lead per nomor telepon ----------------
    ("routers/leads_router.py",
     '    org = user.get("org_id", ORG_ID)\n'
     '    ts = now_iso()\n'
     '    assignee = payload.assigned_to\n'
     '    if is_scoped_sales(user):',
     '    org = user.get("org_id", ORG_ID)\n'
     '    ts = now_iso()\n'
     '    phone = normalize_phone_e164(payload.phone)\n'
     '    dup = await db.leads.find_one({"org_id": org, "phone": phone},\n'
     '                                  {"_id": 0, "id": 1, "name": 1, "assigned_to": 1, "stage": 1})\n'
     '    if dup:\n'
     '        raise HTTPException(status_code=409, detail=(\n'
     '            f"Nomor {phone} sudah terdaftar sebagai lead \'{dup.get(\'name\')}\' "\n'
     '            f"(tahap {dup.get(\'stage\')}, pemilik {dup.get(\'assigned_to\')}). "\n'
     '            "Gunakan lead yang ada agar tidak duplikat."))\n'
     '    assignee = payload.assigned_to\n'
     '    if is_scoped_sales(user):',
     "leads: cegah duplikat nomor telepon"),
    ("routers/leads_router.py",
     '        "id": new_id(), "org_id": org, "name": payload.name, "phone": payload.phone,\n'
     '        "email": payload.email, "source": payload.source, "campaign": payload.campaign,',
     '        "id": new_id(), "org_id": org, "name": payload.name, "phone": phone,\n'
     '        "email": payload.email, "source": payload.source, "campaign": payload.campaign,',
     "leads: simpan telepon ternormalisasi"),

    # ---------------- 5. Cascade rename master ----------------
    ("routers/subcon_router.py",
     '    await db.subcontractors.update_one({"id": sid, "org_id": org}, {"$set": upd})\n'
     '    return {"data": serialize_doc(await db.subcontractors.find_one({"id": sid}, {"_id": 0}))}',
     '    await db.subcontractors.update_one({"id": sid, "org_id": org}, {"$set": upd})\n'
     '    fresh = await db.subcontractors.find_one({"id": sid}, {"_id": 0})\n'
     '    # SSOT: samakan nama yang dikopi ke SPK/termin/CO/PO (dulu jadi basi saat rename).\n'
     '    await cascade_master_change("subcontractors", sid, fresh)\n'
     '    return {"data": serialize_doc(fresh)}',
     "subcon: cascade nama ke dokumen anak"),
    ("routers/customers_router.py",
     '    await db.customers.update_one({"id": cid, "org_id": org}, {"$set": data})\n'
     '    fresh = await db.customers.find_one({"id": cid, "org_id": org}, {"_id": 0})',
     '    await db.customers.update_one({"id": cid, "org_id": org}, {"$set": data})\n'
     '    fresh = await db.customers.find_one({"id": cid, "org_id": org}, {"_id": 0})\n'
     '    await cascade_master_change("customers", cid, fresh)',
     "customers: cascade nama ke komplain/KPR"),

    # ---------------- 6. seed: perbaiki data kopi yang salah ----------------
    ("seed.py",
     '         "unit_code": "A-02", "scheme_id": None, "scheme_name": "Komisi Sales Bertingkat",',
     '         "unit_code": "A-01", "scheme_id": None, "scheme_name": "Komisi Sales Bertingkat",',
     "seed: unit_code komisi #1 konsisten dengan unit_id"),
    ("seed.py",
     '         "unit_code": "A-03", "scheme_id": None, "scheme_name": "Komisi Sales Bertingkat",',
     '         "unit_code": "A-01", "scheme_id": None, "scheme_name": "Komisi Sales Bertingkat",',
     "seed: unit_code komisi #2 konsisten dengan unit_id"),
    # seed: nilai enum kanonik sejak awal
    ("seed.py", '"weather": "Cerah berawan"', '"weather": "cerah_berawan"', "seed: cuaca kanonik"),
    ("seed.py", '"weather": "Cerah"', '"weather": "cerah"', "seed: cuaca kanonik 2"),
    ("seed.py", '"category": "MEP", "severity": "high"', '"category": "mep", "severity": "high"',
     "seed: kategori punch kanonik"),
    ("seed.py", '"specialty": "Struktur & Beton"', '"specialty": "struktur"',
     "seed: bidang subkon kanonik"),
    ("seed.py", '"specialty": "MEP (Listrik & Plumbing)"', '"specialty": "mep"',
     "seed: bidang subkon kanonik 2"),
    ("seed.py", '("PREP-01", "Persiapan",', '("PREP-01", "persiapan",', "seed: BoQ kategori 1"),
    ("seed.py", '("STR-01", "Struktur",', '("STR-01", "struktur",', "seed: BoQ kategori 2"),
    ("seed.py", '("STR-02", "Struktur",', '("STR-02", "struktur",', "seed: BoQ kategori 3"),
    ("seed.py", '("ARS-01", "Arsitektur",', '("ARS-01", "arsitektur",', "seed: BoQ kategori 4"),
    ("seed.py", '("MEP-01", "MEP",', '("MEP-01", "mep",', "seed: BoQ kategori 5"),
    ("seed.py", '("FIN-01", "Finishing",', '("FIN-01", "finishing",', "seed: BoQ kategori 6"),
    ("seed.py", '"interest_unit_type": "Tipe 45", "notes": None',
     '"interest_unit_type": "Tipe 45/90", "notes": None', "seed: tipe unit lead cocok master"),
    ("seed.py", '"interest_unit_type": "Tipe 45", "notes": "Tertarik unit Tipe 45."',
     '"interest_unit_type": "Tipe 45/90", "notes": "Tertarik unit Tipe 45/90."',
     "seed: tipe unit lead cocok master 2"),
]

# import tambahan: (file, baris import baru, anchor setelahnya disisipkan)
IMPORTS = [
    ("routers/subcon_router.py", "import sequences as seq", "from db import"),
    ("routers/subcon_router.py", "from denorm import cascade_master_change", "from db import"),
    ("routers/procurement_router.py", "import sequences as seq", "from db import"),
    ("routers/subcon_claims_router.py", "import sequences as seq", "from db import"),
    ("routers/materials_router.py", "import sequences as seq", "from db import"),
    ("routers/inspection_router.py", "import sequences as seq", "from db import"),
    ("gl_engine.py", "import sequences as seq", "from db import"),
    ("tax_engine.py", "import sequences as seq", "from db import"),
    ("routers/documents_router.py", "import sequences", "from db import"),
    ("routers/deals_router.py", "import sequences as seq", "from db import"),
    ("engine.py", "import reference as ref", "from db import"),
    ("routers/leads_router.py", "import reference as ref", "from db import"),
    ("routers/leads_router.py", "from core_utils import normalize_phone_e164", "from db import"),
    ("routers/customers_router.py", "from denorm import cascade_master_change", "from db import"),
]


def apply():
    ok, skip, fail = 0, 0, []
    for rel, old, new, label in PATCHES:
        p = B / rel
        s = p.read_text()
        if new in s:
            skip += 1
            continue
        if old not in s:
            fail.append(f"{rel}: {label} — pola tidak ditemukan")
            continue
        p.write_text(s.replace(old, new, 1))
        ok += 1
        print(f"  [OK] {rel}: {label}")
    for rel, imp, anchor in IMPORTS:
        p = B / rel
        s = p.read_text()
        if imp in s:
            continue
        idx = s.find(anchor)
        if idx < 0:
            fail.append(f"{rel}: anchor import '{anchor}' tidak ada")
            continue
        s = s[:idx] + imp + "\n" + s[idx:]
        p.write_text(s)
        print(f"  [OK] {rel}: + {imp}")
    print(f"\napplied={ok} skipped={skip} failed={len(fail)}")
    for f in fail:
        print("  [FAIL]", f)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(apply())
