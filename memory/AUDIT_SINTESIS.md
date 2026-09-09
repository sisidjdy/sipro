# Sintesis Audit SIPRO — akar masalah, keputusan, dan rencana

Disusun 6 September 2026 terhadap commit `7da1bd5`.
Menyatukan `AUDIT_TEMUAN.md` (23 temuan) + temuan sesi lanjutan.
Dokumen ini menggantikan urutan batch di `AUDIT_INSTRUKSI_PERBAIKAN.md`.

---

# BAGIAN 1 — Jawaban langsung atas tiga pertanyaan

## 1.1 "Apakah saya tidak bisa chat langsung (bukan template) ke customer via WA API?"

**Bisa. Tapi hanya di dalam jendela 24 jam, dan jendela itu hanya dibuka oleh PEMBELI.**

Ini aturan Meta, bukan batasan SIPRO. Bentuknya:

| Keadaan | Boleh kirim apa |
|---|---|
| Pembeli mengirim pesan ke nomor Anda | Jendela 24 jam **terbuka**. Bebas: teks, gambar, dokumen, suara, tanpa template, tanpa persetujuan Meta, **tanpa biaya per pesan**. |
| 24 jam lewat sejak pesan terakhir pembeli | Jendela **tertutup**. Hanya template `APPROVED` yang bisa dikirim, dan ditagih per pesan. |
| Anda ingin memulai percakapan lebih dulu | Wajib template `APPROVED`. Setelah pembeli **membalas**, jendela terbuka dan Anda bebas mengetik. |

**Yang sering disalahpahami:** mengirim template **tidak** membuka jendela. Yang membuka
jendela adalah **balasan pembeli**. Jadi alurnya selalu: template → pembeli membalas →
jendela terbuka → chat bebas 24 jam.

SIPRO sudah menerapkan ini dengan benar:

```
backend/wa_inbound.py:149          pesan MASUK -> window_expires_at = sekarang + 24 jam
backend/routers/inbox_router.py:27 _window_open()
backend/wa_compliance.py:153-158   teks bebas + jendela tertutup -> tolak #131047 (live)
backend/routers/inbox_router.py:118  jalur kirim TEKS BEBAS: gw.send(..., kind="inbox", body=...)
backend/routers/wa_router.py:258     jalur kirim teks bebas dari layar kontak WA
```

**Kesimpulan praktis:** sales Anda tetap bisa mengobrol normal dengan pembeli lewat SIPRO.
Template hanya dibutuhkan untuk **memulai** percakapan dan untuk **pengingat otomatis**
(tagihan, garansi, booking fee) — karena pengingat selalu terjadi saat jendela tertutup.

Jadi: template bukan penjara. Template adalah pintu masuk. Setelah pintu terbuka, ruangannya
bebas.

---

## 1.2 "Kenapa template ditolak INVALID_FORMAT?"

**Karena payload pengajuan tidak menyertakan contoh nilai variabel (`example`).**

Meta mewajibkan: setiap template yang body-nya memuat variabel `{{1}}` harus mengirim contoh
nilai untuk tiap variabel. Tanpa itu, template ditolak `INVALID_FORMAT`.

Payload yang dikirim SIPRO sekarang (`backend/wa_templates_meta.py:48`):

```python
comps.append({"type": "BODY", "text": to_meta_body(template.get("body", ""), template.get("variables"))})
```

Yang Meta harapkan:

```json
{"type": "BODY",
 "text": "Halo {{1}}, tagihan {{2}} jatuh tempo {{3}}.",
 "example": {"body_text": [["Budi Santoso", "Termin 2", "15 Oktober 2026"]]}}
```

**Bukti bahwa ini penyebabnya ada di layar Anda sendiri.** Dari tangkapan layar Template Meta:

| Template | Punya variabel? | Hasil |
|---|---|---|
| Info Harga (`price_info`) | **Tidak** | ✅ Menunggu review Meta |
| Pengingat Pembayaran | Ya (`{{nama}}`) | ❌ Ditolak Meta |
| Promo Cluster | Ya (`{{nama}}`) | ❌ Ditolak Meta |
| Pengingat Survey | Ya (`{{name}}`, `{{date}}`) | ❌ Ditolak — **INVALID_FORMAT** |
| Aktivasi Ulang | Ya (`{{nama}}`) | ❌ Ditolak Meta |
| Sapaan Awal | Ya (`{{name}}`) | ❌ Ditolak Meta |

