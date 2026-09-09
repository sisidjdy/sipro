"""PUSAT NOTIFIKASI (Fase 64) — kategori, navigasi, dan notifikasi yang BISA HABIS.

## Cacat yang ditutup berkas ini

Notifikasi sudah dibuat oleh ~30 tempat sejak fase-fase awal, tetapi halaman
`/notifications` hanya menumpuknya sebagai satu daftar panjang tanpa kategori, tanpa
tautan ke pekerjaannya, dan **tanpa akhir**: "Kas bon menunggu persetujuan" tetap berdiri
di layar walaupun kas bonnya sudah disetujui dua hari lalu. Akibatnya:

  1. pemakai berhenti membacanya (notifikasi yang selalu penuh = notifikasi yang diabaikan);
  2. yang benar-benar perlu tindakan tenggelam di antara pemberitahuan informatif;
  3. tidak ada jalan dari notifikasi ke halaman yang bersangkutan — pemakai harus mencari
     sendiri unit/kas bon/tugas yang disebut.

## Yang dipegang di sini

* **Kategori diturunkan dari DATA yang sudah ada** (`type` + `related_entity_type`), bukan
  dari field baru yang harus diisi 30 pemanggil. Notifikasi lama otomatis berkategori.
* **`needs_action`** dipisahkan dari kabar informatif: hanya jenis yang menuntut keputusan/
  pekerjaan (tugas, SLA, persetujuan, sebutan) yang masuk "Perlu tindakan".
* **Tautan** dihitung dari `related_entity_type` + id — SATU peta, dipakai halaman notifikasi
  maupun dropdown lonceng, sehingga tidak ada dua tebakan rute yang berbeda.
* **Auto-selesai**: notifikasi yang menuntut tindakan dicabut sendiri begitu DATA-nya
  menunjukkan tindakan itu sudah dilakukan (tugas ditutup, kas bon diputus, PO disetujui,
  klaim garansi ditutup, punch item selesai). Notifikasi tidak dihapus — ia ditandai
  `resolved_at` + alasan, supaya jejaknya masih bisa diperiksa.
"""
import logging
import re

from core_utils import now_iso
from db import db

logger = logging.getLogger("sipro.notif_center")

# ---------------------------------------------------------------- kategori (SSOT)
# type notifikasi (apa adanya di data) -> kategori layar
TYPE_CATEGORY = {
    "mention": "sebutan", "task": "tugas", "sla": "tugas",
    "finance": "keuangan", "cash_advance": "keuangan", "ap_bill": "keuangan",
    "labor_payroll": "keuangan", "financing": "keuangan", "budget_item": "keuangan",
    "budget": "keuangan", "accounting_period": "keuangan", "approval": None,
    "quotation": "penjualan", "deal": "penjualan",
    "lead": "penjualan", "sales": "penjualan", "contract": "penjualan",
    "customer": "penjualan", "conversation": "penjualan", "capture_failure": "penjualan",
    "project": "proyek", "unit": "proyek", "construction": "proyek",
    "material": "proyek", "permit": "proyek", "build_bulk_run": "proyek",
    "punch_item": "proyek", "unit_handover": "proyek", "alert": None,
    "warranty_claim": "layanan", "warranty": "layanan",
    "complaint": "layanan", "info": "sistem", "success": "sistem",
}
# entitas terkait -> kategori (dipakai bila `type` generik seperti "info"/"approval"/"alert")
ENTITY_CATEGORY = {
    "cash_advance": "keuangan", "ap_bill": "keuangan", "loan": "keuangan",
    "labor_payroll": "keuangan", "budget_item": "keuangan",
    "accounting_period": "keuangan", "invoice": "keuangan",
    "payment_intake": "keuangan", "marketing_fee": "keuangan",
    "asset_depreciation": "keuangan", "subcon_retention": "keuangan",
    "lead": "penjualan", "deal": "penjualan", "contract": "penjualan",
    "customer": "penjualan", "quotation": "penjualan", "conversation": "penjualan",
    "capture_failure": "penjualan",
    "project": "proyek", "unit": "proyek", "punch_item": "proyek",
    "unit_handover": "proyek", "build_bulk_run": "proyek", "material_request": "proyek",
    "purchase_order": "proyek", "spk": "proyek", "progress_claim": "proyek",
    "warranty_claim": "layanan", "complaint": "layanan",
    "task": "tugas", "jobdesk": "tugas",
}
CATEGORIES = ("tugas", "keuangan", "penjualan", "proyek", "layanan", "sebutan", "sistem")

