"""seed_phase51.py — data DEMO idempoten untuk Fase 51A (retensi subkon ↔ klaim garansi).

## Kenapa seed ini perlu

Layar Retensi Subkon (Fase 48C) dan gerbangnya yang baru (Fase 51A: klaim garansi menahan
pencairan) TIDAK BISA DICOBA manusia pada basis data demo, karena `subcon_retentions`
kosong: retensi hanya lahir saat termin subkon DISETUJUI, dan di demo belum ada termin yang
disetujui. Akibatnya fitur paling penting fase ini hanya bisa dibuktikan lewat gate/POC —
sementara orang yang membuka aplikasinya melihat halaman kosong dan menyimpulkan fiturnya
tidak ada.

## Dua baris yang dibuat (dan sengaja BERBEDA keadaannya)

1. **RET yang DITAHAN klaim garansi** — SPK finishing dengan lingkup rumah yang SUDAH
   diserahterimakan (`demo_marker="unit_sudah_bast"`, punya klaim garansi berjalan sejak
   Fase 50). Masa pemeliharaannya sengaja SUDAH LEWAT supaya satu-satunya penahan adalah
   klaim garansi — inilah kenyataan yang ditutup Fase 51A, dan tombol "Abaikan penahanan"
   (Manajer Keuangan) bisa benar-benar dicoba di layar.
2. **RET yang SIAP dicairkan** — SPK taman/landscape dengan lingkup rumah yang tidak punya
   klaim garansi maupun temuan punch list terbuka. Ini bahan uji alur lengkap
   ajukan → cairkan, dan pembanding yang membuat "ditahan" bisa dipahami.

## Aturan yang dipatuhi

* **Memakai mesin sungguhan** (`finance_engine.create_ap_bill/approve_ap_bill` +
  `subcon_finance.register_retention`), jadi Utang Retensi di buku besar tetap tie-out
  dengan daftar retensi. Angka demo yang "diketik langsung" akan membuat gate keuangan
  merah — dengan benar.
* **Idempoten** lewat `demo_marker`: restart backend TIDAK menumpuk SPK/termin/retensi baru.
* **Tidak mengganggu bahan uji fase lain**: rumah untuk RET yang siap cair dipilih dari
  rumah yang belum dipakai jadwal pembangunan, punch list, maupun seed fase lain.
"""
import logging
from datetime import date, timedelta

import finance_engine as fe
import storage
import subcon_finance as sf
import warranty_engine as we
from core_utils import new_id, now_iso, today_iso_date
from db import ORG_ID, db
from seed_phase28 import _placeholder_png

logger = logging.getLogger("sipro.seed")

BATCH = "fase51"
HOLD_MARKER = "retensi_ditahan_garansi"   # ditahan klaim garansi berjalan
READY_MARKER = "retensi_siap_cair"        # syarat terpenuhi, bisa dicoba ajukan→cairkan
ACK_MARKER = "klaim_menunggu_pengakuan"   # 51C: menunggu pembeli mengakui di portal


def _days_ago(n: int) -> str:
    return (date.fromisoformat(today_iso_date()) - timedelta(days=n)).isoformat()


