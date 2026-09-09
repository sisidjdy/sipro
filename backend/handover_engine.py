"""Serah terima unit (Fase 50A) — BAST bernomor, daftar periksa bergigi, dan awal masa garansi.

Tiga cacat nyata yang ditutup modul ini:

1. **Serah terima tidak pernah tercatat.** Kamus `unit_status` punya nilai `handed_over` sejak
   Fase 39 tetapi tidak ada satu pun jalan yang menuliskannya; `POST /ar/{deal}/bast` hanya
   mengakui pendapatan. Akibatnya tanggal serah terima tidak bisa dibuktikan, padahal itulah
   titik nol semua kewajiban pasca-huni (garansi) dan penanda sah bahwa risiko sudah pindah
   ke pembeli.
2. **Kunci bisa diserahkan walau pekerjaan belum beres.** Tidak ada pemeriksaan apa pun
   sebelum "serah terima": temuan punch list boleh masih terbuka, inspeksi serah terima belum
   pernah dilakukan, dan kewajiban pembayaran pembeli masih menggantung. Sekarang serah terima
   **DITAHAN** dan menyebut sebabnya satu per satu; hanya peran berwenang yang boleh menerobos
   dengan alasan tertulis, dan terobosan itu melahirkan tugas tinjauan.
3. **Garansi tanpa masa.** Setelan lama hanya punya SATU angka "masa retensi/garansi" untuk
   semua pekerjaan. Sekarang masa dihitung PER BAGIAN (struktur, atap, plumbing, …) dari
   Pusat Konfigurasi, dengan tanggal mulai = tanggal serah terima, sehingga pertanyaan
   "masih garansi atau tidak?" dijawab dengan dasar — bukan perasaan.

Waktu UTC ISO-8601; tanggal serah terima disimpan sebagai `YYYY-MM-DD` (hari kalender).
"""
import calendar
import logging
from datetime import date, datetime, timezone

import doc_registry as dreg
import reference as ref
import sequences as seq
import settings_store as st
from core_utils import new_id, now_iso
from db import db, ORG_ID, ORG_NAME
from engine import auto_create_task
from pdf_utils import build_document_pdf

logger = logging.getLogger("sipro.handover")

OK, BLOCKING, WARNING, MISSING = "ok", "blocking", "warning", "missing_data"
OPEN_PUNCH = ("open", "in_progress")
ISSUED, CANCELLED = "issued", "cancelled"

# Bagian pekerjaan → kunci setelan masa garansi (bulan). Nilai bawaan ada di settings_store,
# jadi lamanya bisa diubah admin tanpa deploy dan perubahannya berjejak.
WARRANTY_KEYS = {
    "struktur": "warranty.struktur_months",
    "atap_plafon": "warranty.atap_plafon_months",
    "dinding_lantai": "warranty.dinding_lantai_months",
    "plumbing": "warranty.plumbing_months",
    "listrik": "warranty.listrik_months",
    "kusen": "warranty.kusen_months",
    "finishing": "warranty.finishing_months",
}


class HandoverHold(Exception):
    """Serah terima ditahan: daftar periksa belum bersih."""

    def __init__(self, reasons: list, items: list = None):
        self.reasons = reasons
        self.items = items or []
        super().__init__(" ".join(reasons))


def _rp(n) -> str:
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


def today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def add_months(day: str, months: int) -> str:
    """Tambah bulan kalender pada tanggal `YYYY-MM-DD` (31 Jan + 1 bulan = 28/29 Feb)."""
    d = date.fromisoformat(str(day)[:10])
    total = (d.year * 12 + (d.month - 1)) + int(months or 0)
    y, m = divmod(total, 12)
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1])).isoformat()


async def warranty_plan(org=ORG_ID) -> list:
    """Masa garansi per bagian dari Pusat Konfigurasi (bukan angka mati di kode)."""
    vals = await st.get_many(list(WARRANTY_KEYS.values()), org_id=org)
    rows = []
    for cat, key in WARRANTY_KEYS.items():
        rows.append({"category": cat, "label": ref.label_of("warranty_category", cat),
                     "months": int(vals.get(key) or 0), "setting_key": key})
    return rows


