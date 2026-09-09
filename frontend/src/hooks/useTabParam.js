// useTabParam — sinkronkan tab aktif ke URL (`?tab=`) untuk halaman yang memakai
// komponen Tabs shadcn (Unit 360 & Proyek). Halaman baru memakai `patterns/TabPage`;
// dua halaman lama ini cukup disambungkan agar aturan IA V2 berlaku sama:
// "tab adalah alamat" — bisa dibagikan, tahan muat-ulang, dan tombol Kembali bekerja.
import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

export default function useTabParam(defaultKey, paramKey = "tab") {
  const [params, setParams] = useSearchParams();
  const value = params.get(paramKey) || defaultKey;
  const setValue = useCallback((next) => {
    const sp = new URLSearchParams(params);
    sp.set(paramKey, next);
    setParams(sp, { replace: false });
  }, [params, paramKey, setParams]);
  return [value, setValue];
}
