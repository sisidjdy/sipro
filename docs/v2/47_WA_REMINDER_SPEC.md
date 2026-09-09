# 47 — SPEC PENGINGAT WHATSAPP OTOMATIS (Fase 51B)

> Dasar: pembacaan kode yang berjalan (`backend/wa_reminder_engine.py`,
> `backend/routers/reminders_router.py`, `backend/scheduler_p51.py`,
> `backend/settings_store.py` grup `pengingat`, `backend/reference_p51.py`,
> `frontend/src/components/omni/RemindersPanel.js`). Cakupan: (a) kandidat pengingat
> **dihitung** dari data yang sudah dimiliki sistem, (b) ambang batas dari Pusat
> Konfigurasi, (c) satu periode satu pengingat (dedup dijaga index unik), (d) status yang
> jujur (simulasi ≠ terkirim), (e) riwayat yang bisa diaudit.
>
> Status: **✅ ADA** (mode kirim **🎭 SIMULASI** selama `WHATSAPP_TOKEN`/`WHATSAPP_PHONE_ID`
> kosong) — dibuktikan gate 42 `scripts/verify_wa_reminders.py` (53 pemeriksaan) dan
> uji-mutasi `scripts/mutasi_51.py` (M23–M39, M52).

---

## 1. Yang SUDAH ADA sebelum Fase 51B

| Modul | Kemampuan |
|---|---|
| `notifications.py` (`send_whatsapp`, `whatsapp_configured`) | lapisan kirim WA Cloud API + mode simulasi bila kredensial kosong (Fase 30) |
| `wa_templates` (Fase 29b) | template pesan yang disetujui, bisa diubah tanpa menyentuh kode |
| `ar_invoices.items[].due_date` | jadwal termin + tunggakan (Fase 27) |
| `unit_handovers.warranties[].expires_at` | tanggal habis garansi **per bagian** (Fase 50) |
| `settings_store.py` | registry setelan + jejak perubahan |
| `wa_playbooks.py` | urutan pesan follow-up **lead** (bukan pengingat kewajiban pembeli) |

**Lubang inti:** semua tanggal penting sudah tersimpan, tetapi **tidak ada satu pun yang
memberi tahu pembelinya.** Pengingat dikirim manual oleh staf: tidak konsisten, tidak ada
jejak siapa sudah diingatkan, dan bila stafnya sibuk tunggakan berkembang diam-diam
sementara garansi habis tanpa pembeli tahu haknya akan berakhir.

---

## 2. Aturan keras modul ini

1. **Kandidat DIHITUNG, tidak diketik.** Tidak ada daftar penerima manual; kandidat lahir
   dari `ar_invoices.items[].due_date` dan `unit_handovers.warranties[].expires_at`.
2. **Ambang batas dari Pusat Konfigurasi** (grup `pengingat`), bukan angka mati:

   | Key | Bawaan | Arti |
   |---|---|---|
   | `reminder.enabled` | `true` | saklar utama pengingat otomatis |
   | `reminder.warranty_days` | `30` | garansi diingatkan bila sisa ≤ N hari |
   | `reminder.installment_days_before` | `3` | termin diingatkan H‑N sebelum jatuh tempo |
   | `reminder.overdue_every_days` | `7` | ember waktu tunggakan (satu pengingat per rentang) |
   | `reminder.template_warranty` / `_installment` / `_overdue` | `payment_reminder` | kode template `wa_templates` yang dipakai |

   `GET /api/reminders/settings` **wajib** mengirim `setting_keys[]` supaya layar bisa
   menautkan ke Pusat Konfigurasi, bukan menjadi jalan buntu.
3. **Satu periode satu pengingat.** `dedup_key` per jenis:

   | Jenis | `dedup_key` |
   |---|---|
   | `warranty_expiring` | `warranty_expiring:{handover_id}:{category}:{expires_at}` |
   | `installment_due` | `installment_due:{invoice_id}:{item}:{due_date}` |
   | `installment_overdue` | `installment_overdue:{invoice_id}:{item}:{tahun}W{minggu}` |

   Dijaga **index unik database** `uq_wa_reminder_dedup` (`org_id`, `dedup_key`) —
   scheduler, tombol manual, dan percobaan ulang boleh bertemu tanpa pesan ganda.
