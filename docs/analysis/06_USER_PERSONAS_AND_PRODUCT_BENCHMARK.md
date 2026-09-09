# SIPRO Rebuild — Dokumen 06
# PERSPEKTIF PENGGUNA (PERSONAS & JOBS-TO-BE-DONE) + BENCHMARK PRODUK

> Status: RISET MENDALAM (sisi pengguna + benchmark produk PMS/PM matang). Bahasa: Indonesia.
> Tujuan: mendesain dari **realita harian pengguna** (bukan asumsi), dan menyerap pola **produk matang** (real-estate CRM & construction field-management) yang relevan.

---

## 1. PERSONAS & JOBS-TO-BE-DONE (JTBD)

> Format: siapa · realita harian · frustrasi · "apa yang dianggap sukses" · kebutuhan sistem.

### P1 — Sales/Marketing Inhouse ("Rina", lapangan)
- **Realita harian:** pegang puluhan lead lintas sumber (Meta/TikTok/referral/walk-in); balas WA, jadwalkan survey, ikut site visit, kejar follow-up, urus booking. Sering di jalan/di lokasi (mobile).
- **Frustrasi:** lead menumpuk tak jelas prioritas; lupa follow-up; data di WA/Excel; tak tahu unit mana masih available; komisi tak transparan.
- **Sukses baginya:** tahu "hari ini harus hubungi siapa", cepat lihat ketersediaan & harga unit, booking tanpa takut bentrok, lihat komisi berjalan.
- **Kebutuhan sistem:** **Work Hub "Hari Saya"** (task berprioritas + SLA), **Next-Best-Action** per lead, ketersediaan unit real-time, **mobile-friendly**, komisi transparan. → (JTBD: "Bantu saya mengubah lead jadi closing tanpa ada yang terlewat.")

### P2 — Marketing Admin / Sales Manager ("Budi")
- **Realita harian:** distribusi lead ke sales, pantau SLA & funnel, approve harga khusus/diskon, coaching tim.
- **Frustrasi:** tak tahu sales mana overload/idle; lead nyangkut; performa tim tak real-time.
- **Sukses:** distribusi adil & cepat, SLA terjaga, konversi tim naik.
- **Kebutuhan:** **Manager Home** (funnel, SLA tim, leaderboard, distribusi lead load-balanced, approval inbox, gamifikasi mission).

### P3 — Finance / Collection ("Sari")
- **Realita harian:** tagih DP/cicilan, catat penerimaan, pantau KPR cair, bayar termin subcon, kelola retensi, siapkan pajak.
- **Frustrasi:** aging tak terlihat; penagihan manual; kas mepet tapi harus bayar subcon; retensi lupa dilepas.
- **Sukses:** kas terprediksi, penagihan tertib, subcon terbayar tepat, laporan akurat (PSAK 72).
- **Kebutuhan:** **Finance Home** (AR aging, AP & retensi, cash-flow projection, contract-liability, pajak jatuh tempo, worklist penagihan).

### P4 — Project Manager / Site Engineer ("Andi", lapangan)
- **Realita harian:** kelola subcon/mandor, opname progres, cek mutu (QC), catat material masuk/keluar, foto lapangan, urus izin/dokumen.
- **Frustrasi:** progres subcon diklaim sepihak; material hilang/tak terlacak; deviasi jadwal ketahuan telat; dokumen izin mepet deadline.
- **Sukses:** progres nyata terverifikasi, material terkontrol (opname cocok), jadwal on-track (kurva-S), izin tepat waktu.
- **Kebutuhan:** **Project Home** (kurva-S plan vs aktual, termin subcon, QC/punch list + foto, material ledger + opname, permit/document tracker), **mobile + offline** (fase lanjut).