async def _unit(org: str, unit_id: str) -> dict:
    unit = await db.units.find_one({"id": unit_id, "org_id": org}, {"_id": 0})
    if not unit:
        raise ValueError("Unit tidak ditemukan.")
    return unit


async def _deal_of(org: str, unit: dict) -> dict:
    deal_id = (unit.get("deal_id") or unit.get("sold_by_deal") or unit.get("booked_by_deal")
               or unit.get("reserved_by_deal"))
    if not deal_id:
        return {}
    return await db.deals.find_one({"id": deal_id, "org_id": org}, {"_id": 0}) or {}


async def _buyer(org: str, deal: dict) -> dict:
    """Nama pembeli diambil dari customer bila ada, kalau tidak dari lead — tidak dikarang."""
    out = {"customer_id": None, "buyer_name": None, "buyer_phone": None}
    if not deal:
        return out
    cust = await db.customers.find_one(
        {"org_id": org, "$or": [{"deal_id": deal.get("id")}, {"lead_id": deal.get("lead_id")}]},
        {"_id": 0, "id": 1, "name": 1, "phone": 1})
    if cust:
        return {"customer_id": cust["id"], "buyer_name": cust.get("name"),
                "buyer_phone": cust.get("phone")}
    lead = await db.leads.find_one({"id": deal.get("lead_id"), "org_id": org},
                                   {"_id": 0, "name": 1, "phone": 1}) or {}
    out["buyer_name"] = lead.get("name")
    out["buyer_phone"] = lead.get("phone")
    return out


async def active_handover(org: str, unit_id: str) -> dict:
    return await db.unit_handovers.find_one(
        {"org_id": org, "unit_id": unit_id, "state": ISSUED}, {"_id": 0})