4. **Jujur soal status** (SSOT `reminder_status`): tanpa kredensial WhatsApp status
   `simulasi` (bukan `terkirim`); penerima tanpa nomor `dilewati` + `reason_code=no_phone`;
   template hilang → `dilewati` + `template_missing`. Tidak ada yang disembunyikan dan tidak
   ada yang dihitung sebagai keberhasilan.
5. **Isi pesan dari template yang disetujui**, bukan kalimat karangan kode. Variabel
   `{{nama}}`, `{{unit}}`, `{{termin}}`, `{{nominal}}`, `{{tanggal}}`, `{{bagian}}`,
   `{{sisa}}` diisi dari data kandidat, lalu `reason` kandidat ditempel agar pesannya tetap
   spesifik.
6. **Tidak mengingatkan hal yang sudah beres**: termin lunas (`sisa_bayar <= 0`), tagihan
   `paid`, garansi yang sudah habis (`sisa < 0`), dan rumah yang belum diserahterimakan
   tidak menghasilkan kandidat.
7. **Identitas penerima ditulis di kolom yang benar** (SSOT `reminder_recipient`): rumah yang
   belum akad belum punya pelanggan, jadi penerimanya `lead` dan id-nya masuk `lead_id` —
   **tidak pernah** ke `customer_id` (dulu ini membuat audit forensik melaporkan FK yatim).

---

## 3. Endpoint & RBAC

| Endpoint | Izin | Jawaban |
|---|---|---|
| `GET /api/reminders/settings` | `reminders:view` | ambang batas + `mode` (`simulasi`/`nyata`) + `mode_detail` + `setting_keys[]` + `hint` jadwal berikutnya |
| `GET /api/reminders/candidates` | `reminders:view` | kandidat hari ini + `reason` + `dedup_key` + `blocked_code`/`blocked_reason`, plus ringkasan `ready`/`blocked` |
| `GET /api/reminders` | `reminders:view` | riwayat (siapa menjalankan, isi pesan, template, status) + `by_status` |
| `POST /api/reminders/run` | `reminders:**manage**` | jalankan sekarang; ringkasan `sent`/`simulated`/`skipped` per jenis + `mode` |

Pemisahan yang disengaja: **semua** peran yang berhubungan dengan pembeli boleh MELIHAT
("pembeli ini sudah diingatkan belum?" adalah pertanyaan kerja harian) — `sales`,
`project_manager`, `finance` termasuk. Yang boleh MENJALANKAN hanya peran pengelola
(`sales_manager`, `marketing_admin`, `dm_supervisor`, `finance_manager`, `owner`,
`super_admin`), karena menjalankannya berarti mengirim pesan sungguhan ke pelanggan.

**Scheduler:** `scheduler_p51.register` menambah job `wa_reminder_daily` pada 01:00 UTC
(= 08:00 WIB). Sekali sehari, bukan tiap jam: ambangnya dihitung dalam HARI, jadi memeriksa
lebih sering hanya menambah risiko pesan ganda tanpa menambah manfaat. Jam kirim yang sopan
adalah bagian dari kualitas pengingat.

---

## 4. Layar (`/automation?tab=reminders` → `components/omni/RemindersPanel.js`)

| Bagian | testId | Aturan |
|---|---|---|
| Banner mode kirim | `remindersMode` | menyebut `simulasi`/`nyata` **apa adanya** beserta sebabnya |
| Kartu ambang batas | `remindersSettings`, `remindersSettingRow`, `remindersConfigLink` | angka + key-nya, tertaut ke Pusat Konfigurasi grup `pengingat` |
| Jalankan sekarang | `remindersRunBtn`, `remindersRunDialog`, `remindersRunKind`, `remindersRunSubmit`, `remindersRunCancel`, `remindersRunResult` | hanya peran ber-`manage`; hasilnya memisahkan terkirim/simulasi/dilewati |
| Kalimat bagi peran tanpa izin | `remindersRunDenied` | kalimat manusiawi, **bukan** tombol mati atau `[object Object]` |
| Kandidat | `remindersSubTabCandidates`, `remindersCandidateRow`, `remindersCandidateBlocked`, `remindersCandidateEmpty` | kandidat tertahan tetap tampil beserta sebabnya |
| Riwayat | `remindersSubTabHistory`, `remindersHistoryRow`, `remindersHistoryBody`, `remindersHistoryEmpty` | isi pesan bisa dibaca ulang; status & jenis memakai `StatusPill group="reminder_status"`/`"reminder_kind"` |

