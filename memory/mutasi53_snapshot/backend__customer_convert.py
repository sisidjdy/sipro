"""KONVERSI LEAD → PEMBELI (Fase 53B).

## Cacat NYATA yang ditutup berkas ini

Pemilik produk melaporkan: *"saya masih belum menemukan bagaimana lead bisa menjadi
customer"*. Pembacaan kode membenarkannya sepenuhnya — sebelum berkas ini, `db.customers`
hanya ditulis oleh dua tempat:

  1. `POST /api/customers` (form manual di layar Pembeli, dan formnya bahkan TIDAK punya
     kolom lead, walau `CustomerCreate` di model punya `lead_id`);
  2. `seed*.py` (data demo).

Sementara itu `build_engine._buyer_binding()` mencari pembeli dengan
`customers.lead_id == deal.lead_id`. Tautan itu tidak pernah dibuat untuk data nyata, jadi:
profil pembeli kosong, portal pembeli tidak menemukan pemiliknya, KPR tidak punya
`customer_id`, rencana bayar tidak punya pemilik, dan BAST tidak tahu siapa yang menerima
kunci. Semua "tersambung" hanya pada data seed — itulah sebabnya alurnya terasa ada padahal
tidak pernah dijalankan sistem.

## Aturan konversi (Dok 26 §2)

1. **Idempoten.** Dijalankan dua kali = hasil sama, tanpa pembeli/kontrak kembar. Kunci:
   `deals.contract_id` + `customers.lead_id`.
2. **Dedup pembeli** berdasarkan NIK, lalu telepon — satu manusia satu baris pembeli, walau
   ia membeli unit kedua.
3. **Bukti dulu, status kemudian.** Konversi hanya boleh setelah reservasi DIKONFIRMASI
   (booking) — atau setelah SPR ditandatangani, sesuai `[CFG] lead.won_trigger`. Sebab
   penolakan memakai kode SSOT (`convert_block`) supaya layar menyebut sebab yang sama.
4. **Dokumen tidak diminta dua kali.** Berkas yang sudah `verified` di lead diwarisi pembeli
   (baris baru menunjuk `file_id` yang SAMA, dengan jejak `inherited_from`).
5. **Tahap lead menjadi `won`** — akhir domain lead (Dok 26 §1), bukan status karangan.
"""
import logging

from pymongo.errors import DuplicateKeyError

import contracts_engine as ce
import kpr_engine as kprmod
import lead_lifecycle as lc
import reference as ref
import settings_store as cfg
from core_utils import due_in, new_id, now_iso
from db import db
from engine import add_activity, auto_create_task, emit

logger = logging.getLogger("sipro.convert")

CONVERT_TRIGGERS = ("booking_fee_verified", "spr_signed", "ppjb_signed", "ajb_signed")
SPR_CODES = ("SPR", "SPR_CASH", "SPR_CASH_STAGED", "SPR_KPR")


def _blk(code: str, detail: str) -> dict:
    return {"code": code, "label": ref.label_of("convert_block", code), "detail": detail}


async def _signed_spr(org: str, deal_id: str) -> dict:
    return await db.documents.find_one(
        {"org_id": org, "deal_id": deal_id, "template_code": {"$in": list(SPR_CODES)},
         "status": "signed"}, {"_id": 0, "doc_number": 1, "template_code": 1})


async def suggested_scheme(org: str, deal: dict) -> str:
    """Skema yang DIUSULKAN (bukan dipaksakan): KPR bila sudah ada pengajuan KPR.

    Sengaja tidak menebak lebih jauh dari itu. Skema pembayaran menentukan isi dokumen
    legal — kalau sistem menebak salah, dokumen yang tercetak ikut salah. Karena itu layar
    WAJIB meminta manusia memilih, dan usulan ini hanya nilai awal.
    """
    app = await db.financing_apps.find_one({"org_id": org, "deal_id": deal["id"]},
                                          {"_id": 0, "id": 1})
    if app:
        return "kpr"
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": deal["id"]},
                                       {"_id": 0, "items": 1})
    if inv and len(inv.get("items") or []) > 2:
        return "cash_bertahap"
    return "cash_keras"