# ======================================================== daftar periksa serah terima
async def handover_check(org: str, unit_id: str) -> dict:
    """Pemeriksaan sebelum kunci diserahkan. Setiap baris menyebut SEBAB & sumbernya."""
    unit = await _unit(org, unit_id)
    deal = await _deal_of(org, unit)
    buyer = await _buyer(org, deal)
    items = []

    def add(code, state, detail, source=None):
        items.append({"code": code, "state": state,
                      "label": ref.label_of("handover_check_item", code),
                      "state_label": ref.label_of("handover_check_state", state),
                      "detail": detail, "source": source})

    # 1. pembangunan selesai
    #
    # Sumber kebenaran status pembangunan adalah `units.construction_status` (SSOT Fase 39):
    # nilai `done` datang dari jadwal yang tuntas, `ready_handover` ditulis oleh finalisasi
    # inspeksi kategori serah terima. Jadwal dipakai sebagai bukti PENDUKUNG (berapa persen),
    # bukan satu-satunya sumber — rumah yang dibangun sebelum modul jadwal ada tetap harus
    # bisa diserahterimakan, sementara jadwal yang belum 100% tetap MENAHAN.
    sched = await db.build_schedules.find_one({"org_id": org, "unit_id": unit_id},
                                              {"_id": 0, "progress": 1, "status": 1})
    cstat = unit.get("construction_status")
    cstat_label = ref.label_of("construction_status", cstat) or cstat or "belum diketahui"
    if cstat in ("done", "ready_handover"):
        add("pembangunan_selesai", OK,
            (f"Status pembangunan: {cstat_label}"
             + (f" \u00b7 progres jadwal {int(sched.get('progress') or 0)}%."
                if sched else " (rumah ini tidak memakai jadwal pembangunan sistem).")),
            f"/units/{unit_id}?tab=build")
    elif not sched:
        add("pembangunan_selesai", BLOCKING,
            (f"Belum ada jadwal pembangunan dan status rumah masih \u201c{cstat_label}\u201d — "
             "selesainya pekerjaan tidak bisa dibuktikan."),
            f"/units/{unit_id}?tab=build")
    else:
        add("pembangunan_selesai", BLOCKING,
            (f"Progres pembangunan baru {int(sched.get('progress') or 0)}% "
             f"(status {cstat_label})."),
            f"/units/{unit_id}?tab=build")

    # 2. temuan punch list yang masih terbuka
    punch = await db.punch_items.find(
        {"org_id": org, "unit_id": unit_id, "status": {"$in": list(OPEN_PUNCH)}},
        {"_id": 0, "title": 1, "severity": 1}).to_list(200)
    if punch:
        names = "; ".join((p.get("title") or "temuan") for p in punch[:3])
        add("punch_terbuka", BLOCKING,
            f"{len(punch)} temuan punch list masih terbuka: {names}"
            + (" …" if len(punch) > 3 else ""),
            f"/units/{unit_id}?tab=build")
    else:
        closed = await db.punch_items.count_documents({"org_id": org, "unit_id": unit_id})
        add("punch_terbuka", OK,
            (f"{closed} temuan sudah ditutup semua." if closed
             else "Tidak ada temuan punch list pada rumah ini."),
            f"/units/{unit_id}?tab=build")

    # 3. inspeksi serah terima
    insp = await db.inspections.find(
        {"org_id": org, "unit_id": unit_id, "category": "handover"},
        {"_id": 0, "inspection_number": 1, "status": 1, "fail_count": 1}).to_list(50)
    passed = [i for i in insp if i.get("status") == "passed"]
    failed = [i for i in insp if i.get("status") == "failed"]
    if passed:
        add("inspeksi_serah_terima", OK,
            f"Inspeksi serah terima {passed[-1].get('inspection_number')} LULUS.",
            f"/units/{unit_id}?tab=quality")
    elif failed:
        add("inspeksi_serah_terima", BLOCKING,
            (f"Inspeksi serah terima {failed[-1].get('inspection_number')} GAGAL — "
             f"{int(failed[-1].get('fail_count') or 0)} item belum lolos."),
            f"/units/{unit_id}?tab=quality")
    elif insp:
        add("inspeksi_serah_terima", BLOCKING,
            "Inspeksi serah terima masih berjalan (belum difinalisasi).",
            f"/units/{unit_id}?tab=quality")
    else:
        add("inspeksi_serah_terima", BLOCKING,
            "Belum ada inspeksi serah terima untuk rumah ini — mutu akhir belum diperiksa.",
            f"/units/{unit_id}?tab=quality")

    # 4. kewajiban pembayaran pembeli — Fase 88E: kebijakan dari Pusat Konfigurasi
    #    (`handover.settlement_policy`): wajib_lunas | minimal_persen | peringatan.
    policy = str(await st.get("handover.settlement_policy", org_id=org) or "wajib_lunas")
    min_pct = float(await st.get("handover.settlement_min_paid_pct", org_id=org) or 0)
    if not deal:
        add("pelunasan_belum", MISSING,
            "Rumah ini belum terikat transaksi pembeli — tidak ada tagihan yang bisa diperiksa.")
    else:
        inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": deal["id"]},
                                            {"_id": 0, "outstanding": 1, "total": 1, "status": 1})
        if not inv:
            add("pelunasan_belum", MISSING,
                "Belum ada jadwal tagihan (AR) untuk transaksi ini — belum ada data pembayaran.",
                "/finance?tab=ar")
        elif int(inv.get("outstanding") or 0) > 0:
            total = int(inv.get("total") or 0)
            paid_pct = round((total - int(inv.get("outstanding") or 0)) / total * 100, 1) if total else 0
            sisa = (f"Sisa kewajiban pembeli {_rp(inv.get('outstanding'))} dari total "
                    f"{_rp(inv.get('total'))} belum beres (terbayar {paid_pct:g}%).")
            if policy == "peringatan":
                add("pelunasan_belum", WARNING,
                    sisa + " Kebijakan organisasi: sisa tagihan hanya PERINGATAN — BAST boleh terbit.",
                    "/finance?tab=ar")
            elif policy == "minimal_persen" and paid_pct >= min_pct:
                add("pelunasan_belum", WARNING,
                    sisa + f" Sudah melewati minimum {min_pct:g}% yang disyaratkan kebijakan.",
                    "/finance?tab=ar")
            else:
                add("pelunasan_belum", BLOCKING,
                    sisa + (f" Minimum terbayar {min_pct:g}%." if policy == "minimal_persen"
                            else " Kebijakan: wajib lunas sebelum BAST."), "/finance?tab=ar")
        else:
            add("pelunasan_belum", OK,
                f"Kewajiban pembeli {_rp(inv.get('total'))} sudah lunas.", "/finance?tab=ar")

    # 5. dokumen wajib serah terima
    if not deal:
        add("dokumen_wajib_kurang", MISSING,
            "Tidak ada transaksi pembeli — daftar dokumen wajib tidak bisa dinilai.")
    else:
        contexts = await dreg.contexts_for("deal", deal["id"], org)
        mtx = await dreg.matrix("deal", deal["id"], contexts, org)
        required = int((mtx.get("counts") or {}).get("required") or 0)
        if not required:
            add("dokumen_wajib_kurang", MISSING,
                "Belum ada master dokumen syarat yang berlaku untuk transaksi ini.",
                "/documents")
        elif not mtx.get("complete"):
            kurang = [r["requirement"].get("name") or r["requirement"].get("code")
                      for r in mtx.get("rows", [])
                      if r["requirement"].get("mandatory") and r["status"] != "verified"]
            add("dokumen_wajib_kurang", BLOCKING,
                f"{len(kurang)} dokumen wajib belum terverifikasi: " + "; ".join(kurang[:3])
                + (" …" if len(kurang) > 3 else ""), "/documents")
        else:
            add("dokumen_wajib_kurang", OK,
                f"{required} dokumen wajib sudah terverifikasi.", "/documents")

    # 6. sudah pernah diserahterimakan? (informasi — penerbitan ulang bersifat idempoten)
    prior = await active_handover(org, unit_id)
    if prior:
        add("bast_sudah_terbit", WARNING,
            (f"Rumah ini sudah diserahterimakan lewat {prior.get('number')} pada "
             f"{prior.get('handed_over_at')} — penerbitan ulang tidak membuat dokumen baru."),
            f"/units/{unit_id}?tab=handover")
    else:
        add("bast_sudah_terbit", OK, "Belum pernah diserahterimakan.")

    blocking = [i for i in items if i["state"] == BLOCKING]
    return {
        "unit": {"id": unit["id"], "code": unit.get("code"), "type": unit.get("type"),
                 "project_id": unit.get("project_id"), "status": unit.get("status"),
                 "status_label": ref.label_of("unit_status", unit.get("status")),
                 "construction_status": unit.get("construction_status")},
        "deal": {"id": deal.get("id"), "price": deal.get("price")} if deal else None,
        "buyer": buyer,
        "items": items,
        "blocking": [{"code": i["code"], "label": i["label"], "detail": i["detail"]}
                     for i in blocking],
        "can_issue": not blocking and not prior,
        "already": prior,
        "warranty_plan": await warranty_plan(org),
        "detail": ("Siap diserahterimakan." if not blocking else
                   f"{len(blocking)} pemeriksaan menahan serah terima."),
    }