**Satu-satunya template yang lolos adalah satu-satunya template tanpa variabel.** Polanya
tidak bisa lebih jelas dari itu.

Perbaikannya kecil: `meta_components()` menyertakan `example.body_text` yang diambil dari
contoh nilai per variabel. Karena itu berarti setiap variabel harus punya contoh, ini
sekaligus memaksa perbaikan WA-04 (validasi body ↔ variables) — dua masalah, satu pekerjaan.

**Catatan:** ada kemungkinan kedua yang harus diverifikasi bersamaan — header bertipe `text`
yang memuat variabel juga butuh `example.header_text`, dan template berkategori
`AUTHENTICATION` punya aturan komponen tersendiri. Minta agen membaca pesan `rejected_reason`
lengkap dari Meta untuk masing-masing template sebelum memperbaiki, jangan hanya percaya
analisis ini.

---

## 1.3 "Kenapa template di Pusat Konfigurasi berbeda dengan yang di menu Lead WA?"

**Datanya sama persis. Yang berbeda adalah apa yang ditampilkan — dan salah satunya berbohong.**

Kedua layar membaca koleksi yang sama lewat endpoint yang sama:

```
frontend/src/components/omni/TemplatesPanel.js:39         api.get("/wa-templates")
frontend/src/components/config/WaTemplateMetaPanel.js:30  api.get("/wa-templates")
```

Bedanya di kolom status:

| Layar | Menampilkan | Sumber |
|---|---|---|
| **Pusat Konfigurasi › Template Meta** | Status resmi Meta | `t.meta_status` |
| **Lead WA › Template** | Status lokal | `t.status` |

Dan inilah cacatnya (`TemplatesPanel.js:101`):

```jsx
<StatusPill status={t.status === "approved" ? "approved" : "pending"} group="wa_template_status" />
```

**Apa pun yang bukan `approved` ditampilkan sebagai "Menunggu".** Template yang **DITOLAK
Meta** muncul di layar Lead WA sebagai "Menunggu" — bukan "Ditolak".

Jadi yang Anda alami itu nyata dan bisa dijelaskan: di satu layar template berstatus
**Ditolak Meta**, di layar lain template yang sama berstatus **Menunggu**. Admin yang hanya
membuka layar Lead WA akan menunggu persetujuan yang tidak akan pernah datang.

**Ini bukan duplikasi data. Ini satu data dengan dua layar yang tidak sepakat.** Yang harus
diperbaiki bukan "hapus salah satu", tetapi **satukan layarnya**.

---

# BAGIAN 2 — Akar masalah

Dua puluh tiga temuan sebelumnya dan sembilan temuan baru sesi ini lahir dari **tiga pola**,
bukan tiga puluh dua kesalahan terpisah. Memperbaiki polanya lebih murah daripada memperbaiki
gejalanya satu per satu.

## Pola A — Aturan ditulis di docstring, tidak ditegakkan di kode

Modulnya menuliskan janji yang benar. Lapisan di bawahnya membatalkannya karena satu
kesalahan kecil.

| Janji tertulis | Yang membatalkannya |
|---|---|
| `wa_reminder_engine.py:26` "Tidak mengingatkan hal yang sudah beres: termin lunas" | baris 206 membaca `paid` — item menyimpan `paid_amount`. Penjaga tidak pernah aktif. |
| PRD Fase 92 "angka kartu = jumlah baris rinciannya" | kartu dan rincian memakai query dan field berbeda (FIN-01) |
| `wa_compliance.py:3` "menolak kategori MARKETING" | dua template promosi diberi kategori `utility`, jadi lolos (WA-07) |
| `doc_layout.py:20` "Tidak ada gaya mati di kode" | invoice memakai layout milik jenis dokumen lain, dan tidak punya entri sendiri (DOC-02) |

**Konsekuensinya:** membaca kode ini memberi rasa aman yang keliru. Docstring-nya bagus, jadi
pembaca berhenti memeriksa.

## Pola B — Nama field yang salah pada objek yang bentuknya mirip

Item termin menyimpan `paid_amount`; invoice menyimpan `paid`. Keduanya dict dengan field
`amount` dan `status`, jadi kekeliruan tidak menimbulkan galat — hanya angka nol yang diam.

Sudah menghasilkan dua cacat besar (WA-02, DOC-01). Sapuan saya hanya mencakup satu pasangan
field. **Pasangan lain belum disapu sama sekali.**

