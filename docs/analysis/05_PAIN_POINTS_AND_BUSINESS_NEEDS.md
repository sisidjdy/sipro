# SIPRO Rebuild — Dokumen 05
# PAIN POINTS LAPANGAN & KEBUTUHAN BISNIS (BERBASIS OUTCOME)

> Status: RISET MENDALAM (grounded ke pain point nyata industri properti ID + benchmark). Bahasa: Indonesia.
> Sudut pandang: **kebutuhan bisnis & realita lapangan**, bukan daftar fitur. Tiap baris: **Pain → Akar Masalah → Dampak Bisnis → Yang SIPRO lakukan → Outcome/KPI**.
> Dokumen ini memperdalam "peta gap" Dok 02 dan menjadi dasar prioritas EPIC di Dok 04.

---

## 0. TIGA OUTCOME BISNIS YANG DIKEJAR (north-star)

Semua fitur SIPRO harus bermuara ke salah satu dari empat outcome bisnis nyata developer:
1. **TINGKATKAN KONVERSI** (lead → booking → akad) & kecepatan jual (absorption/velocity).
2. **CEGAH KEBOCORAN** (material dicuri/over-order/wastage; komisi/retensi salah bayar; fraud).
3. **JAGA DEADLINE** (dokumen legal, perizinan, konstruksi, serah terima) — hindari denda & proyek mangkrak.
4. **AMANKAN ARUS KAS & KEPERCAYAAN** (penagihan lancar, pembayaran subcon tertib, pembeli percaya).

> Realita industri (grounded): developer menengah hanya bertahan **1–3 bulan** tanpa arus kas baru; **70–80% proyek konstruksi ID terlambat**; lead dihubungi **>5 menit** turun peluang kualifikasi **~21x**. Ini bukan teori — ini penentu hidup-mati bisnis.

---

## 1. PILAR SALES & MARKETING — pain → solusi → outcome

| # | Pain lapangan (grounded) | Akar masalah | Dampak bisnis | Yang SIPRO lakukan | Outcome/KPI |
|---|---|---|---|---|---|
| SL-1 | **Respons lead lambat** → minat hilang | Tak ada SLA/penugasan instan; sales sibuk/ tak terpantau | Konversi anjlok (aturan 5-menit: telat >5m = ~21x lebih kecil qualified) | **Auto-assign instan + SLA countdown + Task "Hubungi sekarang" + eskalasi bila lewat SLA** | Median response time ↓; % lead terkontak ≤30 menit ↑ |
| SL-2 | **Lead "bocor"** (tak ditindak, hilang di WA/Excel) | Sistem manual, follow-up tak terstruktur, tak ada kepemilikan jelas | Buang biaya iklan; potensi closing hilang | **CRM terpusat + kepemilikan lead + cadence follow-up + recycle otomatis (no-response)** | Lead tanpa tindak lanjut → 0; cost-per-closing ↓ |
| SL-3 | **Double booking** unit (terjual 2x) | Status unit tak real-time; reservasi manual | Sengketa, reputasi, refund | **Unit atomic hold (find_one_and_update) + status real-time + reservasi ber-expiry** | Insiden double-booking = 0 |
| SL-4 | **KPR ditolak** setelah lama diproses | Tak ada pra-skrining (SLIK/DP), daya beli lemah | Pipeline "palsu", waktu sales terbuang | **Pra-skrining KPR (checklist SLIK/DP/simulasi) sejak nurturing + modul financing multi-bank** | % pengajuan KPR disetujui ↑; deal gugur di akhir ↓ |
| SL-5 | **Follow-up tak konsisten**, sales tak tahu "harus apa" | Tak ada panduan; system of record pasif | Konversi rendah, sales baru lambat produktif | **Work Hub: Task Inbox "Hari Saya" + Next-Best-Action + guided flow** | Aktivitas/ hari ↑; ramp-up sales baru ↓ |
| SL-6 | **Sengketa/opaqueness komisi** | Perhitungan manual, aturan tak jelas | Demotivasi sales, dispute | **Komisi engine transparan (per-deal, saat lunas/akad) + breakdown di Sales Home** | Dispute komisi ↓; retensi sales ↑ |
| SL-7 | **Manajemen tak lihat performa tim real-time** | Data tersebar, tak ada leaderboard | Sulit coaching & alokasi lead | **Manager Home: funnel, SLA tim, leaderboard, gamifikasi mission** | Attainment target tim ↑ (mission +~10%) |

