// sessionBus.js — jembatan satu arah dari lapisan HTTP (modul biasa) ke React.
//
// ## Cacat NYATA yang ditutup berkas ini (Fase 54)
//
// Dulu `apiClient` menangani 401 begini:
//
//     if (status === 401) { localStorage.removeItem(TOKEN_KEY);
//                           localStorage.removeItem("sipro_user"); }
//
// Penyimpanan dibersihkan, tetapi **React tidak pernah diberi tahu**. `AuthContext` masih
// memegang `user`, jadi aplikasi tetap menggambar seluruh kerangkanya — sidebar, tab, kartu —
// sementara SETIAP permintaan berikutnya gagal. Pengguna melihat aplikasi yang tampak normal
// tetapi tidak bisa dipakai, tanpa satu kalimat pun yang menjelaskan, tanpa diantar ke
// halaman masuk, dan pekerjaan yang sedang diisi hilang. Ironisnya komentar di kode itu
// mengaku sedang mencegah keadaan itu.
//
// `apiClient` adalah modul biasa (bukan komponen), jadi ia tidak boleh memanggil hook.
// Berkas ini jembatannya: papan pengumuman kecil tanpa ketergantungan, sehingga tidak ada
// impor melingkar antara lapisan HTTP dan lapisan React.

// Nilai WAJIB sama dengan kamus SSOT `session_state` (backend/reference_p54.py) dan dengan
// tajuk `X-Session-State` yang dikirim server.
export const SESSION_STATE = {
  active: "active",
  missing: "missing",
  expired: "expired",
  invalid: "invalid",
  revoked: "revoked",
};

// Kalimat yang dilihat pengguna di halaman masuk. Sengaja menjelaskan APA YANG TERJADI dan
// APA YANG HARUS DILAKUKAN — bukan menyalahkan pengguna, dan tidak menyebut istilah internal
// (token/cookie/JWT) yang tidak bisa ditindaklanjuti siapa pun.
export const SESSION_END_MESSAGE = {
  [SESSION_STATE.expired]:
    "Sesi Anda berakhir karena sudah cukup lama. Masuk kembali untuk melanjutkan — Anda akan "
    + "dibawa kembali ke halaman yang sedang Anda buka.",
  [SESSION_STATE.invalid]:
    "Sesi Anda tidak dikenali lagi. Masuk kembali untuk melanjutkan.",
  [SESSION_STATE.revoked]:
    "Akses akun Anda sedang dinonaktifkan. Hubungi admin bila ini tidak seharusnya terjadi.",
  [SESSION_STATE.missing]:
    "Anda belum masuk. Silakan masuk untuk melanjutkan.",
};

const RETURN_TO_KEY = "sipro_return_to";
const REASON_KEY = "sipro_session_end_reason";

const listeners = new Set();

/** Berlangganan kabar "sesi berakhir". Mengembalikan fungsi berhenti-berlangganan. */
export function onSessionEnded(cb) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/**
 * Umumkan bahwa sesi BENAR-BENAR berakhir (sudah dicoba diperpanjang dan gagal, atau
 * memang tidak bisa diperpanjang). Sebabnya disimpan supaya halaman masuk bisa menjelaskan
 * diri sendiri walau aplikasi dimuat ulang penuh di tengah jalan.
 */
export function emitSessionEnded(reason = SESSION_STATE.expired) {
  try {
    sessionStorage.setItem(REASON_KEY, reason);
  } catch { /* mode privat / kuota penuh */ }
  listeners.forEach((cb) => {
    try {
      cb(reason);
    } catch { /* satu pendengar yang rusak tidak boleh membungkam yang lain */ }
  });
}

/**
 * Ingat halaman yang sedang dibuka supaya pengguna bisa DIKEMBALIKAN ke sana sesudah masuk
 * ulang. Inilah bedanya "sesi habis" yang sopan dengan yang merusak: tanpa ini, orang yang
 * sedang menelusuri satu unit di antara ratusan harus mencarinya lagi dari awal.
 *
 * `/login` dan `/` tidak pernah diingat (tidak ada gunanya kembali ke sana).
 */
export function rememberReturnTo(path) {
  if (!path || path === "/" || path.startsWith("/login")) return;
  try {
    sessionStorage.setItem(RETURN_TO_KEY, path);
  } catch { /* abaikan */ }
}

/** Ambil DAN hapus tujuan kembali (sekali pakai — jangan sampai memantul terus). */
export function takeReturnTo() {
  try {
    const v = sessionStorage.getItem(RETURN_TO_KEY);
    sessionStorage.removeItem(RETURN_TO_KEY);
    return v || null;
  } catch {
    return null;
  }
}

/**
 * Lihat tujuan kembali TANPA menghapusnya.
 *
 * Perlu dibedakan dari `takeReturnTo()` karena dua tempat memakainya untuk maksud berbeda:
 * halaman masuk hanya ingin MENAMPILKAN kalimat "Anda akan dibawa kembali ke …", sedangkan
 * yang benar-benar melakukan pengalihan adalah penjaga rute. Kalau keduanya memakai versi
 * sekali-pakai, yang menampilkan kalimat akan menghabiskan tujuannya lebih dulu dan pengguna
 * dijanjikan kembali ke tempat kerjanya lalu tetap didaratkan di Beranda — janji yang
 * dilanggar di depan mata.
 */
export function peekReturnTo() {
  try {
    return sessionStorage.getItem(RETURN_TO_KEY) || null;
  } catch {
    return null;
  }
}

/** Ambil DAN hapus sebab sesi berakhir. */
export function takeSessionEndReason() {
  try {
    const v = sessionStorage.getItem(REASON_KEY);
    sessionStorage.removeItem(REASON_KEY);
    return v || null;
  } catch {
    return null;
  }
}

/**
 * Sisa umur token (detik) dibaca dari klaim `exp` tanpa pustaka tambahan.
 *
 * Ini BUKAN pemeriksaan keamanan — server tetap satu-satunya yang memutuskan. Gunanya hanya
 * supaya klien bisa memperpanjang sesi SEBELUM mati, sehingga jalur "401 lalu ulangi" menjadi
 * jaring pengaman, bukan kejadian sehari-hari.
 */
export function secondsLeft(token) {
  if (!token) return 0;
  try {
    const part = token.split(".")[1];
    const json = JSON.parse(atob(part.replace(/-/g, "+").replace(/_/g, "/")));
    return Math.floor(json.exp - Date.now() / 1000);
  } catch {
    return 0;
  }
}
