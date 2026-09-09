# 31 — SPEC ANALYTICS & BI (kamus metrik + endpoint + visualisasi)

> Permintaan owner: analitik **advanced**, visualisasi bagus, dipakai untuk **pengambilan keputusan**. Menutup CR-13, CR-14, CR-15, CR-16, CR-17.
> Pustaka: **recharts 3.6.0 sudah terpasang** (`frontend/package.json:58`) — dipakai untuk semua grafik. Tabel pro memakai `@tanstack/react-table` (satu-satunya dependensi baru).
> Aturan kejujuran angka (pelajaran Fase 36/37): bila input tidak lengkap → tampilkan **"data belum lengkap"**, jangan tampilkan 0. Setiap KPI **wajib bisa di-drill-down** ke daftar barisnya.

## 1. Arsitektur lapisan metrik
```
mentah (koleksi)  ─► metrics/*.py (fungsi murni, 1 metrik = 1 fungsi, ada docstring rumus)
                        │
                        ├─► /api/analytics/*   (hitung langsung, periode kecil)
                        └─► metric_snapshots  (job harian untuk periode besar; selalu bisa dihitung ulang — INV-14)
```
Setiap fungsi metrik mengembalikan `{value, breakdown[], inputs{}, complete: bool, missing[]}` sehingga UI bisa jujur soal kelengkapan data.

## 2. Dashboard per persona (5 halaman di seksi **Analitik & BI**)

| Halaman | Untuk | Isi utama |
|---|---|---|
| **Eksekutif** | owner/direksi | penjualan kumulatif vs target, pendapatan vs RAB+budget (margin), kas masuk, unit terjual, proyeksi selesai proyek, 5 risiko teratas |
| **Penjualan & Lead** | sales manager | funnel per tahap + conversion/churn, velocity, aging, sumber terbaik, demografi, kinerja per sales, alasan lost/reschedule |
| **Marketing** | DM supervisor | spend, CPL, CAC, ROAS per kampanye/adset/ad/creative, mitra vs ads vs organik, attribution + CAPI |
| **Proyek & Biaya** | PM/owner | progres vs rencana, telat, realisasi RAB vs rencana (overbudget), biaya per unit, kurva-S portofolio |
| **Kinerja Tim** | supervisor semua divisi | aktivitas harian per user, ketepatan waktu, bukti, beban kerja, rapor mingguan |

## 3. Kamus metrik — PENJUALAN & UNIT

| Kode | Nama | Rumus | Sumber |
|---|---|---|---|
| `SLS-01` | Unit terjual (kumulatif sejak proyek mulai) | `count(units where sales_status ∈ {booked,sold,handed_over} and contract.signed_at ≤ t)` per hari/bulan (seri kumulatif) | `units`, `contracts` |
| `SLS-02` | Absorpsi | `terjual / total unit` per cluster/proyek | `units` |
| `SLS-03` | Nilai penjualan (booking value) | `Σ contracts.total (aktif)` | `contracts` |
| `SLS-04` | Pendapatan diakui | `Σ revenue_recognitions` | GL (sudah ada) |
| `SLS-05` | Kas masuk | `Σ receipts` per periode | `receipts` |
| `SLS-06` | Piutang jatuh tempo | `Σ ar_invoices overdue` + bucket umur (sudah ada aging) | `ar_invoices` |
| `SLS-07` | Rata-rata harga jual | `Σ nett_price / jumlah kontrak` | `contracts` |
| `SLS-08` | Komposisi skema bayar | share `cash_keras/cash_bertahap/kpr` | `contracts` |
| `SLS-09` | Pendapatan add-on | `Σ price_breakdown[treatment=revenue, code≠unit_price]` | permintaan owner (komponen terpisah) |
| `SLS-10` | Waktu jual per unit | `contract.signed_at - unit.first_listed_at` (median) | `units` |
| `SLS-11` | Pembatalan & refund | jumlah + nilai + potongan diakui | `contracts.cancellation` |

## 4. Kamus metrik — LEAD & LIFECYCLE

