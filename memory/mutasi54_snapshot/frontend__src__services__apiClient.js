import axios from "axios";
import {
  SESSION_STATE, emitSessionEnded, secondsLeft,
} from "@/services/sessionBus";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;
export const TOKEN_KEY = "sipro_token";

// Diperpanjang sedini ini SEBELUM habis. 5 menit cukup longgar untuk jaringan lapangan yang
// lambat, dan cukup pendek supaya perubahan izin oleh admin tidak tertahan lama.
export const RENEW_BEFORE_SECONDS = 300;

const api = axios.create({ baseURL: API });

export const setAuthToken = (token) => {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    localStorage.removeItem(TOKEN_KEY);
    delete api.defaults.headers.common.Authorization;
  }
};

// Attach token from storage on every request (survives reloads).
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Initialize header on module load.
const existing = localStorage.getItem(TOKEN_KEY);
if (existing) api.defaults.headers.common.Authorization = `Bearer ${existing}`;

// --------------------------------------------------------------------------- perpanjangan
// Satu perpanjangan pada satu waktu ("single-flight").
//
// ## Kenapa ini WAJIB, bukan penyempurnaan
// Sejak Fase 52 setiap halaman profil memuat 5-6 panel BERSAMAAN lewat `loadPanels()`
// (`Promise.allSettled`). Kalau token kebetulan habis saat halaman dibuka, keenam permintaan
// itu menerima 401 pada saat yang hampir sama. Tanpa pengunci di bawah ini, keenamnya akan
// memanggil `/auth/refresh` berbarengan: enam token baru diterbitkan, lima di antaranya
// langsung basi, dan permintaan yang sudah diulang bisa memakai token yang sudah ditimpa —
// gagal lagi, lalu memicu "sesi berakhir" PADAHAL sesinya sehat.
let renewal = null;

function sessionState(err) {
  return err?.response?.headers?.["x-session-state"] || "";
}

function isAuthRoute(url) {
  const u = String(url || "");
  return u.includes("/auth/login") || u.includes("/auth/refresh")
    || u.includes("/auth/register") || u.includes("/portal/auth/");
}

function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem("sipro_user");
  delete api.defaults.headers.common.Authorization;
}

/**
 * Minta token kerja baru memakai bekal perpanjangan (cookie `refresh_token`, httponly).
 * Semua pemanggil yang datang saat perpanjangan sedang berjalan menunggu janji yang SAMA.
 */
export function renewSession() {
  if (renewal) return renewal;
  renewal = axios
    .post(`${API}/auth/refresh`, {}, { withCredentials: true })
    .then((res) => {
      const token = res?.data?.access_token;
      if (!token) throw new Error("tanpa token");
      setAuthToken(token);
      return res.data;
    })
    .finally(() => {
      renewal = null;
    });
  return renewal;
}

/**
 * Perpanjang lebih awal bila token tinggal sebentar. Dipanggil `AuthContext` lewat pengatur
 * waktu dan saat tab kembali terlihat (laptop yang ditutup lalu dibuka lagi adalah cara
 * paling umum sebuah sesi "mendadak" habis).
 *
 * Mengembalikan `true` bila sesi masih/kembali sehat.
 */
export async function renewIfExpiringSoon() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return false;
  if (secondsLeft(token) > RENEW_BEFORE_SECONDS) return true;
  try {
    await renewSession();
    return true;
  } catch (e) {
    // TIDAK ADA RESPONS = tidak ada sinyal, BUKAN sesi mati (aturan Fase 35). Mandor di
    // lokasi tanpa sinyal tidak boleh dilempar ke halaman masuk.
    if (!e?.response) return true;
    clearSession();
    emitSessionEnded(sessionState(e) || SESSION_STATE.expired);
    return false;
  }
}

// --------------------------------------------------------------------------- interceptor
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const cfg = err?.config || {};
    if (err?.response?.status !== 401 || isAuthRoute(cfg.url)) {
      return Promise.reject(err);
    }
    const state = sessionState(err);

    // Hanya `expired` yang boleh diselamatkan diam-diam. `invalid`/`revoked`/`missing`
    // berarti memperpanjang pun akan ditolak — mencobanya hanya menambah satu permintaan
    // gagal dan menunda kabar buruknya.
    if (state === SESSION_STATE.expired && !cfg.__sudahDiulang) {
      try {
        await renewSession();
        cfg.__sudahDiulang = true;
        return api.request(cfg);
      } catch (e2) {
        if (!e2?.response) return Promise.reject(err); // tanpa sinyal: jangan bunuh sesi
      }
    }

    // Sampai di sini sesi memang berakhir. Bersihkan jejaknya DAN beri tahu React —
    // membersihkan penyimpanan tanpa memberi tahu React adalah cacat aslinya.
    clearSession();
    emitSessionEnded(state || SESSION_STATE.expired);
    return Promise.reject(err);
  },
);

export default api;
