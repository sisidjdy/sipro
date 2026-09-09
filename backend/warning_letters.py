"""SURAT PERINGATAN TUNGGAKAN SP1/SP2/SP3 (Fase 62).

## Cacat yang ditutup berkas ini

Fase 59 akhirnya menunjuk SIAPA yang menunggak (`arrears_engine`) dan Fase 58 menghitung
dendanya. Tetapi antara "daftar di layar" dan "pembatalan kontrak" tidak ada satu pun
dokumen resmi: penagih mengirim pesan WhatsApp seadanya, dan ketika pembatalan sepihak
benar-benar dipakai, developer tidak bisa menunjukkan bukti bahwa pembeli SUDAH diperingatkan.
Pengadilan dan pembeli sama-sama menanyakan surat itu.

## Aturan yang dipegang

1. **Tidak ada peringatan tanpa tunggakan.** Angka pada surat diambil dari mesin denda
   (`late_fee_engine.assess`) lewat `arrears_engine.months_in_arrears`, bukan diketik ulang.
   Termin yang lewat tanggal tetapi masih di dalam masa toleransi TIDAK boleh dijadikan
   dasar peringatan.
2. **Tingkat tidak boleh melompat.** SP2 hanya sah bila SP1 sudah terbit, SP3 hanya bila
   SP2 sudah terbit. Melompat ke SP3 berarti mencabut kesempatan pembeli memperbaiki —
   dan membuat pembatalan yang menyusulnya rapuh.
3. **SP3 tidak lahir sebelum batas kontrak.** SP3 menyebut hak pembatalan sepihak, jadi ia
   hanya boleh terbit bila tunggakan sudah mencapai batas yang tertulis di SPR
   (`payment.staged.arrears_months_to_cancel`).
4. **Surat MEMPERINGATKAN, tidak membatalkan.** Sama seperti Fase 59: pembatalan tetap
   diajukan Manajer Sales dan diputus Manajer Keuangan.
5. **Idempoten per (kontrak, tingkat, bulan).** Menekan tombol dua kali tidak melahirkan dua
   nomor surat; yang kedua mengembalikan surat yang sama.
"""
import logging

import arrears_engine as arr
import late_fee_engine as lf
import sequences as seq
import settings_store as cfg
from core_utils import new_id, now_iso
from db import ORG_ID, db

logger = logging.getLogger("sipro.warning_letters")

MAX_LEVEL = 3
# Tenggat perbaikan per tingkat: makin tinggi peringatan, makin pendek waktunya.
DEADLINE_DAYS = {1: 14, 2: 7, 3: 7}
LEVEL_LABEL = {1: "Surat Peringatan Pertama (SP1)",
               2: "Surat Peringatan Kedua (SP2)",
               3: "Surat Peringatan Ketiga & Terakhir (SP3)"}


def _rp(v) -> str:
    return "Rp " + f"{int(v or 0):,}".replace(",", ".")


def next_level(issued: list) -> int:
    """Tingkat yang BOLEH diterbitkan berikutnya (SP3 boleh diulang, SP1→SP3 tidak)."""
    tertinggi = max([int(x.get("level") or 0) for x in issued], default=0)
    return min(tertinggi + 1, MAX_LEVEL) if tertinggi < MAX_LEVEL else MAX_LEVEL


async def letters(org: str = ORG_ID, *, deal_id: str = None) -> list:
    q = {"org_id": org}
    if deal_id:
        q["deal_id"] = deal_id
    return await db.warning_letters.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


async def snapshot(org: str, deal_id: str) -> dict:
    """Keadaan tunggakan satu transaksi + surat yang sudah pernah terbit."""
    threshold = int(await cfg.get(arr.KEY_THRESHOLD, org_id=org) or 2)
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})
    hitung = await lf.assess(org, deal_id)
    a = arr.months_in_arrears(hitung.get("rows") or [])
    contract = await db.contracts.find_one({"org_id": org, "deal_id": deal_id},
                                           {"_id": 0}) or {}
    sudah = await letters(org, deal_id=deal_id)
    lanjut = next_level(sudah)
    halangan = []
    if a["months"] < 1:
        halangan.append("Tidak ada termin yang melewati masa toleransi kontrak — belum ada "
                        "dasar untuk memperingatkan.")
    if lanjut >= MAX_LEVEL and a["months"] < threshold:
        halangan.append(f"SP3 menyebut hak pembatalan sepihak, jadi baru bisa terbit setelah "
                        f"tunggakan mencapai {threshold} bulan (sekarang {a['months']} bulan).")
    return {
        "deal_id": deal_id, "unit_code": (inv or {}).get("unit_code"),
        "lead_name": (inv or {}).get("lead_name"),
        "customer_id": contract.get("customer_id"),
        "contract_id": contract.get("id"), "contract_number": contract.get("number"),
        "phone": (inv or {}).get("phone") or contract.get("phone"),
        "months_in_arrears": a["months"], "max_days_late": a["max_days_late"],
        "overdue_amount": a["overdue_amount"], "terms": a["terms"],
        "denda_running": (hitung.get("totals") or {}).get("denda_running", 0),
        "outstanding": int((inv or {}).get("outstanding") or 0),
        "threshold_months": threshold,
        "issued": sudah, "next_level": lanjut, "blocks": halangan,
        "can_issue": not halangan,
    }


