# SIPRO V2 — INDEX & ATURAN PAKAI DOKUMEN (BACA INI DULU)

> **Status:** **Fase 39 + 39b SUDAH DIIMPLEMENTASI** (fondasi data: cluster/blok/tipe unit/add-on/
> komponen biaya/dokumen syarat/settings + wiring siteplan↔unit + status ganda unit, lalu 39b:
> checklist dokumen terpakai nyata di layar Lead & Pelanggan, akun GL jadi dropdown SSOT, riwayat
> migrasi bisa diperiksa). Bukti: `run_all_gates.sh` **22 gates PASS** (termasuk
> `verify_masterplan.py`, `verify_settings.py`, `verify_39b.py`), uji-mutasi `mutasi_39b.py` 20/20 —
> lihat `plan.md` §FASE 39b. Fase 40–51 masih **SPEC**. **Bahasa:** Indonesia. **Dibuat:** 16 Agu 2026.
> **Metode:** pembacaan langsung kode `/app` (grounded, ada `file:line`) + 4 dokumen legal asli milik owner
> di `docs/source_templates/`. Semua angka bisnis di dokumen ini berasal dari kode atau dokumen owner —
> **tidak ada angka karangan**. Yang belum pasti ditandai `⚠️ OPEN` (lihat §6).

## 0. Hubungan dengan seri dokumen lama
- `docs/analysis/00–19` = **framework V1** (dipakai membangun Fase 0–38). **Masih berlaku** untuk: entity registry lama (11), state machine lama (12), engine (13), RBAC (14), finance model (15), API contract (16), NFR (17), event/jobdesk catalog (19).
- Seri **V2 (20–36, dokumen ini)** = perbaikan fondasi + ekspansi CRM/BI berdasarkan review owner 16 Agu 2026. Bila V2 dan V1 berbeda, **V2 menang** dan V2 wajib menyebut dokumen V1 mana yang digantikan.
- `plan.md` = fase yang sedang berjalan. `test_result.md` = bukti pengujian. `CODEBASE_MAP.md` = peta file aktual.

## 1. DECISIONS LOG OWNER (mengikat semua dokumen V2)
Sumber: percakapan owner 16 Agu 2026 (tanya-jawab 5 blok + lampiran 4 dokumen legal + klarifikasi KPR).

