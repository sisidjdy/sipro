# SIPRO Rebuild — Dokumen 02
# RISET BISNIS-PROSES (Properti Indonesia) & BENCHMARK SISTEM MATANG

> Status: RISET (grounded ke regulasi & praktik + benchmark produk). Bahasa: Indonesia.
> Tujuan: memastikan model domain SIPRO baru **benar secara bisnis & regulasi**, dan **belajar dari sistem matang** agar IA/UX/fitur setara kelas dunia namun kontekstual Indonesia.
> Catatan: angka pajak/regulasi bersifat acuan desain (2025–2026); implementasi harus tetap dikonfirmasi ke penasihat pajak/hukum saat go-live.

---

## BAGIAN A — PETA BISNIS-PROSES DEVELOPER PROPERTI INDONESIA (END-TO-END)

Tiga pilar SIPRO memetakan tiga proses inti developer: **Sales & Marketing (Lead-to-Cash)**, **Project/Construction (Plan-to-Handover)**, dan **Finance (Record-to-Report)** — yang saling terhubung lewat **Unit** dan **Deal** sebagai entitas pusat.

### A1. PILAR 1 — SALES & MARKETING (Lead → Booking → Akad)

Alur kanonik + dokumen legal (grounded ke regulasi properti ID):

```
(1) MARKETING/ACQUISITION
    Iklan (Meta/Google/TikTok) · referral · walk-in · event · web
    → Lead masuk (perlu KRK, Sertifikat, IMB/PBG, jaminan sebelum boleh dipasarkan)
(2) NURTURING
    Assignment ke sales · follow-up · scoring · response-time SLA
(3) APPOINTMENT / SURVEY
    Site visit · presentasi unit · simulasi harga & KPR
(4) RESERVASI (BOOKING)
    SPR / Lembar Komitmen (LKTM) + BOOKING FEE (tanda jadi)
    → WAJIB tanda tangan PPJB dalam 30 hari (regulasi)
(5) PPJB (Perjanjian Pengikatan Jual Beli)
    Akta notaris · syarat: konstruksi ≥20% + fasum + review pembeli 7 hari
    → jadwal pembayaran (DP + termin/cicilan) mulai berlaku
(6) PEMBIAYAAN
    KPR (pengajuan bank, BI checking, plafon, tenor, pencairan BERTAHAP per milestone)
    ATAU cash / cash bertahap
(7) KONSTRUKSI & PROGRESS (lihat Pilar 2)
(8) SERAH TERIMA (BAST — Berita Acara Serah Terima)  ← titik pengakuan pendapatan (PSAK 72)
(9) AJB (Akta Jual Beli) di hadapan PPAT
    → BPHTB (pembeli 5%) + PPh final (penjual 1%/2,5%) + PPN 12% (primary, developer PKP)
(10) BALIK NAMA sertifikat (BPN) → SHM/SHGB atas nama pembeli
```

**Implikasi untuk sistem (yang SIPRO lama TIDAK punya):**
- **SPR + booking fee** sebagai sub-status booking formal (bukan hanya deal draft).
- **Dokumen legal berjenjang**: SPR → PPJB → BAST → AJB, tiap dokumen punya prasyarat (gate) & PDF ber-template Bahasa Indonesia + e-sign/upload.
- **Modul KPR/Financing**: bank, plafon, DP, tenor, BI checking, status approval, pencairan bertahap terkait milestone konstruksi.
- **Jadwal pembayaran** yang sadar-skema (KPR vs cash bertahap) + reminder + penalti/denda keterlambatan.
- **SLA & recycle**: no-response appointment → auto-recycle (7 hari) sebagaimana niat SIPRO lama.
- **Komisi/insentif marketing**: per-deal, diakui saat lunas/akad, mendukung agen & tim.

### A2. PILAR 2 — PROJECT / CONSTRUCTION (Plan → Build → Handover, termasuk subcon)

