#!/usr/bin/env python3
"""_patch_vocab_f26.py — Fase 26: hapus SEMUA daftar vocabulary duplikat di backend.

Sebelum: `financing_router.VALID_STATUS`, `gl_engine.VALID_TYPES`,
`omnichannel_router.VALID_EVENTS/ACTIONS`, `tax_engine.TAX_TYPES/RECORD_STATUSES`,
dan literal `("pass","fail")`/`("in","out")`/`("scheduled","done",...)` tersebar di router —
bisa menyimpang dari reference.py (SSOT).
Sesudah: satu sumber = reference.py; pemeriksaan manual yang redundan dihapus karena
models.py sudah memvalidasi lewat Annotated type.

Setiap pola HARUS ketemu tepat 1x; kalau tidak, skrip gagal (anti silent-fail).
"""
import sys

EDITS = {
    "/app/backend/routers/financing_router.py": [
        ('router = APIRouter(prefix="/financing", tags=["financing"])\n\n'
         'VALID_STATUS = {"draft", "submitted", "approved", "rejected", "disbursing", "done"}\n',
         'router = APIRouter(prefix="/financing", tags=["financing"])\n'),
        ('    data = {k: v for k, v in payload.model_dump().items() if v is not None}\n'
         '    if "status" in data and data["status"] not in VALID_STATUS:\n'
         '        raise HTTPException(status_code=400, detail="Status tidak valid.")\n',
         '    # status divalidasi SSOT di models.FinancingUpdate (reference.financing_status)\n'
         '    data = {k: v for k, v in payload.model_dump().items() if v is not None}\n'),
    ],
    "/app/backend/gl_engine.py": [
        ('import sequences as seq\nimport gl_periods\n',
         'import sequences as seq\nimport gl_periods\nimport reference as ref\n'),
        ('DEBIT_NORMAL = ("asset", "expense")\n'
         'VALID_TYPES = ("asset", "liability", "equity", "revenue", "expense")\n',
         'DEBIT_NORMAL = ("asset", "expense")\n'
         '# SSOT: tipe akun hanya didefinisikan di reference.py (dulu daftar ini duplikat).\n'
         'VALID_TYPES = tuple(ref.values("account_type"))\n'),
    ],
    "/app/backend/tax_engine.py": [
        ('import sequences as seq\nfrom db import db, ORG_ID\n',
         'import sequences as seq\nimport reference as ref\nfrom db import db, ORG_ID\n'),
        ('TAX_TYPES = ("ppn", "pph", "bphtb")\n'
         'RECORD_STATUSES = ("pending", "reported", "paid")\n',
         '# SSOT: jenis & status pajak diambil dari reference.py (bukan daftar duplikat).\n'
         'TAX_TYPES = tuple(ref.values("tax_type"))\n'
         'RECORD_STATUSES = tuple(ref.values("tax_status"))\n'),
    ],
    "/app/backend/routers/omnichannel_router.py": [
        ('from db import db, ORG_ID\n', 'import reference as ref\nfrom db import db, ORG_ID\n'),
        ('VALID_EVENTS = {"message.received", "lead.captured", "no_response"}\n'
         'VALID_ACTIONS = {"create_task", "send_template", "suggest_stage", "notify"}\n',
         '# SSOT: pemicu & aksi automasi dari reference.py (grup automation_trigger/action).\n'
         'VALID_EVENTS = set(ref.values("automation_trigger"))\n'
         'VALID_ACTIONS = set(ref.values("automation_action"))\n'),
    ],
    "/app/backend/routers/tax_router.py": [
        ('    if payload.status and payload.status not in tx.RECORD_STATUSES:\n'
         '        raise HTTPException(status_code=400, detail="Status pajak tidak valid")\n', ''),
    ],
    "/app/backend/routers/construction_router.py": [
        ('    if payload.result not in ("pass", "fail"):\n'
         '        raise HTTPException(status_code=400, detail="Hasil QC harus \'pass\' atau \'fail\'")\n', ''),
    ],
    "/app/backend/routers/materials_router.py": [
        ('    if payload.type not in ("in", "out"):\n'
         '        raise HTTPException(status_code=400, detail="Tipe transaksi harus \'in\' (GRN) atau \'out\' (issue)")\n', ''),
    ],
    "/app/backend/routers/leads_router.py": [
        ('    if payload.status not in ("scheduled", "done", "cancelled", "no_show"):\n'
         '        raise HTTPException(status_code=400, detail="Status tidak valid")\n', ''),
    ],
    "/app/backend/routers/orgs_router.py": [
        ('from db import db, ORG_ID, COOKIE_SECURE, COOKIE_SAMESITE\n',
         'import reference as ref\nfrom db import db, ORG_ID, COOKIE_SECURE, COOKIE_SAMESITE\n'),
        ('class OrgUpdate(BaseModel):\n    name: Optional[str] = None\n'
         '    status: Optional[str] = None  # active | suspended\n',
         'class OrgUpdate(BaseModel):\n    name: Optional[str] = None\n'
         '    status: ref.OrgStatus = None\n'),
    ],
}


def main():
    bad = 0
    for path, pairs in EDITS.items():
        src = open(path, encoding="utf-8").read()
        for old, new in pairs:
            n = src.count(old)
            if n != 1:
                print(f"GAGAL {path}: pola {n}x (harus 1x)\n---\n{old}---")
                bad = 1
                continue
            src = src.replace(old, new)
        if not bad:
            open(path, "w", encoding="utf-8").write(src)
            print(f"OK {path} ({len(pairs)} suntingan)")
    return bad


if __name__ == "__main__":
    sys.exit(main())