# =================================================================== terbitkan BAST
async def issue(org: str, unit_id: str, actor: str, *, handed_over_at: str = None,
                received_by: str = None, note: str = None, meter_air: str = None,
                meter_listrik: str = None, keys_handed: int = None,
                override: bool = False, override_reason: str = None,
                client_ref: str = None) -> dict:
    """Terbitkan BAST. Menahan bila daftar periksa belum bersih (kecuali diterobos).

    Idempoten: unit yang sudah punya BAST aktif TIDAK melahirkan dokumen kedua — dokumen
    lamanya diputar ulang, karena "serah terima kedua" atas rumah yang sama tidak ada dalam
    kenyataan (yang ada: pembatalan lalu penerbitan baru).
    """
    prior = await active_handover(org, unit_id)
    if prior:
        logger.info("BAST idempoten: unit %s sudah punya %s", unit_id, prior.get("number"))
        return {**prior, "replay": True}
    check = await handover_check(org, unit_id)
    blocking = check["blocking"]
    if blocking and not override:
        raise HandoverHold([b["detail"] for b in blocking], blocking)
    if blocking and override and len((override_reason or "").strip()) < 10:
        raise ValueError("Alasan terobosan minimal 10 huruf — tulis dasar rumah ini tetap "
                         "diserahkan walau pemeriksaan belum bersih.")

    unit = await _unit(org, unit_id)
    deal = await _deal_of(org, unit)
    buyer = await _buyer(org, deal)
    project = await db.projects.find_one({"id": unit.get("project_id"), "org_id": org},
                                          {"_id": 0, "name": 1, "code": 1}) or {}
    day = str(handed_over_at or today_str())[:10]
    ts = now_iso()
    plan = await warranty_plan(org)
    warranties = [{"category": p["category"], "label": p["label"], "months": p["months"],
                   "starts_at": day, "expires_at": add_months(day, p["months"])}
                  for p in plan if p["months"] > 0]
    doc = {
        "id": new_id(), "org_id": org,
        "number": await seq.next_number("handover", org, prefix="BAST", year=day[:4],
                                        context={"unit_id": unit_id}),
        "unit_id": unit_id, "unit_code": unit.get("code"),
        "project_id": unit.get("project_id"), "project_name": project.get("name"),
        "deal_id": (deal or {}).get("id"), "customer_id": buyer.get("customer_id"),
        "buyer_name": buyer.get("buyer_name"), "buyer_phone": buyer.get("buyer_phone"),
        "state": ISSUED, "state_label": ref.label_of("handover_state", ISSUED),
        "handed_over_at": day, "received_by": received_by or buyer.get("buyer_name"),
        "note": note, "meter_air": meter_air, "meter_listrik": meter_listrik,
        "keys_handed": keys_handed,
        "checklist": [{"code": i["code"], "state": i["state"], "detail": i["detail"]}
                      for i in check["items"]],
        "override_by": actor if (blocking and override) else None,
        "override_reason": (override_reason or "").strip() if (blocking and override) else None,
        "override_items": [b["code"] for b in blocking] if (blocking and override) else [],
        "warranties": warranties,
        "issued_by": actor, "issued_at": ts, "client_ref": client_ref,
        "created_at": ts, "updated_at": ts,
    }
    await db.unit_handovers.insert_one(dict(doc))
    doc.pop("_id", None)
    unit_set = {"status": "handed_over", "handover_id": doc["id"],
                "handover_number": doc["number"], "handed_over_at": day, "updated_at": ts}
    # Rumah yang SUDAH diserahkan tidak boleh terus berlabel "Siap serah terima": pembacanya
    # melihat dua kenyataan yang bertabrakan di satu kartu. Status pembangunan dinaikkan ke
    # `done` HANYA bila sebelumnya `ready_handover` — bila diserahkan lewat terobosan saat
    # pekerjaan memang belum selesai, statusnya dibiarkan apa adanya (menuliskan "selesai"
    # untuk pekerjaan yang belum selesai justru memalsukan keadaan).
    if unit.get("construction_status") == "ready_handover":
        unit_set["construction_status"] = "done"
    await db.units.update_one({"id": unit_id, "org_id": org}, {"$set": unit_set})
    if deal:
        await db.deals.update_one({"id": deal["id"], "org_id": org}, {"$set": {
            "handover_id": doc["id"], "handed_over_at": day, "updated_at": ts}})
    if blocking and override:
        await auto_create_task(
            source_event=f"handover.override:{doc['id']}",
            title=f"Tinjau terobosan serah terima — unit {unit.get('code')}",
            jobdesk_code="TK-03", type="review",
            related_entity_type="unit_handover", related_entity_id=doc["id"],
            assigned_to=None, priority="urgent", org_id=org,
            description=("Diserahkan walau pemeriksaan belum bersih: "
                         + "; ".join(b["label"] for b in blocking)
                         + f" | Alasan {actor}: {override_reason}"))
    logger.info("BAST %s terbit untuk unit %s oleh %s", doc["number"], unit.get("code"), actor)
    return doc


