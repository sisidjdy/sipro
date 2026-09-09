"""MASTER DOKUMEN SYARAT + DOKUMEN YANG DISERAHKAN (Fase 39).

Keputusan owner (D3): dokumen syarat dibuat sebagai MASTER yang bisa ditambah admin, lalu
diunggah per tahap. Modul ini menyediakan dua hal:

  1. `doc_requirements` — master syarat: berlaku pada konteks apa (tahap lead, skema bayar,
     customer legal, onboarding mitra, unit/izin), wajib atau tidak, jenis berkas, masa
     kedaluwarsa, perlu verifikasi atau tidak.
  2. `doc_submissions` — berkas yang benar-benar diserahkan + status verifikasi + AKTOR.

Aturan kejujuran yang dipegang (mengikuti pola `slik.py`): berkas bukti harus BENAR ADA di
penyimpanan (`files`) — id fiktif tidak bisa dijadikan bukti, dan status `verified` selalu
menyimpan siapa yang memverifikasi beserta waktunya.
"""
import logging
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

import reference as ref
from core_utils import new_id, now_iso
from db import db, ORG_ID

logger = logging.getLogger("sipro.docreq")

ENTITY_TYPES = ("lead", "customer", "contract", "unit", "partner", "kpr")

# Default seed — boleh diubah/ditambah admin (bukan aturan mati).
DEFAULT_REQUIREMENTS = [
    {"code": "KTP", "label": "KTP pemesan", "group": "identitas",
     "applies_to": ["lead_stage:spr", "customer:legal"], "mandatory": True, "order": 10},
    {"code": "KTP_PASANGAN", "label": "KTP pasangan", "group": "identitas",
     "applies_to": ["lead_stage:spr"], "mandatory": False, "order": 20,
     "conditional_note": "Wajib bila pemesan sudah menikah."},
    {"code": "KK", "label": "Kartu Keluarga", "group": "identitas",
     "applies_to": ["lead_stage:spr", "customer:legal"], "mandatory": True, "order": 30},
    {"code": "NPWP", "label": "NPWP", "group": "identitas",
     "applies_to": ["lead_stage:spr", "customer:legal"], "mandatory": True, "order": 40},
    {"code": "BUKU_NIKAH", "label": "Buku nikah / akta perkawinan", "group": "identitas",
     "applies_to": ["lead_stage:spr"], "mandatory": False, "order": 50,
     "conditional_note": "Wajib bila pemesan sudah menikah."},
    {"code": "BUKTI_BOOKING_FEE", "label": "Bukti transfer booking fee", "group": "keuangan",
     "applies_to": ["lead_stage:booking"], "mandatory": True, "order": 60},
    {"code": "SLIK_IDEB", "label": "Hasil iDeb / BI Checking", "group": "keuangan",
     "applies_to": ["lead_stage:spr"], "mandatory": True, "order": 70,
     "conditional_note": "Wajib bila hasil BI Checking dipakai meloloskan lead."},
    {"code": "SLIP_GAJI", "label": "Slip gaji 3 bulan terakhir", "group": "kpr",
     "applies_to": ["payment_scheme:kpr"], "mandatory": True, "order": 80},
    {"code": "REK_KORAN", "label": "Rekening koran 3 bulan", "group": "kpr",
     "applies_to": ["payment_scheme:kpr"], "mandatory": True, "order": 90},
    {"code": "SK_KERJA", "label": "SK kerja / surat keterangan usaha", "group": "kpr",
     "applies_to": ["payment_scheme:kpr"], "mandatory": True, "order": 100},
    {"code": "IZIN_USAHA", "label": "NPWP / izin usaha (wirausaha)", "group": "kpr",
     "applies_to": ["payment_scheme:kpr"], "mandatory": False, "order": 110,
     "conditional_note": "Untuk pemohon wirausaha."},
    {"code": "FORM_KPR", "label": "Formulir aplikasi bank", "group": "kpr",
     "applies_to": ["payment_scheme:kpr"], "mandatory": True, "order": 120},
    {"code": "SPR_SIGNED", "label": "SPR yang sudah ditandatangani (scan)", "group": "legal",
     "applies_to": ["customer:legal"], "mandatory": True, "order": 130},
    {"code": "SPKT_SIGNED", "label": "SPKT kelebihan tanah (scan)", "group": "legal",
     "applies_to": ["customer:legal"], "mandatory": False, "order": 140,
     "conditional_note": "Wajib bila unit punya kelebihan tanah."},
    {"code": "PARTNER_KTP", "label": "KTP / akta pendirian mitra", "group": "mitra",
     "applies_to": ["partner:onboarding"], "mandatory": True, "order": 150},
    {"code": "PARTNER_KONTRAK", "label": "Kontrak kerja sama mitra", "group": "mitra",
     "applies_to": ["partner:onboarding"], "mandatory": True, "order": 160},
    {"code": "PARTNER_REKENING", "label": "Bukti rekening bank mitra", "group": "mitra",
     "applies_to": ["partner:onboarding"], "mandatory": True, "order": 170},
]