### P5 — Owner / GM / Super Admin ("Pak Direktur")
- **Realita harian:** ambil keputusan cepat (harga, approval, prioritas proyek), pantau kesehatan bisnis, cegah fraud.
- **Frustrasi:** harus "menggali" ke tiap modul; tak ada satu layar kesehatan bisnis; risiko fraud tersembunyi.
- **Sukses:** satu "Control Tower": penjualan, kas, AR/AP, progres proyek, revenue diakui vs contract-liability, approval pending.
- **Kebutuhan:** **Control Tower** + audit trail + RBAC + switch entitas (multi-tenant).

### P6 — PEMBELI / Customer ("Ibu Dewi") — sering dilupakan sistem lama
- **Realita:** beli unit indent, cemas soal progres & kepastian; bayar bertahap; ingin unit sesuai janji.
- **Frustrasi (grounded):** tak tahu progres (minim update jujur), BAST tak sesuai spek, cacat lambat ditangani, komplain diabaikan, tak ada portal.
- **Sukses:** transparan (progres+foto+jadwal bayar+status dokumen), komplain direspons cepat, unit sesuai.
- **Kebutuhan:** **Customer Portal** (progres, pembayaran, dokumen, kanal komplain + SLA). → langsung menaikkan kepercayaan, ketepatan bayar, & referral.

> **Insight lintas-persona:** semua peran ingin sistem yang **memberi tahu apa yang harus dikerjakan** dan **kontekstual pada data** — memvalidasi pilihan owner "Slack tapi ERP" (Work Hub). Peran lapangan (P1,P4) menuntut **mobile**; peran back-office (P3,P5) menuntut **visibilitas & kontrol**.

---

## 2. BENCHMARK PRODUK (pola yang diserap SIPRO)

### 2.1 Real-Estate Developer CRM (PropertyBase, AscendixRE, Zoho Real Estate, Salesforce+AppExchange)
Pola native yang **wajib** untuk developer (di luar CRM generik):
- **Hierarki Proyek → Blok/Gedung → Unit** (filter & rollup lintas level) + peta lokasi.
- **Master Inventory unit real-time** + **status automation** (`Available → Reserved → Booked → Sold → Due`).
- **Reservation logic**: milestone DP, jatuh tempo, counter-offer; auto-breakdown pembayaran per aturan.
- **Deal & contract lifecycle**: inquiry → auto-create deal+contact; **generate kontrak dari template + checklist**; milestone tracking (paid/due/upcoming).
- **Reporting**: sales velocity, inventory turnover, pipeline health, campaign spend vs closure, agent KPI.
- **Daily agent workflow**: morning **lead triage + scoring**, unified comms, **mobile saat site visit**, visual pipeline (drag-drop), doc handling.

> Pelajaran: **CRM developer ≠ CRM agen generik** — harus paham "fisika penjualan konstruksi" (unit, tipe, milestone, indent). SIPRO mengambil ini **native** (bukan add-on), plus konteks legal ID (SPR/PPJB/AJB/KPR) yang tak dimiliki produk asing.

### 2.2 Construction Field-Management (Procore, Buildertrend, PlanRadar, Fieldwire, Oracle Aconex)
Pola lapangan yang diserap:
- **Daily log / site diary** (progres, tenaga kerja, cuaca, foto).
- **Punch list / snag / defect**: buat tiket di lokasi, foto **dipin ke gambar/denah**, voice/teks, assign + notifikasi, status close-out.
- **Mobile-first + offline** (koneksi site sering jelek) — Fieldwire unggul offline.
- **Photo documentation + version control**; **QR/geolocation** untuk material/aset.
- **Audit-ready records** (bukti legal bila sengketa) — Aconex/PlanRadar.
- **BoQ/estimasi → budget → progress/AIA billing → WIP** (Procore).
- **Homeowner/Customer Portal** (Buildertrend) — best-in-class untuk transparansi pembeli.

> Pelajaran: SIPRO **menyatukan** field-management + sales + finance dalam satu sistem + task hub — menutup "gap otomasi lintas-sistem" yang bahkan Procore/Buildertrend belum selesaikan (dispatch/doc/accounting masih manual).

