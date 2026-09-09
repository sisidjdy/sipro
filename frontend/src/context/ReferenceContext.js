import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import api from "@/services/apiClient";
import { useAuth } from "@/context/AuthContext";

/**
 * ReferenceContext — SSOT daftar pilihan (enum) untuk SELURUH form.
 *
 * Sebelum ini setiap halaman meng-hardcode daftar dropdown-nya sendiri sehingga
 * nilainya berbeda-beda (mis. tahap lead ada 3 versi, kategori pekerjaan ada 3 ejaan)
 * dan backend menerima string apa pun. Sekarang satu-satunya sumber adalah
 * GET /api/reference (backend/reference.py).
 */
const ReferenceContext = createContext(null);

const CACHE_KEY = "sipro:reference";

export function ReferenceProvider({ children }) {
  const { user } = useAuth();
  const [registry, setRegistry] = useState({});
  const [maps, setMaps] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [cachedAt, setCachedAt] = useState(null);

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true); setError("");
    try {
      const res = await api.get("/reference");
      setRegistry(res.data.data || {});
      setMaps(res.data.maps || {});
      setCachedAt(null);
      // Fase 35: simpan kamus pilihan di perangkat. Tanpa ini, mandor yang MEMBUKA ULANG
      // aplikasi di lokasi tanpa sinyal mendapat dropdown kosong (checklist mutu tidak
      // bisa dijawab) sehingga pekerjaan tidak bisa diajukan sama sekali.
      try {
        localStorage.setItem(CACHE_KEY, JSON.stringify({
          at: new Date().toISOString(), data: res.data.data || {}, maps: res.data.maps || {},
        }));
      } catch { /* kuota penuh: aplikasi tetap jalan, hanya tanpa cadangan offline */ }
    } catch (e) {
      let restored = false;
      if (!e?.response) {
        try {
          const snap = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
          if (snap?.data && Object.keys(snap.data).length) {
            setRegistry(snap.data);
            setMaps(snap.maps || {});
            setCachedAt(snap.at);
            restored = true;
          }
        } catch { /* cadangan rusak → jatuh ke pesan galat biasa */ }
      }
      if (!restored) {
        setError(e?.response?.data?.detail
          || "Gagal memuat daftar pilihan (tidak ada jaringan & belum ada cadangan).");
      }
    } finally { setLoading(false); }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const value = useMemo(() => {
    const options = (group) => registry[group]?.options || [];
    const labelOf = (group, val) => {
      if (val === null || val === undefined || val === "") return "-";
      const hit = (registry[group]?.options || []).find((o) => o.value === val);
      return hit ? hit.label : String(val);
    };
    const groupMeta = (group) => registry[group] || { label: group, options: [], dynamic: false };
    return { registry, maps, options, labelOf, groupMeta, loading, error, cachedAt,
      reload: load };
  }, [registry, maps, loading, error, cachedAt, load]);

  return <ReferenceContext.Provider value={value}>{children}</ReferenceContext.Provider>;
}

export function useReference() {
  const ctx = useContext(ReferenceContext);
  if (!ctx) {
    // Fallback aman: komponen tetap render meski dipakai di luar provider.
    return {
      registry: {}, maps: {}, options: () => [], labelOf: (_g, v) => (v ?? "-"),
      groupMeta: () => ({ label: "", options: [], dynamic: false }),
      loading: false, error: "", cachedAt: null, reload: () => {},
    };
  }
  return ctx;
}
