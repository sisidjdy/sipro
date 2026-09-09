# SIPRO Rebuild — Dokumen 09
# CRITICAL SELF-REVIEW & READINESS GAP ASSESSMENT (jujur, sudut pandang eksekutor)

> Status: REVIEW KRITIS INTERNAL. Bahasa: Indonesia.
> Pertanyaan yang dijawab: *"Apakah framework ini sudah sempurna? Jika seorang engineer (atau AI) hanya membaca Dok 01–08, bisakah ia membangun SIPRO dengan sempurna?"*
> Jawaban jujur: **BELUM.** Dok 01–08 kuat di **WHY + WHAT + gambaran produk + strategi**, tetapi **kurang lapisan SPESIFIKASI yang bisa dieksekusi**. Tanpa lapisan itu, eksekutor akan menebak ~15+ keputusan penting → **risiko drift = pola kegagalan SIPRO lama**.

---

## 0. VERDIKT SINGKAT
- **Kematangan Strategi/Bisnis/Produk:** ~85% (kuat).
- **Kematangan Spesifikasi Teknis (siap-build):** ~35% (belum cukup).
- **Kesimpulan:** Framework ini **fondasi berpikir yang sangat baik**, **bukan** cetak-biru siap-implementasi. Untuk mencapai "bisa dibangun sempurna", perlu **Lapisan Spesifikasi (Dok 10+)** + **POC core berisiko** + **definisi MVP tipis**.

---

## 1. UJI JUJUR: "Bisakah saya build sempurna hanya dari Dok 01–08?"
**Tidak.** Berikut titik-titik di mana saya (eksekutor) akan **berhenti / menebak**:

| # | Saat membangun … | Yang tidak ada di Dok 01–08 | Akibat bila ditebak |
|---|---|---|---|
| 1 | Koleksi apa pun | **Skema field-level** (nama field, tipe, enum, wajib/opsional, default, index, relasi) | Struktur data tak konsisten; FE↔BE drift |
| 2 | Endpoint apa pun | **Kontrak API lengkap** (request/response shape, kode status, format error, paginasi, filter) | verify_api_contract tak bisa dibuat; integrasi FE meleset |
| 3 | Lead/Deal/Unit | **State machine formal** (from→event→to + guard + side-effect) — 3-way sync deal↔construction↔finance | Bug transisi & sinkronisasi (area tersulit SIPRO) |
| 4 | Guided Work Engine | **Mekanik event bus** (sync/async? in-request vs worker?), **penjadwal** (SLA breach, expiry booking, no-response recycle) — stack ini **tak punya queue/cron bawaan** | Task otomatis/terjadwal tak jalan andal |
| 5 | Automation Rules | **DSL rule** (skema trigger→kondisi→aksi), evaluasi, idempotency lintas-event | Engine jadi hand-wavy / palsu |
| 6 | RBAC | **Matriks izin nyata** (role × resource × action) | verify_rbac tak ada acuan; guard ambigu |
| 7 | Next-Best-Action | **Aturan/heuristik konkret** (sinyal, threshold, prioritas) | NBA jadi kosmetik, bukan memandu |
| 8 | Finance | **Model akuntansi** (CoA, double-entry, aturan posting jurnal) + **rumus pajak** (PPN 11/12%, BPHTB 5%, PPh final 2,5%/1% — basis & pembulatan) | "Kelihatan benar tapi salah" — risiko fatal |
| 9 | Integrasi WA/Ads | **Rencana real-vs-simulasi** + cara validasi tanpa approval Meta penuh (WABA, template approval bisa berhari-hari) | Fase 1.7 macet karena dependency eksternal |
| 10 | Semua | **NFR**: timezone WIB, currency/rounding IDR, paginasi/performa, upload limit & storage, audit format, error/observability, concurrency (double-booking = kritis konkurensi) | Bug produksi & data korup |
| 11 | UI | **Design system nyata** (tokens/komponen dari design_agent) | UI tak konsisten |
| 12 | Testing | **User story testable** (Given/When/Then) per EPIC | testing_agent tak punya skenario presisi |

---

## 2. GAP ANALISIS KRITIS (dikelompokkan)

### A. RIGOR SPESIFIKASI (gap terbesar)
- **ENTITY_REGISTRY sesungguhnya belum ada** — baru daftar nama koleksi + fungsi, bukan skema field. **Ini blocker #1.**
- **API_CONTRACT belum ada** — daftar endpoint parsial, tanpa bentuk data.
- **STATE_MACHINES belum formal** — lifecycle dijelaskan naratif, bukan tabel transisi + guard + efek. 3-way sync (deal↔construction↔finance) & atomic booking adalah **jantung kompleksitas** dan **paling rawan bug**.

### B. MEKANIK ENGINE & NFR (diremehkan)
- **Event bus + penjadwalan**: FastAPI+Mongo **tanpa** broker/cron bawaan. Perlu keputusan: APScheduler/background task/worker? sync in-request vs async? Idempotency store? Tanpa ini, "Guided Work Engine" & SLA/expiry/recycle **tidak nyata**.
- **Automation Rules engine**: butuh DSL + evaluator + audit + guard anti-loop.
- **Konkurensi**: double-booking hanya aman bila benar-benar atomic + diuji di beban paralel (POC).
- **NFR** (timezone/currency/paginasi/upload/observability/audit) belum dispesifikasi.

### C. RISIKO KEBENARAN DOMAIN (finance & legal)
- **Finance masih konseptual**, belum model akuntansi eksekutabel. Klaim "PSAK 72 jalan" tanpa CoA+jurnal+rumus pajak = **berisiko false-green** (langgar RC-10). Perlu minimal: model contract-liability→revenue posting + worksheet pajak dgn rumus & basis eksplisit; GL penuh boleh fase lanjut **asal dinyatakan jujur**.
- **Legal/dokumen**: PPJB/AJB/BAST butuh **template + aturan prasyarat + e-sign/format PDF** yang belum dispesifikasi (hanya disebut).

