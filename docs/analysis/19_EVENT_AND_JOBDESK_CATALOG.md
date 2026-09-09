# KATALOG EVENT & JOBDESK — MANA YANG BISA OTOMATIS, MANA YANG WAJIB MANUSIA

> Dibuat atas permintaan owner: "kembangkan event apa saja yang ada di lifecycle ini dan
> apa saja yang bisa diakomodir otomatis di system dan yang tidak".
> Sumber kebenaran kode: `backend/jobdesk_catalog.py` (38 jobdesk) + `backend/workhub.py`
> (`auto_verify`) + `backend/wa_playbooks.py`.

## 1. Tiga cara sebuah pekerjaan LAHIR
| Sumber | Artinya | Contoh |
|---|---|---|
| **event** | Dipicu peristiwa nyata di sistem (Event Bus) | lead masuk, temuan punch dibuat, kas bon diajukan |
| **recurring** | Dibuat sesuai jadwal (harian/mingguan/bulanan), idempoten per periode | buku harian harian, tutup buku bulanan |
| **manual** | Ditugaskan supervisor lewat tombol "Jalankan" / "Tugas Baru" | kelola tautan showroom, tugas ad-hoc |

## 2. Event yang SUDAH dipancarkan sistem (bisa memicu tugas otomatis)
`lead.created` · `lead.captured` · `lead.stage_changed` · `message.received` · `message.sent`
· `conversation.unanswered`* · `appointment.due_soon`* · `appointment.passed`*
· `lead.followup_due`* · `ar.overdue`* · `customer.created` · `deal.reserved` · `deal.booked`
· `deal.ppjb` · `deal.ajb` · `deal.sold` · `deal.expired` · `deal.cancelled` · `punch.created`
· `qc.passed` · `qc.failed` · `progress_claim.submitted` · `grn.flagged`(3-way match)
· `material.overbudget` · `permit.due_soon` · `payment.received` · `payment.paid_off`
· `ap.bill_created` · `ap.approved` · `ap.paid` · `collection.reminded` · `collection.late_fee`
· `cashbon.submitted` · `cashbon.disbursed` · `cashbon.settled` · `commission.created/approved/paid`
· `revenue.recognized` · `complaint.created`

\* dihasilkan **sweeper** `workhub.workhub_sweeper()` yang mengubah KONDISI nyata menjadi event
(WA belum dibalas >2 jam, survey H-1, survey lewat tanpa hasil, lead diam ≥3 hari, AR jatuh tempo).

## 3. Yang bisa DIVERIFIKASI OTOMATIS oleh sistem (`verify_mode=system`)
Sistem memeriksa BUKTI pada data, bukan klaim pengguna:

| Pemeriksaan | Cara sistem membuktikan |
|---|---|
| `lead_contacted` | `leads.first_contact_at` terisi |
| `conversation_replied` | percakapan terakhir berarah keluar (`last_direction=out`) |
| `lead_activity_recent` | ada aktivitas lead ≤24 jam |
| `document_spr` / `document_ppjb` | dokumen SPR/PPJB untuk deal itu ada |
| `customer_kyc` | NIK pembeli terisi |
| `complaint_closed` | status komplain `resolved/closed` |
| `punch_fixed` | temuan punya `fix_photos` (foto SESUDAH) |
| `diary_today` | ada buku harian hari ini oleh orang itu |
| `progress_updated` | ada pembaruan fase ≤7 hari |
| `inspection_finalized` | ada inspeksi QC difinalisasi ≤7 hari |
| `wa_template_exists` | ada template WA berstatus approved |
| `broadcast_recent` | ada blasting ≤7 hari |
| `depreciation_posted` | penyusutan periode berjalan sudah diposting |
| `ar_followed_up` | ada catatan penagihan ≤2 hari |

**Bila bukti belum ada, tugas TIDAK ditolak diam-diam**: statusnya menjadi *Menunggu verifikasi*
dengan penjelasan (mis. "Belum ada foto bukti perbaikan") sehingga supervisor bisa menilai.

## 4. Yang WAJIB dinilai MANUSIA (`verify_mode=supervisor`)
Pekerjaan yang mutunya tidak bisa dibaca dari data:

