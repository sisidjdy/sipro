import React from "react";

/**
 * Hint — panel syarat INLINE untuk semua dialog pembangunan.
 *
 * Prinsipnya: pengguna harus tahu APA yang belum lengkap SEBELUM menekan tombol, bukan
 * ditolak diam-diam setelah mengirim. Dipakai bersama oleh dialog Ajukan Hasil,
 * Kembalikan, Terobos Gerbang, Penyebab Telat, dan Hentikan Jadwal supaya bahasanya
 * konsisten di seluruh modul.
 */
export default function Hint({ testId, problems = [], okText }) {
  const ok = !problems.length;
  return (
    <div data-testid={testId}
      className={`rounded-lg border p-2.5 text-[11px] ${ok
        ? "border-emerald-200 bg-emerald-50 text-emerald-900"
        : "border-amber-200 bg-amber-50 text-amber-900"}`}>
      {ok ? <p>{okText}</p> : (
        <>
          <p className="font-semibold">Belum bisa disimpan — lengkapi dulu:</p>
          {problems.map((p, i) => <p key={i}>• {p}</p>)}
        </>
      )}
    </div>
  );
}
