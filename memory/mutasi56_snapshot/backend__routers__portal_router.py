"""Customer Portal (EPIC M1): buyer-facing, OTP auth, transparency on
unit/payment/progress/documents + complaint channel with SLA.

Auth is via portal JWT (type='portal'); staff tokens are rejected. OTP is sent
via the WhatsApp provider (simulation reveals the code in dev). A master OTP
(PORTAL_MASTER_OTP, default '000000') is accepted for deterministic testing.
"""
import io
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from db import db, ORG_ID, ORG_NAME
import build_monitor as bm
import cancellation_engine as cx
import p28_utils as p28
import payment_intake as intake
import reference as ref
import storage
from core_utils import new_id, now_iso, serialize_doc, due_in, normalize_phone_e164
from engine import build_s_curve, auto_create_task, create_notification
from pdf_utils import build_document_pdf
from portal_security import create_portal_token, get_portal_user
from notifications import send_whatsapp, gen_otp
import handover_engine as he
import warranty_engine as we
from models import PortalOtpRequest, PortalOtpVerify, ComplaintCreate
from models_p50 import PortalWarrantyClaim
from models_p51 import PortalClaimAckIn
from models_p47 import PaymentProofIn

router = APIRouter(prefix="/portal", tags=["portal"])


# ----------------------------- helpers -----------------------------
def _norm(ident: str):
    ident = (ident or "").strip()
    if "@" in ident:
        return "email", ident.lower()
    return "phone", normalize_phone_e164(ident)


async def _find_portal_user(ident: str):
    """Find a portal_user by phone/email; auto-provision from a matching customer."""
    kind, val = _norm(ident)
    pu = await db.portal_users.find_one({kind: val}, {"_id": 0})
    if pu:
        return pu
    cust = await db.customers.find_one({kind: val}, {"_id": 0})
    if not cust:
        return None
    ts = now_iso()
    pu = {
        "id": new_id(), "org_id": cust.get("org_id", ORG_ID), "customer_id": cust["id"],
        "name": cust.get("name"), "phone": cust.get("phone"), "email": cust.get("email"),
        "is_active": True, "created_at": ts, "last_login_at": None,
    }
    await db.portal_users.insert_one(dict(pu))
    pu.pop("_id", None)
    return pu


async def _customer(pu: dict) -> dict:
    return await db.customers.find_one({"id": pu.get("customer_id")}, {"_id": 0}) or {}


async def _deals(pu: dict, customer: dict) -> list:
    org = pu.get("org_id", ORG_ID)
    lead_id = customer.get("lead_id")
    if not lead_id:
        return []
    return await db.deals.find({"org_id": org, "lead_id": lead_id}, {"_id": 0}).sort("created_at", -1).to_list(50)


def _payment_summary(inv: dict) -> dict:
    if not inv:
        return {"total": 0, "paid": 0, "outstanding": 0, "next_due": None, "next_amount": 0}
    items = inv.get("items") or []
    nxt = None
    for it in sorted(items, key=lambda x: x.get("due_date") or ""):
        if it.get("status") != "paid":
            nxt = it
            break
    return {
        "total": inv.get("total", 0), "paid": inv.get("paid", 0),
        "outstanding": inv.get("outstanding", 0), "status": inv.get("status"),
        "next_due": (nxt or {}).get("due_date"), "next_amount": (nxt or {}).get("amount", 0),
        "next_label": (nxt or {}).get("label"),
    }


# ----------------------------- auth -----------------------------
@router.post("/auth/request-otp")
async def request_otp(payload: PortalOtpRequest):
    pu = await _find_portal_user(payload.identifier)
    if not pu:
        raise HTTPException(status_code=404, detail="Data pembeli tidak ditemukan untuk kontak tersebut.")
    code = gen_otp()
    await db.portal_otps.update_one(
        {"portal_user_id": pu["id"]},
        {"$set": {"portal_user_id": pu["id"], "code": code, "attempts": 0,
                  "expires_at": due_in(minutes=10), "created_at": now_iso()}},
        upsert=True,
    )
    to = pu.get("phone") or pu.get("email")
    channel = "whatsapp" if pu.get("phone") else "email"
    res = await send_whatsapp(to, f"Kode OTP Portal SIPRO Anda: {code} (berlaku 10 menit). Jangan bagikan kode ini.")
    simulated = res.get("provider") == "simulation"
    return {
        "sent": True, "channel": channel, "masked": _mask(to),
        "dev_code": code if simulated else None,
        "message": "OTP dikirim." + (" Mode simulasi: kode ditampilkan untuk pengujian." if simulated else ""),
    }


def _mask(s: str) -> str:
    if not s:
        return ""
    if "@" in s:
        u, _, d = s.partition("@")
        return (u[:2] + "***@" + d)
    return s[:5] + "****" + s[-2:]