| # | Keputusan | Konsekuensi dokumen |
|---|---|---|
| D1 | **Integrasi iklan:** struktur siap-live + **biaya iklan diinput manual/CSV** dulu; lead capture webhook tetap real; kredensial menyusul | [30](30_MARKETING_INTEGRATION_SPEC.md) |
| D2 | **Reservasi:** 1 lead = **1 unit aktif**, tetapi **bisa dikonfigurasi** | [24](24_CRM_LEAD_SPEC.md) §5, [33](33_CONFIG_CENTER_SPEC.md) |
| D3 | **Dokumen syarat:** dibuat **master, bisa ditambah admin**, lalu bisa diupload per tahap | [24](24_CRM_LEAD_SPEC.md) §6, [33](33_CONFIG_CENTER_SPEC.md) |
| D4 | **AJB/BAST bukan urusan lead** — lead yang sudah sah **menjadi Customer**, semua legal lanjut di Customer Management | [24](24_CRM_LEAD_SPEC.md) §3, [26](26_CUSTOMER_LEGAL_SPEC.md) |
| D5 | **Partner/mitra:** semua skema fee, pemicu, pajak, kontrak **bisa dikonfigurasi (toggle) & lengkap** | [25](25_PARTNER_SPEC.md), [33](33_CONFIG_CENTER_SPEC.md) |
| D6 | **Target:** basis **unit DAN pendapatan**; sediakan **beberapa metode** rumus; item budget = **master, user bisa tambah**; overbudget **general lalu bisa didetailkan** | [32](32_TARGET_BUDGET_SPEC.md) |
| D7 | **BI/SLIK checking = MANUAL dulu** dan **TERPISAH dari urutan** (boleh dilakukan sebelum booking) | [24](24_CRM_LEAD_SPEC.md) §7, [26](26_CUSTOMER_LEGAL_SPEC.md) §2 |
| D8 | **Dokumen bisa di-generate sistem** (SPR Cash / SPR Cash Bertahap / SPR KPR / SPKT) | [27](27_DOCGEN_SPEC.md) |
| D9 | **Sub-alur KPR hanya berlaku bila skema bayar = KPR** | [26](26_CUSTOMER_LEGAL_SPEC.md) §6 |
| D10 | **Urutan eksekusi** = rekomendasi agent: fondasi data & IA → CRM → BI → konsolidasi proyek/konstruksi | [34](34_ROADMAP_EKSEKUSI.md) |
| D11 | **Koreksi alur KPR (owner):** "pilih rumah" **sudah** di lead lifecycle; **berkas** dikumpulkan **saat sudah deal**; **SLIK bank** dilakukan di **menu BI Checking terpisah**; yang menjadi **step** adalah **SP3K** & **akad kredit** (+ appraisal opsional, + pencairan untuk finance) | [26](26_CUSTOMER_LEGAL_SPEC.md) §6 |
| D12 | **Tiap tipe pembayaran punya KOMPONEN BIAYA berbeda** (KPR paling banyak) dan perhitungannya **wajib link ke finance** | [26](26_CUSTOMER_LEGAL_SPEC.md) §3 |
| D13 | **Spek tambahan / lahan lebih / hook = master add-on sendiri**, dipilih **saat reservasi/booking**, dan di finance menjadi **komponen terpisah** (tidak dilebur ke harga unit) | [26](26_CUSTOMER_LEGAL_SPEC.md) §4, [28](28_PROJECT_UNIT_SPEC.md) §5 |

## 2. Peta dokumen V2

```
WHY / FAKTA            KONTRAK DATA & UX          SPEK DOMAIN                       EKSEKUSI
21 Audit Kondisi   →   22 Domain & Wiring   →   24 CRM Lead                  →   34 Roadmap Eksekusi
                       23 IA & UX Blueprint     25 Partner/Mitra                 35 Migrasi Data
                       33 Pusat Konfigurasi     26 Customer, Legal & Bayar       36 Playbook Agent
                                                27 Generator Dokumen
                                                28 Proyek→Cluster→Blok→Unit
                                                29 Konstruksi Unit-Centric
                                                30 Integrasi Marketing/Ads
                                                31 Analytics & BI
                                                32 Target & Budget/RAB
```

