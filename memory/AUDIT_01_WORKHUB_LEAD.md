# AUDIT 01 — WORK HUB & LEAD LIFECYCLE (desain awal vs kondisi terdevelop)

> Dibuat oleh main agent atas permintaan owner: "telusuri desain awal, bandingkan dengan
> kondisi sekarang, laporkan". Semua klaim di bawah punya **bukti** (file:baris atau
> respons API nyata di environment ini, DB hasil seed bersih).

---

## BAGIAN 1 — WORK HUB

### 1.1 Desain awal (Dok 03 §2–§3, Dok 13 §3–§5)
| Unsur | Ketentuan desain |
|---|---|
| Role-Home | Tiap peran punya Home berbeda (Hari Saya / Performa Tim / Keuangan / Proyek / Control Tower), **config-driven** |
| Task Inbox | **Sumber kebenaran PEKERJAAN** pribadi: Terlambat / Hari ini / Akan datang / Menunggu saya + SLA countdown + related record + **tombol aksi terpandu** |
| Sumber task | **Guided Work Engine**: event → task (idempotent `source_event`) + manual |
| NBA | Panel "Langkah Berikutnya" **di setiap record**, tiap NBA WAJIB memetakan ke *guided flow* (tak ada CTA mati) |
| Kolaborasi | Activity feed + komentar/@mention/thread + channel per proyek/deal |

**Yang TIDAK ADA di desain awal (temuan penting):** konsep **divisi**, **supervisor**,
**katalog jobdesk per divisi**, **penugasan oleh supervisor**, **task berulang (recurring)**,
dan **verifikasi hasil kerja oleh atasan**. Dok 03 hanya mengenal 8 peran datar + Role-Home.
Jadi keluhan "workhub kacau / tidak jelas" bukan sekadar bug implementasi — **modelnya
memang belum pernah dirancang**.

### 1.2 Kondisi sekarang + bukti

**D-1 (KRITIS) Dua definisi "tugas saya" yang saling bertolak belakang.**
- `work_router.py:35–41` (`_my_open_tasks`, dipakai `GET /work/home`) → filter `assigned_to`
  **dilewati** untuk `super_admin`/`owner` (FULL_ACCESS_ROLES).
- `work_router.py:57–58` (`GET /work/tasks`) → filter `assigned_to` **hanya** untuk
  `super_admin`/`owner`.
- Bukti nyata (DB seed, 13 task, 0 di antaranya milik superadmin):

| Peran | `/work/home` (Beranda) | `/work/tasks?filter=mine` | `/work/tasks?filter=all` |
|---|---|---|---|
| super_admin | **13** (tugas orang lain, dilabeli "Hari Saya") | **0** | 13 |
| sales_manager | 1 (benar, miliknya) | **13** (tugas semua orang) | 13 (identik → tombol filter tak berfungsi) |

→ Inilah penyebab persis keluhan owner: Beranda penuh, "Tugas Saya" nol.

**D-2 Cakupan task sangat tipis** — WorkHub tidak bisa jadi "pintu pekerjaan".
- Hanya **19 titik** `auto_create_task(` di seluruh backend (`engine.py` 6, leads 2, deals 2,
  construction 2, procurement/portal/materials/inspection/field/petty_cash/loans/finance_reports 1).
- Modul **tanpa task sama sekali**: dokumen legal (SPR/PPJB/BAST/AJB), subkon & SPK, RAB/BoQ,
  Buku Besar/Jurnal, Laporan Keuangan, Pajak, Marketing Fee, Aset Tetap, Customer/KYC,
  penyelesaian Appointment, Site Plan, lead Showroom, Broadcast, Survey, Komplain internal.
- Kosakata tipe task hanya 7 generik (`todo, contact, follow_up, review, approval, inspection,
  payment`) — tidak ada jobdesk per divisi.

**D-3 Tidak ada domain divisi/tim/supervisor.**
- `rbac.py:20–23`: 8 peran datar (`super_admin, owner, sales_manager, marketing_admin, sales,
  finance, project_manager, site_engineer`).
- Tidak ada koleksi `divisions`/`teams`, tidak ada field atasan/anggota di `users`.
- **Tidak ada peran Digital Marketing** (yang terdekat `marketing_admin`).
- Finance & Teknis tanpa supervisor eksplisit (PM merangkap supervisor teknis).

**D-4 Tidak ada mesin penugasan supervisor.**
- `POST /api/work/tasks` **ada di backend tetapi tidak dipakai UI mana pun**
  (grep `work/tasks` di frontend → hanya GET list, complete, snooze).
- Tidak ada: reassign, papan tugas per divisi, beban kerja (workload), task **berulang**,
  template jobdesk, terima/tolak tugas, eskalasi ke atasan.

**D-5 Selesai tanpa bukti.** `TaskComplete` = `{outcome?: str}` (`models.py:61`) — teks bebas,
tidak memeriksa aksi bisnis benar-benar terjadi. "Hubungi lead" bisa ditandai selesai tanpa
kontak apa pun. Status `in_progress` tidak pernah dipakai di UI (hanya Selesai/Snooze).

**D-6 Kosakata status task melanggar SSOT.** `reference.task_status` =
`open|in_progress|snoozed|done|cancelled`, tetapi `work_router.py:110` menulis
`status="completed"` (nilai di luar SSOT).