> **Sinergi:** SL-1 & SL-2 diselesaikan secara nyata oleh **Omnichannel Lead Engine (Dok 07)** — Ads capture <30 dtk + WA in-chat inbox + trigger percakapan→lifecycle. Gambaran produk & implementasinya di **Dok 08 §EPIC 1.7**.

### Prinsip sales yang ditegakkan sistem
- **Speed-to-lead** = metrik #1 (SLA + auto-assign + task instan).
- **Stratifikasi sumber**: portal (volume tinggi, sentuhan rendah, otomasi) vs referral (sentuhan tinggi) — cadence berbeda.
- **Guided selling**: sistem selalu menyodorkan "langkah berikutnya", bukan menunggu sales inisiatif.

---

## 2. PILAR KONSTRUKSI (SUBCON) — cegah kebocoran & jaga deadline

### 2.1 Kebocoran/pencurian material (grounded)
| Pain | Akar masalah | Yang SIPRO lakukan | Outcome/KPI |
|---|---|---|---|
| Material **dicuri / hilang** di site | Pengawasan mandor lemah, gudang tak terkontrol, tanpa opname rutin | **Material ledger: requisition → GRN (terima) → issue ke task → stok site**; **stock opname terjadwal** (bandingkan fisik vs buku); **akses/approval berjenjang**; foto & QR/label opsional | Selisih opname → mendekati 0; kejadian hilang ↓ |
| **Over-ordering** → wastage & rawan hilang | Estimasi kasar, tak ada MRP | **BoQ/RAB → kebutuhan material presisi (MRP); alert bila permintaan > BoQ** | Wastage % ↓; pembelian sesuai BoQ |
| **Markup / fraud** biaya | Kehilangan dipakai alasan markup; pengawasan lemah | **Jejak audit tiap transaksi material + 3-way match (PO→GRN→tagihan) + approval** | Anomali biaya terdeteksi; audit-ready |
| **Sisa akibat design change** | Perubahan mendadak | **Change Order formal → revisi BoQ & material otomatis** | Sisa material terkelola |

> Strategi grounded yang diadopsi: **JIT delivery**, **stock opname rutin (harian/mingguan, akurasi 100%)**, **MRP presisi**, **akses terbatas + jejak audit**, **QR/label** — semua jadi fitur, bukan sekadar SOP di kertas.

### 2.2 Keterlambatan proyek/deadline (grounded: 70–80% proyek telat; manajerial ~80% penyebab)
| Pain | Akar masalah | Yang SIPRO lakukan | Outcome/KPI |
|---|---|---|---|
| **Perizinan/dokumen lambat** (KRK/IMB/PBG, addendum, approval desain) | Birokrasi + tak ada tracker deadline | **Document/Permit tracker dengan deadline + reminder + Task + eskalasi**; **Process Timeline** legal-konstruksi | Dokumen telat ↓; syarat PPJB (≥20%) siap tepat waktu |
| **Deviasi jadwal tak terdeteksi dini** | Tak ada monitoring plan vs aktual | **Kurva-S (rencana vs aktual) + deteksi deviasi + tindakan korektif (task)** | Deviasi terdeteksi dini; on-time ↑ |
| **Koordinasi lemah, keputusan lambat** | Komunikasi tersebar (WA/telepon) | **Work Hub: channel proyek + activity feed + @mention + task ke subcon/PM** | Cycle keputusan ↓ |
| **Progres subcon tak transparan** | Opname manual, klaim sepihak | **Progress claim/opname ter-verifikasi + foto + QC gate sebelum bayar termin** | Termin sesuai progres nyata |
| **Cacat mutu (rework)** | QC lemah, tak terdokumentasi | **QC/inspeksi (pass/fail→qc_hold) + punch list/snag + foto ber-lokasi (pola PlanRadar/Fieldwire)** | Rework ↓; defect closed sebelum BAST |

### 2.3 Yang wajib ada (pelajaran field-management matang)
- **Daily log / site diary** (progres harian + foto + tenaga kerja + cuaca) — mobile, bisa offline (fase lanjut).
- **Punch list / snag / defect** dengan foto **dipin ke lokasi/gambar** + voice note (opsional) + assign + status.
- **Audit trail** semua aktivitas lapangan (bukti legal bila sengketa).

---

## 3. PILAR FINANCE — arus kas, tertib bayar, anti-fraud

> Realita grounded: **arus kas macet = pemicu utama semua sengketa** (penagihan pembeli → KPR macet → tak bisa bayar subcon → proyek mangkrak → gugatan). Developer menengah bertahan 1–3 bulan tanpa cash baru.