## Pola C — Satu konsep, banyak tempat, tidak ada yang jadi kebenaran

| Konsep | Berapa tempat | Akibat |
|---|---|---|
| Status template WA | 2 layar, 2 field (`status` vs `meta_status`) | Layar tidak sepakat (§1.3) |
| Periode akuntansi | 4 salinan `period_of`, 2 perilaku | Penentuan periode tidak deterministik (CFG-01) |
| Progres proyek | `construction_progress` (berbobot fase) vs `units_progress` (rata-rata unit) | Dua angka "progres" yang berbeda definisi (PRJ-02 di bawah) |
| Win rate | LED-07 `won/(won+lost)` vs LED-13 `won/total` | Dua angka win rate yang tidak sebanding (BI-02 di bawah) |
| Kosakata enum | SSOT + 12 layar yang menuliskannya sendiri | Menambah status di SSOT tidak muncul di layar (CFG-03) |

---

# BAGIAN 3 — Temuan baru sesi ini

## WA-12 — Layar Lead WA menampilkan template DITOLAK sebagai "Menunggu"

**KRITIS** · `frontend/src/components/omni/TemplatesPanel.js:101`
Mekanisme dan bukti: §1.3 di atas. Admin menunggu persetujuan yang sudah ditolak.

## WA-13 — Pengajuan template tanpa `example` → ditolak INVALID_FORMAT

**KRITIS** · `backend/wa_templates_meta.py:48`
Mekanisme dan bukti: §1.2 di atas. **Selama ini belum diperbaiki, tidak ada satu pun template
bervariabel yang bisa disetujui Meta — artinya seluruh pengingat otomatis tidak bisa hidup.**

## WA-14 — Isi template tidak bisa diatur dari tempat ia disetujui

**TINGGI** · Layar Pusat Konfigurasi hanya bisa **mengajukan** dan **menarik status**; isi
template hanya bisa diubah di layar Lead WA. Sementara nilai bawaan pengingat
(`reminder.template_*`) diatur di tab lain lagi. Tiga tempat untuk satu keputusan.

## RBAC-01 — Peran baru tidak bisa dibuat sama sekali

**TINGGI** · `backend/rbac.py:20-27`
`ALL_ROLES` adalah daftar Python yang ditulis tangan. Tidak ada endpoint apa pun yang membuat
peran (`admin_router.py` hanya punya `POST /users` dan `PUT /permissions`;
`admin_router.py:86` sekadar mengembalikan `ALL_ROLES`).

**Akibat:** menambah peran seperti "Admin Proyek" atau "Kasir" **membutuhkan perubahan kode
dan deploy ulang.** Untuk produk yang menyebut dirinya multi-tenant dan SaaS-ready
(`db.py:5`), ini batasan struktural, bukan kekurangan fitur kecil.

## RBAC-02 — Kolom aksi tidak punya bahasa manusia sama sekali

**TINGGI** · `backend/rbac_labels.py` (91 baris)
Berkas itu memberi label manusiawi untuk **resource** (`coa` → "Bagan Akun") — bagian ini
sudah benar dan dipakai UI. Tetapi **tidak ada `ACTION_META`**. Aksi tetap tampil sebagai
token teknis Inggris:

`view_all` · `view_own` · `create` · `update` · `approve` · `override` · `manage` ·
`sign` · `verify` · `assign` · `cancel` · `delete`

Admin non-teknis tidak bisa membedakan `view_all` dari `view_own`, atau `override` dari
`approve` — padahal keduanya adalah keputusan wewenang yang serius.

## RBAC-03 — Layar menampilkan kode mesin berdampingan dengan label

**SEDANG** · `frontend/src/pages/AdminPermissions.js:307`
```jsx
<span className="font-mono">{c.resource}</span> ({labelOf(c.resource)}) · {roleLabel(c.role)}
```
Kode teknis ditampilkan lebih dulu dan lebih menonjol daripada namanya. Untuk layar yang
dipakai pemilik usaha menentukan siapa boleh menyetujui pembayaran, ini terbalik.

## PRJ-01 — Progres proyek mengecualikan unit yang belum dijadwalkan

**TINGGI** · `backend/engine.py:224-226`
```python
scheds = await db.build_schedules.find({"org_id": org_id, "project_id": project_id}, ...)
units_progress = round(sum(float(s.get("progress") or 0) for s in scheds) / len(scheds)) if scheds else 0
```
Pembaginya `len(scheds)` — **jumlah unit yang punya jadwal**, bukan jumlah unit proyek.