| Kode | Nama | Rumus |
|---|---|---|
| `LED-01` | Lead masuk | `count(leads)` per periode/sumber/kampanye/mitra |
| `LED-02` | **Conversion rate per tahap** | `masuk_tahap_n+1 / masuk_tahap_n` dalam kohor periode (hitung dari `stage_history`, bukan status akhir) |
| `LED-03` | **Churn/drop per tahap** | `1 - LED-02`; plus `lost_di_tahap_n / masuk_tahap_n` |
| `LED-04` | Velocity per tahap | median(`stage_durations[stage]`) |
| `LED-05` | Aging distribution | histogram umur tahap (0–1h, 1–3h, 3–7h, >7h) |
| `LED-06` | Speed-to-lead | median(`response_time_minutes`) + % ≤ 15 menit |
| `LED-07` | Win rate | `won / (won + lost)` |
| `LED-08` | **CAC** | `(ad_spend + partner_fee_approved + marketing_opex) / count(won)` per periode/kanal — komponen bisa dipilih di UI (transparan) |
| `LED-09` | CPL / cost per qualified | `spend / leads`, `spend / qualified` |
| `LED-10` | Alasan lost (pareto) | group by `close_reason` |
| `LED-11` | Alasan reschedule/batal survei | group by `reason_code` (`appointment_events`) |
| `LED-12` | **Demografi** | distribusi `demography.*` × tahap/menang (usia, pekerjaan, penghasilan, domisili, tanggungan) |
| `LED-13` | Kualitas per sumber | funnel per `source` + `partner_id` |
| `LED-14` | Lead tanpa tindak lanjut | `count(lead where sla_due_at < now and stage aktif)` |
| `LED-15` | Kohor bulanan | matriks kohor bulan masuk × tahap tercapai (retensi pipeline) |

## 5. Kamus metrik — PROYEK, RAB & BIAYA (link ke [32](32_TARGET_BUDGET_SPEC.md))

| Kode | Nama | Rumus |
|---|---|---|
| `PRJ-01` | Progres proyek | rata-rata berbobot progres unit (mesin Fase 31) |
| `PRJ-02` | Deviasi jadwal | `realisasi% - rencana%` per unit/proyek + jumlah unit telat |
| `PRJ-03` | **Realisasi RAB** | `Σ biaya aktual dengan cost_ref.boq_item_id` (dari PO/GRN/AP/SPK claim/material_txns) |
| `PRJ-04` | **RAB vs realisasi** | `realisasi / rencana` per item/kategori/unit/proyek + selisih Rp |
| `PRJ-05` | **Overbudget** | `realisasi > rencana` (general proyek) → drill-down per kategori → per item → per dokumen sumber |
| `PRJ-06` | Biaya per unit | `Σ biaya cost_ref.unit_id / 1` + perbandingan antar unit tipe sama |
| `PRJ-07` | Margin proyek | `pendapatan diakui − (RAB realisasi + budget operasional realisasi)` |
| `PRJ-08` | Proyeksi selesai | dari kecepatan progres + kalender kerja (mesin Fase 36/37) |
| `PRJ-09` | Komitmen belum tertagih | `Σ PO open` (agar overbudget tidak terlambat terlihat) |
| `RAB-01` | **RAB total terstruktur** (Fase 81b) | `Σ (RAB tipe × unit) + RAB add-on terjual + fasum/fasos + umum + item lama` — `rab_engine.project_summary` |
| `RAB-02` | **Margin HPP proyeksi** | `(harga jual seluruh unit + add-on terjual) − RAB total terstruktur` (persona eksekutif) |
| `RAB-03` | Margin HPP per tipe unit | `(Σ harga jual − Σ HPP) / Σ harga jual` per tipe; HPP = RAB tipe + alokasi biaya bersama; unit <10% dihitung sebagai margin tipis |
| `RAB-04` | **SPK fasum melampaui progres fase** | `count(termin disetujui % > progres fase konstruksi tertaut %)` — `rab_engine.fasum_control` |
| `RAB-05` | Selisih SPK terhadap RAB | `Σ (nilai kontrak SPK − dasar RAB)` pada SPK yang lahir dari RAB (`spk.rab_lines`, `override_count`) |
| `RAB-06` | Revisi RAB tipe/add-on | `count(rab_template_versions.replaced_at ∈ rentang)` + selisih total versi pertama → aktif per tipe |

> Catatan Fase 81b: `BGT-06` (margin proyeksi) kini memakai RAB total terstruktur yang sama dengan `RAB-01`, bukan lagi `Σ boq_items` flat.

## 6. Kamus metrik — KINERJA USER (permintaan owner: laporan harian per user)

`user_daily_activity` diisi oleh job harian + real-time increment. `counters` minimal:
`leads_new_assigned, wa_sent, wa_replied, calls_logged, appointments_created, appointments_done, surveys_filled, docs_uploaded, docs_verified, spr_issued, contracts_signed, payments_verified, tasks_done, tasks_late, progress_submitted, inspections_done, punch_closed`.