| Kode | Pekerjaan | Alasan tidak bisa otomatis |
|---|---|---|
| SM-04 | Catat hasil survey / kunjungan | mutu pendampingan & kesimpulan minat = penilaian manusia |
| SM-08 | Dampingi akad / serah terima (BAST) | kehadiran fisik & pelayanan tidak terekam sistem |
| TK-05 | Perbaiki temuan QC gagal | kelayakan perbaikan teknis harus dinilai ulang |
| TK-06 | Requisition & opname material | kewajaran pemakaian vs RAB butuh pertimbangan |
| TK-07 | Verifikasi GRN / 3-way match | kontrol anti-fraud: wajib mata manusia |
| TK-08 | Urus izin jatuh tempo | bukti eksternal (instansi) di luar sistem |
| TK-09 | Verifikasi termin subkon | opname fisik lapangan |
| FN-02 | Verifikasi penerimaan kas | pencocokan bukti transfer |
| FN-03 | Bayar termin setelah QC | segregasi tugas (pembayaran) |
| FN-04/07/08/09/10 | Retensi, tutup buku, pajak, angsuran, marketing fee | keputusan finansial & kepatuhan |
| DM-07 | Laporan performa iklan mingguan | interpretasi angka |

## 5. Yang TIDAK PERLU verifikasi (`verify_mode=none`)
DM-01 (pantau lead ads harian), DM-02 (tangani capture gagal), DM-05 (kelola tautan showroom),
DM-06 (audit atribusi) — cukup catatan hasil kerja; dampaknya rendah & mudah dicek ulang.

## 6. Playbook WhatsApp per TAHAP lead (`wa_playbooks.py`)
| Playbook | Sasaran | Template | Default |
|---|---|---|---|
| `first_touch` | tahap akuisisi, belum dikontak | `welcome` | **tugas** (kontak pertama sebaiknya manusia) |
| `followup_nurturing` | nurturing, diam ≥3 hari | `reengage` | kirim otomatis + tugas |
| `survey_reminder` | ada survey ≤1 hari | `appointment_reminder` | kirim otomatis |
| `payment_reminder` | booking/won dengan AR jatuh tempo ≤3 hari | `payment_reminder` | tugas |
| `promo_blast` | akuisisi/nurturing/daur ulang | `promo` | manual (Digital Marketing) |

Semua playbook punya **jeda kirim (cooldown)** per lead untuk mencegah spam, mencatat aktivitas
pada lead, dan (opsional) membuat tugas tindak lanjut. **Mode pengiriman = SIMULASI** sampai
kredensial WhatsApp Business Cloud API dipasang.

## 7. Tahap lead: pemicu OTOMATIS vs AKSI MANUSIA
| Perpindahan | Pemicu | Otomatis? |
|---|---|---|
| (buat) → acquisition | lead dibuat/di-capture | otomatis |
| acquisition → nurturing | kontak pertama (kirim WA dari record lead / catat telepon) | otomatis **setelah aksi manusia** |
| nurturing → appointment | jadwal survey dibuat | otomatis |
| appointment → booking | reservasi/SPR unit dibuat | otomatis |
| booking → **won** | deal AJB/serah terima/lunas | **otomatis penuh — tidak bisa manual** |
| any → lost / recycle | keputusan manusia + **alasan wajib** (SSOT) | manual beralasan |
| lead diam ≥14 hari | sweeper | otomatis → `recycle` (alasan `no_response`) |
| koreksi data lama | supervisor **override + alasan** (tercatat) | manual, terbatas |

> Semua perpindahan tercatat di `leads.stage_history` (dari, ke, kapan, oleh siapa, alasan,
> bukti, apakah override) sehingga funnel bisa diaudit.

## 8. Belum otomatis (kandidat berikutnya, jujur)
- **BI/SLIK checking** (owner minta ditunda) — masih SIMULASI.
- Webhook kegagalan capture iklan (`capture.failed`) belum dipancarkan; jobdesk DM-02 masih manual.
- Pengiriman WA nyata (butuh kredensial Meta), e-sign, e-Faktur.