```
LAND & PERIZINAN (KRK, sertifikat, IMB/PBG) → SITE DEVELOPMENT (matang lahan, jalan, drainase, utilitas/fasum)
 → BoQ / RAB per tipe unit / blok  → KONTRAK SUBKONTRAKTOR & VENDOR (SPK)
 → PELAKSANAAN per fase (pondasi→struktur→atap→finishing→MEP)
 → PROGRESS CLAIM / TERMIN subcon (opname progres) → RETENSI ditahan (jaminan mutu)
 → QC / INSPEKSI per task (pass/fail → qc_hold) → CHANGE ORDER (variasi)
 → BAST unit ke pembeli (masa pemeliharaan) → pelepasan RETENSI setelah masa pemeliharaan
```

**Yang perlu ditambah vs SIPRO lama (yang hanya weighted phase/task + QC):**
- **BoQ / RAB** (Bill of Quantities / Rencana Anggaran Biaya) per unit/tipe/blok → basis biaya & termin.
- **Subkontraktor/Vendor sebagai entitas** (SPK, nilai kontrak, prequalification ringan, dokumen).
- **Progress claim / termin**: opname progres → tagihan subcon → pembayaran → **retensi** (Retentions Payable).
- **Change Order (variasi)** yang memengaruhi BoQ & termin.
- **Dokumentasi foto** per task/inspeksi (butuh object storage).
- **Kaitan progress → milestone pencairan KPR & pengakuan pendapatan (BAST)**.

### A3. PILAR 3 — FINANCE (Record → Report), disiplin PSAK 72 + pajak

**Prinsip kunci (grounded PSAK 72):** pendapatan developer **diakui saat Serah Terima (point-in-time)**, BUKAN saat DP/termin diterima.

| Tahap | Akuntansi (PSAK 72) | Pajak |
|---|---|---|
| DP & termin diterima | Dicatat **Kewajiban Kontrak (Contract Liability)** — belum pendapatan | (belum) |
| Proses konstruksi | Biaya subcon/material → **Aset dalam Penyelesaian / Biaya Gantung**; **Retensi = Retentions Payable** | Subcon PKP terbitkan Faktur Pajak (PPN Masukan) |
| **Serah Terima (BAST)** | **Akui Pendapatan + COGS penuh** (transfer of control) | Penjual **PPh final 1%/2,5%**; Pembeli **BPHTB 5%** + **PPN 12%** (primary) |

**Model finance yang benar (SIPRO baru) harus memisahkan:**
- **AR (Piutang) sisi pembeli**: jadwal DP/cicilan/KPR, penerimaan kas, aging, denda.
- **AP (Utang) sisi subcon/vendor**: termin/progress claim, **retensi**, pembayaran, aging.
- **Contract Liability**: akumulasi penerimaan sebelum BAST.
- **Revenue Recognition**: trigger di BAST → akui revenue+COGS; kaitkan ke deal/unit.
- **Pajak**: PPN keluaran/masukan, BPHTB (pembeli), PPh final (penjual) — minimal sebagai catatan/worksheet + dokumen; GL penuh menyusul.
- **Cash flow & dashboard**: proyeksi kas dari jadwal AR/AP + termin.

> Ini peningkatan besar dari SIPRO lama (yang hanya `BillingSchedule→Payments`). Model ini juga menutup blindspot RC "bug semantik" (mis. mengakui revenue terlalu dini).

---

## BAGIAN B — BENCHMARK SISTEM MATANG (apa yang kita pelajari & ambil)

### B1. CRM / Sales — Salesforce & HubSpot (tren 2026: dari dashboard → *guided execution*)

| Pola | Salesforce (Einstein Next Best Action) | HubSpot (Sales Workspace 2026) | Yang SIPRO ambil |
|---|---|---|---|
| Filosofi | "Apa yang harus kukerjakan **di record ini** sekarang?" (overlay kontekstual di record page) | "Apa **top tasks** ku lintas pipeline?" (workspace terpusat + Suggested Tasks) | **Keduanya**: Work Hub global (task inbox) + NBA per-record |
| Mesin | Recommendation records + Strategy Flows + komponen NBA; accept → screen flow (tutup loop rekomendasi→eksekusi) | AI "Suggested Tasks" otomatis + "Stalled Deals" (sinyal inaktivitas) | **Guided Work Engine**: task auto + "deal macet"/SLA-breach cards + accept→guided action |
| Data | Activity-centric (email/meeting/task) jadi bahan AI | Native record view lengkap saat mengerjakan task | **Activity feed** sebagai sumber kebenaran interaksi |
| Pelajaran | Setiap rekomendasi butuh aksi valid; jangan biarkan CTA mati | Konteks > kenyamanan: jangan paksa pindah layar | CTA selalu actionable; kerjakan tugas tanpa keluar konteks |

