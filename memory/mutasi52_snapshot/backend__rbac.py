"""RBAC + tenant scope. Enforced from Fase 0 (fix #1 of old SIPRO).

- permission_settings.matrix is the SSOT (admin-overridable); DEFAULT_PERMISSIONS is fallback.
- require_permission(resource, action) is a FastAPI dependency.
- scope_query applies org_id + row-level scope (sales = own; pm/site = assigned project).
"""
from fastapi import Depends, HTTPException

from db import db, ORG_ID
from core_utils import new_id, now_iso
from security import get_current_user

# Roles that see everything within their org.
FULL_ACCESS_ROLES = {"super_admin", "owner"}
# Roles limited to their own assigned rows.
SALES_SCOPED_ROLES = {"sales"}
# Roles limited to their assigned projects.
PROJECT_SCOPED_ROLES = {"project_manager", "site_engineer"}

ALL_ROLES = [
    "super_admin", "owner", "sales_manager", "marketing_admin",
    "sales", "finance", "project_manager", "site_engineer",
    # Fase 29 — divisi Digital Marketing (baru) & supervisor Keuangan
    "dm_supervisor", "dm_staff", "finance_manager",
]

# Fase 29: peran baru MEWARISI matriks peran yang paling dekat supaya tidak perlu
# menulis ulang seluruh matriks (dan supaya izin lama tidak berubah diam-diam).
ROLE_INHERITS = {
    "dm_supervisor": "marketing_admin",
    "dm_staff": "marketing_admin",
    "finance_manager": "finance",
}
# Aksi yang DICABUT dari peran turunan (staf digital marketing tidak boleh menghapus
# atau membagi ulang lead milik sales, dan tidak boleh menyetujui apa pun).
ROLE_DENY = {
    "dm_staff": {"delete", "assign", "approve", "sign", "manage"},
}
# Tambahan izin khusus peran baru (supervisor keuangan boleh menyetujui, supervisor
# digital marketing mengelola otomasi/template/showroom).
ROLE_GRANTS = {
    # Fase 39b: verifikasi dokumen syarat. Ditulis sebagai grant eksplisit (bukan hanya di
    # DEFAULT_PERMISSIONS) karena matriks RBAC organisasi yang sudah tersimpan di DB
    # MENIMPA daftar izin per peran — tanpa ini, aksi `verify` tidak akan pernah aktif pada
    # organisasi yang matriksnya dibuat sebelum fase ini, dan tombol Verifikasi jadi 403.
    "sales_manager": {"documents": ["verify"]},
    "marketing_admin": {"documents": ["verify"]},
    "finance": {"documents": ["verify"]},
    # Fase 31: Manajer Proyek adalah VERIFIKATOR pekerjaan unit (approve pada
    # `construction`). Ditulis sebagai grant eksplisit, bukan hanya di
    # DEFAULT_PERMISSIONS, supaya izin baru tetap berlaku pada organisasi yang
    # dokumen matriks RBAC-nya sudah tersimpan sebelum fase ini.
    "project_manager": {
        "construction": ["approve"],
    },
    "finance_manager": {
        "finance": ["approve"], "commissions": ["approve"], "marketing_fee": ["approve"],
        "petty_cash": ["approve"], "gl": ["manage"], "work_tasks": ["view_all", "create", "update"],
        "documents": ["verify"],   # Fase 39b — supervisor keuangan ikut memverifikasi berkas
        # Fase 47: supervisor keuangan adalah satu-satunya yang boleh MEMBATALKAN
        # pencocokan bank (membalik pembukuan) dan menyetujui/membayar upah harian.
        "bank": ["view_all", "create", "update", "approve"],
        "labor": ["view_all", "approve"],
        # Fase 50A: MENEROBOS daftar periksa serah terima & MEMBATALKAN BAST yang salah
        # terbit adalah keputusan manajerial (kunci diserahkan walau ada yang belum beres,
        # atau dokumen resmi ditarik kembali). Tim proyek/keuangan tetap yang menerbitkan.
        "handover": ["view_all", "create", "override", "cancel"],
        "warranty": ["view_all"],
    },
    "dm_supervisor": {
        "automation_rules": ["manage"], "wa_templates": ["manage"], "channels": ["manage"],
        "broadcasts": ["manage"], "showroom": ["view_all", "update"],
        "work_tasks": ["view_all", "create", "update"],
        # Fase 43: supervisor DM adalah pemilik anggaran iklan \u2014 hanya dia yang boleh
        # MENARIK data dari platform & MENGIRIM ULANG event konversi ke sistem luar.
        "ads": ["manage"],
    },
    "dm_staff": {
        "automation_rules": ["view_all"], "wa_templates": ["view_all", "create", "update"],
        "broadcasts": ["view_all", "create"], "inbox": ["view_all", "create"],
        "work_tasks": ["view_own", "create", "update"],
    },
}