Dua cacat layar yang sudah diperbaiki dan **tidak boleh kembali**:
1. Tab dikendalikan `?tab=` (pola `/subcon`) — sebelumnya `defaultValue="rules"` membuat
   setiap tautan/muat-ulang mendarat di tab Automasi.
2. Tab yang **tidak berizin tidak dirender**, dan tab bawaan adalah tab pertama yang boleh
   dibuka — sebelumnya Manajer Keuangan disambut kotak merah "Akses ditolak … wa_templates"
   sehingga halaman tampak rusak.

---

## 5. Data & index

`wa_reminders` (koleksi baru Fase 51B):

| Field | Arti |
|---|---|
| `kind` | SSOT `reminder_kind` |
| `dedup_key` | penanda periode (lihat §2.3) — **unik** bersama `org_id` |
| `entity_type` / `entity_id` | `ar_invoice` atau `unit_handover` sumber kandidat |
| `unit_id` / `unit_code` | rumah yang diingatkan |
| `customer_id` / `lead_id` / `recipient_type` | identitas penerima di kolom yang benar |
| `phone`, `name` | penerima saat pengingat dibuat |
| `amount`, `due_date`, `days_left`, `reason` | dasar pengingat yang bisa diperiksa ulang |
| `status`, `reason_code`, `detail` | SSOT `reminder_status` + `reminder_skip_reason` + kalimat sebab |
| `body`, `template_code` | isi pesan & template yang dipakai |
| `run_by`, `created_at` | siapa/kapan menjalankan (`system`, `scheduler`, atau email pemakai) |

Index: `uq_wa_reminder_dedup` (`org_id`, `dedup_key`, **unique**) — didaftarkan di
`backend/indexes.py`.

---

## 6. Guardrail (cara membuktikan cepat)

```bash
python3 scripts/verify_wa_reminders.py            # gate 42 — 53 pemeriksaan
python3 scripts/mutasi_51.py --only=M30,M31,M52   # dedup, kejujuran status, index unik
bash scripts/run_all_gates.sh                     # 43 gate, OVERALL PASS
```

Gate 42 membuktikan W1–W11: setelan & mode jujur, kandidat dari data nyata, ambang benar-benar
dipakai (diubah → kandidat hilang, dikembalikan → muncul lagi), RBAC jalankan, dedup dua-kali-
jalan, kejujuran simulasi, penerima tanpa nomor, yang sudah beres tidak diingatkan, riwayat
bisa diaudit, keunikan dijaga **database**, dan permukaan layar (tidak ada testId 51B yang mati).

**Catatan penting untuk pengembang berikutnya:** gate 42 **menolak berjalan** bila
`mode == "nyata"`. Menjalankan pengingat dengan kredensial nyata berarti mengirim WhatsApp
ke pelanggan sungguhan hanya untuk menghijaukan gate — itu merugikan orang di luar layar.
Kosongkan `WHATSAPP_TOKEN`/`WHATSAPP_PHONE_ID` di lingkungan uji.

Gate & POC juga **memulihkan slot dedup** milik data demo setelah selesai (hanya baris
berstatus `simulasi`/`dilewati` — baris `terkirim` adalah fakta dan tidak pernah dihapus),
sehingga layar `/automation?tab=reminders` tidak berakhir dengan semua kandidat berlabel
"Sudah diingatkan untuk periode ini".

---

## 7. Yang SENGAJA tidak dikerjakan di 51B
1. **Tidak ada balasan masuk (inbound).** Pengingat adalah satu arah; percakapan tetap di
   Omnichannel/Playbook WA yang sudah ada.
2. **Tidak ada pengingat internal ke staf** dari modul ini — pekerjaan staf sudah punya Work
   Hub & notifikasi.
3. **Tidak ada penjadwalan per pelanggan** ("jangan hubungi saya hari Minggu"). Bila
   dibutuhkan, tempatnya di Pusat Konfigurasi + preferensi pelanggan, bukan di mesin ini.
