"""SIPRO backend entrypoint (uvicorn server:app).

App factory + lifespan (indexes, seed, scheduler) + router registry. All routes
under /api. Multi-tenant-ready, RBAC-enforced foundation (Fase 0).
"""
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")  # load before importing modules that read env

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from db import client, db, ORG_ID
import gl_engine as gl
from engine import start_scheduler, stop_scheduler
from seed import ensure_indexes, seed_if_empty
from seed_phase25 import seed_site_plan_demo
from seed_phase27 import seed_phase27
from seed_phase28 import seed_demo_photos, seed_demo_plans
from seed_phase29 import seed_phase29
from seed_phase31 import seed_phase31
from seed_phase33 import seed_phase33
from seed_phase36 import seed_phase36
from indexes import ensure_unique_indexes
from migrations import run_migrations
from routers.auth_router import router as auth_router
from routers.admin_router import router as admin_router
from routers.work_router import router as work_router
from routers.workhub_router import router as workhub_router
from routers.activity_router import router as activity_router
from routers.leads_router import router as leads_router
from routers.leads_lifecycle_router import router as leads_lifecycle_router
from routers.inbox_router import router as inbox_router
from routers.deals_router import router as deals_router
from routers.documents_router import router as documents_router
from routers.webhooks_router import router as webhooks_router
from routers.capture_router import router as capture_router
from routers.projects_router import router as projects_router
from routers.construction_router import router as construction_router
from routers.materials_router import router as materials_router
from routers.finance_config_router import router as finance_config_router
from routers.ar_router import router as ar_router
from routers.ap_router import router as ap_router
from routers.commissions_router import router as commissions_router
from routers.cashflow_router import router as cashflow_router
from routers.reports_router import router as reports_router
from routers.realtime_router import router as realtime_router
from routers.customers_router import router as customers_router
from routers.financing_router import router as financing_router
from routers.files_router import router as files_router
from routers.portal_router import router as portal_router
from routers.complaints_router import router as complaints_router
from routers.permits_router import router as permits_router
from routers.field_router import router as field_router
from routers.subcon_router import router as subcon_router
from routers.subcon_claims_router import router as subcon_claims_router
from routers.inspection_router import router as inspection_router
from routers.boq_router import router as boq_router
from routers.procurement_router import router as procurement_router
from routers.gl_router import router as gl_router
from routers.gl_reports_router import router as gl_reports_router
from routers.survey_router import router as survey_router
from routers.tax_router import router as tax_router
from routers.tax_compliance_router import router as tax_compliance_router
# Fase 50A \u2014 serah terima unit (BAST), masa garansi per bagian, dan klaim garansi pasca-huni.
from routers.handover_router import router as handover_router
from routers.reminders_router import router as reminders_router
from routers.contracts_router import router as contracts_router
from routers.omnichannel_router import router as omnichannel_router
from routers.broadcasts_router import router as broadcasts_router
from routers.orgs_router import router as orgs_router
from routers.reference_router import router as reference_router
from routers.master_router import router as master_router
from routers.site_plan_router import router as site_plan_router
from routers.petty_cash_router import router as petty_cash_router
from routers.fixed_assets_router import router as fixed_assets_router
from routers.loans_router import router as loans_router
from routers.marketing_fee_router import router as marketing_fee_router
from routers.public_router import router as public_router
from routers.build_router import router as build_router
from routers.build_ops_router import router as build_ops_router
from routers.build_bulk_router import router as build_bulk_router
from routers.build_calendar_router import router as build_calendar_router
from routers.build_calibration_router import router as build_calibration_router
from routers.spk_scope_router import router as spk_scope_router
from routers.settings_router import router as settings_router
from routers.masterplan_router import router as masterplan_router
from routers.catalog_router import router as catalog_router
from routers.docreq_router import router as docreq_router
from routers.aging_router import router as aging_router
from routers.partners_router import router as partners_router
from routers.ads_router import router as ads_router
from routers.analytics_router import router as analytics_router
from routers.targets_router import router as targets_router
from routers.budget_router import router as budget_router
from routers.build_board_router import router as build_board_router
from routers.bank_router import router as bank_router
from routers.intake_router import router as intake_router
from routers.quotations_router import router as quotations_router
from routers.labor_router import router as labor_router
from routers.vendors_router import router as vendors_router
from routers.procurement_extra_router import router as procurement_extra_router
from routers.subcon_finance_router import router as subcon_finance_router
from routers.stock_router import router as stock_router
from storage import init_storage

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("sipro")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    seeded = await seed_if_empty()
    if seeded:
        logger.info("Database seeded with demo data.")
    # Kavling demo multi-blok untuk Site Plan / Showroom (idempoten).
    await seed_site_plan_demo()
    # Fase 28b: peta SVG demo dibangkitkan agar peta realistis langsung tampil
    # (sebelumnya DB bersih selalu jatuh ke fallback tata letak blok otomatis).
    await seed_demo_plans()
    # Integritas data (hasil audit forensik): index unik natural key + migrasi idempoten
    # (kanonikalisasi enum, backfill counter nomor dokumen, resync field denormalisasi).
    idx = await ensure_unique_indexes()
    if idx["conflicts"]:
        logger.warning("Index unik belum bisa dibuat: %s", [c["index"] for c in idx["conflicts"]])
    mig = await run_migrations()
    if mig["enums"] or mig["denorm"]:
        logger.info("Migrasi data: %s nilai enum dikanonikalisasi, %s field kopi disinkronkan.",
                    len(mig["enums"]), len(mig["denorm"]))
    # Fase 26: pastikan CoA setiap org lengkap (mis. akun baru 2-1450 Titipan Pelanggan).
    orgs = await db.orgs.distinct("id") or [ORG_ID]
    for org_id in orgs:
        await gl.ensure_coa(org_id)
    await init_storage()
    # Fase 27: demo Kas Bon / Aset Tetap / Pembiayaan / Marketing Fee (idempoten, berjurnal).
    # Dijalankan SETELAH CoA lengkap agar akun baru (1-1500, 1-2100, 2-2100, ...) tersedia.
    await seed_phase27(ORG_ID)
    # Fase 29: domain kerja (divisi/supervisor) + katalog jobdesk Work Hub.
    await seed_phase29(ORG_ID)
    # Fase 28b: foto contoh lapangan (placeholder, dilabeli "contoh") lewat lapisan
    # storage yang sama dengan unggahan pengguna — dijalankan SETELAH init_storage.
    await seed_demo_photos(ORG_ID)
    # Fase 31: template jadwal pembangunan + jadwal demo per unit + perbaikan cacat
    # progres/ikatan unit. Dijalankan SETELAH storage siap (butuh unggah foto contoh).
    await seed_phase31(ORG_ID)
    # Fase 33: RAB dipetakan ke langkah jadwal + SPK borongan berbasis item pekerjaan
    # (uang hanya mengalir mengikuti bukti). Setelah jadwal Fase 31 ada.
    await seed_phase33(ORG_ID)
    # Fase 36: MASTER kalender kerja (pola hari + hari libur nasional bawaan yang bisa
    # diubah admin) + inspeksi demo diberi tanggal rencana agar Kalender Jadwal terisi
    # data nyata. Setelah jadwal Fase 31/33 ada.
    await seed_phase36(ORG_ID)
    # Fase 37: kalibrasi template sekali klik — hanya butuh indeks (usulan kalibrasi lahir
    # dari data keterlambatan NYATA, jadi tidak ada seed yang boleh mengarang rekomendasi).
    import build_calibration as bcalib
    await bcalib.ensure_indexes()
    # Fase 39: fondasi data V2 — master default (komponen biaya, add-on, dokumen syarat) +
    # backfill cluster/blok/tipe unit + penautan shape site plan. Idempoten; tidak menyentuh
    # jurnal keuangan. Detail: docs/v2/35_MIGRASI_DATA.md
    import migrations_v2 as mig2
    v2 = await mig2.run_v2_migrations(ORG_ID)
    logger.info("Fondasi V2 siap: %s unit tertaut cluster/blok, %s tipe unit, %s shape peta.",
                v2["M39_1_cluster_block"]["units_linked"],
                v2["M39_2_unit_types"]["types_created"], v2["M39_4_siteplan"]["linked"])
    # Fase 40: data demo pipeline (lead & pembeli) supaya tabel pro benar-benar bisa
    # dilihat & diuji — filter multi, sort, paginasi, dan kolom umur tidak bisa dibuktikan
    # pada 2 lead. Idempoten (ditandai demo_batch="fase40").
    from seed_phase40 import seed_phase40
    await seed_phase40(ORG_ID)
    # Fase 41: jam tahap sebagai FIELD nyata. `reconcile()` mengisi/memperbaiki
    # stage_entered_at & stage_due_at untuk dokumen yang tahapnya berubah lewat jalur lama
    # (seed, impor, endpoint yang belum memakai `stamp`) — idempoten, aman diulang.
    import stage_clock as clock
    filled = await clock.reconcile(org_id=ORG_ID)
    if any(filled.values()):
        logger.info("Jam tahap (Fase 41) disegarkan: %s",
                    {k: v for k, v in filled.items() if v})
    # Fase 42: hak fee mitra lahir dari peristiwa NYATA yang sudah terbit di aplikasi.
    import partner_engine as pengine
    logger.info("Pemicu fee mitra terpasang pada event: %s", pengine.register())
    from seed_phase42 import seed_phase42
    await seed_phase42(ORG_ID)
    # Fase 43: kampanye untuk nama `campaign` yang SUDAH dipakai lead demo + biaya iklan
    # demo (source=manual). Satu kampanye sengaja tanpa biaya & satu hanya sebagian hari,
    # supaya keadaan jujur "data biaya belum lengkap" bisa dilihat & diuji.
    from seed_phase43 import seed_phase43
    await seed_phase43(ORG_ID)
    # Fase 43: SPR ditandatangani → event konversi `SubmitApplication` ke platform iklan.
    import capi_hooks
    logger.info("Hook CAPI terpasang pada event: %s", capi_hooks.register())
    # Fase 45: satu target proyek aktif + master anggaran (konstruksi meringkas RAB,
    # operasional dari akun beban nyata, satu item sengaja overbudget agar peringatannya
    # bisa dilihat). Idempoten (demo_batch="fase45").
    from seed_phase45 import seed_phase45
    await seed_phase45(ORG_ID)
    # Fase 46: izin dinaikkan menjadi BERTINGKAT (menempel proyek/cluster/blok/unit) +
    # contoh masa berlaku (aktif, menjelang kedaluwarsa, kedaluwarsa) & temuan mutu per
    # unit. Izin lama sengaja tidak diberi tanggal berlaku palsu. Idempoten ("fase46").
    from seed_phase46 import seed_phase46
    await seed_phase46(ORG_ID)
    # Fase 47: uang masuk yang bisa dibuktikan (rekening + mutasi belum dicocokkan + satu
    # bukti transfer portal menunggu verifikasi), tenaga kerja harian + absensi 2 hari, dan
    # satu penawaran berdiskon di atas kewenangan sales. Seed TIDAK menekan tombol milik
    # manusia (tidak mencocokkan, tidak memverifikasi, tidak menyetujui). Idempoten.
    from seed_phase47 import seed_phase47
    await seed_phase47(ORG_ID)
    # Fase 48: master vendor + daftar harga, permintaan material yang stoknya kurang (bahan
    # uji "Buat PO"), batas stok minimum, uang muka subkon yang sudah dibayar + potongan
    # menunggu, dan BACKFILL daftar retensi dari tagihan termin lama (uang retensi yang sudah
    # ada di buku besar tetapi belum punya jalan pencairan). Idempoten.
    from seed_phase48 import seed_phase48
    await seed_phase48(ORG_ID)
    # Fase 49: identitas pajak perusahaan CONTOH (tanpa itu semua ekspor pajak ditahan),
    # satu faktur pajak keluaran atas deal ber-AR, dan satu tagihan vendor yang dibayar
    # sebagian DENGAN POTONG PPh 4(2) sehingga bukti potong bernomor terbit otomatis.
    # Seed tidak menutup bulan/tahun (keputusan manusia) dan tidak memoles daftar periksa.
    from seed_phase49 import seed_phase49
    await seed_phase49(ORG_ID)
    # Fase 50: dua rumah demo dengan cerita berbeda \u2014 satu BERSIH & lunas tetapi belum
    # diserahterimakan (tombol "Terbitkan BAST" bisa dicoba di layar), satu sudah
    # diserahterimakan 400 hari lalu sehingga garansi finishing-nya habis sementara struktur
    # masih aktif (bahan uji klaim "lewat masa garansi" vs klaim yang berjalan). Seed tidak
    # menutup klaim & tidak memeriksa mutu (keputusan manusia). Idempoten.
    from seed_phase50 import seed_phase50
    await seed_phase50(ORG_ID)
    # Fase 51A — retensi subkon yang DITAHAN klaim garansi berjalan. Tanpa seed ini layar
    # Retensi Subkon kosong di demo (retensi hanya lahir dari termin yang DISETUJUI),
    # sehingga fitur paling penting fase ini hanya bisa dibuktikan lewat gate — sementara
    # orang yang membuka aplikasinya menyimpulkan fiturnya tidak ada. Satu baris DITAHAN
    # klaim garansi (tombol "Abaikan penahanan" bisa dicoba), satu baris SIAP dicairkan
    # sebagai pembanding. Memakai mesin AP + retensi sungguhan supaya tie-out GL terjaga.
    # Idempoten lewat `demo_marker`.
    from seed_phase51 import seed_phase51
    await seed_phase51(ORG_ID)
    # Fase 53: template dokumen ASLI owner (SPR Cash/Cash Bertahap/KPR + SPKT) sebagai data,
    # tiga skema bayar sesuai dokumen owner, dan backfill kontrak untuk pembeli demo yang
    # sudah ada — supaya layar Kontrak & Legal punya data NYATA, bukan angka karangan.
    from seed_phase53 import seed_phase53
    await seed_phase53(ORG_ID)
    # Fase 41 (SAPUAN TERAKHIR) — jam tahap untuk dokumen yang dibuat seed SESUDAH panggilan
    # reconcile di atas. Cacat nyata yang ditemukan saat penutupan Fase 50: `reconcile()`
    # dipanggil tepat setelah seed Fase 40, sehingga setiap lead/deal/pelanggan yang lahir
    # dari seed Fase 42..50 TIDAK pernah punya `stage_entered_at` — laporan umur tahap
    # kehilangan barisnya dan gate 24 (`verify_41.py`) merah dengan benar. Idempoten.
    filled_late = await clock.reconcile(org_id=ORG_ID)
    if any(filled_late.values()):
        logger.info("Jam tahap (Fase 41) disegarkan setelah seluruh seed: %s",
                    {k: v for k, v in filled_late.items() if v})
    start_scheduler()
    yield
    stop_scheduler()
    client.close()