# resource -> role -> [actions]. Actions: view_all|view_own|view|create|update|
# delete|approve|assign|sign|manage. super_admin/owner => implicit all.
DEFAULT_PERMISSIONS = {
    "leads": {
        "sales_manager": ["view_all", "create", "update", "assign", "delete"],
        "marketing_admin": ["view_all", "create", "update", "assign"],
        "sales": ["view_own", "create", "update"],
        "finance": ["view_all"],
    },
    "deals": {
        "sales_manager": ["view_all", "create", "update"],
        "marketing_admin": ["view_all", "create", "update"],
        "sales": ["view_own", "create", "update"],
        "finance": ["view_all"],
    },
    "reservations": {
        "sales_manager": ["view_all", "create", "update"],
        "marketing_admin": ["view_all", "create", "update"],
        "sales": ["view_own", "create", "update"],
        "finance": ["view_all"],
    },
    "documents": {
        # Fase 39b — aksi `verify` DIPISAH dari `update`. Sebelum ini sales (yang MENGUNGGAH
        # dokumen) juga bisa memverifikasi dokumennya sendiri, sehingga "gerbang bukti"
        # kehilangan artinya. Tabel izin `docs/v2/24_CRM_LEAD_SPEC.md` §13 menegaskan:
        # verifikasi dokumen = sales ✖, sales_manager ✔, marketing_admin ✔, finance ✔,
        # owner/super_admin ✔ (FULL_ACCESS).
        "sales_manager": ["view_all", "create", "update", "sign", "verify"],
        "marketing_admin": ["view_all", "create", "update", "manage", "verify"],
        "sales": ["view_own", "create", "update", "sign"],
        "finance": ["view_all", "verify"],
    },
    "projects": {
        "sales_manager": ["view_all"], "marketing_admin": ["view_all"],
        "sales": ["view_all"], "finance": ["view_all"],
        "project_manager": ["view_all", "create", "update"],
        "site_engineer": ["view_all"],
    },
    "units": {
        "sales_manager": ["view_all"], "marketing_admin": ["view_all"],
        "sales": ["view_all"], "finance": ["view_all"],
        "project_manager": ["view_all", "update"], "site_engineer": ["view_all"],
    },
    "construction": {
        "finance": ["view_all"],
        # Fase 31: `approve` = verifikasi hasil pekerjaan unit, tolak, dan menerobos
        # gerbang mutu. Site engineer sengaja TIDAK punya `approve` (pemisahan tugas:
        # yang mengerjakan tidak boleh memverifikasi pekerjaannya sendiri).
        "project_manager": ["view_all", "create", "update", "approve"],
        "site_engineer": ["view_all", "create", "update"],
    },
    "materials": {
        # Phase 18 SoD: site MENGAJUKAN + keluarkan (create/update); PM MENYETUJUI (approve).
        "finance": ["view_all"],
        "project_manager": ["view_all", "create", "update", "approve"],
        "site_engineer": ["view_all", "create", "update"],
    },
    "finance": {
        "sales_manager": ["view_all"],
        "finance": ["view_all", "create", "update", "approve"],
        "project_manager": ["view_all"],
    },
    "commissions": {
        "sales_manager": ["view_all"], "marketing_admin": ["view_all"],
        "sales": ["view_own"], "finance": ["view_all", "approve"],
    },
    "customers": {
        "sales_manager": ["view_all", "create", "update"],
        "marketing_admin": ["view_all", "create", "update"],
        "sales": ["view_all", "create", "update"],
        "finance": ["view_all"],
    },
    "financing": {
        "sales_manager": ["view_all", "create", "update", "approve"],
        "marketing_admin": ["view_all"],
        "sales": ["view_own", "create", "update"],
        "finance": ["view_all", "create", "update", "approve"],
    },
    "complaints": {
        "sales_manager": ["view_all", "update", "assign", "create"],
        "marketing_admin": ["view_all", "update", "assign", "create"],
        "sales": ["view_own", "update", "create"],
        "finance": ["view_all"],
    },
    "permits": {
        "sales_manager": ["view_all"],
        "finance": ["view_all"],
        "project_manager": ["view_all", "create", "update"],
        "site_engineer": ["view_all", "update"],
    },
    # Fase 47A — mutasi rekening: data kas yang sensitif. Sales & peran lapangan TIDAK
    # punya akses sama sekali. `approve` (membatalkan pencocokan = membalik pembukuan)
    # sengaja lebih ketat daripada `update` (mencocokkan).
    "bank": {
        "finance": ["view_all", "create", "update"],
        "sales_manager": [],
        "project_manager": [],
    },
    # Fase 47C — penawaran: sales membuat miliknya sendiri, manajer memutuskan diskon.
    "quotations": {
        "sales_manager": ["view_all", "create", "update", "approve"],
        "marketing_admin": ["view_all", "create", "update"],
        "sales": ["view_own", "create", "update"],
        "finance": ["view_all"],
    },
    # Fase 47D — absensi & upah: lapangan/PM mencatat, keuangan menyetujui & membayar
    # (yang mencatat kehadiran tidak boleh menyetujui pembayarannya sendiri).
    "labor": {
        "project_manager": ["view_all", "create", "update"],
        "site_engineer": ["view_all", "create", "update"],
        "finance": ["view_all", "approve"],
        "sales_manager": ["view_all"],
    },
    # Fase 48A \u2014 master vendor & daftar harga. Pengadaan (PM/site) dan keuangan sama-sama
    # perlu melihat & mencatat harga; hanya `finance_manager` yang boleh menonaktifkan
    # vendor bermasalah (aksi `manage`) agar daftar rekanan tidak diubah diam-diam.
    "vendors": {
        "finance": ["view_all", "create", "update"],
        "finance_manager": ["view_all", "create", "update", "manage"],
        "project_manager": ["view_all", "create", "update"],
        "site_engineer": ["view_all"],
        "sales_manager": ["view_all"],
    },
    # Fase 48C \u2014 uang muka, potongan & retensi subkon. SoD paling ketat di aplikasi ini:
    # lapangan/PM MENGAJUKAN (`create`), finance MEMBAYAR (`approve`), dan hanya
    # `finance_manager` yang MEMUTUSKAN uang muka + MENCAIRKAN retensi (`manage`).
    "subcon_finance": {
        "project_manager": ["view_all", "create", "update"],
        "site_engineer": ["view_all", "create"],
        "finance": ["view_all", "approve"],
        # Fase 51A: `override` = mengabaikan penahanan pencairan retensi (masa pemeliharaan,
        # punch list, atau KLAIM GARANSI yang masih berjalan). Sengaja dipisah dari `manage`
        # supaya bisa dicabut tanpa mencabut hak mencairkan, dan supaya `finance` biasa serta
        # PM tidak pernah bisa membatalkan jaminan mutu secara diam-diam.
        "finance_manager": ["view_all", "create", "update", "approve", "manage", "override"],
    },
    # Fase 51B: pengingat WhatsApp otomatis (garansi hampir habis, termin, tunggakan).
    # SEMUA peran yang berhubungan dengan pembeli boleh MELIHAT riwayat & kandidat — "apakah
    # pembeli ini sudah diingatkan?" adalah pertanyaan kerja harian. Yang MENJALANKAN hanya
    # peran pengelola, karena menjalankannya berarti mengirim pesan ke pelanggan.
    "reminders": {
        "sales_manager": ["view_all", "manage"],
        "marketing_admin": ["view_all", "manage"],
        "dm_supervisor": ["view_all", "manage"],
        "finance": ["view_all"],
        "finance_manager": ["view_all", "manage"],
        "project_manager": ["view_all"],
        "sales": ["view_all"],
    },
    # Phase 12 — Procurement pillar
    "boq": {
        "sales_manager": ["view_all"],
        "finance": ["view_all"],
        "project_manager": ["view_all", "create", "update", "delete"],
        "site_engineer": ["view_all"],
    },
    "subcon": {
        "finance": ["view_all"],
        "project_manager": ["view_all", "create", "update"],
        "site_engineer": ["view_all"],
    },
    # Phase 16 — EPIC 2.3 Progress Claim (Termin) & Change Order.
    # SoD: field (site/PM) mengajukan & opname; finance/owner MENYETUJUI (-> tagihan AP / ubah nilai kontrak).
    "progress_claims": {
        "finance": ["view_all", "approve"],
        "project_manager": ["view_all", "create", "update"],
        "site_engineer": ["view_all", "create", "update"],
    },
    "change_orders": {
        "finance": ["view_all", "approve"],
        "project_manager": ["view_all", "create", "update"],
        "site_engineer": ["view_all"],
    },
    "procurement": {
        # Segregation of duties: PM/site raise POs, GRNs & bills; finance/owner APPROVE.
        "finance": ["view_all", "create", "approve"],
        "project_manager": ["view_all", "create", "update"],
        "site_engineer": ["view_all", "create"],
    },
    # Phase 13 — CoA / General Ledger (sensitive: finance + owner/super_admin only)
    # Fase 49A/49B: dua aksi baru yang SENGAJA tidak diberikan ke `finance` —
    # `close_override` (menutup bulan walau daftar periksa belum bersih) dan `year_close`
    # (memindah laba tahun berjalan ke Laba Ditahan / membalikkannya). Keduanya mengubah
    # angka yang sudah dilaporkan, jadi kewenangannya berhenti di Manajer Keuangan &
    # Direksi (lihat ROLE_GRANTS["finance_manager"]["gl"] = manage dan FULL_ACCESS_ROLES).
    "gl": {
        "finance": ["view_all", "create", "update"],
    },
    "files": {
        "sales_manager": ["view_all", "create"],
        "marketing_admin": ["view_all", "create"],
        "sales": ["view_all", "create"],
        "finance": ["view_all", "create"],
        "project_manager": ["view_all", "create"],
        "site_engineer": ["view_all", "create"],
    },
    # Fase 28b — halaman showroom PUBLIK (tautan marketing tanpa login). Dipisah dari
    # resource `projects` supaya marketing/sales manager bisa membuka & menutup tautan
    # tanpa diberi hak mengubah master proyek.
    "showroom": {
        "sales_manager": ["view_all", "update"],
        "marketing_admin": ["view_all", "update"],
        "project_manager": ["view_all", "update"],
        "sales": ["view_all"],
        "finance": ["view_all"],
        "site_engineer": [],
    },
    "work_tasks": {
        "sales_manager": ["view_all", "create", "update"],
        "marketing_admin": ["view_all", "create", "update"],
        "sales": ["view_own", "create", "update"],
        "finance": ["view_all", "create", "update"],
        "project_manager": ["view_all", "create", "update"],
        "site_engineer": ["view_own", "create", "update"],
    },
    "activities": {
        "sales_manager": ["view", "create"], "marketing_admin": ["view", "create"],
        "sales": ["view", "create"], "finance": ["view", "create"],
        "project_manager": ["view", "create"], "site_engineer": ["view", "create"],
    },
    "notifications": {
        "sales_manager": ["view_own", "update"], "marketing_admin": ["view_own", "update"],
        "sales": ["view_own", "update"], "finance": ["view_own", "update"],
        "project_manager": ["view_own", "update"], "site_engineer": ["view_own", "update"],
    },
    "automation_rules": {
        "sales_manager": ["manage"], "marketing_admin": ["manage"],
    },
    # EPIC 1.7 — WA message templates + channel accounts (omnichannel config)
    "wa_templates": {
        "sales_manager": ["manage"], "marketing_admin": ["manage"],
    },
    "channels": {
        "sales_manager": ["manage"], "marketing_admin": ["manage"],
    },
    "broadcasts": {
        "sales_manager": ["manage"], "marketing_admin": ["manage"],
    },
    "inbox": {
        "sales_manager": ["view_all", "create"], "marketing_admin": ["view_all", "create"],
        "sales": ["view_own", "create"],
    },
    "appointments": {
        "sales_manager": ["view_all", "create", "update"],
        "marketing_admin": ["view_all", "create", "update"],
        "sales": ["view_own", "create", "update"],
        # Fase 52 — keuangan boleh MEMBACA jadwal survei/janji temu, TIDAK menjadwalkan.
        # Tanpa baris ini matriksnya tidak konsisten dengan dirinya sendiri: `surveys`
        # (kunjungan lokasi) sudah memberi finance ["view_all"] sejak Fase 14, sedangkan
        # `appointments` — JANJI TEMU dari survei yang sama — tidak menyebut finance sama
        # sekali. Akibatnya `GET /api/appointments?lead_id=…` menjawab 403 untuk peran yang
        # justru punya `leads:view_all`, dan tab "Survey" di profil lead menjadi jebakan.
        # Sengaja HANYA baca: yang menjadwalkan survei tetap sales/marketing (pemisahan
        # tugas), jadi tidak ada `create`/`update` di sini.
        "finance": ["view_all"],
        "finance_manager": ["view_all"],
    },
    # Phase 14 — EPIC 1.2 Survey (kunjungan lokasi/unit): terikat lead + appointment
    "surveys": {
        "sales_manager": ["view_all", "create", "update"],
        "marketing_admin": ["view_all", "create", "update"],
        "sales": ["view_own", "create", "update"],
        "finance": ["view_all"],
    },
    "users": {},          # only super_admin/owner
    "permissions": {},    # only super_admin/owner
    "audit_logs": {"finance": ["view_all"]},
    # Phase 15 — EPIC 3.3 Perpajakan (PPN/PPh/BPHTB + Faktur Pajak): finance + owner/super_admin
    # Fase 49E/49F/49G menambah aksi `export` (mengeluarkan berkas e-Faktur/e-Bupot untuk
    # diunggah ke DJP) dan `withholding_issue` (menerbitkan bukti potong bernomor). Keduanya
    # tercakup `manage` milik finance; peran lain tetap 403 karena berkas pajak adalah
    # pernyataan resmi perusahaan.
    "tax": {"finance": ["manage"]},
    # ---------------- Fase 50A: serah terima unit & garansi pasca-huni ----------------
    # Pemisahan tugas yang SENGAJA: yang menerbitkan BAST (tim proyek & keuangan) bukan yang
    # boleh MENEROBOS daftar periksanya. Terobosan berarti kunci diserahkan walau temuan
    # masih terbuka / pembayaran belum beres — itu keputusan manajerial, jadi berhenti di
    # Manajer Keuangan & Direksi (lihat ROLE_GRANTS["finance_manager"]["handover"]).
    "handover": {
        "finance": ["view_all", "create"],
        "project_manager": ["view_all", "create"],
        "site_engineer": ["view_all"],
        "sales_manager": ["view_all"],
        "marketing_admin": ["view_all"],
        "sales": ["view_all"],
    },
    # Klaim garansi: CS/sales MENGAJUKAN (dari komplain pembeli), tim proyek MENGERJAKAN,
    # dan pemeriksaan mutu (`approve`) dipegang Manajer Proyek — supaya yang mengerjakan
    # perbaikan tidak bisa menyatakan pekerjaannya sendiri lulus.
    "warranty": {
        "finance": ["view_all"],
        "project_manager": ["view_all", "create", "update", "approve"],
        "site_engineer": ["view_all", "create", "update"],
        "sales_manager": ["view_all", "create"],
        "marketing_admin": ["view_all", "create"],
        "sales": ["view_all", "create"],
    },
    # ---------------- Fase 27 ----------------
    # Kas Bon: SEMUA peran boleh mengajukan (view_own), finance/owner MENYETUJUI & MENCAIRKAN.
    "petty_cash": {
        "sales_manager": ["view_all", "create", "update"],
        "marketing_admin": ["view_own", "create", "update"],
        "sales": ["view_own", "create", "update"],
        "finance": ["view_all", "create", "update", "approve"],
        "project_manager": ["view_all", "create", "update"],
        "site_engineer": ["view_own", "create", "update"],
    },
    # Aset tetap & penyusutan: keputusan akuntansi -> finance/owner. PM boleh melihat.
    "fixed_assets": {
        "finance": ["view_all", "create", "update", "approve"],
        "project_manager": ["view_all"],
    },
    # Pembiayaan korporat (utang bank/leasing): sensitif -> finance + owner/super_admin.
    "loans": {
        "finance": ["view_all", "create", "update", "approve"],
    },
    # Marketing fee agen eksternal: sales/marketing mengajukan, finance/owner menyetujui+bayar.
    "marketing_fee": {
        "sales_manager": ["view_all", "create", "update"],
        "marketing_admin": ["view_all", "create", "update"],
        "sales": ["view_own", "create"],
        "finance": ["view_all", "update", "approve"],
    },
    # ---------------- Fase 39 (Fondasi Data V2) ----------------
    # `settings` = Pusat Konfigurasi (aturan bisnis). Hanya super_admin/owner yang boleh
    # MENGUBAH (keduanya FULL_ACCESS); peran lain boleh MELIHAT agar tahu aturan yang berlaku.
    "settings": {
        "sales_manager": ["view_all"], "marketing_admin": ["view_all"],
        "finance": ["view_all"], "finance_manager": ["view_all"],
        "project_manager": ["view_all"], "sales": ["view_all"], "site_engineer": ["view_all"],
    },
    # `catalog` = master tipe unit, spek tambahan (add-on), komponen biaya.
    "catalog": {
        "sales_manager": ["view_all", "create", "update"],
        "marketing_admin": ["view_all"], "sales": ["view_all"],
        "finance": ["view_all", "update"], "finance_manager": ["view_all", "update"],
        "project_manager": ["view_all", "create", "update"], "site_engineer": ["view_all"],
    },
    # `doc_requirements` = master dokumen syarat per tahap/skema/mitra.
    "doc_requirements": {
        "sales_manager": ["view_all", "create", "update"],
        "marketing_admin": ["view_all", "create", "update"],
        "sales": ["view_all"], "finance": ["view_all", "update"],
        "finance_manager": ["view_all", "update"], "project_manager": ["view_all"],
        "site_engineer": ["view_all"],
    },
    # ---------------- Fase 41 (jam tahap) & Fase 42 (mitra & fee) ----------------
    # `aging` = laporan umur tahap & kebijakan SLA. SEMUA peran boleh MELIHAT (angka ini
    # dipakai untuk kerja harian: "punya saya yang mana yang lewat SLA?"), tetapi hanya
    # admin/owner (FULL_ACCESS) yang boleh MENJALANKAN pemeliharaan `reconcile`.
    "aging": {
        "sales_manager": ["view_all"], "marketing_admin": ["view_all"],
        "sales": ["view_all"], "finance": ["view_all"], "finance_manager": ["view_all"],
        "project_manager": ["view_all"], "site_engineer": ["view_all"],
        "dm_supervisor": ["view_all"], "dm_staff": ["view_all"],
    },
    # `partners` = master mitra + aturan fee. Yang MENGUBAH aturan fee menyangkut uang,
    # jadi sales biasa hanya boleh MELIHAT (agar bisa memilih mitra saat membuat lead).
    # Persetujuan & pembayaran tagihan fee tetap memakai resource `marketing_fee`.
    "partners": {
        "sales_manager": ["view_all", "create", "update"],
        "marketing_admin": ["view_all", "create", "update"],
        "dm_supervisor": ["view_all", "create", "update"],
        "sales": ["view_all"], "dm_staff": ["view_all"],
        "finance": ["view_all", "update"], "finance_manager": ["view_all", "update"],
        "project_manager": ["view_all"],
    },
    # ---------------- Fase 43 (kampanye & biaya iklan, atribusi/CAPI) ----------------
    # `ads` = master kampanye, biaya iklan (manual/CSV/API), kinerja, atribusi & event CAPI.
    # Pemisahan tugas yang BENAR-BENAR dipaksakan (diperbaiki Fase 44 — komentar lama
    # mengklaim `update` hanya milik supervisor DM, padahal `dm_staff` MEWARISI izin
    # `marketing_admin` lewat ROLE_INHERITS sehingga ia juga bisa mengomit impor; komentar
    # yang berbeda dengan kode adalah cara tercepat membuat orang salah menyimpulkan siapa
    # boleh apa):
    #   * marketing_admin, dm_supervisor, dm_staff → view/create/update (isi biaya harian,
    #     daftarkan kampanye, komit impor). `dm_staff` mendapatkannya dari pewarisan.
    #   * HANYA dm_supervisor (+ owner/super_admin) → `manage`: menarik data platform &
    #     mengirim ulang event CAPI, yaitu aksi yang MENYENTUH SISTEM LUAR. `dm_staff`
    #     dicabut `manage` lewat ROLE_DENY, jadi tombol itu memang tidak untuk dia.
    #   * Keuangan MELIHAT (biaya iklan adalah beban yang mereka bukukan) tetapi TIDAK boleh
    #     mengarang angka kampanye.
    #   * sales/PM/pelaksana lapangan: tidak ada akses (anggaran iklan bukan urusan mereka).
    "ads": {
        "sales_manager": ["view_all", "create", "update"],
        "marketing_admin": ["view_all", "create", "update"],
        "finance": ["view_all"], "finance_manager": ["view_all"],
        "project_manager": [], "site_engineer": [], "sales": [],
    },
    # ---------------- Fase 44 (Analitik & BI) ----------------
    # `analytics` = 5 dashboard metrik + kamus metrik + ekspor. SEMUA peran boleh MELIHAT —
    # angka adalah alat kerja, bukan hak istimewa — tetapi row-scope tetap berlaku: peran
    # dalam `SALES_SCOPED_ROLES` hanya melihat data yang ia tangani (dipaksakan server lewat
    # `owner_email`, bukan disembunyikan di layar). `manage` (menghitung ulang snapshot)
    # hanya untuk owner/super_admin + supervisor divisi yang memang bertanggung jawab atas
    # angkanya, karena hitung-ulang menyentuh seluruh koleksi.
    "analytics": {
        "sales_manager": ["view_all", "manage"], "marketing_admin": ["view_all"],
        "sales": ["view_own"], "finance": ["view_all"],
        "finance_manager": ["view_all", "manage"],
        "project_manager": ["view_all", "manage"], "site_engineer": ["view_all"],
        "dm_supervisor": ["view_all", "manage"], "dm_staff": ["view_all"],
    },
    # ---------------- Fase 45 (Target Proyek & Budget/RAB) ----------------
    # `targets` = target unit & pendapatan per proyek/cluster/sales.
    #   * `manage` = mengaktifkan & menutup target. Dipisah dari `update` karena
    #     MENGAKTIFKAN target berarti menjadikannya rencana RESMI perusahaan — itu keputusan
    #     manajemen, bukan penyuntingan biasa.
    #   * sales hanya `view_own`: ia melihat target NAMANYA sendiri (dipaksakan server lewat
    #     `owner_email`), bukan target proyek milik semua orang.
    #   * pelaksana lapangan tidak punya akses: target penjualan bukan urusannya.
    "targets": {
        "sales_manager": ["view_all", "create", "update", "manage"],
        "marketing_admin": ["view_all"],
        "sales": ["view_own"],
        "finance": ["view_all"], "finance_manager": ["view_all", "manage"],
        "project_manager": ["view_all"], "site_engineer": [],
        "dm_supervisor": ["view_all"], "dm_staff": ["view_all"],
    },
    # `budget` = master item anggaran + realisasi 3 lapis + margin + peringatan.
    # Pemisahan tugas yang DIPAKSAKAN (dan diuji, jadi jangan dianggap cacat):
    #   * PM & finance MENYUSUN item anggaran (`create`/`update`);
    #   * hanya `approve` (manajer keuangan + owner/super_admin) yang boleh MEREVISI
    #     rencana anggaran — yang menyusun anggaran tidak menyetujui perubahannya sendiri;
    #   * `manage` (jalankan pemeriksaan ambang) juga khusus manajer keuangan/owner;
    #   * sales tidak punya akses (anggaran proyek bukan urusannya) → 403 yang benar.
    "budget": {
        "sales_manager": ["view_all"],
        "marketing_admin": ["view_all"],
        "sales": [],
        "finance": ["view_all", "create", "update"],
        "finance_manager": ["view_all", "create", "update", "approve", "manage"],
        "project_manager": ["view_all", "create", "update", "delete"],
        "site_engineer": ["view_all"],
        "dm_supervisor": ["view_all"], "dm_staff": ["view_all"],
    },
}