async def preview(org: str, deal_id: str) -> dict:
    """Apa yang akan terjadi bila dikonversi — atau sebab kenapa belum boleh."""
    deal = await db.deals.find_one({"id": deal_id, "org_id": org}, {"_id": 0})
    if not deal:
        raise ValueError("Deal tidak ditemukan.")
    lead = await db.leads.find_one({"id": deal.get("lead_id")}, {"_id": 0}) or {}
    unit = await db.units.find_one({"id": deal.get("unit_id")},
                                  {"_id": 0, "code": 1, "type": 1, "price": 1}) or {}
    contract = await db.contracts.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})
    existing = None
    if lead.get("id"):
        existing = await db.customers.find_one({"org_id": org, "lead_id": lead["id"]},
                                              {"_id": 0, "id": 1, "name": 1, "nik": 1})
    if not existing:
        existing = await _dedup_customer(org, lead)
    trigger = str(await cfg.get("lead.won_trigger", org_id=org) or "spr_signed")
    spr = await _signed_spr(org, deal_id)
    blocks = []
    if deal.get("status") in ("cancelled", "expired"):
        blocks.append(_blk("deal_batal", "Reservasi unit ini sudah dibatalkan/kedaluwarsa."))
    elif deal.get("status") == "reserved":
        blocks.append(_blk("deal_belum_booking",
                           "Reservasi belum dikonfirmasi. Konfirmasi booking fee lebih "
                           "dahulu (tombol 'Konfirmasi Booking' pada kartu unit)."))
    if not (lead.get("name") or "").strip() or not (lead.get("phone") or "").strip():
        blocks.append(_blk("data_diri_kosong",
                           "Nama dan nomor telepon pembeli wajib ada sebelum kontrak dibuat."))
    if contract:
        blocks.append(_blk("sudah_pembeli",
                           f"Deal ini sudah punya kontrak {contract.get('number')}."))
    # Pemicu `spr_signed` TIDAK dijadikan penahan keras: ia hanya peringatan, karena banyak
    # developer menandatangani SPR di atas kertas lebih dahulu lalu mengunggah scannya.
    catatan = None
    if trigger == "spr_signed" and not spr:
        catatan = ("Kebijakan Anda (Pusat Konfigurasi → lead.won_trigger) menyebut pembeli "
                   "lahir saat SPR DITANDATANGANI. Belum ada SPR bertanda tangan untuk deal "
                   "ini — konversi tetap bisa dilakukan, tetapi terbitkan & tanda tangani "
                   "SPR-nya agar jejaknya lengkap.")
    return {
        "can_convert": not blocks,
        "blocks": blocks,
        "note": catatan,
        "trigger": trigger,
        "trigger_label": ref.label_of("lead_stage", "won"),
        "signed_spr": spr,
        "deal": {"id": deal["id"], "status": deal.get("status"),
                 "unit_code": unit.get("code"), "unit_type": unit.get("type"),
                 "price": deal.get("price"), "booking_fee": deal.get("booking_fee"),
                 "quotation_no": deal.get("quotation_no")},
        "lead": {"id": lead.get("id"), "name": lead.get("name"), "phone": lead.get("phone"),
                 "email": lead.get("email"), "stage": lead.get("stage")},
        "existing_customer": existing,
        "contract": contract,
        "suggested_scheme": await suggested_scheme(org, deal),
        "schemes": [{"value": s, "label": ref.label_of("payment_scheme", s)}
                    for s in ce.SCHEMES],
    }


async def _dedup_customer(org: str, lead: dict, nik: str = None) -> dict:
    """Satu manusia = satu baris pembeli. NIK lebih kuat daripada telepon.

    `nik` = NIK yang DIKETIK saat konversi. Cacat nyata yang ditutup parameter ini: dulu
    dedup hanya membaca NIK dari dokumen LEAD, sehingga NIK yang baru diketik di dialog
    konversi tidak pernah dibandingkan — dan karena `customers` punya index unik
    (`uq_customers_nik`), permintaannya mati dengan **HTTP 500 DuplicateKeyError** alih-alih
    menautkan pembeli yang sudah ada (kasus wajar: pembeli lama membeli unit kedua).
    """
    for kandidat in ((nik or "").strip(), (lead.get("nik") or "").strip()):
        if kandidat:
            c = await db.customers.find_one({"org_id": org, "nik": kandidat}, {"_id": 0})
            if c:
                return c
    phone = (lead.get("phone") or "").strip()
    if phone:
        return await db.customers.find_one({"org_id": org, "phone": phone}, {"_id": 0})
    return None