async def _recipient(org: str, snap: dict) -> dict:
    """Nama & nomor pembeli untuk surat dan pengiriman — dari pelanggan bila ada."""
    cust = await db.customers.find_one({"org_id": org, "id": snap.get("customer_id")},
                                       {"_id": 0, "name": 1, "phone": 1, "address": 1}) \
        if snap.get("customer_id") else None
    if not cust:
        deal = await db.deals.find_one({"org_id": org, "id": snap["deal_id"]},
                                       {"_id": 0, "lead_id": 1}) or {}
        lead = await db.leads.find_one({"org_id": org, "id": deal.get("lead_id")},
                                       {"_id": 0, "name": 1, "phone": 1}) if deal else None
        cust = lead or {}
    return {"name": cust.get("name") or snap.get("lead_name") or "Pembeli",
            "phone": cust.get("phone") or snap.get("phone"),
            "address": cust.get("address") or ""}


async def issue(org: str, deal_id: str, level: int, actor: str) -> dict:
    """Terbitkan surat peringatan. Menolak melompat tingkat & tunggakan yang belum ada."""
    level = int(level or 0)
    if level < 1 or level > MAX_LEVEL:
        raise ValueError("Tingkat peringatan hanya SP1, SP2, atau SP3.")
    snap = await snapshot(org, deal_id)
    if snap["months_in_arrears"] < 1:
        raise ValueError("Tidak ada termin yang melewati masa toleransi kontrak, jadi tidak "
                         "ada yang bisa diperingatkan. Periksa kembali daftar tunggakan.")
    if level > snap["next_level"]:
        raise ValueError(
            f"Peringatan tidak boleh melompat: terbitkan SP{snap['next_level']} lebih dulu. "
            "Melompati tingkat mencabut kesempatan pembeli memperbaiki dan membuat "
            "pembatalan yang menyusulnya rapuh.")
    if level == MAX_LEVEL and snap["months_in_arrears"] < snap["threshold_months"]:
        raise ValueError(
            f"SP3 menyebut hak pembatalan sepihak, jadi hanya sah setelah tunggakan "
            f"{snap['threshold_months']} bulan (sekarang {snap['months_in_arrears']} bulan).")
    periode = now_iso()[:7]
    lama = await db.warning_letters.find_one(
        {"org_id": org, "deal_id": deal_id, "level": level, "period": periode}, {"_id": 0})
    if lama:
        return {**lama, "duplicate": True}
    penerima = await _recipient(org, snap)
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "deal_id": deal_id, "level": level,
        "level_label": LEVEL_LABEL[level], "period": periode,
        "number": await seq.next_number("warning_letter", org, prefix="SP", context={
            "level": level, "unit_id": snap.get("unit_id"), "project_id": snap.get("project_id"),
            "customer_name": penerima.get("name")}),
        "unit_code": snap.get("unit_code"), "buyer_name": penerima["name"],
        "buyer_phone": penerima["phone"], "buyer_address": penerima["address"],
        "customer_id": snap.get("customer_id"), "contract_id": snap.get("contract_id"),
        "contract_number": snap.get("contract_number"),
        "months_in_arrears": snap["months_in_arrears"],
        "max_days_late": snap["max_days_late"], "overdue_amount": snap["overdue_amount"],
        "denda_running": snap["denda_running"], "outstanding": snap["outstanding"],
        "terms": snap["terms"], "threshold_months": snap["threshold_months"],
        "deadline_days": DEADLINE_DAYS[level],
        "issued_by": actor, "created_at": ts, "updated_at": ts,
    }
    await db.warning_letters.insert_one(dict(doc))
    doc.pop("_id", None)
    logger.info("Surat peringatan %s terbit untuk deal %s (%s bulan, %s)",
                doc["number"], deal_id, doc["months_in_arrears"],
                _rp(doc["overdue_amount"]))
    return doc


async def get(org: str, letter_id: str) -> dict:
    return await db.warning_letters.find_one({"org_id": org, "id": letter_id}, {"_id": 0})


async def ensure_indexes() -> None:
    await db.warning_letters.create_index([("org_id", 1), ("deal_id", 1), ("level", 1),
                                           ("period", 1)], unique=True,
                                          name="wl_org_deal_level_period")
    await db.warning_letters.create_index([("org_id", 1), ("created_at", -1)])