**Akibat:** proyek 100 unit, 5 di antaranya dijadwalkan dan 80% jadi → kartu menampilkan
**80% progres proyek**, padahal 95 unit belum disentuh. Angka ini naik justru karena unit
lain belum dijadwalkan.

Ditambah: rata-ratanya **tidak berbobot** — satu Tipe 36 selesai dihitung sama dengan satu
Tipe 90 selesai.

## PRJ-02 — Dua angka "progres proyek" dengan definisi berbeda

**SEDANG** · `projects.construction_progress` (rata-rata fase berbobot, `engine.py:236`) dan
`projects.units_progress` (rata-rata unit tak berbobot, baris 224). Keduanya tersimpan di
dokumen yang sama dan keduanya tampil sebagai "progres" di layar berbeda. Tidak ada penjelasan
mana yang mana.

## BI-01 — "Sumber lead terbaik" bisa dimenangkan oleh sumber dengan satu lead

**TINGGI** · `backend/metrics/leads.py:396-400`
```python
row["win_pct"] = pct(row["won"], row["value"])
best = max((r for r in per_source.values() if r["win_pct"] is not None), key=lambda r: r["win_pct"])
```
Tidak ada batas sampel minimum. Sumber dengan **1 lead yang kebetulan closing** menghasilkan
win rate 100% dan mengalahkan sumber dengan 300 lead di 42%.

Metrik ini dipakai memutuskan ke mana anggaran iklan diarahkan.

## BI-02 — Dua definisi "win rate" dalam satu modul

**SEDANG** · `backend/metrics/leads.py`
- LED-07 (baris 216-220): `won / (won + lost)` — lead berjalan tidak dihitung. Terdokumentasi.
- LED-13 (baris 396): `won / total lead` — lead berjalan ikut jadi pembagi.

Angka per sumber akan **selalu lebih kecil** daripada win rate keseluruhan, dan keduanya
tampil dengan nama yang sama di layar berbeda. Pemakai akan menyimpulkan ada yang salah
dengan datanya, padahal yang berbeda adalah definisinya.

---

# BAGIAN 4 — Keputusan yang harus Anda ambil (bukan keputusan teknis)

Perbaikan di bawah bergantung pada jawaban Anda. Tanpa ini agen akan menebak.

### K-1 · Satu layar template, di mana?
Rekomendasi: **hapus tab template di Lead WA, pindahkan seluruhnya ke Pusat Konfigurasi ›
Template Meta**, dan jadikan satu layar itu tempat mengatur isi, kategori, variabel, contoh
nilai, pengajuan ke Meta, status, **dan** pemetaan "template mana untuk pengingat apa".
Layar Lead WA cukup memilih template yang sudah `APPROVED`, tidak mengubahnya.

Alasannya: template hanya berguna setelah disetujui Meta. Memisahkan "menulis isinya" dari
"melihat apakah disetujui" adalah sumber kebingungan yang Anda alami.

### K-2 · Peran dinamis atau tetap?
Apakah Anda perlu membuat peran sendiri (mis. "Kasir", "Admin Proyek") tanpa bantuan
developer? Kalau ya, ini pekerjaan tersendiri: peran menjadi data di koleksi, bukan konstanta
Python, dan seluruh `ROLE_INHERITS` / `ROLE_GRANTS` / `ROLE_DENY` ikut berpindah.

### K-3 · Bukti bayar (DOC-03)
Apakah KWITANSI sudah memenuhi peran "bukti bayar", atau perlu dokumen terpisah per termin?

### K-4 · Progres proyek yang mana yang benar?
Untuk kartu "Progres konstruksi" di layar pemilik: berbobot nilai unit, berbobot fase, atau
jumlah unit selesai / total unit? Ketiganya sah; yang tidak sah adalah menampilkan tiga-tiganya
dengan nama yang sama.

### K-5 · DSO (FIN-03)
Hitung DSO yang benar, atau ganti namanya menjadi sesuatu yang jujur?

---

# BAGIAN 5 — Rencana kerja yang disintesis

Menggantikan urutan batch di `AUDIT_INSTRUKSI_PERBAIKAN.md`. **Aturan verifikasi di dokumen
itu tetap berlaku penuh: verifikasi dulu, perbaiki kemudian, laporkan yang tidak terbukti.**