@router.post("/auth/verify-otp")
async def verify_otp(payload: PortalOtpVerify):
    pu = await _find_portal_user(payload.identifier)
    if not pu:
        raise HTTPException(status_code=404, detail="Data pembeli tidak ditemukan.")
    master = os.environ.get("PORTAL_MASTER_OTP", "000000")
    code = (payload.code or "").strip()
    if code != master:
        rec = await db.portal_otps.find_one({"portal_user_id": pu["id"]}, {"_id": 0})
        if not rec or rec.get("code") != code:
            raise HTTPException(status_code=400, detail="Kode OTP salah.")
        if rec.get("expires_at") and rec["expires_at"] < now_iso():
            raise HTTPException(status_code=400, detail="Kode OTP kedaluwarsa. Minta kode baru.")
    await db.portal_otps.delete_one({"portal_user_id": pu["id"]})
    await db.portal_users.update_one({"id": pu["id"]}, {"$set": {"last_login_at": now_iso()}})
    token = create_portal_token(pu)
    return {"token": token, "profile": {"name": pu.get("name"), "customer_id": pu.get("customer_id"),
                                         "phone": pu.get("phone"), "email": pu.get("email")}}


# ----------------------------- data -----------------------------
@router.get("/me")
async def me(pu: dict = Depends(get_portal_user)):
    cust = await _customer(pu)
    return {"data": {"name": pu.get("name"), "phone": pu.get("phone"), "email": pu.get("email"),
                     "customer": serialize_doc({k: cust.get(k) for k in
                                                ["name", "nik", "npwp", "address", "kyc_status"]})}}


@router.get("/overview")
async def overview(pu: dict = Depends(get_portal_user)):
    org = pu.get("org_id", ORG_ID)
    cust = await _customer(pu)
    deals = await _deals(pu, cust)
    out = []
    for d in deals:
        unit = await db.units.find_one({"id": d.get("unit_id")}, {"_id": 0}) or {}
        project = await db.projects.find_one({"id": d.get("project_id")}, {"_id": 0}) or {}
        inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": d["id"]}, {"_id": 0})
        fin = await db.financing_apps.find_one({"org_id": org, "deal_id": d["id"]}, {"_id": 0})
        doc_count = await db.documents.count_documents({"org_id": org, "deal_id": d["id"]})
        open_complaints = await db.complaints.count_documents(
            {"org_id": org, "deal_id": d["id"], "status": {"$ne": "resolved"}})
        out.append({
            "deal_id": d["id"], "status": d.get("status"), "price": d.get("price"),
            "unit_code": unit.get("code"), "unit_type": unit.get("type"),
            "project_name": project.get("name"),
            "construction_progress": unit.get("construction_progress", 0),
            "construction_status": unit.get("construction_status"),
            # Label WAJIB ikut: portal pembeli memakai token sendiri sehingga tidak bisa
            # membaca `/api/reference` milik staf, dan tanpa ini layar pembeli menampilkan
            # nilai enum mentah ("done", "ready_handover") sebagai keterangan progres.
            "construction_status_label": ref.label_of("construction_status",
                                                      unit.get("construction_status")),
            "payment": _payment_summary(inv),
            "financing": fin and {"bank_name": fin.get("bank_name"), "status": fin.get("status"),
                                  "plafon": fin.get("plafon"), "disbursed_total": fin.get("disbursed_total"),
                                  "slik_status": fin.get("slik_status")},
            "documents_count": doc_count, "open_complaints": open_complaints,
        })
    return {"data": serialize_doc(out), "customer_name": cust.get("name")}


@router.get("/payments")
async def payments(pu: dict = Depends(get_portal_user)):
    org = pu.get("org_id", ORG_ID)
    cust = await _customer(pu)
    deals = await _deals(pu, cust)
    result = []
    for d in deals:
        inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": d["id"]}, {"_id": 0})
        receipts = await db.receipts.find({"org_id": org, "deal_id": d["id"]},
                                          {"_id": 0}).sort("created_at", -1).to_list(200)
        result.append({
            "deal_id": d["id"], "unit_code": inv.get("unit_code") if inv else None,
            "summary": _payment_summary(inv),
            "schedule": (inv or {}).get("items", []),
            "receipts": receipts,
        })
    return {"data": serialize_doc(result)}


# ----------------------------- Fase 47B: setor bukti transfer -----------------------------
PROOF_TYPES = ("image/jpeg", "image/png", "image/webp", "image/heic", "application/pdf")
PROOF_MAX_BYTES = 8 * 1024 * 1024