app = FastAPI(title="SIPRO API", version="0.1.0", lifespan=lifespan)
api = APIRouter(prefix="/api")


@app.exception_handler(RequestValidationError)
async def readable_validation_error(_request, exc: RequestValidationError):
    """Fase 26: galat validasi SSOT tampil sebagai 400 + pesan Indonesia yang bisa dibaca.

    Sebelumnya pydantic mengembalikan 422 dengan detail berbentuk daftar objek,
    sehingga toast di frontend menampilkan "[object Object]" alih-alih alasan aslinya.
    """
    parts = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", []) if x not in ("body", "query", "path"))
        msg = str(err.get("msg", "")).replace("Value error, ", "")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return JSONResponse(status_code=400,
                        content={"detail": " | ".join(parts) or "Data yang dikirim tidak valid."})


@api.get("/")
async def root():
    return {"message": "SIPRO API", "status": "ok"}


@api.get("/health")
async def health():
    return {"status": "ok", "service": "sipro-backend"}


api.include_router(auth_router)
api.include_router(admin_router)
api.include_router(work_router)
api.include_router(workhub_router)
api.include_router(activity_router)
api.include_router(leads_router)
api.include_router(leads_lifecycle_router)
api.include_router(inbox_router)
api.include_router(deals_router)
api.include_router(documents_router)
api.include_router(webhooks_router)
api.include_router(capture_router)
api.include_router(projects_router)
api.include_router(construction_router)
api.include_router(materials_router)
api.include_router(finance_config_router)
api.include_router(ar_router)
api.include_router(ap_router)
api.include_router(commissions_router)
api.include_router(cashflow_router)
api.include_router(reports_router)
api.include_router(realtime_router)
api.include_router(customers_router)
api.include_router(financing_router)
api.include_router(files_router)
api.include_router(portal_router)
api.include_router(complaints_router)
api.include_router(permits_router)
api.include_router(field_router)
api.include_router(subcon_router)
api.include_router(subcon_claims_router)
api.include_router(spk_scope_router)
api.include_router(inspection_router)
api.include_router(boq_router)
api.include_router(procurement_router)
api.include_router(gl_router)
api.include_router(gl_reports_router)
api.include_router(survey_router)
api.include_router(tax_router)
api.include_router(omnichannel_router)
api.include_router(broadcasts_router)
api.include_router(orgs_router)
api.include_router(reference_router)
api.include_router(master_router)
api.include_router(site_plan_router)
api.include_router(petty_cash_router)
api.include_router(fixed_assets_router)
api.include_router(loans_router)
api.include_router(marketing_fee_router)
api.include_router(public_router)
api.include_router(build_router)
api.include_router(build_ops_router)
api.include_router(build_bulk_router)
api.include_router(build_calendar_router)
api.include_router(build_calibration_router)
# Fase 39 (Fondasi Data V2): Pusat Konfigurasi + hierarki proyek/cluster/blok/unit +
# katalog master (tipe unit, spek tambahan, komponen biaya) + master dokumen syarat.
api.include_router(settings_router)
api.include_router(masterplan_router)
api.include_router(catalog_router)
api.include_router(docreq_router)
# Fase 41 — umur tahap & kebijakan SLA (satu sumber ambang untuk semua daftar).
api.include_router(aging_router)
# Fase 42 — mitra & fee (master mitra, aturan fee, atribusi, analitik).
api.include_router(partners_router)
api.include_router(ads_router)
api.include_router(analytics_router)
# Fase 45 — target proyek (5 metode, dinamis) & master anggaran + realisasi RAB 3 lapis.
api.include_router(targets_router)
api.include_router(budget_router)
api.include_router(build_board_router)
# Fase 47 — uang masuk yang bisa dibuktikan (rekonsiliasi bank + bukti transfer portal),
# penawaran/simulasi harga untuk lead, dan absensi + upah harian tenaga kerja.
api.include_router(bank_router)
api.include_router(intake_router)
api.include_router(quotations_router)
api.include_router(labor_router)
# Fase 48 — pengadaan & subkon lanjutan: master vendor + daftar harga (48A), permintaan
# lapangan → PO + retur barang + 3-way match yang MENAHAN (48B), uang muka/potongan/retensi
# subkon (48C), evaluasi berbukti (48D), dan kendali stok antar proyek (48E).
api.include_router(vendors_router)
api.include_router(procurement_extra_router)
api.include_router(subcon_finance_router)
api.include_router(stock_router)
# Fase 49 — penutupan buku bergigi (daftar periksa + tutup tahun), laporan owner, dan
# kepatuhan pajak: faktur pengganti/batal + ekspor e-Faktur, bukti potong (e-Bupot) dengan
# pembetulan bernomor tetap, serta rekap SPT Masa PPN yang bisa direkonstruksi.
api.include_router(tax_compliance_router)
api.include_router(handover_router)
api.include_router(reminders_router)
api.include_router(contracts_router)
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    # Fase 54 — `X-Session-State` membawa SEBAB sebuah permintaan ditolak (missing/expired/
    # invalid/revoked). Tanpa didaftarkan di sini, peramban menyembunyikannya dari
    # JavaScript (aturan CORS), sehingga frontend kembali harus menebak: setiap 401 dianggap
    # "sesi mati" dan pengguna dilempar keluar walau sesinya sebenarnya masih bisa
    # diperpanjang diam-diam.
    expose_headers=["X-Session-State"],
)
