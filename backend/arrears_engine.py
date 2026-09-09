"""KANDIDAT PEMBATALAN KARENA TUNGGAKAN (Fase 59).

## Utang yang dibayar berkas ini

Dokumen SPR yang dicetak sistem ini menuliskan hak developer membatalkan pesanan sepihak
bila pembeli menunggak `payment.staged.arrears_months_to_cancel` bulan (bawaan 2). Pasalnya
tercetak, angkanya bahkan bisa diubah pemilik usaha dari Pusat Konfigurasi — tetapi sampai
Fase 58 **tidak ada satu pun layar yang menunjuk siapa yang sudah melewatinya**. Akibatnya
aturan itu hanya hidup di kertas: yang menagih menghafal sendiri, dan pembatalan hanya
terjadi kalau ada orang yang ingat.

## Keputusan rancangan yang paling penting: MENGUSULKAN, BUKAN MEMBATALKAN

Mesin ini **tidak pernah** membatalkan kontrak. Ia menyusun daftar kandidat dan menitipkan
TUGAS kepada Manajer Keuangan. Alasannya bukan kehati-hatian yang malas:

  * membatalkan kontrak berarti melepas rumah ke stok, membatalkan tagihan, dan menerbitkan
    utang refund — tiga peristiwa uang yang tidak boleh lahir dari `cron` tanpa manusia;
  * tunggakan sering punya sebab yang tidak ada di database (musibah, dana KPR tertahan
    bank, kesepakatan lisan) — persis keadaan yang Fase 58 sediakan keringanannya;
  * alur pembatalan yang benar sudah ada sejak Fase 56: **diajukan** Manajer Sales,
    **diputus** Manajer Keuangan, **dibayar** Keuangan. Menambah jalan potong otomatis akan
    merusak pemisahan tugas yang justru dibangun untuk melindungi uang pembeli.

## Bagaimana "menunggak dua bulan" dihitung

Tunggakan dihitung dari termin yang **lewat toleransi** menurut mesin denda Fase 58 (bukan
dari H+1 jatuh tempo — kontraknya sendiri memberi tenggang). Bulan tunggakan diambil dari
yang LEBIH BESAR antara:

  * **jumlah termin** cicilan yang lewat toleransi (tunggakan akumulatif: dua cicilan
    bulanan yang tak dibayar = dua bulan), dan
  * **lama keterlambatan** termin tertua dibagi 30 hari (tunggakan berurutan: satu termin
    yang dibiarkan 70 hari = dua bulan).

Keduanya dipakai karena SPR menyebut "berurutan maupun akumulatif". Memakai salah satu saja
membuat setengah kasus nyata lolos dari aturannya sendiri.
"""
import logging

import cancellation_engine as cx
import late_fee_engine as lf
import reference as ref
import settings_store as cfg
from core_utils import now_iso
from db import ORG_ID, db
from engine import auto_create_task
from finance_engine import notify_finance

logger = logging.getLogger("sipro.arrears")

KEY_THRESHOLD = "payment.staged.arrears_months_to_cancel"


def _rp(v) -> str:
    return f"Rp {int(v or 0):,}".replace(",", ".")


def months_in_arrears(rows: list) -> dict:
    """Bulan tunggakan menurut SPR: akumulatif (jumlah termin) DAN berurutan (lama hari)."""
    telat = [r for r in rows if r["state"] == "terlambat" and not r.get("is_penalty")]
    by_terms = len(telat)
    max_days = max((int(r["days_late"] or 0) for r in telat), default=0)
    by_days = max_days // 30
    return {"months": max(by_terms, by_days), "by_terms": by_terms, "by_days": by_days,
            "max_days_late": max_days,
            "overdue_amount": sum(int(r["outstanding"] or 0) for r in telat),
            "terms": [{"label": r["label"], "due_date": r["due_date"],
                       "days_late": r["days_late"], "outstanding": r["outstanding"]}
                      for r in telat]}


def stage_of(months: int, threshold: int) -> str:
    if months >= threshold:
        return "kandidat_batal"
    if months >= max(1, threshold - 1):
        return "perhatian"
    return "aman"


