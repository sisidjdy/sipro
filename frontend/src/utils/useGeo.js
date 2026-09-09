import { useCallback, useEffect, useState } from "react";

/**
 * useGeoCapture — merekam LOKASI saat bukti kerja diambil (Fase 32).
 *
 * Kenapa tidak dari EXIF foto? Pipeline foto SIPRO memang MEMBUANG metadata EXIF/GPS
 * supaya berkas yang dibagikan (ke pembeli, subkon, bank) tidak membocorkan lokasi rumah.
 * Jadi koordinat diminta eksplisit dari peramban/HP, ditampilkan apa adanya ke pengguna,
 * dan hanya diwajibkan bila admin menyalakan kebijakannya.
 *
 * Status yang jujur (bukan "gagal" tanpa penjelasan):
 *   idle | asking | ready | denied | unsupported | error
 */
export default function useGeoCapture(required) {
  const [geo, setGeo] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  const ask = useCallback(() => {
    if (!navigator.geolocation) {
      setStatus("unsupported");
      setError("Peramban ini tidak mendukung perekaman lokasi. Buka dari HP, atau minta "
        + "admin mematikan kewajiban lokasi.");
      return;
    }
    setStatus("asking");
    setError("");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGeo({
          lat: pos.coords.latitude, lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy ? Math.round(pos.coords.accuracy) : null,
          captured_at: new Date().toISOString(),
        });
        setStatus("ready");
      },
      (err) => {
        setStatus(err.code === 1 ? "denied" : "error");
        setError(err.code === 1
          ? "Izin lokasi ditolak. Aktifkan izin lokasi untuk aplikasi ini lalu coba lagi."
          : "Lokasi belum bisa dibaca (sinyal GPS lemah). Keluar ke area terbuka lalu coba lagi.");
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 },
    );
  }, []);

  useEffect(() => {
    if (required && status === "idle") ask();
  }, [required, status, ask]);

  return { geo, status, error, ask, ok: !required || !!geo };
}