### B2. Construction PM — Procore (enterprise) & Buildertrend (residential)

| Kapabilitas | Procore | Buildertrend | Yang SIPRO ambil |
|---|---|---|---|
| BoQ/Estimasi | Native, cost codes, takeoff | Estimasi → budget | **BoQ/RAB** per tipe unit + cost code |
| Subcon | Prequalification, lien waiver, insurance/COI tracking | Pembayaran & lien dasar | **Subcon entity + SPK + termin + retensi** (versi ID) |
| Progress billing | AIA billing, WIP, real-time job cost | Progress billing sederhana | **Termin/progress claim + opname + retensi** |
| Scheduling | CPM/Gantt, RFI/submittal | Dependency, weather, selections, change order | **Gantt/timeline + change order + foto** (bertahap) |
| Portal klien | Data-heavy | **Homeowner Portal** best-in-class | **Customer Portal** pembeli (status unit/pembayaran/progres) |
| Gap keduanya | Otomasi lintas-sistem (dispatch/doc/accounting) manual | idem | **Keunggulan SIPRO: satu sistem** — otomasi task lintas modul via event bus |

### B3. ERP/Finance & Work OS — Odoo/SAP, monday.com/ClickUp, Slack/Teams

- **Odoo/NetSuite/SAP**: pisahkan AR/AP/GL, dokumen berantai, approval berjenjang → kita adopsi **model finance berlapis** + **Pusat Persetujuan terpadu**.
- **monday.com / ClickUp**: WorkOS = "source of truth for **work**"; board/status/automation ("when status changes → notify") → kita adopsi **task board + automation rules**.
- **Slack/Teams**: "source of truth for **conversation**"; **Activity Feed = pusat triase** (news / collaboration / reminders / alerts), **@mention**, **thread**, notifikasi **per-channel**. → kita adopsi **Activity & Collaboration layer** yang menempel di record ERP (bukan chat terpisah).

**Sintesis "Slack tapi ERP" (pilihan owner = C, Work Hub terpadu):**
> Gabungkan (a) **Task Inbox global** ("Hari Saya": due/overdue/SLA/next-best-action) + (b) **Activity feed + komentar/@mention/thread** menempel di tiap record (lead/deal/unit/proyek/subcon) + (c) **Guided flow** (accept task → aksi terpandu yang memutasi record + log activity + majukan stage) + (d) **Channel per proyek/deal** untuk kolaborasi tim. WorkOS untuk *work*, feed untuk *conversation* — dalam satu sistem, kontekstual pada data ERP.

---

## BAGIAN C — PETA GAP (SIPRO lama → target kelas-matang)

| Area | SIPRO lama | Target (belajar dari benchmark + regulasi ID) |
|---|---|---|
| IA | Modul flat, sama semua peran | Flow-based + Role-Home + Work Hub task-based |
| Panduan | Pasif (system of record) | Next-Best-Action + guided flows + tours/onboarding |
| Kolaborasi | Tidak ada | Activity feed + komentar + @mention + thread + channel |
| Sales legal | Stage generik | SPR/booking-fee → PPJB → BAST → AJB + KPR + pajak |
| Konstruksi | Weighted phase/QC | + BoQ/RAB + subcon/SPK + termin + retensi + change order + foto |
| Finance | Billing→Payment | AR + AP + contract-liability + revenue-recognition (BAST) + pajak |
| RBAC | Tidak ada | Ditegakkan + gate + permission matrix config |
| Kualitas | Tanpa gate | Guardrail eksekutabel + DoD jujur |
| Portal pembeli | Tidak ada | Customer Portal (status unit/pembayaran/progres) |
| Komunikasi | WA mock | WA Business API terjadwal + notifikasi in-app/email |

> Kesimpulan Dok 02: model domain SIPRO baru harus **menautomasi rantai legal-finansial-konstruksi ID** dan **memandu pengguna** — dua hal yang persis menjadi keunggulan atas sistem lama dan pembeda dari tool asing yang tak paham konteks Indonesia.
