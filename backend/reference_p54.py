"""SSOT reference registry — TAMBAHAN Fase 54 (Ketahanan Sesi).

Digabungkan ke `reference.GROUPS` lewat `_PHASES` di `reference.py`.

## Lubang NYATA yang ditutup Fase 54

Laporan pemakai (tercatat `test_reports/iteration_85.json`, satu-satunya sisa Fase 53):
*"Login sessions expire frequently during testing. Users need to re-login multiple times
during extended use."*

Empat sebabnya, semua terbukti di kode:

1. **`POST /api/auth/refresh` tidak pernah ada.** `auth_router.py` menulis "…, logout,
   refresh" di baris pertamanya, `create_refresh_token()` dipanggil di login DAN register,
   cookie `refresh_token` disetel 7 hari — lalu tidak ada satu baris pun yang membacanya.
   Sesi mati keras di jam ke-24; pekerjaan yang sedang diisi hilang.
2. **Cookie kedaluwarsa mengalahkan Bearer yang sah.** `security._extract_token` membaca
   cookie lebih dulu dan hanya turun ke header bila cookie KOSONG — cookie yang ADA tapi
   BASI langsung 401 walau header membawa token sempurna.
3. **Sebab 401 tidak bisa dibedakan mesin.** "belum masuk", "sesi berakhir", "token cacat",
   dan "akses dicabut" semuanya hanya kalimat. Layar tidak bisa memilih tindakan yang
   berbeda (diam-diam perpanjang vs antar ke halaman masuk), jadi ia memilih yang paling
   merusak: menghapus sesi dan membiarkan pengguna di aplikasi yang semua permintaannya
   gagal.
4. **Perpanjangan bisa menjadi pintu belakang.** Tanpa gerbang, akun yang dinonaktifkan dan
   penyewa yang disuspend bisa memperpanjang sesinya 7 hari lagi; dan `super_admin` yang
   sedang "bertindak sebagai" penyewa lain bisa dipulangkan diam-diam ke org asalnya
   (layarnya menyebut penyewa lama, datanya sudah milik penyewa lain).

Kamus di bawah ini adalah bahasa bersama untuk keadaan-keadaan sesi itu. Sengaja SSOT:
layar tidak boleh mengarang kalimatnya sendiri, dan **sebab** sebuah sesi ditolak harus
punya kode agar bisa diuji dan agar tindakan lanjutannya tidak ditebak-tebak.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P54: dict = {
    "session_state": {
        "label": "Keadaan Sesi",
        "strict": True,
        "help": ("Dikirim server pada tajuk `X-Session-State` setiap kali sebuah permintaan "
                 "ditolak karena sesi. Kode inilah yang menentukan TINDAKAN layar: hanya "
                 "`expired` yang boleh dicoba diperpanjang diam-diam; `missing`, `invalid`, "
                 "dan `revoked` harus mengantar pengguna ke halaman masuk. Badan jawaban "
                 "(`detail`) tetap KALIMAT manusia — kalau ia menjadi objek, layar repo ini "
                 "mencetaknya sebagai \"[object Object]\"."),
        "options": [
            _o("active", "Sesi aktif"),
            _o("missing", "Belum masuk (tidak ada bekal sesi sama sekali)"),
            _o("expired", "Sesi berakhir karena waktu — boleh diperpanjang"),
            _o("invalid", "Bekal sesi tidak dikenali / salah jenis"),
            _o("revoked", "Akses dicabut (akun dinonaktifkan atau organisasi disuspend)"),
        ],
    },
    "session_renewal": {
        "label": "Hasil Perpanjangan Sesi",
        "strict": True,
        "help": ("Dipakai catatan jejak & layar untuk menjelaskan mengapa sesi diperpanjang "
                 "atau tidak. `slid` berarti bekal 7 hari ikut diperbarui karena sisanya "
                 "sudah sedikit — hanya terjadi bila pemakai MEMANG masih bekerja."),
        "options": [
            _o("renewed", "Diperpanjang (token kerja baru diterbitkan)"),
            _o("slid", "Diperpanjang + bekal 7 hari diperbarui (jendela bergeser)"),
            _o("refused_expired", "Ditolak: bekal perpanjangan sudah kedaluwarsa"),
            _o("refused_invalid", "Ditolak: bekal perpanjangan tidak sah atau salah jenis"),
            _o("refused_revoked", "Ditolak: akun atau organisasi sudah dinonaktifkan"),
        ],
    },
}