@router.post("/payments/proof/upload")
async def upload_payment_proof(file: UploadFile = File(...), deal_id: str = Form(...),
                               pu: dict = Depends(get_portal_user)):
    """Unggah FOTO/PDF bukti transfer dari portal — satu-satunya jalan pelanggan melampirkan bukti.

    Kenapa endpoint sendiri: `/api/files/upload` menuntut izin STAF (`files:create`), sehingga
    sebelum ini `POST /portal/payments/proof` mustahil dipenuhi pelanggan (bukti wajib minimal
    satu berkas, tetapi tidak ada cara mengunggahnya) — fitur yang tidak bisa dicapai sama
    dengan tidak ada. Pembatasan di sini sengaja lebih ketat daripada unggahan staf: hanya
    gambar/PDF, maksimal 8 MB, dan wajib menyebut transaksi MILIK pelanggan itu sendiri.
    """
    org = pu.get("org_id", ORG_ID)
    cust = await _customer(pu)
    deals = await _deals(pu, cust)
    if not any(d["id"] == deal_id for d in deals):
        raise HTTPException(status_code=404,
                            detail="Transaksi tidak ditemukan pada akun Anda.")
    data = await file.read()
    ctype = (file.content_type or "").lower()
    if ctype not in PROOF_TYPES:
        raise HTTPException(status_code=400, detail=(
            "Bukti transfer harus berupa foto (JPG/PNG/WEBP/HEIC) atau PDF — "
            f"berkas Anda bertipe {ctype or 'tidak dikenali'}."))
    if len(data) > PROOF_MAX_BYTES:
        raise HTTPException(status_code=400, detail=(
            f"Ukuran berkas {len(data) // 1024 // 1024} MB melebihi batas 8 MB — "
            "kirim foto yang lebih kecil atau potret ulang struknya."))
    try:
        rec = await storage.save_file(
            data=data, filename=file.filename or "bukti-transfer.jpg",
            content_type=ctype or "application/octet-stream", org_id=org,
            owner_type="payment_proof", owner_id=deal_id,
            # Pengunggah adalah PELANGGAN, bukan pengguna sistem: jangan tulis alamat email
            # yang tidak ada di daftar pengguna (jejak audit yang tidak bisa ditelusuri).
            uploaded_by="portal", doc_type="bukti_transfer", tag="payment_proof",
            optimize=ctype.startswith("image/"), watermark_lines=None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.files.update_one({"id": rec["id"]},
                              {"$set": {"portal_customer_id": cust.get("id")}})
    return {"data": {"id": rec["id"], "filename": rec.get("original_filename"),
                     "content_type": rec.get("content_type"), "size": rec.get("size")},
            "message": "Berkas terunggah. Lanjutkan dengan mengirim bukti transfernya."}


@router.post("/payments/proof")
async def submit_payment_proof(payload: PaymentProofIn,
                              pu: dict = Depends(get_portal_user)):
    """Pelanggan mengirim bukti transfer.

    Yang PENTING: ini KLAIM, bukan pelunasan. Tagihan tidak berubah sedikit pun sampai
    finance memverifikasi (uji negatif di gate). Dengan begitu portal berhenti menjadi
    ruang tafsir ("saya sudah transfer kok") tanpa mengorbankan kebenaran uang.
    """
    org = pu.get("org_id", ORG_ID)
    cust = await _customer(pu)
    deals = await _deals(pu, cust)
    deal = next((d for d in deals if d["id"] == payload.deal_id), None)
    if not deal:
        raise HTTPException(status_code=404,
                            detail="Transaksi tidak ditemukan pada akun Anda.")
    owned = await db.files.count_documents(
        {"org_id": org, "id": {"$in": payload.file_ids}, "owner_type": "payment_proof",
         "portal_customer_id": cust.get("id"), "is_deleted": False})
    if owned != len(payload.file_ids):
        raise HTTPException(status_code=400, detail=(
            "Berkas bukti tidak lengkap atau bukan milik akun Anda — unggah ulang fotonya."))
    try:
        doc = await intake.create_from_portal(
            org, customer=cust, deal=deal, amount=payload.amount,
            transfer_date=payload.transfer_date, file_ids=payload.file_ids,
            bank_name=payload.bank_name, note=payload.note,
            actor=(pu.get("email") or pu.get("phone") or cust.get("name")))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(doc),
            "message": ("Bukti transfer terkirim. Status: menunggu verifikasi finance - "
                        "tagihan Anda akan berkurang setelah diverifikasi.")}


@router.get("/payments/submissions")
async def my_payment_submissions(pu: dict = Depends(get_portal_user)):
    """Riwayat bukti transfer + statusnya (termasuk ALASAN bila ditolak)."""
    out = await intake.listing(pu.get("org_id", ORG_ID), customer_id=pu.get("customer_id"),
                               limit=100)
    return {"data": serialize_doc(out["data"]), "total": out["total"],
            "summary": out["summary"]}


