# 49 — SPEC: KETAHANAN SESI (Fase 54)

> Domain: otentikasi & masa hidup sesi (staf + portal pembeli).
> Gate: `scripts/verify_session_resilience.py` (**gate 45**) · Mutasi: `scripts/mutasi_54.py`
> POC: `poc/poc_54.py` · Bahan uji: `scripts/_fixture54.py`

---

## 1. Keluhan yang memicu fase ini

`test_reports/iteration_85.json` (laporan uji terakhir Fase 53), prioritas MEDIUM — satu-satunya
sisa yang belum ditutup:

> *"Login sessions expire frequently during testing. Users need to re-login multiple times
> during extended use."*

Keluhan ini terdengar seperti gangguan kecil. Bukan. Di ERP ini seorang pemakai bisa sedang
berada di tengah **dialog komponen biaya kontrak**, **dialog tahap legal**, atau **form
opname** ketika sesinya berakhir — dan sebelum Fase 54 tidak ada satu pun mekanisme yang
menyelamatkan pekerjaan itu, memperingatkan lebih dulu, atau bahkan sekadar menjelaskan apa
yang terjadi.

---

## 2. Empat cacat NYATA (bukan penyempurnaan)

### C1 — `POST /api/auth/refresh` tidak pernah ada
Baris pertama `backend/routers/auth_router.py` sejak lama berbunyi
`"""Auth routes: login, register, me, logout, refresh."""`. `login()` **dan** `register()`
memanggil `create_refresh_token()`. `_set_cookies()` menulis cookie `refresh_token` dengan
umur 7 hari. Dan **tidak ada satu baris pun yang membacanya** — tidak ada
`@router.post("/refresh")`.

Akibatnya: `create_access_token()` memberi umur 24 jam, tanpa jalur perpanjangan apa pun.
Pada jam ke-24 pemakai dilempar keluar. Token refresh adalah janji yang ditulis kode kepada
dirinya sendiri lalu tidak pernah ditepati.

### C2 — Cookie kedaluwarsa MENGALAHKAN Bearer yang masih sah
```python
# backend/security.py — SEBELUM Fase 54
def _extract_token(request):
    token = request.cookies.get("access_token")
    if not token:                      # <-- hanya kalau cookie KOSONG
        header = request.headers.get("Authorization", "")
        ...
```
Cookie yang **ADA tetapi KEDALUWARSA** membuat `jwt.decode` melempar
`ExpiredSignatureError` → 401, walau header membawa token sempurna.

Ini juga **penghalang keras** bagi perbaikan C1: endpoint refresh menyerahkan token baru yang
disimpan frontend di `localStorage` dan dikirim sebagai Bearer, sementara peramban masih
melampirkan cookie `access_token` yang lama. Tanpa C2 diperbaiki, sesi yang baru diperpanjang
justru **401 selamanya**. Karena itu C2 harus ditutup bersama C1, bukan sesudahnya.

### C3 — Penyimpanan dibersihkan tanpa memberi tahu React
```js
// frontend/src/services/apiClient.js — SEBELUM Fase 54
if (err?.response?.status === 401 && !url.includes("/auth/login")) {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem("sipro_user");
  delete api.defaults.headers.common.Authorization;
}
```
`AuthContext` tidak pernah tahu. `user` tetap terisi, jadi aplikasi menggambar seluruh
kerangkanya — sidebar, tab, kartu — sementara **setiap** permintaan berikutnya gagal. Tanpa
pesan, tanpa diantar ke halaman masuk, dan isian yang sedang dikerjakan hilang. Ironisnya
komentar di kode itu mengaku sedang mencegah keadaan tersebut.

### C4 — Perpanjangan bisa menjadi pintu belakang / memindahkan penyewa
Dua bahaya yang lahir dari perbaikan C1 kalau dikerjakan asal jadi:
* **Pintu belakang:** akun yang dinonaktifkan dan penyewa yang disuspend bisa memperpanjang
  sesinya sampai 7 hari — "menonaktifkan akun" menjadi hanya tulisan di layar admin.
* **Pindah penyewa diam-diam:** `super_admin` yang sedang "bertindak sebagai" penyewa lain
  membawa klaim `active_org_id`. Bila refresh menerbitkan token tanpa klaim itu, ia pulang ke
  org asalnya **tanpa pesan** — layar masih menulis nama penyewa lama sementara datanya sudah
  milik penyewa lain. Cacat data lintas penyewa yang tidak kelihatan.

---

## 3. Aturan yang DIPAKSAKAN sejak Fase 54

### 3.1 Resolusi bekal sesi (`backend/security.py`)
1. `candidate_tokens()` mengumpulkan **header `Authorization` DULU**, lalu cookie.
   Alasannya bukan selera: header adalah pilihan **sengaja** pemanggil pada permintaan itu,
   cookie dilampirkan peramban **otomatis** dan bisa jauh lebih tua. Yang sengaja menang atas
   yang otomatis.
2. `decode_session_tokens()` mencoba **semua** kandidat dan hanya menolak bila **semuanya**
   gagal. Token yang sah adalah token yang sah, dari pintu mana pun ia datang.
