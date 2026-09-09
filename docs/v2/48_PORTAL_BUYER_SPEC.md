# 48 — SPEC PORTAL PEMBELI DIPERKUAT: BAST, KWITANSI & PENGAKUAN KLAIM (Fase 51C)

> Dasar: pembacaan kode yang berjalan (`backend/routers/portal_router.py`,
> `backend/portal_security.py`, `backend/models_p51.py`, `backend/warranty_engine.py`,
> `frontend/src/components/portal/panels/`). Cakupan: (a) pembeli mengunduh **BAST**
> miliknya, (b) pembeli mengunduh **kwitansi** pembayarannya, (c) pembeli **mengakui**
> perbaikan garansi selesai — atau menyatakan **belum beres**, (d) dokumen orang lain tidak
> bocor, (e) kosong-jujur.
>
> Status: **✅ ADA** — dibuktikan gate 43 `scripts/verify_portal_warranty.py`
> (46 pemeriksaan) dan uji-mutasi `scripts/mutasi_51.py` (M40–M51).

---

## 1. Yang SUDAH ADA sebelum Fase 51C

| Modul | Kemampuan |
|---|---|
| `portal_security.py` | token portal terpisah (`type="portal"`) — token staf **tidak** bisa dipakai di portal, dan sebaliknya |
| `portal_router.py` (Fase 26/30b/47B) | login OTP, ringkasan, progres, site plan, foto lapangan, komplain, unggah bukti transfer |
| `portal_router.py` (Fase 50A) | `GET /portal/warranty` + `POST /portal/warranty/claims` (ajukan klaim) |
| `handover_engine.pdf_bytes` | PDF BAST (sebelumnya **hanya** bisa diunduh staf) |
| `warranty_engine.close` | penutupan klaim **mewajibkan** pengakuan pembeli |
| `utils/portalDownload.js` | unduhan lewat sesi portal (blob), bukan tautan mentah bertoken |

**Tiga lubang yang tersisa sampai Fase 50 dan ditutup di 51C:**

| Kode | Lubang | Penutup |
|---|---|---|
| P‑H1 | Salinan **BAST**-nya sendiri tidak bisa diambil pembeli, padahal dokumen itu dasar penghitungan masa garansinya | `GET /portal/handovers` + `GET /portal/handovers/{id}/pdf` |
| P‑H2 | **Kwitansi** pembayaran tidak bisa diunduh siapa pun — bukti bayar hanya ada di kepala staf | `GET /portal/receipts` + `GET /portal/receipts/{id}/pdf` |
| P‑H3 | Mesin MEWAJIBKAN "pengakuan pembeli" untuk menutup klaim garansi, tetapi pembeli tidak pernah diberi pintunya → **stafnya yang mengetik atas nama pembeli** | `GET /portal/warranty/claims/{id}` + `POST /portal/warranty/claims/{id}/ack` |

---

## 2. Aturan yang DIPAKSAKAN

### 2.1 Kepemilikan diperiksa NYATA, bukan disaring di layar
1. BAST milik pembeli ditemukan lewat **dua jalur** yang keduanya sah: `customer_id`-nya,
   **atau** rumah dari deal miliknya (`_my_handovers`). Rumah yang sudah diserahterimakan
   sebelum akun portalnya dibuat tetap ketemu.
2. Kwitansi disaring lewat `deal_id` milik pembeli (`_my_receipts`).
3. Klaim garansi disaring lewat `customer_id` **atau** unit miliknya (`_my_claim`).
4. Dokumen yang bukan miliknya dijawab **404 (bukan 403)** — membedakan "ada tapi bukan
   milikmu" dari "tidak ada" membocorkan keberadaan dokumen orang lain.
5. Id yang ditebak (uuid acak) juga **404**, bukan 500.

### 2.2 Pengakuan penyelesaian klaim (`POST /portal/warranty/claims/{id}/ack`)
Kontrak: `models_p51.PortalClaimAckIn` = `{satisfied: bool = true, note: str | null}`.

| Keadaan | Perilaku |
|---|---|
| Klaim belum `diverifikasi` (mis. masih `dikerjakan`) | **400** dengan alasan jujur: penutupan hanya untuk perbaikan yang sudah **diperiksa** mutunya. Menutup klaim yang belum diperiksa = menghapus jejak masalah yang mungkin masih ada |
| `satisfied = true` | `warranty_engine.close` → status `ditutup`, `ack_by` = **nama + nomor dari sesi portal**, `ack_note` tersimpan, temuan punch perbaikannya ikut ditutup, tim diberi tahu |
| `satisfied = false` | Klaim **TIDAK ditutup** — dikembalikan ke `dikerjakan`, `ack_note` + `ack_rejected_by` tersimpan, dan tim yang menangani **diberi tahu** (bukan catatan diam) |
| Klaim sudah `ditutup` | **400** — pengakuan kedua tidak diterima |

**Pengakuan tercatat atas nama PEMBELI** (`"{nama} ({nomor})"`), bukan atas nama staf. Ini
inti P‑H3: tanda tangan digital sederhana yang jujur soal siapa yang menyatakan.

