import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import portalApi, {
  PORTAL_TOKEN_KEY, onPortalSessionEnded, setPortalToken, takePortalEndReason,
} from "@/services/portalClient";

const PortalAuthContext = createContext(null);

// Kalimat untuk PEMBELI — bukan untuk staf. Tidak menyebut istilah internal, dan menyebut
// cara masuk yang mereka kenal (kode OTP lewat WhatsApp).
export const PORTAL_END_MESSAGE = {
  expired: "Sesi Anda sudah berakhir karena tidak dipakai beberapa waktu. Masuk kembali "
    + "dengan kode OTP untuk melanjutkan.",
  invalid: "Sesi Anda tidak dikenali lagi. Masuk kembali dengan kode OTP untuk melanjutkan.",
  revoked: "Akses portal Anda sedang dinonaktifkan. Silakan hubungi kami.",
  missing: "Masuk dengan kode OTP untuk melihat rumah Anda.",
};

export function PortalAuthProvider({ children }) {
  const [token, setToken] = useState(localStorage.getItem(PORTAL_TOKEN_KEY));
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [endReason, setEndReason] = useState(() => takePortalEndReason());

  const bootstrap = useCallback(async () => {
    if (!token) { setLoading(false); return; }
    try {
      const res = await portalApi.get("/portal/me");
      setProfile(res.data.data);
      setEndReason(null);
    } catch (e) {
      // Tanpa RESPONS berarti tanpa sinyal, bukan sesi mati (aturan Fase 35 — pembeli sering
      // membuka portal dari lokasi proyek yang sinyalnya buruk). Jangan buang sesinya.
      if (e?.response) {
        setPortalToken(null);
        setToken(null);
        setProfile(null);
      }
    } finally { setLoading(false); }
  }, [token]);

  useEffect(() => { bootstrap(); }, [bootstrap]);

  // Sesi portal yang ditolak server harus benar-benar ditutup DI REACT juga, supaya
  // pembeli diantar ke halaman masuk beserta penjelasannya — bukan dibiarkan menatap
  // panel-panel yang gagal memuat.
  useEffect(() => onPortalSessionEnded((reason) => {
    setToken(null);
    setProfile(null);
    setEndReason(reason);
  }), []);

  const login = (newToken, prof) => {
    setPortalToken(newToken);
    setToken(newToken);
    setProfile(prof || null);
    setEndReason(null);
  };

  const logout = () => {
    setPortalToken(null);
    setToken(null);
    setProfile(null);
    setEndReason(null);
  };

  return (
    <PortalAuthContext.Provider value={{ token, profile, loading, login, logout, endReason }}>
      {children}
    </PortalAuthContext.Provider>
  );
}

export const usePortalAuth = () => useContext(PortalAuthContext);