| Kode | Nama | Rumus |
|---|---|---|
| `USR-01` | Aktivitas harian | tabel user × hari × counter (dari `activities`, `tasks`, `messages`, `stage_history.actor`) |
| `USR-02` | Ketepatan waktu | `tugas selesai ≤ due / total selesai` (definisi Fase 29d dipertahankan) |
| `USR-03` | Kontribusi pipeline | lead ditangani → tahap tercapai → nilai kontrak |
| `USR-04` | Waktu respons | median waktu balas WA per user |
| `USR-05` | Beban kerja | tugas aktif + lead aktif per user (deteksi overload) |
| `USR-06` | Bukti kerja | rata-rata lampiran per tugas selesai |
| `USR-07` | Jejak siapa mengerjakan tahap | dari `stage_history.actor` — per tahap per user (permintaan owner) |

**Laporan harian** (`GET /api/analytics/users/daily?date=&user=`) menghasilkan ringkasan naratif + tabel; bisa dikirim otomatis (WA/email) ke supervisor lewat penjadwal yang sudah ada.

## 7. Endpoint analitik
```
GET /api/analytics/executive?project_id=&period=
GET /api/analytics/sales/funnel?from=&to=&group_by=source|campaign|partner|sales
GET /api/analytics/sales/cohort?from=&to=
GET /api/analytics/sales/units-sold?project_id=&granularity=day|week|month   (SLS-01 kumulatif)
GET /api/analytics/leads/aging
GET /api/analytics/leads/demography?dimension=age|occupation|income|domicile
GET /api/analytics/marketing/performance?level=campaign|adset|ad|creative
GET /api/analytics/marketing/cac?components=ads,partner,opex
GET /api/analytics/project/budget-vs-actual?project_id=&drill=category|item|unit
GET /api/analytics/project/schedule-health?project_id=
GET /api/analytics/users/daily?date=&user=
GET /api/analytics/users/leaderboard?from=&to=&metric=
GET /api/analytics/export?metric=&format=csv|xlsx
```
Semua endpoint: RBAC-aware (sales hanya datanya sendiri kecuali punya `view_all`), mendukung `project_id`, `cluster_id`, `from/to`, `group_by`, dan mengembalikan `complete/missing`.

## 8. Visualisasi (recharts) — pilih grafik sesuai pertanyaan

| Pertanyaan | Grafik | Komponen |
|---|---|---|
| Sudah berapa terjual vs target? | **area kumulatif + garis target** | `AreaChart` + `ReferenceLine` |
| Di mana lead bocor? | **funnel bertingkat + label %** | bar horizontal bertumpuk (funnel jujur, angka di label) |
| Kampanye mana efisien? | **scatter CPL vs conversion** + ukuran = spend | `ScatterChart` |
| Biaya vs anggaran? | **bar rencana vs realisasi + garis 100%** | `BarChart` + `ReferenceLine` |
| Progres proyek? | **kurva-S** rencana vs realisasi | `LineChart` |
| Umur pipeline? | **histogram aging** + heatmap tahap×umur | `BarChart`, grid warna |
| Kohor lead? | **matriks kohor** | tabel warna (bukan chart) |
| Kinerja tim? | **bar peringkat + sparkline tren** | `BarChart`, `LineChart` mini |
| Komposisi (skema bayar/sumber) | **donut maksimal 6 irisan** + sisanya "lainnya" | `PieChart` |

Aturan: maksimal **2 sumbu y**, tanpa 3D, tanpa animasi lebay; legenda kontras (gate Fase 38); setiap grafik punya tombol **CSV** & **PNG**; klik elemen → drill-down tabel.

## 9. Definition of Done
1. Semua metrik di §3–§6 punya endpoint + tampilan + drill-down.
2. Angka bisa direkonstruksi manual (uji: hitung ulang 5 metrik dari data mentah → sama).
3. Bila `ad_spend` kosong → CPL/CAC/ROAS menampilkan "data biaya belum lengkap" (uji negatif).
4. RBAC: sales tidak bisa melihat data sales lain (uji 403/filter).
5. Ekspor CSV/XLSX bekerja untuk semua tabel analitik.
6. Gate baru `verify_analytics.py` (uji-mutasi angka) + `run_all_gates.sh` PASS.