# Jenis yang MENUNTUT tindakan/keputusan (bukan sekadar kabar).
ACTION_TYPES = {"task", "sla", "mention", "approval", "cash_advance", "capture_failure",
                "warranty_claim", "warranty", "complaint", "ap_bill", "financing",
                "quotation"}
ACTION_ENTITIES = {"task", "cash_advance", "ap_bill", "warranty_claim", "complaint",
                   "capture_failure", "punch_item", "purchase_order", "progress_claim",
                   "loan", "labor_payroll"}
# Kata pada judul yang menandakan permintaan keputusan (dipakai bila jenisnya generik).
ACTION_WORDS = ("perlu", "menunggu", "wajib", "tinjau", "persetujuan", "disetujui?",
                "terlambat", "lewat", "gagal", "tertunggak", "mohon")

# ---------------------------------------------------------------- tautan navigasi
ENTITY_LINK = {
    "lead": "/leads/{id}", "deal": "/deals", "contract": "/customers",
    "customer": "/customers/{id}", "project": "/projects/{id}", "unit": "/units/{id}",
    "task": "/tasks", "cash_advance": "/petty-cash", "ap_bill": "/finance",
    "invoice": "/finance", "accounting_period": "/accounting",
    "budget_item": "/projects/{id}", "loan": "/corporate-financing",
    "labor_payroll": "/field", "punch_item": "/field", "unit_handover": "/units/{id}",
    "warranty_claim": "/complaints", "complaint": "/complaints",
    "quotation": "/deals", "conversation": "/inbox", "capture_failure": "/automation",
    "build_bulk_run": "/build", "material_request": "/materials",
    "purchase_order": "/procurement", "spk": "/subcon", "progress_claim": "/subcon",
    "warranty": "/complaints", "payment_intake": "/finance",
    "marketing_fee": "/marketing-fee", "asset_depreciation": "/fixed-assets",
    "subcon_retention": "/subcon", "jobdesk": "/tasks",
}
TYPE_LINK = {"mention": "/tasks", "sla": "/tasks", "task": "/tasks",
             "finance": "/finance", "construction": "/construction",
             "material": "/materials", "permit": "/permits", "sales": "/deals",
             "budget": "/projects"}
# Jenis yang tautannya DITENTUKAN jenisnya, bukan entitasnya: notifikasi tugas harus
# membawa pemakai ke papan tugas (tempat tindakannya), bukan ke halaman objek yang disebut.
TYPE_LINK_WINS = {"task", "sla", "mention"}


def category_of(n: dict) -> str:
    ent = n.get("related_entity_type")
    typ = n.get("type")
    kat = TYPE_CATEGORY.get(typ)
    if kat in (None, "sistem") and ent:
        kat = ENTITY_CATEGORY.get(ent, kat)
    return kat or "sistem"


def needs_action(n: dict) -> bool:
    if n.get("type") in ACTION_TYPES or n.get("related_entity_type") in ACTION_ENTITIES:
        return True
    judul = f"{n.get('title') or ''} {n.get('body') or ''}".lower()
    return any(w in judul for w in ACTION_WORDS)


def link_of(n: dict) -> str:
    ent, eid = n.get("related_entity_type"), n.get("related_entity_id")
    if n.get("type") in TYPE_LINK_WINS:
        return TYPE_LINK[n["type"]]
    pola = ENTITY_LINK.get(ent)
    if pola:
        if "{id}" in pola:
            return pola.replace("{id}", eid) if eid else pola.split("/{id}")[0]
        return pola
    return TYPE_LINK.get(n.get("type"), "")


def decorate(n: dict) -> dict:
    """Tambahkan kategori, penanda tindakan & tautan — dihitung, tidak disimpan ganda."""
    return {**n, "category": category_of(n), "needs_action": needs_action(n),
            "link": link_of(n), "group_key": group_key(n)}


# ---------------------------------------------------------------- kelompok kembar (Fase 65)
# Notifikasi yang sama JENISNYA sering datang berkali-kali ("Kas bon KB-2026-0007 menunggu
# persetujuan", lalu -0008, -0009 …). Sebelum ini tiap kejadian memakan satu baris, jadi
# lima permintaan diskon = lima baris yang harus dibaca satu-satu padahal tindakannya satu
# tempat. Kelompok dihitung dari data yang sudah ada — TIDAK ada field baru yang harus
# diisi ~30 pemanggil `create_notification`, dan notifikasi lama ikut berkelompok.
_NOMOR = re.compile(r"\d[\d.,:/-]*")
_KODE = re.compile(r"\b[A-Z]{2,}[-/][A-Za-z0-9./-]+\b")