def _clean(payload) -> dict:
    return {k: v for k, v in payload.model_dump(exclude_none=True).items()}


# ------------------------------------------------------------------ master syarat
async def list_requirements(org: str = ORG_ID, context: str = None, group: str = None,
                            active: bool = None) -> list:
    query = {"org_id": org}
    if group:
        query["group"] = group
    if active is not None:
        query["active"] = active
    if context:
        query["applies_to"] = context
    return await db.doc_requirements.find(query, {"_id": 0}).sort(
        [("order", 1), ("code", 1)]).to_list(300)


async def create_requirement(payload, actor: str, org: str = ORG_ID) -> dict:
    if await db.doc_requirements.find_one({"org_id": org, "code": payload.code}, {"_id": 1}):
        raise ValueError(f"Dokumen syarat '{payload.code}' sudah ada.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, **_clean(payload),
           "created_by": actor, "created_at": ts, "updated_at": ts}
    if doc.get("needs_verification") is None:
        import settings_store as cfg
        doc["needs_verification"] = bool(
            await cfg.get("doc.require_verification_default", org_id=org))
    doc.setdefault("active", True)
    await db.doc_requirements.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def update_requirement(req_id: str, payload, actor: str, org: str = ORG_ID) -> dict:
    patch = _clean(payload)
    if not patch:
        raise ValueError("Tidak ada perubahan.")
    patch.update({"updated_at": now_iso(), "updated_by": actor})
    res = await db.doc_requirements.update_one({"id": req_id, "org_id": org}, {"$set": patch})
    if not res.matched_count:
        raise LookupError("Dokumen syarat tidak ditemukan.")
    return await db.doc_requirements.find_one({"id": req_id}, {"_id": 0})


async def matching(contexts: list, org: str = ORG_ID) -> list:
    """Semua syarat yang berlaku untuk kumpulan konteks (mis. tahap + skema bayar)."""
    if not contexts:
        return []
    return await db.doc_requirements.find(
        {"org_id": org, "active": True, "applies_to": {"$in": list(contexts)}},
        {"_id": 0}).sort([("order", 1), ("code", 1)]).to_list(300)


# ------------------------------------------------------------------ penyerahan dokumen
async def _file_meta(file_id: str, org: str) -> dict:
    row = await db.files.find_one(
        {"org_id": org, "id": file_id, "is_deleted": False},
        {"_id": 0, "id": 1, "original_filename": 1, "content_type": 1, "size": 1,
         "uploaded_by": 1, "created_at": 1, "sha256": 1})
    if not row:
        raise ValueError(f"Berkas tidak ditemukan di penyimpanan: {file_id}")
    return row


async def _same_evidence_status(payload, meta: dict, org: str):
    """Cari penyerahan lain untuk syarat yang sama yang ISI BERKASNYA identik.

    Index unik hanya menjaga `file_id` — mengunggah ULANG berkas yang sama menghasilkan
    `file_id` baru, jadi bukti kembar tetap bisa masuk dua kali (checklist lalu punya dua
    baris "menunggu verifikasi" untuk berkas yang sama, dan verifikator mengerjakan
    pekerjaan yang sama dua kali). Sidik jari `files.sha256` (sudah ada sejak Fase 31 untuk
    menolak foto bukti daur ulang) dipakai di sini.

    Penyerahan berstatus `rejected` SENGAJA tidak menghalangi: bila penolakan ternyata
    keliru, pengguna masih boleh menyerahkan berkas yang sama sekali lagi.
    """
    if not meta.get("sha256"):
        return None
    prev = await db.doc_submissions.find(
        {"org_id": org, "entity_type": payload.entity_type, "entity_id": payload.entity_id,
         "requirement_code": payload.requirement_code,
         "status": {"$in": ["pending", "verified"]}},
        {"_id": 0, "file_id": 1, "status": 1}).to_list(100)
    if not prev:
        return None
    hit = await db.files.find_one(
        {"org_id": org, "id": {"$in": [p["file_id"] for p in prev]},
         "sha256": meta["sha256"]}, {"_id": 0, "id": 1})
    if not hit:
        return None
    return next((p["status"] for p in prev if p["file_id"] == hit["id"]), "pending")