def _permitted(perms, action) -> bool:
    if "all" in perms or "manage" in perms:
        return True
    if action in perms:
        return True
    if action == "view" and any(a in perms for a in ("view", "view_all", "view_own")):
        return True
    return False


async def get_matrix() -> dict:
    """Matriks efektif = DEFAULT_PERMISSIONS + override tersimpan di DB.

    Digabung (bukan diganti) supaya resource/peran BARU dari kode langsung berlaku
    walau dokumen matriks di DB dibuat sebelum fase ini (dulu: matriks DB menang total,
    sehingga resource baru tak pernah aktif sampai admin menyimpan ulang).
    """
    merged = {res: dict(roles) for res, roles in DEFAULT_PERMISSIONS.items()}
    doc = await db.permission_settings.find_one({"key": "rbac_matrix"}, {"_id": 0})
    for res, roles in ((doc or {}).get("matrix") or {}).items():
        merged.setdefault(res, {}).update(roles or {})
    return merged


def _role_perms(matrix: dict, resource: str, role: str) -> list:
    """Izin efektif satu peran: matriks langsung → warisan peran → tambahan khusus."""
    return _role_perms_detail(matrix, resource, role)["perms"]


# Aksi yang dikenal mesin RBAC. Dipakai layar Hak Akses untuk menawarkan pilihan yang
# BENAR-BENAR berarti (bukan kotak centang karangan) dan untuk menolak aksi asing.
KNOWN_ACTIONS = ["view", "view_all", "view_own", "create", "update", "delete", "assign",
                 "approve", "verify", "sign", "override", "cancel", "manage", "all"]