async def _subcontractor(org: str, name: str, code: str, specialty: str,
                         marker: str) -> dict:
    doc = await db.subcontractors.find_one({"org_id": org, "name": name}, {"_id": 0})
    if doc:
        return doc
    ts = now_iso()
    # `code` WAJIB terisi: koleksi ini punya index unik (org_id, code), jadi dua vendor
    # tanpa kode = tabrakan `code: null` (cacat yang menghentikan seed pada percobaan pertama).
    doc = {"id": new_id(), "org_id": org, "code": code, "name": name,
           "specialty": specialty, "phone": "+628129990151", "email": None,
           "npwp": None, "address": None, "pic_name": None, "rating": None,
           "is_active": True, "notes": None,
           "demo_batch": BATCH, "demo_marker": marker,
           "created_by": "seed", "created_at": ts, "updated_at": ts}
    await db.subcontractors.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def _spk(org: str, *, marker: str, number: str, sub: dict, unit: dict, title: str,
               scope: str, value: int, maintenance_days, start_days_ago: int) -> dict:
    """SPK demo + satu item lingkup pada `unit` (lingkup unit = adil: retensi milik
    pekerjaan ITU, bukan seluruh proyek)."""
    doc = await db.spk.find_one({"org_id": org, "demo_marker": marker}, {"_id": 0})
    if not doc:
        ts = now_iso()
        doc = {
            "id": new_id(), "org_id": org,
            "spk_number": number,
            "subcontractor_id": sub["id"], "subcontractor_name": sub["name"],
            "project_id": unit["project_id"], "project_name": unit.get("project_name"),
            "title": title, "scope": scope,
            "contract_value": value, "retention_pct": 5.0,
            "start_date": _days_ago(start_days_ago),
            "end_date": _days_ago(max(start_days_ago - 60, 0)),
            "status": "active", "progress_pct": 0, "billed_pct": 0,
            "scope_mode": "lumpsum", "maintenance_days": maintenance_days,
            "notes": None, "demo_batch": BATCH, "demo_marker": marker,
            "created_by": "pm@sipro.co.id", "created_at": ts, "updated_at": ts,
        }
        await db.spk.insert_one(dict(doc))
        doc.pop("_id", None)
    # Idempotensi lingkup: cukup diperiksa "SPK ini sudah punya lingkup atau belum".
    # Memeriksa per (spk_id, unit_id) TIDAK cukup — bila rumah pilihan berubah antar restart
    # (mis. rumah lama kini punya lingkup lalu tersaring keluar), setiap restart menambah
    # SATU baris lingkup baru ke SPK yang sama, dan lingkup retensi melebar diam-diam.
    if not await db.spk_scope_items.count_documents({"org_id": org, "spk_id": doc["id"]}):
        ts = now_iso()
        await db.spk_scope_items.insert_one({
            "id": new_id(), "org_id": org, "spk_id": doc["id"],
            "spk_number": doc["spk_number"], "project_id": unit["project_id"],
            "subcontractor_id": sub["id"], "subcontractor_name": sub["name"],
            "unit_id": unit["id"], "unit_code": unit.get("code"),
            "schedule_id": None, "build_item_id": None,
            "step_code": "FIN-99", "step_name": title, "week": 1, "weight": 100.0,
            "order": 1, "value": value, "boq_item_id": None, "cost_code": None,
            "category": "finishing", "pending_claim_id": None, "claim_id": None,
            "claim_number": None, "claimed_at": None, "exclude_reason": None,
            "demo_batch": BATCH, "demo_marker": marker,
            "created_by": "seed", "created_at": ts, "updated_at": ts})
    return doc


async def _retention(org: str, *, marker: str, number: str, spk: dict,
                     approved_days_ago: int) -> dict:
    """Termin DISETUJUI + tagihan AP + retensi, lewat mesin yang dipakai aplikasi."""
    prior = await db.subcon_retentions.find_one({"org_id": org, "demo_marker": marker},
                                                {"_id": 0})
    if prior:
        return prior
    ts = now_iso()
    approved_at = _days_ago(approved_days_ago)
    gross = round(int(spk["contract_value"]) * 0.6)
    claim = {
        "id": new_id(), "org_id": org,
        "claim_number": number,
        "spk_id": spk["id"], "spk_number": spk["spk_number"],
        "subcontractor_id": spk["subcontractor_id"],
        "subcontractor_name": spk["subcontractor_name"],
        "project_id": spk["project_id"], "project_name": spk.get("project_name"),
        "period": "Termin 1 (0%→60%)", "prev_pct": 0, "claimed_pct": 60,
        "verified_pct": 60, "effective_pct": 60,
        "contract_value_at_submit": spk["contract_value"],
        "gross_est": gross, "gross": gross, "retention_pct": 5.0,
        "basis": "lumpsum", "due_date": approved_at, "status": "approved",
        "note": "Pekerjaan finishing selesai dan diverifikasi supervisor.",
        "approved_by": "finlead@sipro.co.id", "approved_at": approved_at,
        "demo_batch": BATCH, "demo_marker": marker,
        "created_by": "site@sipro.co.id", "created_at": ts, "updated_at": ts,
    }
    bill = await fe.create_ap_bill(spk["subcontractor_name"], spk["project_id"], gross,
                                   5.0, approved_at,
                                   f"Termin {claim['claim_number']} SPK {spk['spk_number']}",
                                   "seed", org)
    bill = await fe.approve_ap_bill(bill["id"], "finlead@sipro.co.id", org)
    claim["retention_held"] = int(bill.get("retention_held", 0))
    claim["net"] = int(bill.get("net", 0))
    claim["ap_bill_id"] = bill["id"]
    await db.progress_claims.insert_one(dict(claim))
    claim.pop("_id", None)
    await db.ap_invoices.update_one({"id": bill["id"], "org_id": org},
                                    {"$set": {"demo_batch": BATCH, "demo_marker": marker,
                                              "spk_id": spk["id"]}})
    ret = await sf.register_retention(org, spk, claim, bill, "seed")
    if ret:
        await db.subcon_retentions.update_one(
            {"id": ret["id"], "org_id": org},
            {"$set": {"demo_batch": BATCH, "demo_marker": marker}})
        await db.spk.update_one({"id": spk["id"], "org_id": org},
                                {"$set": {"progress_pct": 60, "updated_at": now_iso()}})
    return ret