async def cancel(org: str, hid: str, actor: str, reason: str) -> dict:
    """Batalkan BAST yang salah terbit: status unit dikembalikan & masa garansi ditutup.

    Dokumen TIDAK dihapus — pembatalan adalah peristiwa, bukan penghapusan sejarah.
    """
    doc = await db.unit_handovers.find_one({"id": hid, "org_id": org}, {"_id": 0})
    if not doc:
        raise ValueError("Berita acara serah terima tidak ditemukan.")
    if doc.get("state") == CANCELLED:
        raise ValueError(f"{doc.get('number')} sudah dibatalkan sebelumnya.")
    if len((reason or "").strip()) < 10:
        raise ValueError("Alasan pembatalan minimal 10 huruf.")
    open_claims = await db.warranty_claims.count_documents(
        {"org_id": org, "handover_id": hid,
         "state": {"$in": ["diajukan", "dikerjakan", "selesai", "diverifikasi"]}})
    if open_claims:
        raise ValueError(f"Masih ada {open_claims} klaim garansi berjalan pada serah terima ini — "
                         "tuntaskan atau tolak klaimnya lebih dulu.")
    ts = now_iso()
    await db.unit_handovers.update_one({"id": hid, "org_id": org}, {"$set": {
        "state": CANCELLED, "state_label": ref.label_of("handover_state", CANCELLED),
        "cancel_reason": reason.strip(), "cancelled_by": actor, "cancelled_at": ts,
        "updated_at": ts}})
    prev = "sold" if (doc.get("deal_id")) else "available"
    await db.units.update_one({"id": doc["unit_id"], "org_id": org}, {"$set": {
        "status": prev, "handover_id": None, "handover_number": None,
        "handed_over_at": None, "updated_at": ts}})
    await auto_create_task(
        source_event=f"handover.cancel:{hid}",
        title=f"Tinjau pembatalan serah terima {doc.get('number')}",
        jobdesk_code="TK-03", type="review",
        related_entity_type="unit_handover", related_entity_id=hid,
        assigned_to=None, priority="high", org_id=org,
        description=f"Dibatalkan {actor}: {reason.strip()}")
    return await db.unit_handovers.find_one({"id": hid, "org_id": org}, {"_id": 0})


