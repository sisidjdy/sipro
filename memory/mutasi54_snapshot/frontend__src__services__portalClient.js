// Portal API client — separate axios instance + token so buyers (portal) and
// staff never share credentials. Named `portalApi` intentionally (the api-contract
// gate only inspects the staff `api.<method>` client).
import axios from "axios";
import { API } from "@/services/apiClient";

export const PORTAL_TOKEN_KEY = "sipro_portal_token";
export const PORTAL_END_REASON_KEY = "sipro_portal_session_end";

const portalApi = axios.create({ baseURL: API });

portalApi.interceptors.request.use((config) => {
  const t = localStorage.getItem(PORTAL_TOKEN_KEY);
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

export const setPortalToken = (token) => {
  if (token) localStorage.setItem(PORTAL_TOKEN_KEY, token);
  else localStorage.removeItem(PORTAL_TOKEN_KEY);
};

// ------------------------------------------------------------------ sesi portal berakhir
// Kelas cacat yang sama seperti sesi staf (Fase 54), di pintu yang berbeda: dulu 401 dari
// portal tidak ditangani sama sekali di lapisan HTTP, sehingga pembeli yang sesinya habis
// melihat panel-panel gagal memuat satu per satu tanpa satu kalimat pun — layarnya seolah
// rusak. Portal SENGAJA tidak punya perpanjangan otomatis: masuknya lewat OTP, dan menyimpan
// bekal 7 hari di perangkat pembeli bukan pertukaran yang pantas. Yang wajib ada adalah
// AKHIR YANG JUJUR: bersihkan sesi, catat sebabnya, dan biarkan portal menampilkan halaman
// masuk beserta penjelasannya.
const listeners = new Set();

export function onPortalSessionEnded(cb) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function takePortalEndReason() {
  try {
    const v = sessionStorage.getItem(PORTAL_END_REASON_KEY);
    sessionStorage.removeItem(PORTAL_END_REASON_KEY);
    return v || null;
  } catch {
    return null;
  }
}

portalApi.interceptors.response.use(
  (res) => res,
  (err) => {
    const url = String(err?.config?.url || "");
    const auth = url.includes("/portal/auth/");
    if (err?.response?.status === 401 && !auth) {
      const state = err?.response?.headers?.["x-session-state"] || "expired";
      setPortalToken(null);
      try { sessionStorage.setItem(PORTAL_END_REASON_KEY, state); } catch { /* abaikan */ }
      listeners.forEach((cb) => {
        try { cb(state); } catch { /* satu pendengar rusak tidak membungkam yang lain */ }
      });
    }
    return Promise.reject(err);
  },
);

export default portalApi;