### D. RISIKO INTEGRASI/EKSTERNAL (bisa menggagalkan jadwal)
- **WA Cloud API & Meta Lead Ads** bergantung akun Meta Business, WABA, **template approval (hari–minggu)**, verified app. **Owner mungkin belum punya.** Perlu: (1) playbook via integration agent, (2) daftar kredensial ke owner **di awal**, (3) **mode simulasi jujur + POC round-trip** agar flow teruji tanpa menunggu approval, (4) keputusan eksplisit **apa yang real vs simulasi saat rilis**.

### E. REALISME SCOPE / MVP (pola gagal SIPRO lama)
- Scope = 3 pilar + omnichannel + work hub + portal + multi-tenant. **Tanpa "irisan MVP tipis"**, risiko *boil-the-ocean* = **persis kegagalan SIPRO lama** ("banyak fitur NOT STARTED").
- **Belum ada definisi "vertical slice pertama"** yang tipis, shippable, dan **membuktikan arsitektur** (mis. *Ads/WA capture → lead → task → appointment → SPR/booking* untuk 1 proyek/2 peran).

### F. DESAIN & VALIDASI
- **Design system** belum diproduksi (perlu design_agent).
- **Strategi POC** untuk core berisiko belum ada (workflow kita mewajibkan buktikan core dulu).
- **Diagram** (ERD, state machine, flow O2C, arsitektur omnichannel) belum ada — mempersulit alignment.

---

## 3. APA YANG SUDAH BAIK (agar seimbang, tidak semua kurang)
- WHY/root-cause **grounded** (regulasi, pain lapangan, benchmark) — jarang dimiliki proyek sejenis.
- Product vision **jelas & pembeda** (Work Hub, omnichannel, guided).
- **Traceability matrix** mengikat kebutuhan→gate — dasar disiplin yang benar.
- **Guardrail philosophy** (dari kn, ditingkatkan) — mencegah false-green **asal benar-benar dieksekusi**.

---

## 4. YANG DIBUTUHKAN AGAR "BISA DIBANGUN SEMPURNA" (Lapisan Spesifikasi — Dok 10+)
> Ini rekomendasi menutup gap **sebelum/awal Fase 0**, agar eksekusi tak menebak.

1. **Dok 10 — ENTITY_REGISTRY (skema field-level)**: tiap koleksi → field (tipe/enum/wajib/default), index, relasi, invarian. *(Blocker #1)*
2. **Dok 11 — API_CONTRACT**: konvensi (paginasi/filter/error), lalu endpoint per modul dgn request/response.
3. **Dok 12 — STATE_MACHINES & INVARIANTS**: tabel transisi lead/deal/unit + **3-way sync** + atomic booking + guard + side-effect + invarian yang di-*gate*.
4. **Dok 13 — ENGINE SPEC**: event bus (mode & dispatch), **penjadwal** (pilihan teknis), Guided Work Engine (aturan task), **Automation Rules DSL**, idempotency.
5. **Dok 14 — RBAC_MATRIX**: role × resource × action (nyata).
6. **Dok 15 — FINANCE MODEL**: contract-liability→RevRec posting + **rumus pajak eksplisit** + (opsi) CoA/GL fase lanjut (dinyatakan jujur).
7. **Dok 16 — NBA RULES**: sinyal, threshold, prioritas, contoh per stage.
8. **Dok 17 — INTEGRATION & POC PLAN**: kredensial yang diminta ke owner, real-vs-simulasi, POC round-trip WA/Ads + atomic booking + scheduler.
9. **Dok 18 — MVP SLICE & TEST SCENARIOS**: vertical slice pertama + user story Given/When/Then untuk testing_agent.
10. **NFR STANDARD**: timezone WIB, IDR rounding, paginasi, upload/storage, audit, observability, concurrency.
11. **Design guidelines** (via design_agent) + **diagram** (ERD/state/flow/arsitektur).

---

## 5. REKOMENDASI URUTAN (revisi realistis)
1. **Tutup Lapisan Spesifikasi (Dok 10–18)** untuk **irisan MVP dulu** (bukan seluruh sistem sekaligus) — cukup untuk membangun *vertical slice pertama* tanpa menebak.
2. **POC core berisiko** (scheduler+event+idempotent task; WA webhook round-trip simulasi; atomic booking konkuren; RevRec math) — buktikan sebelum bangun luas.
3. **Design system** (design_agent).
4. **Fase 0 Fondasi** + **MVP slice** → gate hijau → testing_agent → baru melebar per pilar.

> Prinsip: **spesifikasi tipis-tapi-presisi untuk irisan MVP**, lalu lebarkan. Ini menyeimbangkan kecepatan & kebenaran, dan **menghindari dua kegagalan**: (a) boil-the-ocean tanpa spec (SIPRO lama), (b) over-spec seluruh sistem sebelum satu barispun jalan.

## 6. JAWABAN AKHIR UNTUK OWNER
- **Sempurna?** Belum. **Cukup untuk mulai coding membabi-buta?** Tidak (dan tidak seharusnya).
- **Cukup sebagai fondasi berpikir & arah?** Ya, kuat.
- **Langkah agar benar-benar siap-build:** tamb«ah **Lapisan Spesifikasi (Dok 10–18) untuk MVP slice** + **POC core** + **design system**. Setelah itu, saya percaya diri eksekusi bisa presisi & minim drift.
