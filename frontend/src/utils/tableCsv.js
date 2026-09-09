// tableCsv — ekspor baris tabel menjadi CSV yang benar-benar bisa dibuka di Excel Indonesia.
//
// Cacat yang ditutup: ekspor lama menempelkan nilai apa adanya, sehingga (a) teks bertanda
// kutip merusak kolom, (b) Excel dengan locale ID salah membaca pemisah koma, (c) huruf
// beraksen/rupiah jadi mojibake tanpa BOM UTF-8.

const cell = (value) => {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
};

/** Bangun teks CSV (pemisah `;` — default Excel locale Indonesia). */
export function toCsv(columns, rows, sep = ";") {
  const head = columns.map((c) => cell(c.header)).join(sep);
  const body = (rows || []).map((row) => columns.map((c) => {
    const raw = c.exportValue ? c.exportValue(row) : row[c.key];
    return cell(raw);
  }).join(sep)).join("\r\n");
  return `${head}\r\n${body}`;
}

/** Unduh CSV. Nama berkas selalu bertanggal agar tidak saling menimpa di folder unduhan. */
export function downloadCsv(columns, rows, name = "data") {
  const csv = toCsv(columns, rows);
  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${name}-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return csv.length;
}