@router.get("/progress")
async def progress(pu: dict = Depends(get_portal_user)):
    org = pu.get("org_id", ORG_ID)
    cust = await _customer(pu)
    deals = await _deals(pu, cust)
    result = []
    for d in deals:
        unit = await db.units.find_one({"id": d.get("unit_id")}, {"_id": 0}) or {}
        phases = await db.construction_phases.find(
            {"org_id": org, "project_id": d.get("project_id")}, {"_id": 0}).sort("order", 1).to_list(300)
        # Fase 28b — bukti visual: foto lapangan (punch berfoto pada unit ini + buku
        # harian proyek) dengan cakupan ditandai jujur agar pembeli tidak salah paham.
        photos = await p28.collect_unit_photos(org, d.get("project_id"), d.get("unit_id"), limit=6)
        # Bukti kerja berpasangan: pembeli melihat foto SEBELUM & SESUDAH tiap temuan
        # pada unitnya, bukan tumpukan foto tanpa konteks.
        repairs = await p28.collect_repair_pairs(org, d.get("unit_id"), limit=5)
        # Fase 31: progres RUMAH pembeli berasal dari jadwal pembangunan unitnya sendiri.
        # `phases` di bawah adalah pekerjaan KAWASAN (jalan/drainase), dilabeli jujur di UI.
        build = await bm.buyer_milestones(org, d.get("unit_id")) if d.get("unit_id") else None
        result.append({
            "deal_id": d["id"], "unit_code": unit.get("code"),
            "construction_progress": unit.get("construction_progress", 0),
            "construction_status": unit.get("construction_status"),
            "construction_status_label": ref.label_of("construction_status",
                                                      unit.get("construction_status")),
            "build": build,
            "phases": [{"name": p.get("name"), "weight": p.get("weight"),
                        "progress": p.get("progress", 0), "status": p.get("status")} for p in phases],
            "curve": build_s_curve(phases),
            "photos": photos,
            "repairs": repairs,
        })
    return {"data": serialize_doc(result)}


# ------------------- Peta kavling pembeli (Fase 28b) -------------------
async def _portal_projects(pu: dict, deals: list) -> list:
    return sorted({d.get("project_id") for d in deals if d.get("project_id")})


@router.get("/site-plan")
async def portal_site_plan(pu: dict = Depends(get_portal_user)):
    """Peta site plan untuk pembeli: kavling MILIKNYA disorot, kavling lain anonim.

    Privasi tetangga dijaga: yang keluar hanya kode + status kavling lain (tanpa harga,
    tanpa nama pembeli, tanpa nilai transaksi). Data harga hanya untuk kavling sendiri.
    """
    org = pu.get("org_id", ORG_ID)
    cust = await _customer(pu)
    deals = await _deals(pu, cust)
    pids = await _portal_projects(pu, deals)
    if not pids:
        return {"data": {"projects": []}}
    own_units = {d.get("unit_id") for d in deals if d.get("unit_id")}
    out = []
    for pid in pids:
        proj = await db.projects.find_one({"id": pid, "org_id": org},
                                          {"_id": 0, "name": 1, "location": 1}) or {}
        plan = await db.site_plans.find_one({"org_id": org, "project_id": pid},
                                            {"_id": 0, "view_box": 1, "shapes": 1})
        rows = await db.units.find({"org_id": org, "project_id": pid},
                                   {"_id": 0, "id": 1, "code": 1, "block": 1, "type": 1,
                                    "status": 1, "price": 1, "luas_bangunan": 1,
                                    "luas_tanah": 1, "orientation": 1, "corner": 1,
                                    "construction_progress": 1}).sort("code", 1).to_list(2000)
        units = []
        for u in rows:
            mine = u["id"] in own_units
            lb, lt = p28.parse_luas(u)
            units.append({
                "id": u["id"], "code": u.get("code"), "block": p28.block_of(u),
                "status": u.get("status", "available"), "mine": mine,
                "type": u.get("type") if mine else None,
                "price": int(u.get("price") or 0) if mine else None,
                "luas_bangunan": lb if mine else None, "luas_tanah": lt if mine else None,
                "orientation": u.get("orientation") if mine else None,
                "corner": bool(u.get("corner")) if mine else None,
                "construction_progress": u.get("construction_progress", 0) if mine else None,
            })
        out.append({"project_id": pid, "project_name": proj.get("name"),
                    "location": proj.get("location"), "plan": serialize_doc(plan),
                    "units": units,
                    "my_codes": [u["code"] for u in units if u["mine"]]})
    return {"data": {"projects": out}}


