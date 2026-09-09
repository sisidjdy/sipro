// testId permukaan Fase 54 — ketahanan sesi: perpanjangan otomatis, peringatan sebelum
// sesi berakhir, dan kembali ke halaman yang sama sesudah masuk ulang.
//
// Dipisah per fase (aturan repo) supaya berkas testId tidak menjadi tempat sampah: setiap
// id di sini menempel pada permukaan yang BARU lahir di Fase 54.
export const P54 = {
  // --- spanduk peringatan sesi (muncul hanya bila perpanjangan otomatis GAGAL)
  banner: "session-warning-banner",
  bannerCountdown: "session-warning-countdown",
  bannerRenew: "session-warning-renew",
  bannerDismiss: "session-warning-dismiss",

  // --- halaman masuk: penjelasan mengapa pengguna ada di sini
  loginSessionNotice: "login-session-notice",
  loginReturnTo: "login-return-to-hint",
};