async def list_handovers(org: str, project_id: str = None, unit_id: str = None,
                         state: str = None) -> dict:
    q = {"org_id": org}
    if project_id:
        q["project_id"] = project_id
    if unit_id:
        q["unit_id"] = unit_id
    if state:
        q["state"] = state
    rows = await db.unit_handovers.find(q, {"_id": 0}).sort("handed_over_at", -1).to_list(500)
    for r in rows:
        r["warranty"] = warranty_rows(r)
        r["open_claims"] = await db.warranty_claims.count_documents(
            {"org_id": org, "handover_id": r["id"],
             "state": {"$in": ["diajukan", "dikerjakan", "selesai", "diverifikasi"]}})
    issued = [r for r in rows if r.get("state") == ISSUED]
    return {
        "rows": rows,
        "summary": {
            "total": len(rows), "issued": len(issued),
            "cancelled": sum(1 for r in rows if r.get("state") == CANCELLED),
            "override": sum(1 for r in issued if r.get("override_by")),
            "warranty_active": sum(1 for r in issued
                                   if any(w["state"] != "habis" for w in r["warranty"])),
        },
        "detail": ("Belum ada rumah yang diserahterimakan — belum ada data, bukan nol."
                   if not rows else f"{len(issued)} rumah sudah diserahterimakan."),
    }