### 2.3 Kosong-jujur
1. Belum ada BAST → `data: []` **dengan kalimat sebab**: "rumah belum diserahterimakan, jadi
   memang belum ada dokumennya" — bukan tabel hampa.
2. Belum ada kwitansi → "belum ada data, **bukan Rp 0**".
3. Belum ada rumah atas nama pembeli → kalimat sebab, bukan daftar kosong tanpa penjelasan.
4. Daftar BAST yang ada pun membawa kalimat gunanya: "simpan salinannya: dokumen ini dasar
   penghitungan masa garansi rumah Anda."

### 2.4 Unduhan tanpa membocorkan token
Semua unduhan portal lewat `utils/portalDownload.js` (permintaan blob memakai sesi portal),
**bukan** `<a href>` bertoken. Tautan mentah bertoken bocor ke riwayat peramban, log proxy,
dan tombol "bagikan". Galat dibaca sebagai **kalimat** (`portalBlobError`), bukan
`[object Object]` atau berkas PDF rusak.

---

## 3. Endpoint & layar

| Endpoint | Layar | testId (`constants/testIds/p51.js`) |
|---|---|---|
| `GET /portal/handovers` | tab **Dokumen** → `DocumentsPanel.js` | `portalBastSection`, `portalBastRow`, `portalBastEmpty` |
| `GET /portal/handovers/{id}/pdf` | tombol unduh BAST | `portalBastPdf` |
| `GET /portal/receipts` | tab **Dokumen** | `portalReceiptSection`, `portalReceiptRow`, `portalReceiptEmpty` |
| `GET /portal/receipts/{id}/pdf` | tombol unduh kwitansi | `portalReceiptPdf` |
| `GET /portal/warranty` | tab **Garansi** → `WarrantyPanel.js` | (panel garansi Fase 50A) |
| `POST /portal/warranty/claims` | tombol ajukan klaim | (panel garansi Fase 50A) |
| `GET /portal/warranty/claims/{id}` | rincian klaim | `portalClaimDetail` |
| `POST /portal/warranty/claims/{id}/ack` | `ClaimAckDialog.js` | `portalAckBtn`, `portalAckDialog`, `portalAckYes`, `portalAckNo`, `portalAckNote`, `portalAckSubmit`, `portalAckCancel` |

Aturan layar:
1. Tombol pengakuan **hanya** muncul untuk klaim yang sudah `diverifikasi`.
2. Dialog menjelaskan akibat pilihan "Belum beres" apa adanya: **"Klaim TIDAK akan ditutup."**
   Layar yang tidak menjelaskan akibat memancing pembeli menutup klaim yang belum beres.
3. Semua unduhan memakai `portalDownload` + `portalBlobError` (lihat §2.4).
4. Panel dokumen benar-benar **dirender** dari `PortalDashboard.js` (import saja tidak cukup).

---

## 4. Data

Tidak ada koleksi baru. Field tambahan pada `warranty_claims`:

| Field | Arti |
|---|---|
| `ack_by` | siapa yang MENGAKUI perbaikan selesai (nama + nomor pembeli dari sesi portal) |
| `ack_note` | catatan pembeli apa adanya |
| `ack_rejected_by` | siapa yang menyatakan perbaikan **belum** beres |

---

## 5. Guardrail (cara membuktikan cepat)

```bash
python3 scripts/verify_portal_warranty.py         # gate 43 — 46 pemeriksaan
python3 scripts/mutasi_51.py --only=M40,M43,M44   # kebocoran & pengakuan
bash scripts/run_all_gates.sh                     # 43 gate, OVERALL PASS
```

Gate 43 membuktikan C1–C10: dokumen miliknya bisa diunduh (PDF benar-benar `%PDF`), dokumen
orang lain tidak bocor (403/404), pintu portal butuh token portal (token staf ditolak),
pengakuan hanya untuk perbaikan yang sudah diperiksa, "belum beres" tidak menutup klaim,
pengakuan tercatat atas nama pembeli, pekerjaan perbaikannya ikut ditutup, kosong-jujur, dan
permukaan layar (tidak ada testId 51C yang mati).

**Portal pengujian:** `/portal`, login OTP dengan `PORTAL_MASTER_OTP` (bawaan `000000`).

---

## 6. Yang SENGAJA tidak dikerjakan di 51C
1. **Tidak ada tanda tangan digital bersertifikat** untuk pengakuan. Yang dijanjikan modul
   ini adalah jejak yang jujur (siapa, kapan, dari sesi mana), bukan e-sign berkekuatan
   hukum — itu urusan `ESIGN_*` (spec 27) dan butuh kredensial penyedia.
2. **Tidak ada tautan unduh publik** (share link tanpa login). Dokumen ini memuat nomor
   rumah, nominal, dan identitas pembeli.
3. **Pembeli tidak bisa membatalkan klaim** yang sudah diajukan; ia bisa menyatakan "belum
   beres", dan penutupan tetap keputusan bersama (staf memeriksa mutu, pembeli mengakui).