async def _ready_unit(org: str, taken: set) -> dict:
    """Rumah bersih untuk SPK 'siap cair': tanpa klaim garansi & tanpa punch terbuka."""
    kotor = set(await db.punch_items.distinct(
        "unit_id", {"org_id": org, "status": {"$in": ["open", "in_progress"]}}))
    berklaim = set(await db.warranty_claims.distinct("unit_id", {"org_id": org}))
    async for u in db.units.find({"org_id": org, "status": "available"},
                                 {"_id": 0, "id": 1, "code": 1, "project_id": 1}).sort("code", 1):
        if u["id"] in taken or u["id"] in kotor or u["id"] in berklaim:
            continue
        if await db.spk_scope_items.count_documents({"org_id": org, "unit_id": u["id"]}):
            continue
        return u
    return None


async def _claim_awaiting_ack(org: str, unit: dict) -> dict:
    """Klaim garansi yang perbaikannya SUDAH diperiksa mutu dan menunggu PENGAKUAN PEMBELI.

    Tanpa baris ini, pintu paling baru Fase 51C ("Konfirmasi perbaikan" di portal) tidak
    bisa dicoba manusia: mesin hanya menerima pengakuan untuk klaim berstatus
    `diverifikasi`, dan di demo tidak ada satu pun yang sampai ke sana. Seed sengaja
    BERHENTI sebelum penutupan — menutupnya adalah keputusan PEMBELI, bukan seed.

    Alur yang dilewati sama dengan aplikasi (bukan status yang diketik langsung):
    ajukan → terima → selesai (wajib foto) → periksa mutu oleh orang LAIN.
    """
    prior = await db.warranty_claims.find_one({"org_id": org, "demo_marker": ACK_MARKER},
                                              {"_id": 0})
    if prior:
        return prior
    # Kategori STRUKTUR: masa garansinya panjang (120 bulan), jadi klaim ini PASTI masih
    # dalam masa garansi walau rumahnya diserahkan 400 hari lalu. Kategori pendek akan
    # menghasilkan klaim yang justru DITOLAK dan ceritanya hilang dari demo.
    claim = await we.create_claim(
        org, unit_id=unit["id"], category="struktur",
        title="Rembes pada sambungan sloof samping",
        description=("Data DEMO — perbaikan sudah selesai dan lulus pemeriksaan "
                     "mutu; tinggal menunggu PENGAKUAN pembeli di portal."),
        source="portal_pembeli", actor="seed")
    cid = claim["id"]
    await db.warranty_claims.update_one({"id": cid, "org_id": org},
                                        {"$set": {"demo_batch": BATCH,
                                                  "demo_marker": ACK_MARKER}})
    if claim.get("state") == "ditolak":
        logger.info("Seed Fase 51C dilewati: klaim demo ditolak (%s)",
                    claim.get("reject_detail"))
        return claim
    if claim.get("state") == "diajukan":
        await we.decide(org, cid, accept=True, actor="seed",
                        reason="Masih dalam masa garansi struktur; dijadwalkan penyuntikan.",
                        assigned_to="site@sipro.co.id")
    foto = await storage.save_file(
        data=_placeholder_png("Bukti perbaikan sloof (DEMO 51C)", (62, 110, 82)),
        filename="bukti-perbaikan-sloof-demo51.png", content_type="image/png",
        org_id=org, owner_type="warranty_claim", owner_id=cid, uploaded_by="seed",
        doc_type="warranty_fix", tag="warranty", optimize=True,
        watermark_lines=[f"CONTOH · unit {unit.get('code')}", "perbaikan garansi DEMO 51C"])
    await we.complete(org, cid, actor="site@sipro.co.id", photo_file_ids=[foto["id"]],
                      note="Sambungan sloof disuntik epoxy dan diplester ulang.")
    # Pemeriksa WAJIB orang lain (pemisahan tugas dijaga di data, bukan di layar).
    await we.verify(org, cid, actor="pm@sipro.co.id", passed=True,
                    note="Tidak ada rembes setelah uji siram 2x24 jam.")
    return await db.warranty_claims.find_one({"id": cid, "org_id": org}, {"_id": 0})