async def _inherit_documents(org: str, lead_id: str, customer_id: str, actor: str) -> int:
    """Berkas yang sudah DIVERIFIKASI di lead tidak diminta ulang ke pembeli (Dok 26 §2.6)."""
    rows = await db.doc_submissions.find(
        {"org_id": org, "entity_type": "lead", "entity_id": lead_id, "status": "verified"},
        {"_id": 0}).to_list(200)
    n = 0
    for r in rows:
        already = await db.doc_submissions.find_one(
            {"org_id": org, "entity_type": "customer", "entity_id": customer_id,
             "requirement_code": r.get("requirement_code"), "file_id": r.get("file_id")},
            {"_id": 0, "id": 1})
        if already:
            continue
        ts = now_iso()
        await db.doc_submissions.insert_one({
            **{k: v for k, v in r.items() if k not in ("id", "entity_type", "entity_id")},
            "id": new_id(), "entity_type": "customer", "entity_id": customer_id,
            "inherited_from": r["id"], "inherited_at": ts, "inherited_by": actor,
            "note": ((r.get("note") or "") + " · diwarisi dari berkas lead").strip(),
            "updated_at": ts,
        })
        n += 1
    return n


async def convert(org: str, deal_id: str, actor: str, payload: dict = None) -> dict:
    """Jadikan lead pembeli: pembeli + kontrak + (KPR) + warisan dokumen + tugas. Idempoten."""
    payload = payload or {}
    pre = await preview(org, deal_id)
    deal = await db.deals.find_one({"id": deal_id, "org_id": org}, {"_id": 0})
    lead = await db.leads.find_one({"id": deal.get("lead_id")}, {"_id": 0}) or {}

    # --- idempoten: kontrak sudah ada -> kembalikan apa adanya, jangan membuat kembar
    existing_contract = await db.contracts.find_one({"org_id": org, "deal_id": deal_id},
                                                    {"_id": 0})
    if existing_contract:
        cust = await db.customers.find_one({"id": existing_contract["customer_id"]},
                                          {"_id": 0})
        return {"created": False, "customer": cust, "contract": existing_contract,
                "inherited_documents": 0,
                "note": "Deal ini sudah menjadi pembeli — tidak ada yang dibuat ulang."}

    blocks = [b for b in pre["blocks"] if b["code"] != "sudah_pembeli"]
    if blocks:
        raise ValueError("Belum bisa dijadikan pembeli. "
                         + " ".join(b["detail"] for b in blocks))

    scheme = (payload.get("scheme") or pre["suggested_scheme"])
    if scheme not in ce.SCHEMES:
        raise ValueError(f"Skema pembayaran '{scheme}' tidak dikenal.")
    ts = now_iso()

    # --- pembeli: tautkan yang sudah ada, atau buat baru dari data lead + lengkapan form
    cust = await db.customers.find_one({"org_id": org, "lead_id": lead.get("id")}, {"_id": 0}) \
        or await _dedup_customer(org, lead, payload.get("nik"))
    diri = {k: payload.get(k) for k in ("nik", "npwp", "address", "occupation",
                                        "monthly_income", "spouse_name", "spouse_nik",
                                        "heir_name", "heir_relation")
            if payload.get(k) not in (None, "")}
    if cust:
        # Pembeli lama membeli unit kedua = SATU orang, DUA lead. `lead_id` pertama tidak
        # ditimpa (jejaknya tetap benar); lead berikutnya masuk `lead_ids[]`.
        setter = {"converted_at": cust.get("converted_at") or ts, "updated_at": ts, **diri}
        if not cust.get("lead_id"):
            setter["lead_id"] = lead.get("id")
        await db.customers.update_one(
            {"id": cust["id"]},
            {"$set": setter, "$addToSet": {"lead_ids": lead.get("id")}})
        cust = await db.customers.find_one({"id": cust["id"]}, {"_id": 0})
    else:
        cust = {
            "id": new_id(), "org_id": org, "name": lead.get("name"),
            "phone": lead.get("phone"), "email": lead.get("email"),
            "lead_id": lead.get("id"), "lead_ids": [lead.get("id")],
            "kyc_status": "pending", "kyc_files": [],
            "source": lead.get("source"), "assigned_to": deal.get("assigned_to"),
            "converted_at": ts, "converted_from_deal": deal_id,
            "created_by": actor, "created_at": ts, "updated_at": ts, **diri,
        }
        try:
            await db.customers.insert_one(dict(cust))
        except DuplicateKeyError:
            # Lomba dua permintaan (klik ganda / dua tab): baris pembeli sudah dibuat
            # permintaan lain. Tautkan yang ada — jangan mati dengan 500.
            cust = await _dedup_customer(org, lead, payload.get("nik"))
            if not cust:
                raise ValueError("Data pembeli bentrok dengan baris yang sudah ada "
                                 "(NIK/telepon). Periksa daftar Pembeli.")
            await db.customers.update_one({"id": cust["id"]}, {
                "$set": {"updated_at": ts, **diri},
                "$addToSet": {"lead_ids": lead.get("id")}})
            cust = await db.customers.find_one({"id": cust["id"]}, {"_id": 0})
        else:
            cust.pop("_id", None)

    # --- kontrak + skema AR + (bila KPR) pengajuan KPR
    contract = await ce.ensure_contract(org, deal, cust, scheme, actor)
    await ce.ensure_payment_scheme(org, scheme)
    if scheme == "kpr":
        await kprmod.ensure_kpr_app(org, contract, actor)

    # --- ikatan unit → deal → lead → pembeli (dipakai portal, laporan, jadwal bangun)
    try:
        import build_engine as be
        await be.sync_unit_binding(org, deal.get("unit_id"))
    except Exception:  # noqa: BLE001
        logger.exception("sync_unit_binding gagal saat konversi deal %s", deal_id)

    inherited = await _inherit_documents(org, lead.get("id"), cust["id"], actor)

    # --- tahap lead: `won` = akhir domain lead (Dok 26 §1)
    if lead and lead.get("stage") != "won":
        try:
            await lc.record(lead, "won", actor=actor, source="deal",
                            reason=f"Menjadi pembeli — kontrak {contract.get('number')}",
                            evidence={"deal_id": deal_id, "contract_id": contract["id"],
                                      "customer_id": cust["id"]})
        except Exception as e:  # noqa: BLE001 — gerbang tahap tidak boleh menggagalkan konversi
            logger.warning("Tahap lead tidak bisa dimajukan ke won: %s", e)

    # --- tugas administrasi (Dok 26 §2.7)
    if not (cust.get("nik") and cust.get("npwp")):
        await auto_create_task(
            source_event=f"customer.kyc:{cust['id']}", jobdesk_code="SM-07",
            title=f"Lengkapi berkas & KYC pembeli: {cust.get('name')}",
            type="todo", related_entity_type="customer", related_entity_id=cust["id"],
            assigned_to=deal.get("assigned_to"), due_date=due_in(days=3), priority="high",
            org_id=org)
    await auto_create_task(
        source_event=f"contract.costs:{contract['id']}",
        title=(f"Isi komponen biaya kontrak {contract.get('number')} "
               "(BPHTB, notaris" + (", biaya bank, asuransi" if scheme == "kpr" else "") + ")"),
        type="todo", related_entity_type="contract", related_entity_id=contract["id"],
        assigned_to=None, due_date=due_in(days=5), priority="medium", org_id=org)

    await add_activity(entity_type="lead", entity_id=lead.get("id"), type="system",
                       actor=actor, org_id=org,
                       body=(f"Lead menjadi PEMBELI: kontrak {contract.get('number')} "
                             f"unit {contract.get('unit_code')} · skema "
                             f"{ref.label_of('payment_scheme', scheme)}."))
    await add_activity(entity_type="customer", entity_id=cust["id"], type="system",
                       actor=actor, org_id=org,
                       body=(f"Pembeli dibuat dari lead {lead.get('name')} "
                             f"({inherited} berkas diwarisi dari lead)."))
    await emit("lead.converted", "customer", cust["id"],
               {"lead_id": lead.get("id"), "deal_id": deal_id,
                "contract_id": contract["id"], "scheme": scheme}, org_id=org)
    return {"created": True, "customer": cust, "contract": contract,
            "inherited_documents": inherited,
            "note": (f"{cust.get('name')} kini pembeli dengan kontrak "
                     f"{contract.get('number')}.")}


