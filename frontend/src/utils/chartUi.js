// chartUi — pembantu tampilan grafik (Recharts) yang dipakai bersama.
//
// Kenapa ada: Recharts mewarnai TULISAN pada legenda dengan warna garis serinya. Untuk
// seri "Rencana" (amber #f59e0b) tulisan itu hanya berkontras 2.1:1 terhadap latar putih —
// terbaca samar, dan itu terukur oleh `scripts/ui_audit_dialogs.py` (temuan D6), bukan
// selera. Kotak warna legenda TETAP memakai warna serinya (supaya kaitan ke garis jelas),
// yang diperbaiki hanya warna tulisannya.

import React from "react";

/** Formatter legenda: tulisan memakai warna teks utama, kotak warna seri tidak diubah. */
export function legendLabel(value) {
  return <span style={{ color: "hsl(var(--foreground))" }}>{value}</span>;
}

/** Warna garis seri — satu sumber supaya grafik lintas halaman tidak beda-beda. */
export const SERIES = {
  plan: "#f59e0b",
  actual: "#0d9488",
  cashIn: "#0d9488",
  cashOut: "#e11d48",
};