def _role_perms_detail(matrix: dict, resource: str, role: str) -> dict:
    """Izin efektif + ASAL-USULNYA, supaya layar Hak Akses bisa jujur.

    Asal-usul (`sources`) penting karena tiga lapis aturan bertumpuk:
      * `matrix`    — matriks tersimpan/bawaan (bisa diubah admin),
      * `inherited` — peran baru mewarisi peran terdekat (`ROLE_INHERITS`),
      * `granted`   — tambahan yang dipasang di kode (`ROLE_GRANTS`).

    Tanpa ini layar Hak Akses menampilkan sel KOSONG untuk peran turunan (dm_staff,
    dm_supervisor, finance_manager) padahal API-nya menjawab 200 — layar keamanan yang
    berbohong, tepatnya jenis kebohongan yang paling berbahaya.

    **Daftar KOSONG yang tertulis eksplisit = PENCABUTAN.** Sebelum ini `[]` dianggap
    "belum diatur" sehingga warisan peran dan grant kode menghidupkannya kembali: admin
    mencabut izin di layar, sistem menjawab "tersimpan", dan aksesnya tetap ada. Sekarang
    kunci yang ADA tetapi kosong berarti tidak boleh — warisan & grant tidak dipakai.
    """
    res_map = matrix.get(resource) or {}
    sources, inherited_from = [], None
    if role in res_map:
        perms = list(res_map[role] or [])
        if not perms:
            return {"perms": [], "sources": ["revoked"], "inherited_from": None,
                    "revoked": True}
        sources.append("matrix")
    elif role in ROLE_INHERITS:
        inherited_from = ROLE_INHERITS[role]
        perms = list(res_map.get(inherited_from) or [])
        if perms:
            sources.append("inherited")
        else:
            inherited_from = None
    else:
        perms = []
    grants = list((ROLE_GRANTS.get(role) or {}).get(resource) or [])
    if grants:
        perms += grants
        sources.append("granted")
    deny = ROLE_DENY.get(role)
    dicabut_kode = []
    if deny:
        dicabut_kode = sorted({p for p in perms if p in deny})
        perms = [p for p in perms if p not in deny]
    return {"perms": sorted(set(perms)), "sources": sources,
            "inherited_from": inherited_from, "revoked": False,
            "denied_by_code": dicabut_kode}