# ==================================================================== masa garansi
def _norm_warranty(w: dict) -> dict:
    """Lengkapi satu baris garansi yang tersimpan agar SELALU bisa dibaca manusia.

    Kenapa ini ada: baris garansi disimpan di dalam dokumen BAST (`unit_handovers.warranties`),
    dan dokumen itu bisa lahir dari beberapa jalan — penerbitan normal, bahan uji gate/POC,
    dan dokumen lama sebelum kolom `label` ada. Sebelum ini pembaca (`warranty_rows`,
    `pdf_bytes`) mengambil `w["label"]` langsung, jadi SATU dokumen tanpa kolom itu membuat
    **unduhan PDF BAST mati 500** — kegagalan yang menimpa pembeli, bukan penguji. Nama bagian
    memang tidak perlu disimpan: itu turunan `category` di Kamus Data (`warranty_category`),
    jadi di sini diturunkan ulang, bukan diminta dari dokumen.

    `months` juga diturunkan bila hilang (dari selisih `starts_at`→`expires_at`), dan
    `expires_at` dihitung dari `starts_at + months` bila memang belum tercatat. Semua turunan
    ditandai `derived` supaya layar tetap jujur soal apa yang dihitung ulang.
    """
    w = dict(w or {})
    derived = []
    cat = w.get("category")
    if not w.get("label"):
        w["label"] = ref.label_of("warranty_category", cat) or cat or "Bagian tidak dikenal"
        derived.append("label")
    if not w.get("expires_at") and w.get("starts_at") and w.get("months"):
        w["expires_at"] = add_months(w["starts_at"], int(w["months"]))
        derived.append("expires_at")
    if w.get("months") in (None, "") and w.get("starts_at") and w.get("expires_at"):
        a = date.fromisoformat(str(w["starts_at"])[:10])
        b = date.fromisoformat(str(w["expires_at"])[:10])
        w["months"] = (b.year * 12 + b.month) - (a.year * 12 + a.month)
        derived.append("months")
    if derived:
        w["derived_fields"] = derived
    return w


def warranty_rows(handover: dict, at: str = None, expiring_days: int = 30) -> list:
    """Keadaan masa garansi per bagian pada tanggal `at` (bawaan: hari ini).

    Baris tanpa tanggal habis yang tidak bisa dihitung DILEWATI dan dicatat di log — lebih
    baik daftar kurang satu baris beserta jejaknya daripada seluruh dokumen gagal terbuka.
    """
    ref_day = date.fromisoformat(str(at or today_str())[:10])
    out = []
    for raw in (handover or {}).get("warranties", []):
        w = _norm_warranty(raw)
        if not w.get("expires_at"):
            logger.warning("Baris garansi tanpa tanggal habis pada BAST %s (bagian %s) "
                           "dilewati", (handover or {}).get("number"), w.get("category"))
            continue
        exp = date.fromisoformat(str(w["expires_at"])[:10])
        days_left = (exp - ref_day).days
        state = "habis" if days_left < 0 else ("hampir_habis" if days_left <= expiring_days
                                              else "aktif")
        out.append({**w, "days_left": days_left, "state": state,
                    "state_label": ref.label_of("warranty_state", state)})
    return out