async def seed_phase51(org: str = ORG_ID) -> dict:
    """Idempoten: hanya membuat yang belum ada."""
    out = {}
    # ---------- 1. retensi yang DITAHAN klaim garansi ----------
    unit_bast = await db.units.find_one(
        {"org_id": org, "demo_marker": "unit_sudah_bast"},
        {"_id": 0, "id": 1, "code": 1, "project_id": 1})
    if not unit_bast:
        logger.info("Seed Fase 51 dilewati: rumah demo ber-BAST (Fase 50) belum ada.")
        return out
    project = await db.projects.find_one({"id": unit_bast["project_id"], "org_id": org},
                                         {"_id": 0, "name": 1}) or {}
    unit_bast["project_name"] = project.get("name")
    sub = await _subcontractor(org, "CV Rapi Finishing", "SUB-51A", "finishing",
                               HOLD_MARKER)
    spk_hold = await _spk(
        org, marker=HOLD_MARKER, number="SPK/DEMO51/TAHAN", sub=sub, unit=unit_bast,
        title="Finishing & sanitasi rumah siap huni",
        scope=("Pekerjaan finishing (cat, keramik, sanitasi) pada rumah yang kemudian "
               "diserahterimakan — retensi menjadi jaminan mutu pasca-huni."),
        value=120_000_000, maintenance_days=30, start_days_ago=420)
    # Masa pemeliharaan 30 hari dari termin yang disetujui 380 hari lalu = SUDAH LEWAT,
    # jadi satu-satunya penahan adalah klaim garansi yang masih berjalan.
    ret_hold = await _retention(org, marker=HOLD_MARKER, number="TRM/DEMO51/TAHAN",
                                spk=spk_hold, approved_days_ago=380)
    if ret_hold:
        out["retensi_ditahan_garansi"] = ret_hold.get("retention_number")

    # ---------- 2. retensi yang SIAP dicairkan (pembanding) ----------
    unit_ready = await _ready_unit(org, {unit_bast["id"]})
    if unit_ready:
        unit_ready["project_name"] = project.get("name")
        sub2 = await _subcontractor(org, "CV Taman Hijau", "SUB-51B", "landscape",
                                    READY_MARKER)
        spk_ready = await _spk(
            org, marker=READY_MARKER, number="SPK/DEMO51/CAIR", sub=sub2, unit=unit_ready,
            title="Taman & paving halaman",
            scope="Pekerjaan taman, paving, dan pagar halaman satu unit.",
            value=40_000_000, maintenance_days=30, start_days_ago=200)
        ret_ready = await _retention(org, marker=READY_MARKER, number="TRM/DEMO51/CAIR",
                                     spk=spk_ready, approved_days_ago=150)
        if ret_ready:
            out["retensi_siap_cair"] = ret_ready.get("retention_number")

    # ---------- 3. klaim garansi yang menunggu PENGAKUAN pembeli (51C) ----------
    ack = await _claim_awaiting_ack(org, unit_bast)
    if ack:
        out["klaim_menunggu_pengakuan"] = f"{ack.get('number')} ({ack.get('state')})"
    if out:
        logger.info("Seed Fase 51 (retensi ↔ garansi, pengakuan pembeli): %s", out)
    return out