def effective_matrix(matrix: dict) -> dict:
    """Matriks EFEKTIF untuk semua peran × resource (dengan asal-usulnya).

    Inilah yang harus dilihat admin: hasil akhir yang ditegakkan `require_permission`,
    bukan hanya baris yang kebetulan tertulis di dokumen matriks.
    """
    out = {}
    for resource in matrix:
        out[resource] = {}
        for role in ALL_ROLES:
            if role in FULL_ACCESS_ROLES:
                out[resource][role] = {"perms": ["all"], "sources": ["full_access"],
                                       "inherited_from": None, "revoked": False,
                                       "denied_by_code": []}
                continue
            out[resource][role] = _role_perms_detail(matrix, resource, role)
    return out


def validate_matrix(candidate: dict) -> list:
    """Periksa matriks kiriman admin. Mengembalikan daftar galat berbahasa manusia.

    Menolak lebih baik daripada menyimpan diam-diam sesuatu yang tidak akan pernah
    berlaku: resource/peran/aksi yang tidak dikenal mesin RBAC hanya akan jadi baris mati
    di database dan membuat layar Hak Akses menjanjikan hal yang tidak ditegakkan.
    """
    errors = []
    if not isinstance(candidate, dict) or not candidate:
        return ["Matriks izin kosong atau bukan objek."]
    for resource, roles in candidate.items():
        if resource not in DEFAULT_PERMISSIONS:
            errors.append(f"Resource '{resource}' tidak dikenal mesin RBAC.")
            continue
        if not isinstance(roles, dict):
            errors.append(f"Isi resource '{resource}' harus objek peran → daftar aksi.")
            continue
        for role, perms in roles.items():
            if role not in ALL_ROLES:
                errors.append(f"Peran '{role}' (resource '{resource}') tidak dikenal.")
                continue
            if role in FULL_ACCESS_ROLES:
                errors.append(
                    f"Peran '{role}' selalu berakses penuh dan tidak bisa dibatasi dari "
                    "layar ini — mencabutnya akan mengunci semua orang keluar.")
                continue
            if perms is None:
                continue
            if not isinstance(perms, list):
                errors.append(f"Aksi untuk '{role}' pada '{resource}' harus berupa daftar.")
                continue
            asing = [p for p in perms if p not in KNOWN_ACTIONS]
            if asing:
                errors.append(f"Aksi tidak dikenal pada '{resource}' → '{role}': "
                              + ", ".join(map(str, asing)))
    return errors