async def warranty_status(org: str, unit_id: str, at: str = None) -> dict:
    """Ringkasan garansi satu rumah. Bila belum diserahterimakan: mengaku belum ada data."""
    unit = await _unit(org, unit_id)
    ho = await active_handover(org, unit_id)
    expiring = int(await st.get("warranty.expiring_days", org_id=org) or 30)
    if not ho:
        return {
            "unit": {"id": unit_id, "code": unit.get("code")},
            "handover": None, "rows": [], "claims": [],
            "missing": True,
            "detail": ("Rumah ini belum diserahterimakan, jadi masa garansi belum mulai — "
                       "belum ada data, bukan nol hari."),
        }
    rows = warranty_rows(ho, at=at, expiring_days=expiring)
    claims = await db.warranty_claims.find(
        {"org_id": org, "unit_id": unit_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {
        "unit": {"id": unit_id, "code": unit.get("code")},
        "handover": ho, "rows": rows, "claims": claims, "missing": False,
        "summary": {
            "aktif": sum(1 for r in rows if r["state"] == "aktif"),
            "hampir_habis": sum(1 for r in rows if r["state"] == "hampir_habis"),
            "habis": sum(1 for r in rows if r["state"] == "habis"),
            "claims_open": sum(1 for c in claims if c.get("state") in
                               ("diajukan", "dikerjakan", "selesai", "diverifikasi")),
        },
        "detail": (f"Diserahterimakan {ho.get('handed_over_at')} lewat {ho.get('number')}; "
                   f"{sum(1 for r in rows if r['state'] != 'habis')} dari {len(rows)} bagian "
                   "masih bergaransi."),
    }


# ========================================================================= dokumen
async def pdf_bytes(org: str, hid: str) -> tuple:
    """BAST sebagai PDF nyata (bukan tangkapan layar) — bisa dicetak & ditandatangani."""
    doc = await db.unit_handovers.find_one({"id": hid, "org_id": org}, {"_id": 0})
    if not doc:
        raise ValueError("Berita acara serah terima tidak ditemukan.")
    w = warranty_rows(doc)
    lines = [
        f"Nomor : {doc.get('number')}",
        f"Tanggal serah terima : {doc.get('handed_over_at')}",
        f"Proyek : {doc.get('project_name') or '-'}",
        f"Unit : {doc.get('unit_code') or '-'}",
        f"Pembeli : {doc.get('buyer_name') or '-'}",
        f"Diterima oleh : {doc.get('received_by') or doc.get('buyer_name') or '-'}",
        f"Meter air : {doc.get('meter_air') or '-'}",
        f"Meter listrik : {doc.get('meter_listrik') or '-'}",
        f"Jumlah kunci diserahkan : {doc.get('keys_handed') if doc.get('keys_handed') is not None else '-'}",
        f"Status : {ref.label_of('handover_state', doc.get('state'))}",
        "",
        "Masa garansi yang berlaku sejak tanggal serah terima:",
    ]
    if not w:
        lines.append("Belum ada masa garansi tercatat pada dokumen ini.")
    for row in w:
        bulan = (f"{row['months']} bulan" if row.get("months")
                 else "lama garansi belum tercatat")
        lines.append(f"{row.get('label')} : {bulan} (sampai {row.get('expires_at')})")
    if doc.get("override_by"):
        lines += ["", (f"Catatan terobosan : diserahkan oleh {doc['override_by']} walau "
                       f"pemeriksaan belum bersih. Alasan: {doc.get('override_reason')}")]
    if doc.get("note"):
        lines += ["", f"Catatan : {doc['note']}"]
    if doc.get("state") == CANCELLED:
        lines += ["", (f"DOKUMEN DIBATALKAN {doc.get('cancelled_at')} oleh "
                       f"{doc.get('cancelled_by')} — {doc.get('cancel_reason')}")]
    import doc_layout as dl
    _lay = await dl.get_layout(org, "BAST")
    _imgs = await dl.images(org, _lay)
    pdf = build_document_pdf(layout=_lay, images=_imgs,
        title="BERITA ACARA SERAH TERIMA UNIT", doc_number=doc.get("number"),
        script_context={"date": str(doc.get("handed_over_at") or doc.get("issued_at") or "")[:10], "sales_name": doc.get("issued_by") or ""},
        content="\n".join(lines), org_name=ORG_NAME,
        signatures=[{"role": "Pihak Pertama (Pengembang)", "name": doc.get("issued_by"),
                     "signed_at": doc.get("issued_at")},
                    {"role": "Pihak Kedua (Pembeli)",
                     "name": doc.get("received_by") or doc.get("buyer_name"),
                     "signed_at": doc.get("handed_over_at")}])
    return pdf, doc
