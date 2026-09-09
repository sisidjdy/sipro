import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import api, {
  RENEW_BEFORE_SECONDS, TOKEN_KEY, renewIfExpiringSoon, renewSession, setAuthToken,
} from "@/services/apiClient";
import {
  SESSION_STATE, onSessionEnded, secondsLeft, takeSessionEndReason,
} from "@/services/sessionBus";

const AuthContext = createContext(null);

// Profil pengguna terakhir disimpan di perangkat (Fase 35). Token tetap satu-satunya
// otoritas — server selalu memeriksanya; cadangan ini hanya supaya aplikasi tidak
// melempar mandor ke halaman login saat dibuka ulang tanpa sinyal.
const USER_KEY = "sipro_user";

// Sedini apa spanduk peringatan muncul bila perpanjangan otomatis GAGAL. Lebih panjang
// daripada ambang perpanjangan supaya pemakai punya waktu nyata menyelesaikan isian.
const WARN_BEFORE_SECONDS = 240;

function cachedUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [offlineSession, setOfflineSession] = useState(false);
  // Sebab sesi berakhir, dibaca halaman masuk untuk menjelaskan diri sendiri.
  const [sessionEndReason, setSessionEndReason] = useState(() => takeSessionEndReason());
  // Peringatan pra-habis. `null` = tidak ada masalah (keadaan normal).
  const [sessionWarning, setSessionWarning] = useState(null);
  const warnDismissed = useRef(false);

  const bootstrap = useCallback(async () => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setLoading(false);
      return;
    }
    setAuthToken(token);
    try {
      const res = await api.get("/auth/me");
      setUser(res.data.data);
      setOfflineSession(false);
      try { localStorage.setItem(USER_KEY, JSON.stringify(res.data.data)); } catch { /* kuota */ }
    } catch (e) {
      // TIDAK ADA RESPONS = tidak ada sinyal, BUKAN sesi kedaluwarsa. Dulu mandor yang
      // membuka ulang aplikasi di lokasi tanpa sinyal langsung terlempar ke halaman login
      // sehingga papan & antrean tidak bisa dilihat — seolah pekerjaannya hilang.
      const cached = cachedUser();
      if (!e?.response && cached) {
        setUser(cached);
        setOfflineSession(true);
      } else {
        setAuthToken(null);
        localStorage.removeItem(USER_KEY);
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  // ------------------------------------------------------------------ sesi benar-benar mati
  // Cacat Fase 54: `apiClient` dulu menghapus penyimpanan pada 401 tetapi TIDAK memberi tahu
  // React, sehingga aplikasi tetap tergambar utuh sementara semua permintaannya gagal.
  // Sekarang kabar itu masuk ke sini dan sesi benar-benar ditutup di lapisan React juga.
  useEffect(() => onSessionEnded((reason) => {
    setSessionWarning(null);
    setSessionEndReason(reason);
    setUser(null);
    setOfflineSession(false);
    localStorage.removeItem(USER_KEY);
  }), []);

  // --------------------------------------------------------- perpanjangan diam-diam (normal)
  // Jalur yang seharusnya dialami 99% pemakai: sesi diperpanjang sebelum habis dan tidak ada
  // apa pun yang muncul di layar. Jalur "401 lalu ulangi" di `apiClient` adalah jaring
  // pengaman untuk kasus yang tidak bisa diramalkan (tab lama, laptop ditutup, jam beda).
  useEffect(() => {
    if (!user || offlineSession) return undefined;

    let hidup = true;
    let timer = null;

    const periksa = async () => {
      if (!hidup) return;
      const token = localStorage.getItem(TOKEN_KEY);
      if (!token) return;
      const sisa = secondsLeft(token);
      if (sisa > RENEW_BEFORE_SECONDS) {
        if (!warnDismissed.current) setSessionWarning(null);
        jadwalkan(Math.min(sisa - RENEW_BEFORE_SECONDS, 60));
        return;
      }
      const sehat = await renewIfExpiringSoon();
      if (!hidup) return;
      if (sehat) {
        warnDismissed.current = false;
        setSessionWarning(null);
        jadwalkan(60);
        return;
      }
      // Gagal diperpanjang DAN masih ada respons server → sesi memang akan mati. Kalau
      // `emitSessionEnded` sudah jalan, komponen ini akan dilepas; kalau belum (mis. bekal
      // hampir habis), pemakai berhak diperingatkan sebelum kehilangan isian.
      const sisaBaru = secondsLeft(localStorage.getItem(TOKEN_KEY));
      if (sisaBaru <= WARN_BEFORE_SECONDS && !warnDismissed.current) {
        setSessionWarning({ secondsLeft: Math.max(sisaBaru, 0) });
      }
      jadwalkan(30);
    };

    const jadwalkan = (detik) => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(periksa, Math.max(detik, 5) * 1000);
    };

    periksa();

    // Laptop yang ditutup lalu dibuka lagi adalah cara paling umum sebuah sesi "mendadak"
    // habis: pengatur waktu tidak jalan saat tab tidur, jadi periksa ulang begitu tab
    // kembali terlihat.
    const onVisible = () => {
      if (document.visibilityState === "visible") periksa();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
    return () => {
      hidup = false;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onVisible);
    };
  }, [user, offlineSession]);

  /** Tombol "Sambungkan ulang" pada spanduk peringatan. */
  const renewNow = useCallback(async () => {
    try {
      const data = await renewSession();
      if (data?.data) {
        setUser(data.data);
        try { localStorage.setItem(USER_KEY, JSON.stringify(data.data)); } catch { /* kuota */ }
      }
      warnDismissed.current = false;
      setSessionWarning(null);
      return true;
    } catch {
      return false;
    }
  }, []);

  const dismissSessionWarning = useCallback(() => {
    warnDismissed.current = true;
    setSessionWarning(null);
  }, []);

  const login = useCallback(async (email, password) => {
    const res = await api.post("/auth/login", { email, password });
    setAuthToken(res.data.access_token);
    let profile = res.data.data;
    // LAPIS KEDUA untuk cacat Fase 53: bila jawaban login (server lama / proxy yang
    // memangkas) tidak membawa `permissions`, JANGAN pakai apa adanya — profil tanpa izin
    // membuat `can()` menjawab "tidak boleh" untuk semuanya dan layar menuduh hak akses
    // (pemakai super admin pun melihat "Anda tidak punya akses"). Ambil profil lengkap.
    if (!profile?.permissions) {
      try {
        profile = (await api.get("/auth/me")).data.data;
      } catch { /* biarkan pakai profil login; bootstrap akan melengkapi */ }
    }
    setUser(profile);
    setOfflineSession(false);
    setSessionEndReason(null);
    setSessionWarning(null);
    warnDismissed.current = false;
    try { localStorage.setItem(USER_KEY, JSON.stringify(profile)); } catch { /* kuota */ }
    return profile;
  }, []);

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout"); } catch { /* ignore */ }
    setAuthToken(null);
    localStorage.removeItem(USER_KEY);
    setUser(null);
    setOfflineSession(false);
    setSessionWarning(null);
    // Keluar atas kemauan sendiri BUKAN sesi yang berakhir — halaman masuk tidak boleh
    // menuduh "sesi Anda berakhir" pada orang yang baru saja menekan tombol Keluar.
    setSessionEndReason(null);
    takeSessionEndReason();
  }, []);

  // EPIC M4 — super_admin org switch: swap the access token for one carrying the
  // target org context, then hard-reload so every page refetches under that tenant.
  const switchOrg = useCallback(async (orgId) => {
    const res = await api.post(`/admin/orgs/${orgId}/switch`);
    setAuthToken(res.data.access_token);
    window.location.assign("/");
    return res.data.data;
  }, []);

  // Fase 39b — `can(resource, action)` menjawab "apakah peran ini boleh?" memakai izin
  // EFEKTIF yang dikirim backend di `GET /auth/me` (`user.permissions`). Matriksnya tetap
  // satu sumber di `backend/rbac.py`; yang ditiru di sini hanya CARA MEMBACANYA — dan
  // aturannya harus sama dengan `rbac._permitted`: `manage`/`all` berarti boleh apa saja,
  // dan `view` dipenuhi oleh `view_all`/`view_own`.
  // Dipakai mis. untuk menyembunyikan tombol "Verifikasi" dokumen dari sales (yang justru
  // mengunggahnya) — kalau tidak, tombolnya ada tetapi selalu 403.
  const can = useCallback((resource, action) => {
    const perms = user?.permissions;
    if (!perms) return false;
    if ((perms["*"] || []).includes("*")) return true;
    const list = perms[resource] || [];
    if (list.includes("manage") || list.includes("all") || list.includes(action)) return true;
    return action === "view"
      && ["view", "view_all", "view_own"].some((a) => list.includes(a));
  }, [user]);

  // `permsKnown` membedakan dua hal yang SANGAT berbeda dan dulu tercampur:
  //   • izin sudah diketahui dan jawabannya TIDAK BOLEH  → kartu "akses ditolak" benar;
  //   • izin BELUM diketahui (profil sesi belum lengkap)  → kartu itu KEBOHONGAN.
  // Layar memakai ini agar tidak pernah menuduh hak akses saat sebenarnya datanya belum ada.
  const permsKnown = !!user?.permissions;

  // Penyembuhan diri: profil sesi tanpa `permissions` diperbaiki dengan mengambil ulang
  // `/auth/me` (bukan dibiarkan menjadi layar "tidak punya akses").
  useEffect(() => {
    if (user && !user.permissions && !offlineSession) {
      bootstrap();
    }
  }, [user, offlineSession, bootstrap]);

  return (
    <AuthContext.Provider value={{ user, loading, offlineSession, login, logout, switchOrg,
      can, permsKnown, refresh: bootstrap,
      sessionEndReason,
      sessionWarning, renewNow, dismissSessionWarning,
      SESSION_STATE }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};