async def can(role: str, resource: str, action: str) -> bool:
    if role in FULL_ACCESS_ROLES:
        return True
    matrix = await get_matrix()
    return _permitted(_role_perms(matrix, resource, role), action)


async def effective_permissions(role: str) -> dict:
    """Izin efektif satu peran untuk SELURUH resource — dipakai `GET /auth/me`.

    Tujuannya agar frontend bisa menyembunyikan aksi yang pasti ditolak backend tanpa
    menyalin aturan RBAC (dulu satu-satunya cara adalah menebak dari nama peran, yang
    membuat aturan punya dua versi). Peran FULL_ACCESS ditandai `"*": ["*"]`.
    """
    if role in FULL_ACCESS_ROLES:
        return {"*": ["*"]}
    matrix = await get_matrix()
    out = {}
    for resource in matrix:
        perms = _role_perms(matrix, resource, role)
        if perms:
            out[resource] = sorted(set(perms))
    return out


def require_permission(resource: str, action: str):
    async def dep(user: dict = Depends(get_current_user)):
        if not await can(user.get("role"), resource, action):
            raise HTTPException(
                status_code=403,
                detail=f"Akses ditolak: tidak memiliki izin '{action}' pada '{resource}'",
            )
        return user
    return dep


def require_super_admin():
    """Cross-tenant operations (org management/onboarding/switch) are super_admin-only.
    Note: owner is FULL_ACCESS *within its own tenant* but must NOT manage other tenants."""
    async def dep(user: dict = Depends(get_current_user)):
        if user.get("role") != "super_admin":
            raise HTTPException(status_code=403, detail="Akses ditolak: khusus super admin.")
        return user
    return dep