3. **Jenis token dipaksa dua arah**: token `refresh` ditolak sebagai token kerja (kalau tidak,
   umur sesi efektif menjadi 7 hari dan seluruh guna access token hilang), dan token `access`
   ditolak sebagai bekal perpanjangan.
4. Sebab penolakan diutamakan: **`expired` mengalahkan `invalid`**, karena hanya `expired`
   yang bisa ditindaklanjuti. Melaporkannya sebagai `invalid` berarti memaksa pemakai
   mengetik sandi padahal sesinya masih bisa diselamatkan.

### 3.2 Sebab penolakan: kode untuk mesin, kalimat untuk manusia
Tajuk **`X-Session-State`** (kamus SSOT `session_state`, `backend/reference_p54.py`):

| kode | arti | tindakan layar |
|---|---|---|
| `active` | sesi sehat | — |
| `missing` | belum masuk, tidak ada bekal apa pun | antar ke halaman masuk |
| `expired` | berakhir karena waktu | **coba perpanjang diam-diam** |
| `invalid` | bekal tidak dikenali / salah jenis | antar ke halaman masuk |
| `revoked` | akun dinonaktifkan / penyewa disuspend | antar ke halaman masuk + kalimat admin |

`detail` **tetap string kalimat**. Kalau ia dijadikan objek, layar repo ini (yang mencetak
`detail` apa adanya) langsung melahirkan `[object Object]` di muka pengguna — dilarang di repo
ini, dan dijaga gate 45 (`D5b`/`D6b`/`D7b`) serta mutan `M10`.

Kalimatnya juga **tidak menyebut** token/JWT/cookie: pemakai tidak bisa berbuat apa pun
dengan istilah itu. Dijaga `D5c`/`D6c`/`D7c` + `U2`, mutan `M11`/`M33`.

### 3.3 `POST /api/auth/refresh`
| aturan | alasan | dijaga |
|---|---|---|
| hanya `type="refresh"` diterima | umur sesi efektif tidak boleh menjadi 7 hari | `D9`, M18 |
| gerbang akun (`is_active`) | menonaktifkan akun harus benar-benar mengakhiri sesinya | `D17`, M16 |
| gerbang penyewa (`status != suspended`) | sama dengan `/auth/login`, bukan aturan kedua | `D16`, M15 |
| `active_org_id` **dipertahankan** | super admin tidak boleh dipulangkan diam-diam | `D15`, M14 |
| cookie `access_token` **disetel ulang** | jebakan cookie basi (C2) tidak boleh kembali | `K9`, M13 |
| jawaban memakai `session_payload()` | satu bentuk profil sesi dengan `/login` & `/me` (aturan Fase 53), sehingga perubahan izin admin ikut berlaku saat diperpanjang | `D11`, M17 |
| bekal 7 hari diperbarui **hanya** bila sisanya < separuh | orang yang MASIH bekerja tidak diusir di hari ke-7, tetapi jendelanya tidak menjadi tak terbatas hanya karena aplikasi ramai memanggil endpoint ini | POC `H1..H4` |
| bisa lewat cookie **atau** badan permintaan / `X-Refresh-Token` | cookie `httponly` tidak terbaca klien non-peramban (skrip gate, alat uji) — mereka tidak boleh dipaksa memalsukan peramban | POC `C14` |

Konstanta umur ada di **satu** tempat (`security.ACCESS_TTL` / `REFRESH_TTL`); `auth_router`
menurunkan `max_age` cookie darinya. Dulu `86400`/`604800` diketik langsung di router,
terpisah dari `timedelta` di `security.py` — dua tempat yang harus diubah bersamaan dan karena
itu pasti akan berbeda suatu hari. Dijaga `K13`+`D1` (umur cookie = umur token), mutan `M19`.

### 3.4 Frontend: pulih dulu, mengaku kemudian
| lapisan | aturan | alasan |
|---|---|---|
| `services/apiClient.js` | **single-flight** perpanjangan | Sejak Fase 52 setiap halaman profil memuat 5-6 panel bersamaan (`loadPanels`/`allSettled`). Bila token habis saat halaman dibuka, keenamnya 401 hampir serentak; tanpa pengunci, enam token diterbitkan, lima langsung basi, dan permintaan yang diulang memakai token yang sudah ditimpa → gagal lagi → "sesi berakhir" **padahal sesinya sehat**. |
| `services/apiClient.js` | hanya `expired` dicoba diperpanjang | `invalid`/`revoked`/`missing` pasti ditolak juga; mencobanya hanya menambah permintaan gagal dan menunda kabar buruknya |
| `services/apiClient.js` | ulangi permintaan **maksimal sekali** | tidak ada gelung tak berujung |
| `services/apiClient.js` | galat **tanpa respons** ≠ sesi mati | aturan Fase 35: mandor di lokasi tanpa sinyal tidak boleh dilempar ke halaman masuk |
| `services/sessionBus.js` | papan pengumuman tanpa ketergantungan | `apiClient` adalah modul biasa (bukan komponen) dan tidak boleh memanggil hook; ini yang menutup C3 tanpa impor melingkar |
| `context/AuthContext.js` | **perpanjangan proaktif** pada `exp − 5 menit`, plus pemeriksaan ulang saat tab kembali terlihat / jaringan kembali | Laptop yang ditutup lalu dibuka adalah cara paling umum sebuah sesi "mendadak" habis: pengatur waktu tidak jalan saat tab tidur. Jalur "401 lalu ulangi" menjadi **jaring pengaman**, bukan kejadian sehari-hari. |
| `components/layout/SessionBanner.js` | peringatan **hanya** bila perpanjangan otomatis GAGAL | 99% pemakai tidak boleh melihat apa pun. Yang tidak bisa diselamatkan berhak diperingatkan **sebelum** kehilangan isian: hitung mundur jujur + "Sambungkan ulang" + kalimat yang menyebut akibatnya ("selesaikan & simpan") |
| `App.js` + `pages/Login.js` | tempat kerja dicatat lalu **dipulihkan** | Tanpa ini, orang yang sesinya habis saat menelusuri satu unit di antara ratusan harus mencarinya lagi dari awal — itulah yang membuat "sesi habis" terasa seperti kehilangan pekerjaan |