async def candidates(org: str = ORG_ID, *, own_email: str | None = None) -> dict:
    """Semua kontrak dengan tunggakan, diberi tahap terhadap batas kontraknya."""
    threshold = int(await cfg.get(KEY_THRESHOLD, org_id=org) or 2)
    query: dict = {"org_id": org, "status": {"$in": ["unpaid", "partial"]}}
    if own_email:
        query["assigned_to"] = own_email
    invoices = await db.ar_invoices.find(query, {"_id": 0}).to_list(2000)
    out = []
    for inv in invoices:
        hitung = await lf.assess(org, inv.get("deal_id"))
        arr = months_in_arrears(hitung.get("rows") or [])
        if arr["months"] < max(1, threshold - 1):
            continue
        contract = await db.contracts.find_one(
            {"org_id": org, "deal_id": inv.get("deal_id")}, {"_id": 0})
        stage = stage_of(arr["months"], threshold)
        blocks = await cx.blocks(org, contract) if contract else [
            {"code": "kontrak_belum_ada", "label": ref.label_of("cancel_block",
                                                                "kontrak_belum_ada"),
             "detail": ("Transaksi ini belum punya kontrak, jadi yang bisa dibatalkan adalah "
                        "reservasi/booking dari daftar deal — bukan kontrak.")}]
        out.append({
            "deal_id": inv.get("deal_id"), "unit_code": inv.get("unit_code"),
            "lead_name": inv.get("lead_name"), "assigned_to": inv.get("assigned_to"),
            "customer_id": (contract or {}).get("customer_id"),
            "contract_id": (contract or {}).get("id"),
            "contract_number": (contract or {}).get("number"),
            "scheme": (contract or {}).get("scheme") or inv.get("scheme_name"),
            "months_in_arrears": arr["months"], "by_terms": arr["by_terms"],
            "by_days": arr["by_days"], "max_days_late": arr["max_days_late"],
            "overdue_amount": arr["overdue_amount"],
            "denda_running": (hitung.get("totals") or {}).get("denda_running", 0),
            "denda_charged": (hitung.get("totals") or {}).get("denda_charged", 0),
            "in_grace_amount": (hitung.get("totals") or {}).get("in_grace_outstanding", 0),
            "outstanding": int(inv.get("outstanding") or 0),
            "terms": arr["terms"],
            "stage": stage, "stage_label": ref.label_of("arrears_stage", stage),
            "threshold_months": threshold,
            "blocks": blocks,
            "can_request_cancellation": bool(contract) and not blocks,
            # Kalimat per baris supaya layar tidak menyimpulkan sendiri: yang berhak
            # menyimpulkan adalah aturan kontrak, dan aturan itu disebutkan di sini.
            "rule_note": (f"Ketentuan SPR: developer berhak membatalkan sepihak setelah "
                          f"tunggakan {threshold} bulan (Pusat Konfigurasi → "
                          f"{KEY_THRESHOLD}). Tunggakan dihitung SESUDAH masa toleransi "
                          "kontrak, bukan sejak hari jatuh tempo."),
        })
    out.sort(key=lambda r: (-r["months_in_arrears"], -r["overdue_amount"]))
    kandidat = [r for r in out if r["stage"] == "kandidat_batal"]
    return {
        "rows": out, "threshold_months": threshold,
        "totals": {"count": len(out), "count_candidate": len(kandidat),
                   "overdue_amount": sum(r["overdue_amount"] for r in kandidat),
                   "denda_running": sum(r["denda_running"] for r in kandidat)},
        "note": ("Daftar ini MENGUSULKAN, tidak membatalkan. Pembatalan tetap diajukan "
                 "Manajer Sales dari tab Kontrak & Legal dan diputus Manajer Keuangan — "
                 "melepas rumah ke stok, membatalkan tagihan, dan menerbitkan utang refund "
                 "adalah peristiwa uang yang tidak boleh lahir dari penjadwal."),
    }


async def sweep(org: str = ORG_ID, actor: str = "system") -> dict:
    """Titipkan TUGAS peninjauan kepada Manajer Keuangan — idempoten per (kontrak, bulan).

    Idempotensi dijaga `source_event` supaya tombol "Buat tugas peninjauan" dan penjadwal
    harian boleh bertemu tanpa menghasilkan tumpukan tugas kembar untuk pembeli yang sama.
    """
    data = await candidates(org)
    period = now_iso()[:7]
    managers = await db.users.find(
        {"org_id": org, "role": "finance_manager", "is_active": True},
        {"_id": 0, "email": 1}).to_list(20)
    emails = [m["email"] for m in managers] or [None]
    dibuat, dilewati = [], []
    for row in data["rows"]:
        if row["stage"] != "kandidat_batal":
            continue
        key = row["contract_id"] or row["deal_id"]
        made = False
        for email in emails:
            task = await auto_create_task(
                source_event=f"arrears_review:{key}:{period}:{email or 'unassigned'}",
                title=f"Tinjau tunggakan {row['months_in_arrears']} bulan · unit "
                      f"{row['unit_code'] or '-'}",
                type="follow_up", related_entity_type="deal",
                related_entity_id=row["deal_id"], assigned_to=email,
                description=(
                    f"{row['lead_name'] or 'Pembeli'} menunggak "
                    f"{row['months_in_arrears']} bulan ({_rp(row['overdue_amount'])} lewat "
                    f"toleransi, keterlambatan terlama {row['max_days_late']} hari). "
                    f"{row['rule_note']} Pilihannya: beri keringanan/penjadwalan ulang, "
                    "atau minta Manajer Sales mengajukan pembatalan dari tab Kontrak & "
                    "Legal untuk diputus di sini. Jangan membatalkan tanpa berbicara "
                    "dengan pembelinya."),
                priority="high", org_id=org)
            made = made or bool(task)
        if made:
            dibuat.append({"deal_id": row["deal_id"], "unit_code": row["unit_code"],
                           "months": row["months_in_arrears"]})
        else:
            dilewati.append(row["deal_id"])
    if dibuat:
        await notify_finance(
            org, "Tunggakan melewati batas kontrak",
            (f"{len(dibuat)} pesanan menunggak ≥ {data['threshold_months']} bulan dan "
             "menunggu keputusan Manajer Keuangan (keringanan atau pembatalan)."),
            "finance", "cancellation", None)
    logger.info("Sweep tunggakan: %s tugas baru, %s sudah ada", len(dibuat), len(dilewati))
    return {"created": dibuat, "skipped": dilewati, "actor": actor,
            "threshold_months": data["threshold_months"],
            "count_candidate": data["totals"]["count_candidate"]}