async def create_submission(payload, actor: str, org: str = ORG_ID) -> dict:
    req = await db.doc_requirements.find_one(
        {"org_id": org, "code": payload.requirement_code}, {"_id": 0})
    if not req:
        raise ValueError(f"Dokumen syarat '{payload.requirement_code}' tidak ada di master.")
    if payload.entity_type not in ENTITY_TYPES:
        raise ValueError(f"entity_type harus salah satu: {', '.join(ENTITY_TYPES)}")
    meta = await _file_meta(payload.file_id, org)
    dup = await _same_evidence_status(payload, meta, org)
    if dup:
        raise ValueError(
            f"Berkas dengan isi yang sama sudah pernah diserahkan untuk syarat "
            f"'{req['code']}' (status: {ref.label_of('doc_submission_status', dup)}). "
            f"Pilih berkas lain, atau tunggu hasil verifikasi berkas yang sudah masuk.")
    ts = now_iso()
    needs = bool(req.get("needs_verification", True))
    expires = None
    if req.get("expiry_days"):
        expires = (datetime.now(timezone.utc)
                   + timedelta(days=int(req["expiry_days"]))).isoformat()
    doc = {
        "id": new_id(), "org_id": org, "requirement_code": req["code"],
        "requirement_label": req["label"], "group": req.get("group"),
        "entity_type": payload.entity_type, "entity_id": payload.entity_id,
        "file_id": payload.file_id, "file": meta, "note": payload.note,
        "status": "pending" if needs else "verified",
        "verified_by": None if needs else "system", "verified_at": None if needs else ts,
        "reject_reason": None, "expires_at": expires,
        "history": [{"at": ts, "actor": actor, "action": "upload",
                     "note": payload.note, "file_id": payload.file_id}],
        "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    # Index unik `uq_doc_submission` (org, entity_type, entity_id, requirement_code, file_id)
    # mencegah berkas yang SAMA diserahkan dua kali. Tanpa penangkapan ini, pengguna yang
    # menekan "Unggah ulang" lalu memilih berkas yang sama mendapat **500 Internal Server
    # Error** — layar hanya berbunyi "Gagal mengunggah dokumen" tanpa alasan.
    try:
        await db.doc_submissions.insert_one(dict(doc))
    except DuplicateKeyError:
        raise ValueError(
            f"Berkas '{meta.get('original_filename') or payload.file_id}' sudah pernah "
            f"diserahkan untuk syarat '{req['code']}'. Pilih berkas lain, atau tunggu "
            f"hasil verifikasi berkas yang sudah masuk.")
    doc.pop("_id", None)
    await refresh_progress(payload.entity_type, payload.entity_id, org)
    return doc


async def _set_status(sub_id: str, status: str, actor: str, org: str, *, reason=None,
                      note=None) -> dict:
    sub = await db.doc_submissions.find_one({"id": sub_id, "org_id": org}, {"_id": 0})
    if not sub:
        raise LookupError("Dokumen tidak ditemukan.")
    ts = now_iso()
    patch = {"status": status, "updated_at": ts, "reject_reason": reason}
    if status == "verified":
        patch.update({"verified_by": actor, "verified_at": ts})
    await db.doc_submissions.update_one({"id": sub_id}, {
        "$set": patch,
        "$push": {"history": {"at": ts, "actor": actor, "action": status,
                              "reason": reason, "note": note}}})
    await refresh_progress(sub["entity_type"], sub["entity_id"], org)
    return await db.doc_submissions.find_one({"id": sub_id}, {"_id": 0})


async def verify_submission(sub_id: str, actor: str, note=None, org: str = ORG_ID) -> dict:
    return await _set_status(sub_id, "verified", actor, org, note=note)


async def reject_submission(sub_id: str, actor: str, reason: str, org: str = ORG_ID) -> dict:
    return await _set_status(sub_id, "rejected", actor, org, reason=reason)


async def submissions_for(entity_type: str, entity_id: str, org: str = ORG_ID) -> list:
    rows = await db.doc_submissions.find(
        {"org_id": org, "entity_type": entity_type, "entity_id": entity_id},
        {"_id": 0}).sort("created_at", -1).to_list(200)
    for r in rows:
        r["status_label"] = ref.label_of("doc_submission_status", r.get("status"))
    return rows


async def matrix(entity_type: str, entity_id: str, contexts: list,
                 org: str = ORG_ID) -> dict:
    """Matriks syarat × dokumen diserahkan — dipakai UI (DocMatrix) & gerbang bukti."""
    reqs = await matching(contexts, org)
    subs = await submissions_for(entity_type, entity_id, org)
    by_code = {}
    for s in subs:
        by_code.setdefault(s["requirement_code"], []).append(s)
    rows, counts = [], {"required": 0, "verified": 0, "pending": 0, "rejected": 0, "missing": 0}
    for r in reqs:
        items = by_code.get(r["code"], [])
        status = "missing"
        if any(i["status"] == "verified" for i in items):
            status = "verified"
        elif any(i["status"] == "pending" for i in items):
            status = "pending"
        elif any(i["status"] == "rejected" for i in items):
            status = "rejected"
        if r.get("mandatory"):
            counts["required"] += 1
            counts[status if status in counts else "missing"] += 1
        rows.append({"requirement": r, "status": status, "submissions": items,
                     "status_label": (ref.label_of("doc_submission_status", status)
                                      if status != "missing" else "Belum diunggah")})
    complete = all(x["status"] == "verified" for x in rows if x["requirement"].get("mandatory"))
    return {"rows": rows, "counts": counts, "complete": complete, "contexts": contexts}


async def refresh_progress(entity_type: str, entity_id: str, org: str = ORG_ID) -> dict:
    """Denormalisasi ringkas ke entitas induk (tampilan cepat di tabel/kartu)."""
    subs = await submissions_for(entity_type, entity_id, org)
    prog = {"total": len(subs),
            "verified": sum(1 for s in subs if s["status"] == "verified"),
            "pending": sum(1 for s in subs if s["status"] == "pending"),
            "rejected": sum(1 for s in subs if s["status"] == "rejected"),
            "updated_at": now_iso()}
    coll = {"lead": db.leads, "customer": db.customers, "unit": db.units,
            "partner": db.agents, "contract": db.contracts, "kpr": db.financing_apps}.get(entity_type)
    if coll is not None:
        await coll.update_one({"id": entity_id, "org_id": org}, {"$set": {"doc_progress": prog}})
    return prog


# ------------------------------------------------------------------ konteks berlaku
# Urutan tahap lead yang dipakai mesin lifecycle (`lead_lifecycle.ORDER`). Ditulis ulang
# di sini sebagai konstanta agar modul dokumen tidak mengimpor mesin lifecycle
# (menghindari impor berputar); nilainya dijaga sama oleh gate `verify_masterplan.py`.
LEAD_ORDER = ("acquisition", "nurturing", "appointment", "booking", "won")


async def contexts_for(entity_type: str, entity_id: str, org: str = ORG_ID) -> list:
    """Konteks syarat dokumen yang BERLAKU untuk satu entitas — diturunkan dari datanya.

    Aturan ini SENGAJA di backend: kalau frontend yang memutuskan, aturannya jadi dua versi
    dan checklist bisa "lupa" satu syarat tanpa ada yang tahu.

    * lead     — tahap sekarang + tahap BERIKUTNYA (supaya sales menyiapkan berkas sebelum
      pindah tahap, bukan setelah tertahan) + berkas SPR begitu lead sudah booking/menang.
    * customer — dokumen legal; ditambah syarat KPR bila pelanggan punya pengajuan KPR.
    * partner / kpr — onboarding mitra & berkas bank.
    """
    if entity_type == "lead":
        lead = await db.leads.find_one({"id": entity_id, "org_id": org},
                                       {"_id": 0, "stage": 1}) or {}
        stage = lead.get("stage")
        ctx = [f"lead_stage:{stage}"] if stage else []
        if stage in LEAD_ORDER:
            ctx.append(f"lead_stage:{LEAD_ORDER[min(LEAD_ORDER.index(stage) + 1, 4)]}")
        if stage in ("booking", "won"):
            ctx.append("lead_stage:spr")
        return list(dict.fromkeys(ctx))
    if entity_type == "customer":
        ctx = ["customer:legal"]
        if await db.financing_apps.find_one({"org_id": org, "customer_id": entity_id},
                                            {"_id": 1}):
            ctx.append("payment_scheme:kpr")
        return ctx
    if entity_type == "partner":
        return ["partner:onboarding"]
    if entity_type == "kpr":
        return ["payment_scheme:kpr"]
    return []


async def seed_defaults(org: str = ORG_ID) -> dict:
    ts = now_iso()
    added = 0
    for r in DEFAULT_REQUIREMENTS:
        if await db.doc_requirements.find_one({"org_id": org, "code": r["code"]}, {"_id": 1}):
            continue
        await db.doc_requirements.insert_one({
            "id": new_id(), "org_id": org, "active": True, "needs_verification": True,
            "allowed_mime": ["image/jpeg", "image/png", "application/pdf"], "max_mb": 10,
            "expiry_days": None, "created_by": "seed", "created_at": ts, "updated_at": ts, **r})
        added += 1
    if added:
        logger.info("Master dokumen syarat: %s baris default ditambahkan", added)
    return {"requirements": added}
