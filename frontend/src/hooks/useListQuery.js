// useListQuery — status query daftar (cari + filter + sort + halaman) yang HIDUP DI URL.
//
// Kenapa di URL, bukan di useState:
//   1. **KPI beranda harus bisa di-drill-down** (US-40-4): satu klik pada "Booking 7" harus
//      membuka daftar yang SUDAH terfilter. Itu hanya mungkin bila filter dibaca dari URL.
//   2. Bisa dibagikan/di-bookmark: "kirim saya daftar lead lewat SLA" = kirim tautan.
//   3. Tombol Kembali browser mengembalikan filter sebelumnya (dulu filter hilang).
//
// Kontrak: nilai filter bertipe ARRAY dianggap multi (URL: dipisah koma), string dianggap
// tunggal (mis. rentang tanggal). Bentuk default menentukan tipenya — bukan tebakan runtime.
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

const BASE = { q: "", sort: "", direction: "asc", skip: 0, limit: 25 };

export default function useListQuery({ filters = {}, sort = "", direction = "desc",
  limit: limitProp } = {}) {
  const { user } = useAuth();
  // Bawaan baris per halaman = `ui.table_page_size` (Pusat Konfigurasi › Tampilan).
  const limit = limitProp ?? user?.ui?.table_page_size ?? 25;
  const [params, setParams] = useSearchParams();
  const defaults = useMemo(() => ({ ...BASE, sort, direction, limit, ...filters }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sort, direction, limit, JSON.stringify(filters)]);

  const query = useMemo(() => {
    const out = {};
    Object.entries(defaults).forEach(([key, def]) => {
      const raw = params.get(key);
      if (Array.isArray(def)) {
        out[key] = raw ? raw.split(",").filter(Boolean) : [];
      } else if (typeof def === "number") {
        const n = Number(raw);
        out[key] = raw !== null && Number.isFinite(n) ? n : def;
      } else {
        out[key] = raw !== null ? raw : def;
      }
    });
    return out;
  }, [params, defaults]);

  /** Ubah sebagian query. Perubahan filter/cari SELALU kembali ke halaman 1 (kalau tidak,
   *  pemakai bisa berada di halaman 5 dari hasil yang hanya punya 1 halaman = layar kosong). */
  const setQuery = useCallback((patch) => {
    const next = new URLSearchParams(params);
    const resetsPage = Object.keys(patch).some((k) => !(["skip", "limit"].includes(k)));
    Object.entries(patch).forEach(([key, value]) => {
      const isEmpty = value === "" || value === null || value === undefined
        || (Array.isArray(value) && value.length === 0);
      const same = String(defaults[key] ?? "") === String(value ?? "");
      if (isEmpty || (same && !Array.isArray(defaults[key]))) next.delete(key);
      else next.set(key, Array.isArray(value) ? value.join(",") : String(value));
    });
    if (resetsPage && patch.skip === undefined) next.delete("skip");
    setParams(next, { replace: true });
  }, [params, defaults, setParams]);

  const reset = useCallback(() => {
    const next = new URLSearchParams(params);
    Object.keys(defaults).forEach((k) => next.delete(k));
    setParams(next, { replace: true });
  }, [params, defaults, setParams]);

  /** Parameter untuk axios: array → "a,b"; kosong → tidak dikirim (biar backend pakai default). */
  const apiParams = useMemo(() => {
    const out = {};
    Object.entries(query).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        if (value.length) out[key] = value.join(",");
      } else if (value !== "" && value !== null && value !== undefined) {
        out[key] = value;
      }
    });
    return out;
  }, [query]);

  const filterKeys = useMemo(
    () => Object.keys(filters), // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(filters)],
  );
  const activeCount = useMemo(() => filterKeys.reduce((n, k) => {
    const v = query[k];
    return n + (Array.isArray(v) ? (v.length ? 1 : 0) : (v ? 1 : 0));
  }, 0), [filterKeys, query]);

  return { query, setQuery, reset, apiParams, activeCount, filterKeys };
}