## Tahap 1 — Angka yang salah di mata pembeli
`WA-02` · `DOC-01`
Dua baris kode, dampak terbesar, paling mudah diverifikasi. Kerjakan lebih dulu untuk
membuktikan dokumen audit ini layak dipercaya.

## Tahap 2 — Buat WhatsApp benar-benar bisa hidup
`WA-13` (example) → `WA-04` (validasi body↔variables) → `WA-01` (template per jenis pengingat)
→ `WA-03` (riwayat jujur) → `WA-12` (status di layar Lead WA)

Urutan ini tidak boleh dibalik. Tanpa WA-13, tidak ada template yang bisa disetujui, jadi
WA-01 tidak bisa diuji. **Selama tahap ini belum selesai, mode WhatsApp tidak boleh diubah ke
`live`.**

## Tahap 3 — Satukan template (butuh keputusan K-1)
`WA-14` · `WA-05` · `WA-06` · `WA-08` · `WA-09` · `WA-07`
Satu layar, satu kebenaran: isi, kategori, variabel + contoh, status Meta, dan pemetaan ke
pengingat. Template `APPROVED` dibekukan; perubahan berarti versi baru.

## Tahap 4 — Bahasa dan wewenang (butuh keputusan K-2)
`RBAC-02` (buat `ACTION_META` — ini yang paling cepat memberi manfaat) · `RBAC-03` ·
`RBAC-01` (bila K-2 = ya)

`ACTION_META` bisa dikerjakan dalam satu sesi dan langsung membuat layar Hak Akses bisa
dipakai orang non-teknis. Kerjakan itu dulu, terlepas dari jawaban K-2.

## Tahap 5 — Dokumen & konfigurasi
`DOC-02` · `CFG-03` · `CFG-04` · `UI-01` · `UI-02` · `DOC-03` (bila K-3 = perlu)

## Tahap 6 — Angka pembukuan & BI (butuh keputusan K-4, K-5)
`CFG-01` · `CFG-02` · `FIN-01` · `FIN-02` · `FIN-03` · `PRJ-01` · `PRJ-02` · `BI-01` · `BI-02`

Tahap ini mengubah angka historis. **Ukur dampaknya sebelum mengubah**, dan laporkan berapa
jurnal/laporan yang berpindah sebelum menjalankan migrasi apa pun.

## Tahap 7 — Cegah kelahiran ulang
Ini yang paling bernilai jangka panjang:

1. `memory/FIELD_MAP.md` — peta nama field uang per bentuk dokumen, plus gate
   `verify_field_names.py` (menutup Pola B).
2. `scripts/verify_card_drilldown.py` — angka kartu wajib sama dengan jumlah baris rinciannya
   (menutup Pola A untuk KPI).
3. Perluas `audit_forms_deep.py` ke `<SelectItem>` (CFG-04, menutup Pola C untuk kosakata).
4. Satu gate yang memeriksa: setiap metrik BI punya `formula` tertulis, dan dua metrik dengan
   nama mirip tidak boleh punya formula berbeda tanpa nama yang membedakannya (menutup
   Pola C untuk angka).

---

# BAGIAN 6 — Yang masih belum diaudit

Supaya tidak ada yang mengira gambarannya sudah utuh:

| Area | Status |
|---|---|
| Akuntansi & GL — neraca, laba rugi, arus kas, tutup buku, e-Faktur, e-Bupot | **Belum diverifikasi angkanya.** Baru jalur periode. |
| Metrik BI selain lead & proyek (marketing, sales, budget, pricing, rab, team) | Belum ditelusuri rumusnya satu per satu |
| Pengadaan, subkon, 3-way match, retensi | Belum diaudit |
| Portal pembeli | Belum diaudit |
| Kartu KPI Beranda, Pembangunan, Marketing vs drilldown-nya | Belum dibandingkan |
| Keamanan & permukaan auth pada repo ini | Belum diaudit |
| UI visual — tata letak, konsistensi, responsif | Belum dilihat; perlu dijalankan |

Berdasarkan tiga pola di Bagian 2, area yang paling mungkin menyimpan cacat setingkat WA-02
adalah **akuntansi/GL** (banyak field uang dengan nama mirip) dan **kartu KPI yang belum
dibandingkan dengan drilldown-nya** (Pola A sudah terbukti di FIN-01).
