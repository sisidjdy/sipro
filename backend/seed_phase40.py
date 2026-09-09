"""seed_phase40.py — data demo pipeline untuk Fase 40 (IA & Design System V2).

MENGAPA perlu: tabel pro (cari + filter multi + sort + paginasi + aksi massal + kolom umur)
tidak bisa dibuktikan — apalagi diuji — pada 2 lead dan 1 pembeli. Fase 40 mengubah cara
data DILIHAT, jadi harus ada data yang cukup untuk melihat: beberapa halaman, beberapa
tahap, beberapa PIC, beberapa sumber, dan umur yang bervariasi (agar warna SLA muncul).

Sifat seed ini:
  * **Idempotent** — ditandai `demo_batch: "fase40"`; dijalankan ulang tidak menduplikasi.
  * **Jujur** — hanya membuat data MASTER pipeline (lead/pembeli) memakai jalur normal
    (skor dari `compute_lead_score`, riwayat tahap ditulis seperti mesin lifecycle menulisnya),
    TIDAK mengarang angka laporan/keuangan/progres.
  * **Aman untuk gate** — telepon unik (index unik `org_id+phone`), `assigned_to` selalu
    user demo yang benar-benar ada, dan tidak ada lead `won` tanpa deal (tahap tertinggi
    yang dibuat = `booking`) supaya invarian bisnis tidak dilanggar.
"""
import logging
import random
from datetime import datetime, timezone

from db import db, ORG_ID
from core_utils import new_id, now_iso, now
from engine import compute_lead_score

logger = logging.getLogger("sipro.seed")
BATCH = "fase40"

# PIC demo (harus ada di seed dasar — dicek verify_data_integrity: assigned_to -> user valid)
OWNERS = ["sales@sipro.co.id", "sales2@sipro.co.id", "marketing@sipro.co.id"]
# CACAT NYATA yang diperbaiki Fase 43: dua nilai di daftar ini BUKAN kosakata SSOT
# (`google_ads` dan `tiktok`, seharusnya `google_lead` & `tiktok_ads`). Migrasi kanonikalisasi
# enum berjalan SEBELUM seed, jadi nilai salah itu selalu selamat: laporan atribusi memecah
# satu kanal menjadi dua nama, dan `reference.SOURCE_SCORE` tidak mengenali 'tiktok' sehingga
# lead iklan TikTok diberi skor terendah seperti impor manual.
SOURCES = ["meta_ads", "google_lead", "walk_in", "referral", "whatsapp", "tiktok_ads",
           "import"]
STAGES = ["acquisition", "nurturing", "appointment", "booking", "lost", "recycle"]
CAMPAIGNS = ["cluster-a-meta", "harmony-google-brand", "tiktok-awareness", None]
TYPES = ["Tipe 36/72", "Tipe 45/90", "Tipe 60/120"]

FIRST = ["Bapak", "Ibu"]
NAMES = [
    "Agus Salim", "Siti Rahmawati", "Budi Santoso", "Dewi Lestari", "Eko Prasetyo",
    "Fitri Handayani", "Gunawan Wibisono", "Hesti Purnama", "Indra Kusuma", "Julia Anggraini",
    "Kurniawan Hakim", "Lina Marlina", "Muhammad Fauzan", "Nadia Safitri", "Oki Setiawan",
    "Putri Ayu Ningrum", "Rizky Ramadhan", "Sri Wahyuni", "Taufik Hidayat", "Utami Dewi",
    "Vino Bastian", "Wulan Sari", "Yusuf Maulana", "Zahra Aulia", "Andi Firmansyah",
    "Bella Kartika", "Chandra Wijaya", "Diana Puspita", "Erwin Saputra", "Farah Nabila",
    "Galih Pratama", "Hana Maharani", "Irfan Nugroho", "Kirana Melati", "Leo Hartanto",
    "Maya Kusumastuti", "Nanda Prakoso", "Olivia Simanjuntak", "Pandu Winata", "Ratna Juwita",
    "Samuel Tanjung", "Tiara Ramadhani", "Umar Abdullah", "Vera Simbolon",
]


def _phone(i: int) -> str:
    return f"+6281244{i:05d}"