---

## 4. Portal pembeli — kelas cacat yang sama, dan yang SENGAJA tidak dikerjakan

`backend/portal_security.py` mengidap **C2 yang identik** (cookie `portal_token` dibaca
sebelum header) dan **C3 dalam bentuk lebih buruk**: 401 dari portal tidak ditangani sama
sekali di lapisan HTTP, sehingga pembeli yang sesinya habis melihat panel-panel gagal memuat
satu per satu tanpa satu kalimat pun — layarnya seolah rusak. Keduanya ditutup:
urutan kandidat dibenahi (`K25`, mutan M21), tajuk `X-Session-State` ikut dikirim (`P6`,
mutan M22), dan `portalClient` mengakhiri sesi dengan jujur lalu `PortalLogin` menjelaskan
dirinya sendiri dengan kalimat untuk **pembeli** (kode OTP), bukan istilah internal.

**SENGAJA TIDAK dikerjakan:** portal tidak mendapat perpanjangan otomatis. Masuknya lewat
OTP, dan menyimpan bekal 7 hari di perangkat pembeli bukan pertukaran yang pantas untuk
kenyamanan 12 jam. Yang wajib ada di portal adalah **akhir yang jujur**, bukan sesi yang
panjang.

**Dua dunia sesi tetap terpisah** dan itu diuji dua arah: token portal tidak bisa masuk
endpoint staf (`P4`) dan token staf tidak bisa menyusup ke portal (`P5`).

---

## 5. Yang SENGAJA tidak dikerjakan (jangan dianggap lubang)

1. **Daftar-hitam token (revocation list).** Sebuah access token yang sudah terbit tetap sah
   sampai `exp`-nya, kecuali akunnya dimatikan — gerbang akun diperiksa **setiap** permintaan
   lewat `load_session_user()`, jadi menonaktifkan akun langsung menghentikan sesi yang
   berjalan (`D17b`). Yang TIDAK diperiksa setiap permintaan adalah status **organisasi**
   (butuh satu pembacaan `orgs` per permintaan); penegakannya ada di `login` dan `refresh`
   (jeda maksimum = umur access token).
2. **Rotasi refresh token dengan deteksi pemakaian ulang.** Jendela geser sudah membatasi
   umur; deteksi pemakaian ulang menuntut penyimpanan status token per perangkat, dan itu
   fase tersendiri bila memang dibutuhkan.
3. **Sesi lintas tab yang disinkronkan lewat `storage` event.** Setiap tab memperpanjang
   sendiri; single-flight hanya berlaku per tab. Ini menghasilkan paling banyak satu
   perpanjangan berlebih per tab — tidak merusak apa pun.

---

## 6. Peta endpoint ↔ layar

| endpoint | dipakai layar | testId |
|---|---|---|
| `POST /api/auth/refresh` | `services/apiClient.js` (`renewSession`), tombol "Sambungkan ulang" | `session-warning-renew` |
| tajuk `X-Session-State` | `apiClient` (pilih tindakan), `portalClient` | — |
| — (klien) | spanduk peringatan sesi | `session-warning-banner`, `session-warning-countdown`, `session-warning-dismiss` |
| — (klien) | halaman masuk menjelaskan dirinya | `login-session-notice`, `login-return-to-hint` |
| — (klien) | portal menjelaskan dirinya | `portal-session-notice` |

## 7. Bukti

* `python3 poc/poc_54.py` → **75 pemeriksaan PASS** (A dasar · B prioritas token · C
  perpanjangan · D multi-penyewa · E gerbang · F semua peran · G portal · H jendela geser)
* `python3 scripts/verify_session_resilience.py` → **gate 45 HIJAU, 66 pemeriksaan**
* `python3 scripts/mutasi_54.py --ringkas` → **36 mutan** (lihat hasil di
  `memory/gatelogs/mutasi_54_hasil.tsv`)
* `bash scripts/run_all_gates.sh` → OVERALL PASS (**45 gates**)