| Dok | Judul | Isi inti | Wajib dibaca oleh |
|---|---|---|---|
| [21](21_AUDIT_KONDISI.md) | Audit Kondisi Saat Ini | 34 temuan `CR-xx` + bukti `file:line` + severity | semua |
| [22](22_DOMAIN_DATA_WIRING.md) | Domain, Data & Wiring | koleksi baru/ubah, invarian, index, rantai lead→unit→customer→konstruksi→finance | backend |
| [23](23_IA_UX_BLUEPRINT.md) | IA & UX Blueprint | 3 sumbu navigasi, peta menu lama→baru, pola tabel-first | frontend |
| [24](24_CRM_LEAD_SPEC.md) | CRM & Lead Lifecycle | stage machine v2, aging, profil lead, perbaikan SPR | backend+frontend |
| [25](25_PARTNER_SPEC.md) | Mitra / Pihak Ketiga | master mitra, skema fee, pajak, kontrak, portal, analitik | backend+frontend |
| [26](26_CUSTOMER_LEGAL_SPEC.md) | Customer, Legal & Pembayaran | konversi, cash/bertahap/KPR, PPJB/AJB/BAST, pembatalan & refund | backend+frontend |
| [27](27_DOCGEN_SPEC.md) | Generator Dokumen | field map 4 dokumen asli, penomoran, klausa configurable, e-sign | backend |
| [28](28_PROJECT_UNIT_SPEC.md) | Proyek, Cluster, Blok, Unit | hierarki master data + siteplan wiring + status ganda | backend+frontend |
| [29](29_CONSTRUCTION_SPEC.md) | Konstruksi Unit-Centric | konsolidasi 6 menu → 1 hub, lifecycle pembangunan unit | backend+frontend |
| [30](30_MARKETING_INTEGRATION_SPEC.md) | Integrasi Marketing & Ads | Meta/Google siap-live, spend manual/CSV, CAPI, WA Cloud API | backend |
| [31](31_ANALYTICS_BI_SPEC.md) | Analytics & BI | kamus metrik + rumus + endpoint + visualisasi | backend+frontend |
| [32](32_TARGET_BUDGET_SPEC.md) | Target & Budget/RAB | 3 metode target, master budget, realisasi RAB, overbudget | backend+frontend |
| [33](33_CONFIG_CENTER_SPEC.md) | Pusat Konfigurasi | registry `settings` + semua toggle terkumpul | backend+frontend |
| [34](34_ROADMAP_EKSEKUSI.md) | Roadmap Eksekusi | Fase 39–51: scope, user story, DoD, gate | semua |
| [35](35_MIGRASI_DATA.md) | Migrasi Data | backfill idempoten + perubahan semantik + rollback | backend |
| [36](36_PLAYBOOK_AGENT.md) | Playbook Agent | aturan anti-halusinasi, gate, batas file, cara tutup fase | **semua agent** |

## 3. Aturan penulisan yang dipakai di seri ini
1. Setiap klaim tentang kode wajib punya `path:line` **yang benar-benar ada**.
2. Setiap angka bisnis wajib punya sumber: `[SSOT]` (reference.py), `[DOC]` (dokumen owner), `[CFG]` (setting bisa diubah), `[CALC]` (hasil hitungan). Tidak ada `[ASUMSI]` tanpa tanda `⚠️ OPEN`.
3. Setiap fitur punya: kontrak data → endpoint → UI → invarian → cara diuji.
4. Bahasa UI = Indonesia. Bahasa kode = Inggris (konsisten dengan kode yang ada).

## 4. Definisi status implementasi yang dipakai
`✅ ADA` (berjalan & terbukti gate) · `🟡 SEBAGIAN` (ada tapi tidak memenuhi kebutuhan owner) · `❌ BELUM` · `🐞 CACAT` (ada tapi salah/logic bug) · `🎭 SIMULASI` (jujur bukan live).

## 5. Cara agent berikutnya memakai dokumen ini
```
1. Baca 36_PLAYBOOK_AGENT.md            (aturan main; 5 menit)
2. Baca 34_ROADMAP_EKSEKUSI.md          (fase mana yang aktif)
3. Baca spec fase itu (mis. 24 + 27)    (kontrak yang harus dipenuhi)
4. Baca 22 + 33                          (skema data & setting yang menyentuh fase itu)
5. Bangun → tulis scripts/verify_<fase>.py → bash scripts/run_all_gates.sh harus PASS
6. Tutup fase: update plan.md + test_result.md + tandai status di dokumen V2 terkait
```

