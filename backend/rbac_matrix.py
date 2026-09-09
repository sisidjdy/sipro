"""rbac_matrix.py — DEFAULT_PERMISSIONS (matriks izin bawaan per sumber daya).

Dipisah dari `rbac.py` agar tiap berkas tetap di bawah batas 800 baris
(gate `validate_compliance.py`). SSOT tetap satu: `rbac` mengimpor kamus ini.
"""

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
        "project_manager": ["view_all", "create", "update", "delete"],
        "site_engineer": ["view_all"],
    },
    "units": {
        "sales_manager": ["view_all"], "marketing_admin": ["view_all"],
        "sales": ["view_all"], "finance": ["view_all"],
        "project_manager": ["view_all", "create", "update", "delete"], "site_engineer": ["view_all"],
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
        "sales_manager": ["view_all", "create", "update", "delete"],
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
    # Fase 69 — MESIN HARGA: skema diskon, promo, kupon. Yang MENYUSUN aturan (manajer
    # sales/keuangan) berbeda dari yang MEMAKAINYA (sales hanya memilih dari yang berlaku).
    "pricing": {
        "sales_manager": ["view_all", "create", "update"],
        "marketing_admin": ["view_all", "create", "update"],
        "sales": ["view_all"],
        "finance": ["view_all"],
        "finance_manager": ["view_all", "create", "update"],
    },
    # Fase 53 — KONTRAK PEMBELI (kontrak, komponen biaya, rencana bayar, tahap legal).
    # Pemisahan tugas yang disengaja: Sales/Marketing MEMBUAT & mengurus dokumen, Keuangan
    # MENGISI komponen biaya (BPHTB/notaris/bank memang angkanya) dan mengaktifkan kontrak,
    # sedangkan MEMAJUKAN TAHAP LEGAL (`manage`) hanya manajer — bukan pengaju yang sama.
    "contracts": {
        "sales_manager": ["view_all", "create", "update", "manage"],
        "marketing_admin": ["view_all", "create", "update"],
        "sales": ["view_own", "create"],
        "finance": ["view_all", "update"],
        "finance_manager": ["view_all", "update", "manage"],
        "project_manager": ["view_all"],
    },
    # Fase 56C — pembatalan kontrak & refund berjurnal. TIGA tangan berbeda dengan sengaja:
    # yang MENGAJUKAN (manajer sales/marketing) tidak memutuskan, yang MEMUTUSKAN (manajer
    # keuangan) tidak membayar sendiri, dan yang MEMBAYAR (keuangan) tidak boleh mengabaikan
    # penahanan "menunggu unit terjual kembali" \u2014 itu keputusan manajerial (`override`).
    "cancellation": {
        "sales_manager": ["view_all", "create"],
        "marketing_admin": ["view_all", "create"],
        "sales": ["view_own"],
        "finance": ["view_all", "update"],
        "finance_manager": ["view_all", "create", "update", "approve", "override"],
        "project_manager": ["view_all"],
    },
    # Fase 58 — denda & toleransi keterlambatan. DUA tangan berbeda dengan sengaja: yang
    # MENAGIHKAN denda (Keuangan, `create`) tidak boleh MERINGANKANNYA (`override`, hanya
    # Manajer Keuangan) — keringanan membalik jurnal & wajib beralasan tertulis.
    "late_fee": {
        "finance": ["view_all", "create"],
        "finance_manager": ["view_all", "create", "override"],
        "sales_manager": ["view_all"], "marketing_admin": ["view_all"],
        "sales": ["view_own"], "project_manager": ["view_all"],
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
    # `coa` = Bagan Akun (Chart of Accounts). Dipisah dari `gl` supaya admin bisa memberi
    # hak melihat daftar akun (dipakai dropdown jurnal/rekening bank) tanpa membuka jurnal,
    # dan sebaliknya mengunci penambahan/perubahan akun hanya pada peran tertentu.
    "coa": {
        "finance": ["view_all", "create", "update"],
        "finance_manager": ["view_all", "create", "update", "manage"],
        "project_manager": ["view_all"],
    },
    # `organizations` = manajemen tenant/organisasi (khusus super admin; owner hanya melihat).
    "organizations": {"owner": ["view_all"]},
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
        "finance": ["view_all"],
        "finance_manager": ["view_all"],
        # Fase 63 — agenda tidak lagi hanya "janji temu jual": rapat internal, kunjungan
        # proyek, dan rapat vendor juga hidup di sini, jadi peran proyek & keuangan HARUS
        # bisa membuat agendanya sendiri. Pemisahan tugas tetap dijaga di router:
        # agenda yang MENYEBUT LEAD hanya boleh dibuat pemakai yang berhak melihat lead
        # (`leads:view`), sehingga menjadwalkan survei pembeli tetap milik sales/marketing.
        "project_manager": ["view_all", "create", "update"],
        "site_engineer": ["view_all", "create", "update"],
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
    # Fase 57A — skema pembayaran yang bisa dikonfigurasi. Yang MENYUSUN skema (manajer
    # sales/keuangan) berbeda dari yang MENETAPKAN skema pada satu kontrak: mengubah skema
    # kontrak berarti mengubah jadwal kewajiban pembeli, jadi izinnya (`assign`) terpisah.
    "payment_scheme": {
        "sales_manager": ["view_all", "create", "update", "assign"],
        "marketing_admin": ["view_all"],
        "sales": ["view_all"],
        "finance": ["view_all"],
        "finance_manager": ["view_all", "create", "update", "assign"],
        "project_manager": ["view_all"],
        "site_engineer": ["view_all"],
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
    # `legal` = halaman legal publik (Kebijakan Privasi, S&K, Penghapusan Data) + antrean
    # permintaan penghapusan data pribadi. Admin Legal mengelola penuh; manajer sales/
    # marketing & supervisor DM boleh melihat (mereka yang berhadapan dengan pembeli).
    "legal": {
        "legal_admin": ["view_all", "create", "update", "manage"],
        "sales_manager": ["view_all"], "marketing_admin": ["view_all"],
        "dm_supervisor": ["view_all"], "finance_manager": ["view_all"],
    },
}