### 2.3 Ringkas: apa yang SIPRO AMBIL vs TINGGALKAN
| Dari produk matang | AMBIL | TINGGALKAN/tunda |
|---|---|---|
| Real-estate CRM | Hierarki proyek-unit, inventory status automation, reservation milestone, contract-from-template, lead scoring, mobile pipeline | MLS/IDX (tak relevan ID) |
| Construction PM | Daily log, punch list/defect+foto berlokasi, material ledger+opname, progress billing/termin, kurva-S, customer portal | BIM penuh, CPM kompleks (fase lanjut) |
| Work OS / Slack | Task board + automation rules, activity feed, @mention, thread, channel per entitas | Chat umum lepas-konteks |
| CRM 2026 (SF/HubSpot) | Next-Best-Action, guided execution, "stalled deal"/SLA cards | AI berat (mulai heuristik dulu, LLM opsional) |

---

## 3. KERANGKA METRIK/KPI (outcome-driven) — dibangun ke dashboard tiap peran

> Angka acuan (grounded 2026) untuk target & alarm; dikalibrasi ulang saat operasi nyata.

### Sales/Marketing
- **Speed-to-lead / response time** (metrik #1): target **≤5 menit** kontak pertama (telat → ~21x lebih kecil qualified).
- **Lead-to-close**: ~2–5% (all sources), referral 14–25%+, portal 0,4–1,2% → **stratifikasi cadence per sumber**.
- **Appointment-to-sale**: ~25–30%.
- **Absorption rate** (units sold ÷ inventory / bulan): sehat **1,5–3%**, tinggi **>4%**; **presale 30–50%**.
- **Sales velocity** = (deals × avg price × conversion) ÷ sales-cycle-days → turunkan cycle (mis. 45→30 hari).
- Produktivitas: aktivitas/hari, meeting/minggu, pipeline movement; **leaderboard + mission** (mission → +~10% attainment).

### Konstruksi
- **Deviasi kurva-S** (aktual vs rencana) — alarm bila negatif.
- **Selisih stock opname** (fisik vs buku) → target ~0; **wastage %**.
- **Defect open vs closed** sebelum BAST; **rework rate**.
- **On-time milestone / permit** (dokumen legal tepat waktu).

### Finance
- **AR aging & DSO** (days sales outstanding); **% overdue**.
- **Cash-flow projection** (AR masuk vs AP+termin keluar) — runway.
- **Contract-liability vs revenue diakui** (PSAK 72).
- **AP subcon aging & retensi** jatuh tempo.

### Kepercayaan Pembeli
- **Waktu respons komplain** (target ≤7 hari); **defect closure time**; **on-time BAST**; **referral rate** (target 25%+ dari pembeli puas).

---

## 4. IMPLIKASI DESAIN (dari sisi pengguna)
1. **Mobile-first untuk peran lapangan** (sales & site) — layout & interaksi diuji di layar kecil sejak awal.
2. **Kontekstual & memandu** — tiap layar menjawab "apa langkah saya sekarang", bukan sekadar tabel.
3. **Transparansi lintas-pihak** — data yang sama, view berbeda per peran (progressive disclosure) + Customer Portal.
4. **Anti-kebocoran by design** — approval berjenjang + jejak audit + 3-way match + opname sebagai alur inti, bukan tambahan.
5. **Deadline-aware** — SLA, reminder, kurva-S, permit tracker melekat pada task & notifikasi.

> Kesimpulan Dok 05–06: rebuild SIPRO harus dinilai dari **outcome bisnis** (konversi, cegah kebocoran, jaga deadline, arus kas & kepercayaan) dan dirancang dari **realita harian pengguna** (termasuk pembeli). Ini yang membedakannya dari "system of record" lama dan dari tool asing yang tak paham konteks Indonesia.