def _norm_title(title: str) -> str:
    """Buang bagian yang membuat judul kembar tampak berbeda (nomor dokumen, tanggal, id)."""
    s = _KODE.sub("#", title or "")
    s = _NOMOR.sub("#", s)
    s = re.sub(r"[#]{2,}", "#", s)
    return re.sub(r"\s+", " ", s).strip().lower()[:90]


def group_key(n: dict) -> str:
    """Kunci kelompok: jenis + entitas + judul yang sudah dinormalkan (stabil, bisa dikirim
    ke server sebagai satu nilai aksi)."""
    return "|".join([n.get("type") or "-", n.get("related_entity_type") or "-",
                     _norm_title(n.get("title"))])


def group_rows(rows: list) -> list:
    """Ringkas baris menjadi kelompok kembar (yang terbaru menjadi wakil kelompoknya).

    Kelompok berisi SATU baris tetap tampil apa adanya (`group_count = 1`) supaya layar
    tidak berpura-pura mengelompokkan sesuatu yang tidak kembar.
    """
    bucket: dict = {}
    urutan: list = []
    for r in rows:
        k = r.get("group_key") or group_key(r)
        if k not in bucket:
            bucket[k] = []
            urutan.append(k)
        bucket[k].append(r)
    out = []
    for k in urutan:
        anggota = bucket[k]
        wakil = dict(anggota[0])
        wakil.update({
            "group_key": k, "group_count": len(anggota),
            "group_unread": sum(1 for a in anggota if not a.get("read")),
            "group_action": sum(1 for a in anggota
                                if a.get("needs_action") and not a.get("resolved_at")),
            "group_ids": [a["id"] for a in anggota],
            "group_oldest_at": anggota[-1].get("created_at"),
            "group_members": [{"id": a["id"], "title": a.get("title"),
                               "body": a.get("body"), "created_at": a.get("created_at"),
                               "read": bool(a.get("read")), "link": a.get("link"),
                               "resolved_at": a.get("resolved_at")}
                              for a in anggota[:20]],
        })
        out.append(wakil)
    return out


# ---------------------------------------------------------------- auto-selesai
# entitas -> (koleksi, field status, nilai status yang berarti "sudah ditangani", alasan)
RESOLVERS = {
    "task": ("tasks", "status", {"done", "closed", "cancelled"}, "tugasnya sudah ditutup"),
    "cash_advance": ("cash_advances", "status",
                     {"approved", "rejected", "disbursed", "settled", "closed"},
                     "kas bonnya sudah diputus"),
    "purchase_order": ("purchase_orders", "status", {"approved", "received", "closed",
                                                     "cancelled"},
                       "PO-nya sudah diputus"),
    "progress_claim": ("progress_claims", "status", {"approved", "rejected", "cancelled"},
                       "terminnya sudah diputus"),
    "warranty_claim": ("warranty_claims", "status", {"closed", "resolved", "rejected"},
                       "klaim garansinya sudah ditutup"),
    "complaint": ("complaints", "status", {"closed", "resolved"},
                  "keluhannya sudah ditutup"),
    "punch_item": ("punch_items", "status", {"done", "closed", "verified"},
                   "temuannya sudah diselesaikan"),
    "ap_bill": ("ap_invoices", "status", {"paid", "cancelled", "void"},
                "tagihannya sudah dibayar"),
    "capture_failure": ("capture_failures", "status", {"resolved", "ignored", "recovered"},
                        "kegagalan capture-nya sudah ditangani"),
    "marketing_fee": ("marketing_fees", "status",
                      {"approved", "rejected", "paid", "cancelled", "settled"},
                      "tagihan fee-nya sudah diputus"),
}

# Judul notifikasi tugas berbentuk "Tugas baru: <judul tugas>" — satu-satunya penunjuk ke
# tugasnya (pemanggil lama menyimpan entitas BISNIS, bukan id tugas). Prefix ini dipakai
# untuk mencabut notifikasi begitu tugasnya benar-benar ditutup.
TASK_PREFIX = "Tugas baru: "
TASK_CLOSED = {"done", "closed", "cancelled", "verified"}