async def _seed_leads(org: str, rnd: random.Random) -> int:
    if await db.leads.count_documents({"org_id": org, "demo_batch": BATCH}) > 0:
        return 0
    ts_now = now()
    docs = []
    for i, base_name in enumerate(NAMES):
        stage = STAGES[i % len(STAGES)]
        # umur bervariasi: ada yang masuk beberapa jam lalu, ada yang menganggur 60+ hari
        age_hours = [3, 9, 26, 50, 100, 200, 400, 720, 1400][i % 9] + i
        created = (ts_now.timestamp() - age_hours * 3600)
        created_iso = datetime.fromtimestamp(created, tz=timezone.utc).isoformat()
        owner = OWNERS[i % len(OWNERS)]
        lead = {
            "id": new_id(), "org_id": org, "demo_batch": BATCH,
            "name": f"{FIRST[i % 2]} {base_name}",
            "phone": _phone(i + 1), "email": None,
            "source": SOURCES[i % len(SOURCES)], "campaign": CAMPAIGNS[i % len(CAMPAIGNS)],
            "stage": stage, "assigned_to": owner,
            "interest_unit_type": TYPES[i % len(TYPES)],
            "notes": None,
            "first_contact_at": created_iso if i % 3 else None,
            "response_time_minutes": (5 + i % 40) if i % 3 else None,
            "created_at": created_iso, "updated_at": created_iso, "created_by": "seed",
        }
        # Lead yang sudah bergerak: tulis riwayat tahap seperti mesin lifecycle menulisnya,
        # sehingga "umur tahap" benar-benar lebih muda dari "umur total" (bukan angka hiasan).
        if stage != "acquisition":
            moved_at = datetime.fromtimestamp(
                created + (age_hours * 3600) * 0.4, tz=timezone.utc).isoformat()
            lead["stage_history"] = [{
                "from": "acquisition", "to": stage, "at": moved_at, "actor": owner,
                "reason": "Perpindahan tahap (data demo Fase 40)", "evidence": {},
                "override": False, "source": "seed",
            }]
            lead["stage_changed_at"] = moved_at
        lead.update(compute_lead_score(lead))
        docs.append(lead)
    if docs:
        await db.leads.insert_many(docs)
    return len(docs)


async def _seed_customers(org: str) -> int:
    if await db.customers.count_documents({"org_id": org, "demo_batch": BATCH}) > 0:
        return 0
    ts = now_iso()
    rows = [
        ("Bapak Hendra Gunawan", "3174010203040001", 18500000, "submitted", "Karyawan Swasta"),
        ("Ibu Ratih Prameswari", "3174010203040002", 12750000, "pending", "Wiraswasta"),
        ("Bapak Slamet Riyadi", "3174010203040003", 9500000, "submitted", "ASN"),
        ("Ibu Nurul Aini", "3174010203040004", 27000000, "pending", "Dokter"),
        ("Bapak Bayu Anggara", "3174010203040005", 15250000, "submitted", "TNI/Polri"),
    ]
    docs = []
    for i, (name, nik, income, kyc, job) in enumerate(rows):
        docs.append({
            "id": new_id(), "org_id": org, "demo_batch": BATCH, "name": name,
            "phone": f"+6281255{i + 1:05d}", "email": None, "nik": nik, "npwp": None,
            "address": "Jl. Melati No. 12, Bekasi", "occupation": job,
            "monthly_income": income, "spouse_name": None, "spouse_nik": None,
            "heir_name": None, "heir_relation": None, "notes": None,
            "kyc_status": kyc, "kyc_files": [], "lead_id": None,
            "created_at": ts, "updated_at": ts, "created_by": "seed",
        })
    if docs:
        await db.customers.insert_many(docs)
    return len(docs)


async def seed_phase40(org_id: str = ORG_ID) -> dict:
    """Idempotent. Mengembalikan ringkasan jumlah yang dibuat (0 bila sudah ada)."""
    rnd = random.Random(40)
    leads = await _seed_leads(org_id, rnd)
    customers = await _seed_customers(org_id)
    if leads or customers:
        logger.info("Seed Fase 40: %s lead demo + %s pembeli demo (pipeline untuk IA V2)",
                    leads, customers)
    return {"leads": leads, "customers": customers}