| # | Pain | Akar masalah | Yang SIPRO lakukan | Outcome/KPI |
|---|---|---|---|---|
| FN-1 | **Penagihan pembeli macet** (DP/cicilan/termin) | Tak ada jadwal & reminder; aging tak terlihat | **AR schedule + reminder otomatis + AR aging + worklist penagihan + denda** | AR overdue ↓; DSO ↓ |
| FN-2 | **KPR pencairan lambat/tak terlacak** | Status bank tak terpantau, tak terkait milestone | **Financing tracker (status, plafon, pencairan bertahap terkait milestone konstruksi)** | Waktu pencairan ↓; cash-in tepat |
| FN-3 | **Subcon telat dibayar → proyek berhenti** | Tak ada visibilitas kas & termin | **AP subcon (dari termin) + cash-flow projection dari jadwal AR/AP** | Proyek mangkrak akibat cash ↓ |
| FN-4 | **Sengketa retensi** | Retensi tak tercatat/terlepas tak jelas | **Retentions Payable + jadwal pelepasan (masa pemeliharaan)** | Dispute retensi ↓ |
| FN-5 | **Pengakuan pendapatan salah** (terlalu dini) | Tak paham PSAK 72 | **DP/termin = Contract Liability; revenue diakui saat BAST (point-in-time) + COGS** | Laporan akurat & audit-ready |
| FN-6 | **Fraud** (under-invoicing, manipulasi laporan) | Pengawasan lemah, tekanan target | **Approval berjenjang + jejak audit + 3-way match + segregation via RBAC** | Anomali terdeteksi; kontrol ↑ |
| FN-7 | **Pajak** (PPN/BPHTB/PPh) terlewat | Perhitungan manual | **Tax worksheet + dokumen + reminder jatuh tempo** | Kepatuhan ↑; denda pajak ↓ |

---

## 4. PILAR KEPERCAYAAN PEMBELI (customer trust) — sering diabaikan, padahal kritikal

> Grounded: keluhan konsumen properti ID berulang **10 tahun terakhir** — minim transparansi progres, BAST tak sesuai spesifikasi, cacat bangunan lambat ditangani, komplain diabaikan. Ketiadaan **customer portal** = penurun kepercayaan utama.

| Pain pembeli | Yang SIPRO lakukan | Outcome/KPI |
|---|---|---|
| Progres pembangunan tak transparan | **Customer Portal: progres (kurva-S/%/foto), jadwal pembayaran, status dokumen** | Kepercayaan ↑; komplain "tak tahu progres" ↓ |
| BAST tak sesуai spesifikasi | **Checklist serah terima + punch list bersama pembeli + BAST digital** | Sengketa serah terima ↓ |
| Cacat bangunan lambat ditangani | **Kanal komplain resmi + SLA perbaikan + tracking status (masa garansi)** | Waktu respons komplain ↓ (target ≤7 hari) |
| Dokumen legal tak jelas | **Status dokumen (PPJB/AJB/sertifikat) transparan di portal** | Transparansi ↑ |

> Customer Portal bukan "nice to have": ia langsung mengurangi sengketa, mempercepat pembayaran (pembeli percaya → bayar tepat waktu), dan membangun reputasi (referral ↑).

---

## 5. RINGKAS: PEMETAAN PAIN → EPIC (prioritas)

| Outcome | Pain teratas | EPIC penjawab (Dok 04) |
|---|---|---|
| Konversi ↑ | Respons lambat, lead bocor, KPR ditolak, guided selling | EPIC 1.0 Work Hub, 1.1 Lead, 1.5 KPR pra-skrining |
| Cegah kebocoran | Material dicuri/over-order, fraud | EPIC 2.1 BoQ/MRP, 2.x Material ledger+opname, 3.6 audit/3-way match |
| Jaga deadline | Dokumen/perizinan lambat, deviasi jadwal | EPIC 1.4 PPJB tracker, 2.3 Progress+Kurva-S, F9 Timeline |
| Arus kas & trust | Penagihan macet, subcon telat, pembeli tak percaya | EPIC 3.0 AR, 3.1 AP+retensi, 3.2 RevRec, M1 Customer Portal |

> Catatan penyeimbang: sebagian mitigasi terbaik (mis. BIM, RFID penuh, AI scoring) bersifat **lanjutan**. SIPRO memprioritaskan yang **berdampak tinggi & risiko rendah** dulu (SLA/task, opname, AR/aging, timeline, portal) lalu mematangkan (AI/real-time/BIM).