## 6. ⚠️ OPEN — pertanyaan yang MASIH harus dijawab owner (jangan dikarang)
| Kode | Pertanyaan | Dampak bila dikarang |
|---|---|---|
| OQ-1 | **SPKT**: tabel menulis harga kelebihan tanah **Rp2.000.000/m²**, klausa menulis **Rp1.250.000/m²**. Mana yang benar / keduanya (harga list vs harga disepakati)? | dokumen legal salah nominal |
| OQ-2 | SPR Cash Bertahap: DP 80% + 20% dicicil 6×; SPR Cash keras: DP 80% + 20% saat progres 100%. Apakah 80/20 ini **default semua proyek** atau per proyek/promo? | skema pembayaran salah |
| OQ-3 | Booking fee Rp1.000.000 `[DOC]` — berlaku semua proyek atau per proyek/tipe? | AR & refund salah |
| OQ-4 | PPh mitra: tarif PPh 21 (perorangan) & PPh 23 (badan) yang dipakai perusahaan Anda berapa %? | potongan pajak & jurnal salah |
| OQ-5 | Nomor dokumen SPR contoh `5201/SPR-CASH/HL5/VIII/2026` — apakah `5201` counter global, per proyek, atau per bulan? | penomoran legal salah |
| OQ-6 | Demografi lead yang WAJIB direkam (usia, pekerjaan, penghasilan, domisili, jumlah tanggungan, sumber info)? Mana yang wajib vs opsional? | analitik demografi kosong |
| OQ-7 | Retensi bangunan: berapa lama masa retensi setelah akad/AJB? (dokumen hanya menyebut "sesuai ketentuan PT") | SLA komplain/garansi salah |
| OQ-8 | Siapa boleh **override** aturan (mis. 2 unit per lead, tunggakan, refund)? `sales_manager` saja atau `owner` juga? | RBAC salah |
| OQ-9 | **Perlakuan akuntansi biaya titipan**: BPHTB / notaris / biaya bank ditagih ke pembeli — diakui sebagai **titipan pelanggan (2-1450, bukan pendapatan)** seperti rekomendasi saya, atau sebagai **pendapatan jasa**? | laba & pajak salah |
| OQ-10 | Daftar **spek tambahan (add-on)** yang berlaku di Anda beserta harganya (mis. kanopi, pagar, taman, upgrade lantai, tambah daya listrik)? | master add-on kosong |
| OQ-11 | Apakah perlu template **PPJB / AJB / BAST / kwitansi / surat pembatalan** juga di-generate sistem? Bila ya, mohon kirim contoh dokumennya (seperti SPR/SPKT) | dokumen lanjutan dikarang |

## 7. Spec tambahan Fase 40–51 (ditulis setelah seri 21–36)

Seri 20–36 ditulis saat Fase 39; fase-fase berikutnya menambah spec sendiri dengan aturan
penulisan yang sama (§3). Daftar ini yang harus dibaca agent sebelum menyentuh fase terkait.

| Dok | Judul | Fase | Status |
|---|---|---|---|
| [40](40_PETA_NAV_V2.md) | Peta Navigasi V2 | 40 | ✅ ADA |
| [41](41_UANG_MASUK_UPAH_SPEC.md) | Uang Masuk Terbukti & Upah Terbayar Benar | 47 | ✅ ADA |
| [42](42_PENGADAAN_SUBKON_SPEC.md) | Pengadaan & Subkon Lanjutan | 48 | ✅ ADA |
| [43](43_CLOSING_TAX_COMPLIANCE_SPEC.md) | Tutup Buku, Laporan Owner, Pajak & Kepatuhan | 49 | ✅ ADA |
| [44](44_HANDOVER_WARRANTY_SPEC.md) | Serah Terima (BAST), Masa Garansi & Klaim Pasca-Huni | 50A | ✅ ADA |
| [45](45_OFFLINE_PWA_SPEC.md) | Antrean Perangkat Terpadu (offline/PWA) | 50B | ✅ ADA |
| [46](46_RETENTION_WARRANTY_SPEC.md) | **Retensi Subkon ↔ Klaim Garansi** | 51A | ✅ ADA (gate 41) |
| [47](47_WA_REMINDER_SPEC.md) | **Pengingat WhatsApp Otomatis** | 51B | ✅ ADA · kirim 🎭 SIMULASI |
| [48](48_PORTAL_BUYER_SPEC.md) | **Portal Pembeli: BAST, Kwitansi & Pengakuan Klaim** | 51C | ✅ ADA (gate 43) |

Bukti Fase 51: `bash scripts/run_all_gates.sh` → **OVERALL PASS (43 gates)**;
`python3 scripts/mutasi_51.py --ringkas` → **52 mutasi SEMUA TERTANGKAP**;
`python3 poc/poc_51.py` → PASS (67 pemeriksaan).