@router.get("/files/{file_id}")
async def portal_file(file_id: str, request: Request, variant: str = Query(None)):
    """Unduh/tampilkan foto lapangan untuk pembeli (mendukung `?auth=` untuk <img>).

    Kepemilikan diverifikasi NYATA: berkas hanya boleh diakses bila benar-benar
    dirujuk oleh buku harian atau temuan punch pada proyek tempat pembeli punya deal.
    Fase 30b: `?variant=thumb` melayani versi kecil (hemat kuota pembeli di galeri).
    """
    pu = await get_portal_user(request)
    org = pu.get("org_id", ORG_ID)
    cust = await _customer(pu)
    deals = await _deals(pu, cust)
    pids = await _portal_projects(pu, deals)
    if not pids:
        raise HTTPException(403, "Tidak ada proyek terkait akun Anda.")
    q = {"org_id": org, "project_id": {"$in": pids},
         "$or": [{"photo": file_id}, {"photos": file_id}, {"fix_photos": file_id}]}
    allowed = (await db.site_diaries.count_documents(q)) or (await db.punch_items.count_documents(q))
    if not allowed:
        # Fase 47B: bukti transfer yang DIUNGGAH pelanggan itu sendiri juga harus bisa
        # dilihat kembali olehnya (tanpa ini, riwayat bukti hanya berisi nama berkas).
        allowed = await db.files.count_documents(
            {"org_id": org, "id": file_id, "owner_type": "payment_proof",
             "portal_customer_id": cust.get("id"), "is_deleted": False})
    if not allowed:
        raise HTTPException(404, "Foto tidak ditemukan.")
    rec = await db.files.find_one({"id": file_id, "org_id": org, "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Foto tidak ditemukan.")
    path, want_type = await storage.variant_source(rec, variant)
    try:
        data, ctype = await storage.get_file_bytes(path, rec.get("provider"))
    except FileNotFoundError:
        raise HTTPException(404, "Objek foto tidak ada di storage.")
    return Response(content=data, media_type=want_type or ctype,
                    headers={"Cache-Control": "private, max-age=3600"})


@router.get("/documents")
async def documents(pu: dict = Depends(get_portal_user)):
    org = pu.get("org_id", ORG_ID)
    cust = await _customer(pu)
    deals = await _deals(pu, cust)
    ids = [d["id"] for d in deals]
    rows = []
    if ids:
        rows = await db.documents.find({"org_id": org, "deal_id": {"$in": ids}},
                                       {"_id": 0, "content": 0}).sort("created_at", -1).to_list(100)
    return {"data": serialize_doc(rows)}


@router.get("/cancellations")
async def cancellations(pu: dict = Depends(get_portal_user)):
    """Pembatalan & refund MILIK PEMBELI — dengan bahasa untuk pembeli, bukan untuk staf.

    Fase 56C. Hitungannya TIDAK disusun ulang di sini: ia dibaca dari mesin pembatalan
    (`cancellation_engine.portal_rows`) supaya pembeli dan staf tidak pernah membaca dua
    versi angka yang berbeda.
    """
    cust = await _customer(pu)
    deals = await _deals(pu, cust)
    out = await cx.portal_rows(pu.get("org_id", ORG_ID), [d["id"] for d in deals])
    return {"data": serialize_doc(out["data"]), "reason": out["reason"]}


@router.get("/documents/{doc_id}/pdf")
async def document_pdf(doc_id: str, request: Request):
    pu = await get_portal_user(request)
    org = pu.get("org_id", ORG_ID)
    cust = await _customer(pu)
    deals = await _deals(pu, cust)
    ids = [d["id"] for d in deals]
    doc = await db.documents.find_one({"id": doc_id, "org_id": org}, {"_id": 0})
    if not doc or doc.get("deal_id") not in ids:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    pdf = build_document_pdf(title=doc.get("title", "Dokumen"), doc_number=doc.get("doc_number"),
                             content=doc.get("content", ""), signatures=doc.get("signatures"),
                             org_name=ORG_NAME)
    filename = f"{(doc.get('doc_number') or 'dokumen').replace('/', '-')}.pdf"
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{filename}"'})


# ----------------------------- reference (SSOT untuk portal) -----------------------------
@router.get("/reference")
async def portal_reference(_pu: dict = Depends(get_portal_user)):
    """Subset kamus data untuk portal pembeli (Fase 26).

    Portal memakai token sendiri sehingga tidak bisa mengakses `/api/reference` milik staf;
    dulu akibatnya daftar kategori komplain di-hardcode di frontend portal dan nilainya
    menyimpang dari SSOT (mis. \"umum\" vs kanonik \"lainnya\").
    """
    allowed = ("complaint_category", "complaint_status", "priority",
               # Fase 50A: portal pembeli menampilkan masa garansi & status klaim; labelnya
               # WAJIB dari kamus data yang sama dengan layar staf, kalau tidak pembeli dan
               # staf membaca dua versi kata untuk keadaan yang sama.
               "warranty_category", "warranty_state", "warranty_claim_state",
               "warranty_claim_source", "warranty_reject_reason")
    reg = ref.public_registry()
    return {"data": {k: reg[k] for k in allowed if k in reg}}


# ----------------------------- complaints -----------------------------
@router.get("/complaints")
async def list_complaints(pu: dict = Depends(get_portal_user)):
    org = pu.get("org_id", ORG_ID)
    rows = await db.complaints.find({"org_id": org, "customer_id": pu.get("customer_id")},
                                    {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"data": serialize_doc(rows)}


@router.post("/complaints")
async def create_complaint(payload: ComplaintCreate, pu: dict = Depends(get_portal_user)):
    org = pu.get("org_id", ORG_ID)
    cust = await _customer(pu)
    deals = await _deals(pu, cust)
    deal = next((d for d in deals if d["id"] == payload.deal_id), deals[0] if deals else None)
    unit_code, unit_id = None, None
    if deal:
        unit = await db.units.find_one({"id": deal.get("unit_id")}, {"_id": 0}) or {}
        unit_code = unit.get("code")
        # Fase 50A: komplain dulu hanya menyimpan KODE unit, bukan id-nya. Akibatnya tidak
        # ada satu pun jalan otomatis dari keluhan pembeli ke rumahnya (dan ke masa
        # garansinya) — CS harus mencari sendiri kavlingnya. Sekarang id-nya ikut disimpan.
        unit_id = unit.get("id") or deal.get("unit_id")
    ts = now_iso()
    cid = new_id()
    sla = due_in(hours=48)
    doc = {
        "id": cid, "org_id": org, "customer_id": pu.get("customer_id"),
        "customer_name": pu.get("name"), "deal_id": deal["id"] if deal else None,
        "unit_code": unit_code, "unit_id": unit_id,
        "category": payload.category or "umum",
        "subject": payload.subject, "message": payload.message,
        "status": "open", "priority": payload.priority or "medium",
        "assigned_to": (deal or {}).get("assigned_to"),
        "sla_due_at": sla, "responses": [], "created_at": ts, "updated_at": ts,
    }
    await db.complaints.insert_one(dict(doc))
    # SLA task for the responsible sales/CS + notification.
    assignee = doc.get("assigned_to")
    await auto_create_task(
        source_event=f"complaint:{cid}", title=f"Komplain pembeli: {payload.subject}",
        jobdesk_code="SM-09",
        type="complaint", related_entity_type="complaint", related_entity_id=cid,
        assigned_to=assignee, sla_due_at=sla, priority=doc["priority"],
        description=f"{pu.get('name')} ({unit_code or '-'}): {payload.message}", org_id=org)
    if assignee:
        await create_notification(user_email=assignee, title="Komplain pembeli baru",
                                  body=f"{pu.get('name')}: {payload.subject}", type="complaint", org_id=org)
    await send_whatsapp(pu.get("phone"),
                        f"Terima kasih. Komplain Anda '{payload.subject}' telah kami terima dan akan ditindaklanjuti (SLA 2x24 jam).")
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}

# ----------------------------- garansi & klaim (Fase 50A) -----------------------------
async def _my_units(pu: dict) -> list:
    """Rumah milik pembeli ini (dari deal-nya) — dipakai layar garansi portal."""
    cust = await _customer(pu)
    deals = await _deals(pu, cust)
    out = []
    for d in deals:
        if not d.get("unit_id"):
            continue
        unit = await db.units.find_one({"id": d["unit_id"], "org_id": pu.get("org_id", ORG_ID)},
                                       {"_id": 0, "id": 1, "code": 1, "type": 1,
                                        "project_id": 1, "status": 1})
        if unit:
            out.append({**unit, "deal_id": d["id"]})
    return out


@router.get("/warranty")
async def portal_warranty(pu: dict = Depends(get_portal_user)):
    """Masa garansi rumah saya + riwayat klaim.

    Kenapa ada di portal: pembeli adalah orang yang PALING butuh tahu "bagian ini masih
    garansi sampai kapan". Sebelum Fase 50 jawabannya hanya ada di kepala staf, jadi setiap
    keluhan berubah menjadi perdebatan tanpa dasar.
    """
    org = pu.get("org_id", ORG_ID)
    units = await _my_units(pu)
    rows = []
    for u in units:
        st_ = await he.warranty_status(org, u["id"])
        rows.append({"unit": {"id": u["id"], "code": u.get("code"), "type": u.get("type")},
                     "handover": st_.get("handover"), "warranty": st_.get("rows"),
                     "claims": st_.get("claims"), "missing": st_.get("missing"),
                     "detail": st_.get("detail")})
    return {"data": serialize_doc(rows), "total": len(rows),
            "detail": ("Belum ada rumah yang terdaftar atas nama Anda — belum ada data."
                       if not rows else
                       f"{len(rows)} rumah; masa garansi dihitung dari tanggal serah terima.")}


@router.post("/warranty/claims")
async def portal_create_claim(payload: PortalWarrantyClaim,
                              pu: dict = Depends(get_portal_user)):
    """Ajukan klaim garansi langsung dari portal pembeli.

    Klaim yang masa garansinya sudah lewat TIDAK dibuang diam-diam: klaimnya tetap
    tercatat berstatus DITOLAK beserta tanggal habisnya, supaya pembeli punya jawaban
    tertulis yang bisa diperiksa ulang.
    """
    org = pu.get("org_id", ORG_ID)
    units = {u["id"] for u in await _my_units(pu)}
    if payload.unit_id not in units:
        raise HTTPException(status_code=403,
                            detail="Rumah ini tidak terdaftar atas nama Anda.")
    try:
        doc = await we.create_claim(
            org, unit_id=payload.unit_id, category=payload.category, title=payload.title,
            description=payload.description, source="portal_pembeli",
            photo_file_ids=payload.photo_file_ids, actor=pu.get("phone") or pu.get("name"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await send_whatsapp(pu.get("phone"),
                        (f"Klaim garansi {doc['number']} kami terima: {doc['title']}."
                         if doc["state"] != "ditolak" else
                         f"Klaim garansi {doc['number']} tidak dapat kami proses: "
                         f"{doc.get('reject_detail')}"))
    return {"data": serialize_doc(doc),
            "message": (f"Klaim {doc['number']} diterima dan akan ditindaklanjuti tim proyek."
                        if doc["state"] != "ditolak" else
                        f"Klaim {doc['number']} tercatat namun DITOLAK: {doc.get('reject_detail')}")}


@router.get("/warranty/claims")
async def portal_claims(pu: dict = Depends(get_portal_user)):
    org = pu.get("org_id", ORG_ID)
    out = await we.list_claims(org, customer_id=pu.get("customer_id"))
    return {"data": serialize_doc(out["rows"]), "total": out["total"],
            "detail": out["detail"]}


# ============================ Fase 51C — dokumen & pengakuan milik pembeli ============
# Tiga hal yang paling sering diminta manusia justru belum ada sampai Fase 50:
#   1. salinan BAST-nya sendiri (hanya bisa diunduh staf),
#   2. kwitansi pembayarannya (tidak bisa diunduh siapa pun),
#   3. cara MENGAKUI bahwa perbaikan garansi selesai — padahal mesin MEWAJIBKAN pengakuan
#      pembeli untuk menutup klaim, jadi selama ini stafnya yang mengetik atas nama pembeli.
async def _my_handovers(pu: dict) -> list:
    org = pu.get("org_id", ORG_ID)
    unit_ids = [u["id"] for u in await _my_units(pu)]
    q = {"org_id": org, "$or": [{"customer_id": pu.get("customer_id")}]}
    if unit_ids:
        q["$or"].append({"unit_id": {"$in": unit_ids}})
    return await db.unit_handovers.find(q, {"_id": 0}).sort("handed_over_at", -1).to_list(50)


@router.get("/handovers")
async def portal_handovers(pu: dict = Depends(get_portal_user)):
    """Berita acara serah terima milik pembeli ini (bisa diunduh sebagai PDF)."""
    rows = await _my_handovers(pu)
    return {"data": serialize_doc(rows), "total": len(rows),
            "detail": ("Belum ada berita acara serah terima atas nama Anda — rumah belum "
                       "diserahterimakan, jadi memang belum ada dokumennya."
                       if not rows else
                       f"{len(rows)} berita acara serah terima. Simpan salinannya: dokumen "
                       "ini dasar penghitungan masa garansi rumah Anda.")}


@router.get("/handovers/{hid}/pdf")
async def portal_handover_pdf(hid: str, pu: dict = Depends(get_portal_user)):
    mine = {h["id"] for h in await _my_handovers(pu)}
    if hid not in mine:
        # Sengaja 404 (bukan 403): membedakan "ada tapi bukan milikmu" dari "tidak ada"
        # membocorkan keberadaan dokumen orang lain.
        raise HTTPException(status_code=404,
                            detail="Berita acara serah terima tidak ditemukan atas nama Anda.")
    try:
        blob, doc = await he.pdf_bytes(pu.get("org_id", ORG_ID), hid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    name = (doc.get("number") or "BAST").replace("/", "-")
    return Response(content=blob, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


async def _my_receipts(pu: dict) -> list:
    org = pu.get("org_id", ORG_ID)
    cust = await _customer(pu)
    deal_ids = [d["id"] for d in await _deals(pu, cust)]
    if not deal_ids:
        return []
    return await db.receipts.find({"org_id": org, "deal_id": {"$in": deal_ids}},
                                  {"_id": 0}).sort("created_at", -1).to_list(200)


@router.get("/receipts")
async def portal_receipts(pu: dict = Depends(get_portal_user)):
    """Kwitansi penerimaan pembayaran milik pembeli ini."""
    rows = await _my_receipts(pu)
    total = sum(int(r.get("amount") or 0) for r in rows)
    return {"data": serialize_doc(rows), "total": len(rows), "total_amount": total,
            "detail": ("Belum ada pembayaran yang tercatat atas nama Anda — belum ada data, "
                       "bukan Rp 0." if not rows else
                       f"{len(rows)} kwitansi, total Rp {total:,}".replace(",", "."))}


@router.get("/receipts/{rid}/pdf")
async def portal_receipt_pdf(rid: str, pu: dict = Depends(get_portal_user)):
    rows = {r["id"]: r for r in await _my_receipts(pu)}
    doc = rows.get(rid)
    if not doc:
        raise HTTPException(status_code=404, detail="Kwitansi tidak ditemukan atas nama Anda.")
    cust = await _customer(pu)
    alokasi = "; ".join(f"{a.get('label')}: Rp {int(a.get('amount') or 0):,}".replace(",", ".")
                        for a in (doc.get("allocations") or [])) or "-"
    isi = "\n".join([
        f"Nomor kwitansi : {doc.get('receipt_no') or doc.get('id')}",
        f"Tanggal : {str(doc.get('created_at'))[:10]}",
        f"Diterima dari : {cust.get('name') or '-'}",
        f"Unit : {doc.get('unit_code') or '-'}",
        f"Jumlah : Rp {int(doc.get('amount') or 0):,}".replace(",", "."),
        f"Cara bayar : {ref.label_of('payment_method', doc.get('method')) or doc.get('method') or '-'}",
        f"Dialokasikan ke : {alokasi}",
        f"Catatan : {doc.get('note') or '-'}",
        "",
        "Kwitansi ini sah sebagai bukti penerimaan pembayaran dan dicetak dari sistem.",
    ])
    pdf = build_document_pdf(title="Kwitansi Penerimaan Pembayaran",
                             doc_number=doc.get("receipt_no") or doc.get("id"),
                             content=isi, signatures=None, org_name=ORG_NAME)
    name = str(doc.get("receipt_no") or "kwitansi").replace("/", "-")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


async def _my_claim(pu: dict, cid: str) -> dict:
    org = pu.get("org_id", ORG_ID)
    doc = await db.warranty_claims.find_one({"id": cid, "org_id": org}, {"_id": 0})
    unit_ids = {u["id"] for u in await _my_units(pu)}
    if not doc or (doc.get("customer_id") != pu.get("customer_id")
                   and doc.get("unit_id") not in unit_ids):
        raise HTTPException(status_code=404,
                            detail="Klaim garansi tidak ditemukan atas nama Anda.")
    return doc


@router.get("/warranty/claims/{cid}")
async def portal_claim_detail(cid: str, pu: dict = Depends(get_portal_user)):
    doc = await _my_claim(pu, cid)
    return {"data": serialize_doc(doc)}


@router.post("/warranty/claims/{cid}/ack")
async def portal_claim_ack(cid: str, payload: PortalClaimAckIn,
                           pu: dict = Depends(get_portal_user)):
    """Pembeli MENGAKUI perbaikan garansi selesai — klaim baru bisa ditutup setelah ini.

    Pengakuan tercatat atas nama pembeli (nama + nomor dari sesi portalnya), bukan atas nama
    staf. Bila perbaikannya belum diperiksa mutu (`diverifikasi`), pengakuan ditolak dengan
    alasan jujur: menutup klaim yang belum diperiksa berarti menghapus jejak masalah yang
    mungkin masih ada.
    """
    org = pu.get("org_id", ORG_ID)
    doc = await _my_claim(pu, cid)
    aktor = f"{pu.get('name') or 'Pembeli'} ({pu.get('phone') or pu.get('email') or '-'})"
    if not payload.satisfied:
        # Pembeli menyatakan BELUM beres: klaim dikembalikan ke pengerjaan, bukan ditutup.
        await db.warranty_claims.update_one({"id": cid, "org_id": org}, {"$set": {
            "state": "dikerjakan", "state_label": ref.label_of("warranty_claim_state",
                                                               "dikerjakan"),
            "ack_note": (payload.note or "").strip() or None,
            "ack_rejected_by": aktor, "updated_at": now_iso()}})
        await create_notification(
            user_email=doc.get("assigned_to"), title="Pembeli menyatakan perbaikan BELUM beres",
            body=(f"Klaim {doc.get('number')} — {doc.get('title')}: "
                  f"{(payload.note or 'tanpa catatan')}"),
            type="warranty", related_entity_type="warranty_claim", related_entity_id=cid,
            org_id=org)
        fresh = await db.warranty_claims.find_one({"id": cid, "org_id": org}, {"_id": 0})
        return {"data": serialize_doc(fresh),
                "message": ("Terima kasih. Kami catat perbaikan BELUM selesai dan tim akan "
                            "menindaklanjuti — klaim tidak ditutup.")}
    try:
        fresh = await we.close(org, cid, actor=aktor, ack_by=aktor, ack_note=payload.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await create_notification(
        user_email=doc.get("assigned_to"), title="Pembeli mengakui perbaikan garansi selesai",
        body=f"Klaim {doc.get('number')} ditutup setelah pengakuan pembeli.",
        type="warranty", related_entity_type="warranty_claim", related_entity_id=cid,
        org_id=org)
    return {"data": serialize_doc(fresh),
            "message": (f"Terima kasih. Klaim {doc.get('number')} kami tutup atas pengakuan "
                        "Anda; riwayatnya tetap tersimpan.")}
