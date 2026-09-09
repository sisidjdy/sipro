// Ekspor CSV di sisi klien (tanpa dependensi) — dipakai halaman laporan keuangan.
// Nilai dibungkus tanda kutip & escape agar aman untuk Excel/Sheets (delimiter ';'
// karena locale Indonesia memakai koma sebagai desimal).

const DELIM = ";";

const cell = (v) => {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return /[";\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export function toCsv(headers, rows) {
  const head = headers.map(cell).join(DELIM);
  const body = rows.map((r) => r.map(cell).join(DELIM)).join("\n");
  return `${head}\n${body}`;
}

export function downloadCsv(filename, headers, rows) {
  const csv = toCsv(headers, rows);
  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