async def auto_convert_if_configured(org: str, deal_id: str, trigger: str,
                                     actor: str = "system") -> dict:
    """Dipanggil dari penangan peristiwa (booking / SPR ditandatangani).

    Konversi otomatis hanya jalan bila `[CFG] lead.won_trigger` MEMANG menyebut pemicu ini.
    Kalau tidak, tidak terjadi apa-apa — dan itu bukan kegagalan: pemilik produk yang
    menentukan kapan lead menjadi pembeli, bukan kode.
    """
    want = str(await cfg.get("lead.won_trigger", org_id=org) or "spr_signed")
    if want != trigger:
        return {"created": False, "skipped": True,
                "note": f"Pemicu konversi disetel '{want}', peristiwa ini '{trigger}'."}
    try:
        return await convert(org, deal_id, actor, {})
    except ValueError as e:
        logger.info("Konversi otomatis dilewati untuk deal %s: %s", deal_id, e)
        return {"created": False, "skipped": True, "note": str(e)}


async def customer_of_deal(org: str, deal_id: str) -> dict:
    c = await db.contracts.find_one({"org_id": org, "deal_id": deal_id},
                                    {"_id": 0, "customer_id": 1})
    if not c:
        return None
    return await db.customers.find_one({"id": c["customer_id"]}, {"_id": 0})