def is_scoped_sales(user: dict) -> bool:
    return user.get("role") in SALES_SCOPED_ROLES


def is_project_scoped(user: dict) -> bool:
    return user.get("role") in PROJECT_SCOPED_ROLES


def project_query(user: dict, query: dict = None) -> dict:
    """org_id + project membership scope (pm/site_engineer -> assigned projects)."""
    q = dict(query or {})
    q["org_id"] = user.get("org_id", ORG_ID)
    if user.get("role") in PROJECT_SCOPED_ROLES:
        q["members"] = user.get("email")
    return q


async def assert_project_access(project_id: str, user: dict):
    """Raise 404/403 if project missing or not accessible to a project-scoped user."""
    proj = await db.projects.find_one({"id": project_id, "org_id": user.get("org_id", ORG_ID)}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Proyek tidak ditemukan")
    if user.get("role") in PROJECT_SCOPED_ROLES and user.get("email") not in (proj.get("members") or []):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan anggota proyek ini")
    return proj


def scope_query(user: dict, query: dict = None, own_field: str = "assigned_to") -> dict:
    """Add org_id + row-level scope to a Mongo query."""
    q = dict(query or {})
    q["org_id"] = user.get("org_id", ORG_ID)
    if user.get("role") in SALES_SCOPED_ROLES:
        q[own_field] = user.get("email")
    return q


async def audit_log(user: dict, action: str, resource: str, entity_id: str = None, meta: dict = None):
    await db.audit_logs.insert_one({
        "id": new_id(), "org_id": user.get("org_id", ORG_ID),
        "actor": user.get("email"), "actor_role": user.get("role"),
        "action": action, "resource": resource, "entity_id": entity_id,
        "meta": meta or {}, "created_at": now_iso(),
    })