**D-7 CTA mati (melanggan Dok 13 §5).** `Home.js:46` → aksi NBA hanya `navigate("/tasks")`;
`TaskCard.js:56–60` menampilkan tipe entitas sebagai **teks** tanpa deep-link ke record.

**D-8 KPI Home sebagian bukan data nyata.** `work_router.py:186–189`: KPI finance
"AR Outstanding" & "AP + Retensi Due" **hardcoded 0**. Control Tower hanya total
lead/deal/proyek/pengguna — bukan penjualan hari/MTD, kas, approval pending (Dok 03 §2).

---

## BAGIAN 2 — LEAD LIFECYCLE

### 2.1 Desain awal (Dok 12 §1, Dok 07 Bagian C, Dok 13 §4–§5)
Transisi stage adalah **akibat aksi/event + bukti**, bukan pilihan bebas:

| Dari | Pemicu (guard) | Ke | Efek |
|---|---|---|---|
| (buat) | `lead.created` | acquisition | Task "Hubungi ≤5 mnt", auto-assign |
| acquisition | kontak pertama **atau WA masuk** | nurturing | set `first_contacted_at` sekali + `response_time_minutes` |
| nurturing | appointment dibuat/dikonfirmasi via chat | appointment | Task siapkan survey |
| appointment | reservasi/booking dibuat | booking | Deal draft |
| any | tidak ada respons X hari (scheduler) | recycle | Task re-engage + `recycle_reason` |
| recycle | re-kontak | nurturing/acquisition | reset follow-up |

Ditambah: keyword intent WA → **usulan NBA** naik stage (human-in-the-loop, `require_confirmation`).

### 2.2 Kondisi sekarang + bukti

**L-1 (KRITIS) Stage bisa dipilih seenaknya.** `LeadDetail.js:145–158` menyediakan dropdown
"Ubah Stage" + tombol Terapkan; `leads_router.py:203` **hanya** memeriksa ketetanggaan
`STAGE_FLOW` — tidak ada syarat bukti. Bukti eksekusi nyata (peran sales_manager):
- `nurturing → booking` **BERHASIL** padahal lead itu **tidak punya deal** (`deals` untuk lead = `[]`).
- `booking → won` **BERHASIL** padahal deal terkait masih `booked` (belum lunas/akad/BAST).
(kedua perubahan sudah dikembalikan setelah pembuktian)

**L-2 Sebagian sudah aksi-berbasis (yang ini benar).** `first-contact` → nurturing
(`leads_router.py:171`), appointment dibuat → appointment (`:279`), deal dibuat → booking
(`deals_router.py:98`).

**L-3 Jalur akhir & mundur tidak lengkap.** Tidak ada jalur otomatis ke `won` (dari deal
completed/BAST/pelunasan) — hanya dropdown manual. `lost` tidak butuh alasan;
`no_response_sweeper` (`engine.py:520–548`) **tidak** memindahkan stage ke `recycle`
(hanya kirim template + task) — berbeda dari Dok 12 §1. Tidak ada `lost_reason`/`recycle_reason`.

**L-4 (KRITIS) WA in-system terputus dari lifecycle.** `inbox_router.py:77–119` (kirim/terima
pesan): tidak menulis `first_contact_at`, tidak menghitung `response_time_minutes`, tidak
menambah activity ke **timeline lead**, tidak memajukan stage. Balasan pelanggan hanya
memicu **task usulan**. Di `LeadDetail.js` **tidak ada tombol WA / thread percakapan** →
sales harus keluar ke `/inbox` dan mencari percakapan sendiri.

**L-5 Usulan NBA berhenti jadi teks.** `engine.py:297–304` action `suggest_stage` membuat task
berjudul "Usulan (NBA): majukan stage lead ke '...'" **tanpa** tombol Setuju/Tolak → tidak ada
1-klik terapkan (padahal Dok 13 §4 mensyaratkan human-in-the-loop yang bisa dieksekusi).

**L-6 Usulan bisa melompat ke `won`.** `inbox_router.py:124–127` `NEXT_STAGE` memetakan
`booking → won`, sehingga chat bisa menyarankan "won" tanpa deal/pembayaran.

**L-7 Tidak ada `stage_history`.** Tidak ada catatan siapa/kapan/berapa lama tiap stage →
tidak bisa mengukur kecepatan funnel maupun mengaudit lompatan stage (hanya activity teks).

**L-8 UX tidak memandu.** Tidak ada panel "Langkah Berikutnya" di record lead (Dok 03 §3.2),
tidak ada checklist syarat naik stage, tidak ada stepper/pipeline visual di detail; aksi
(Kontak Pertama / Jadwalkan Survey / Buat Reservasi) berjejer tanpa urutan & tanpa keterangan
mana yang seharusnya dilakukan sekarang.

---

## RINGKAS PENYEBAB
1. **Model domain kerja belum ada** (divisi/supervisor/jobdesk/recurring/verifikasi).
2. **Task engine baru "menempel" di 19 titik** — bukan lapisan yang membungkus semua fitur.
3. **Semantik scope task tidak konsisten** antara Home dan halaman Tugas (D-1).
4. **Lifecycle lead ditegakkan sebagai graf transisi**, bukan **gerbang bukti**; dan kanal WA
   yang seharusnya jadi pemicu utama tidak tersambung ke record lead.