async def _resolve_task_notifs(org: str, email: str) -> int:
    """Cabut notifikasi "Tugas baru: …" yang tugasnya sudah selesai/ditutup/hilang."""
    rows = await db.notifications.find(
        {"org_id": org, "user_email": email, "resolved_at": None, "type": "task",
         "title": {"$regex": f"^{TASK_PREFIX}"}},
        {"_id": 0, "id": 1, "title": 1}).sort("created_at", -1).limit(200).to_list(200)
    if not rows:
        return 0
    judul = {r["id"]: r["title"][len(TASK_PREFIX):].strip() for r in rows}
    terbuka = set(await db.tasks.distinct(
        "title", {"org_id": org, "assigned_to": email,
                  "status": {"$nin": list(TASK_CLOSED)},
                  "title": {"$in": list(set(judul.values()))}}))
    target = [nid for nid, t in judul.items() if t not in terbuka]
    if not target:
        return 0
    ts = now_iso()
    res = await db.notifications.update_many(
        {"id": {"$in": target}},
        {"$set": {"resolved_at": ts, "resolved_reason": "tugasnya sudah tidak terbuka lagi",
                  "read": True, "read_at": ts}})
    return res.modified_count


async def resolve_done(org: str, email: str, limit: int = 200) -> int:
    """Cabut notifikasi yang tindakannya SUDAH dilakukan (dilihat dari data, bukan tebakan).

    Dijalankan saat pemakai membuka daftarnya: murah (hanya notifikasi miliknya yang belum
    selesai) dan membuat daftar "Perlu tindakan" benar-benar menyusut ketika pekerjaan
    dikerjakan — inti keluhan pemakai.
    """
    q = {"org_id": org, "user_email": email, "resolved_at": None,
         "related_entity_type": {"$in": list(RESOLVERS)},
         "related_entity_id": {"$ne": None}}
    rows = await db.notifications.find(
        q, {"_id": 0, "id": 1, "related_entity_type": 1, "related_entity_id": 1}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    # Notifikasi tugas ditangani jalur sendiri (penunjuknya judul, bukan id entitas) dan
    # HARUS dijalankan walau tidak ada notifikasi berentitas — dulu `return 0` di sini
    # membuat pencabutan tugas tidak pernah berjalan.
    dari_tugas = await _resolve_task_notifs(org, email)
    if not rows:
        return dari_tugas
    # Kelompokkan per entitas supaya satu jenis = satu kueri, bukan satu kueri per notifikasi.
    per_ent: dict = {}
    for r in rows:
        per_ent.setdefault(r["related_entity_type"], {}).setdefault(
            r["related_entity_id"], []).append(r["id"])
    ts = now_iso()
    dicabut = 0
    for ent, bucket in per_ent.items():
        koleksi, field, selesai, alasan = RESOLVERS[ent]
        docs = await db[koleksi].find({"id": {"$in": list(bucket)}},
                                      {"_id": 0, "id": 1, field: 1}).to_list(500)
        status = {d["id"]: d.get(field) for d in docs}
        ids = [nid for eid, nids in bucket.items() for nid in nids
               if status.get(eid) in selesai]
        # Entitas yang sudah TIDAK ADA lagi (dihapus/dibatalkan) juga tidak menuntut apa pun.
        hilang = [nid for eid, nids in bucket.items() for nid in nids
                  if eid not in status]
        target = ids + hilang
        if not target:
            continue
        res = await db.notifications.update_many(
            {"id": {"$in": target}},
            {"$set": {"resolved_at": ts, "resolved_reason": alasan, "read": True,
                      "read_at": ts}})
        dicabut += res.modified_count
    if dicabut:
        logger.info("%s notifikasi dicabut otomatis untuk %s (tindakan sudah dilakukan)",
                    dicabut, email)
    return dicabut + dari_tugas


# ---------------------------------------------------------------- daftar & ringkasan
async def summary(org: str, email: str) -> dict:
    """Jumlah per kategori & per keadaan — dihitung dari notifikasi yang MASIH berlaku."""
    rows = await db.notifications.find(
        {"org_id": org, "user_email": email, "dismissed_at": None},
        {"_id": 0, "type": 1, "related_entity_type": 1, "read": 1, "title": 1, "body": 1,
         "resolved_at": 1}).sort("created_at", -1).limit(1000).to_list(1000)
    per_kat = {k: 0 for k in CATEGORIES}
    belum = sudah = tindakan = 0
    for r in rows:
        d = decorate(r)
        per_kat[d["category"]] = per_kat.get(d["category"], 0) + 1
        if r.get("read"):
            sudah += 1
        else:
            belum += 1
            if d["needs_action"] and not r.get("resolved_at"):
                tindakan += 1
    return {"per_category": per_kat, "unread": belum, "read": sudah,
            "needs_action": tindakan, "total": len(rows)}
