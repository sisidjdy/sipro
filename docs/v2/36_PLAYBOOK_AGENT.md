# 36 — PLAYBOOK AGENT (aturan kerja untuk agent penerus)

> Dokumen ini adalah **instruksi paling ideal untuk agent berikutnya** (termasuk untuk diri saya sendiri di sesi berikutnya). Tujuannya satu: **tidak ada halusinasi, tidak ada regresi, tidak ada klaim palsu.**

## 1. Lima menit pertama (wajib, jangan dilewati)
```
1. cat /app/plan.md | tail -80              → fase apa yang aktif & status terakhir
2. cat /app/docs/v2/20_INDEX_V2.md          → keputusan owner (D1..D10) + daftar ⚠️ OPEN
3. cat /app/docs/v2/34_ROADMAP_EKSEKUSI.md  → scope + user story + DoD fase aktif
4. baca spec fase itu (mis. 24, 26, 27)     → kontrak yang harus dipenuhi
5. cat /app/memory/test_credentials.md      → akun uji (sandi demo: Sipro#2026)
6. bash scripts/run_all_gates.sh            → pastikan hijau SEBELUM mengubah apa pun
```
Bila gate sudah merah sebelum Anda menyentuh kode: **perbaiki dulu**, jangan menumpuk perubahan.

## 2. Aturan anti-halusinasi
1. **Jangan mengarang angka bisnis.** Semua nominal/persentase/hari berasal dari: `[DOC]` (dokumen owner di `docs/source_templates/`), `[CFG]` (`settings`), atau `[SSOT]` (`reference.py`). Bila tidak ada → tanya owner, atau tandai `⚠️ OPEN` di Dok 20 dan pakai default yang **diberi label jelas di UI**.
2. **Jangan mengklaim integrasi live** bila kredensial tidak ada. Pakai pola `mode: live|simulation` dan tampilkan lencananya (aturan sejak Fase 17).
3. **Jangan menebak nama file/endpoint.** Verifikasi dengan `grep`/`glob` sebelum menulis dokumen atau kode.
4. **Jangan menghapus fitur** untuk "merapikan". Konsolidasi = pindah tempat + pertahankan kemampuan; buktikan dengan checklist fitur lama → baru.
5. **Jangan menyentuh** `MONGO_URL`, `DB_NAME`, `REACT_APP_BACKEND_URL`.
6. **Angka "0" itu berbahaya.** Bila input tidak lengkap, tampilkan "data belum lengkap", bukan 0 (pelajaran Fase 36/37 dan aturan Dok 31).

## 3. Aturan kode (tidak bisa dinegosiasi)
| Aturan | Nilai | Penjaga |
|---|---|---|
| Ukuran file | router/py ≤800 · page/komponen js ≤500 · util/service js ≤300 · css ≤400 | `scripts/validate_compliance.py` |
| URL backend | tidak boleh hard-code di frontend; pakai `process.env.REACT_APP_BACKEND_URL` | idem |
| Prefiks API | semua endpoint di bawah `/api` | ingress k8s |
| Enum | wajib lewat `reference.py` (SSOT) + migrasi kanonikalisasi | `verify_data_integrity.py` |
| Aturan bisnis | wajib lewat `settings_store` (tidak hard-code) | `verify_no_hardcoded_rules.py` (baru) |
| Riwayat | setiap perubahan status menulis `{from,to,at,actor,reason,evidence}` | `verify_business_invariants.py` |
| Jurnal | idempoten via `source_event` unik | invarian saldo akun |
| `data-testid` | dari registry `frontend/src/constants/testIds` | `verify_ui_surfaces.py` |
| Label UI | Bahasa Indonesia; setiap field punya label; panel punya latar | gate Fase 38 |
| Dependensi | backend: `pip install` lalu perbarui `requirements.txt`; frontend: **hanya `yarn add`** | — |

## 4. Urutan mengerjakan satu fase
```
1. todo list fase (dari user story di Dok 34)
2. kontrak dulu: model + endpoint + setting + migrasi   (backend)
3. uji cepat curl untuk tiap endpoint baru
4. UI: pakai komponen pola (DataTable/FilterBar/TabPage/...) — jangan bikin pola baru
5. tulis scripts/verify_<fase>.py:
   - periksa invarian data, bukan hanya status 200
   - WAJIB uji-mutasi: rusak kode sengaja → gate harus MERAH → kembalikan
6. bash scripts/run_all_gates.sh  → harus PASS 20+ gates
7. buktikan user story di browser (screenshot) — bukan hanya curl
8. panggil testing agent untuk konfirmasi independen
9. tutup fase: update plan.md (bukti + angka), test_result.md, status di dokumen V2
```

## 5. Cara menulis gate yang bermutu
- Satu gate = satu janji bisnis. Contoh `verify_spr_docgen.py`:
  1. reservasi kedua untuk lead sama → **harus** 409;
  2. SPR tanpa dokumen mandatory → **harus** 400;
  3. nomor SPR 20 permintaan paralel → 20 nomor unik;
  4. ubah `booking_fee.refund_kpr_rejected_pct` → teks PDF berubah;
  5. dokumen final diedit → **harus** ditolak.
- Gate harus **mandiri** (buat data sendiri, bersihkan sendiri) dan **cepat** (<60s).
- Output ringkas: `PASSED n/n` atau daftar temuan yang bisa ditindak.

## 6. Kapan berhenti dan bertanya ke owner
Tanya (jangan tebak) bila menyentuh: nominal/persentase legal, tarif pajak, urutan SOP internal, kebijakan refund, siapa boleh override, tarif harga add-on, format nomor dokumen, isi klausa. Gunakan daftar `⚠️ OPEN` di [20](20_INDEX_V2.md) §6 sebagai pertanyaan siap-kirim (OQ-1 … OQ-9).

## 7. Definisi "selesai" (jangan mengaku selesai sebelum semua ini benar)
- [ ] Semua user story fase terbukti di browser oleh agent.
- [ ] Gate baru ada, uji-mutasi terbukti, seluruh gate PASS.
- [ ] Tidak ada angka bisnis hard-code; semua bisa diubah dari Pusat Konfigurasi.
- [ ] Tidak ada fitur lama yang hilang (checklist pemetaan).
- [ ] Migrasi idempoten dijalankan 2× tanpa efek samping.
- [ ] `plan.md` + `test_result.md` diperbarui dengan **bukti angka**, bukan kalimat optimis.
- [ ] Tidak ada mock/data karangan yang tertinggal.

## 8. Peta cepat kode (per 16 Agu 2026)
```
backend/
  server.py            registry router (semua /api)         lead_lifecycle.py  gerbang tahap lead
  db.py                Mongo + ORG_ID + setting env         slik.py            BI/SLIK berbukti
  reference.py         SSOT 85 grup enum                    marketing_fee.py   fee mitra + jurnal
  rbac.py              peran & izin                          engine.py          event bus + scheduler
  gl_engine.py         jurnal & CoA                          build_*.py         mesin konstruksi F31-37
  indexes.py           index unik                            migrations.py      migrasi idempoten
  sequences.py         penomoran dokumen                     storage.py         berkas (emergent/mongo)
  routers/*.py         56 router                             seed*.py           data demo
frontend/src/
  config/navigationConfig.js   menu + PAGE_META + peran
  pages/*.js                   38 halaman
  components/patterns/         pola UI (dikembangkan Fase 40)
  constants/testIds            registry data-testid
scripts/                       19 gate + POC + audit tools
docs/analysis/00-19            framework V1
docs/v2/20-36                  spesifikasi V2 (dokumen ini)
docs/source_templates/         4 dokumen legal asli owner
```
