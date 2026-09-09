// Token warna peta (BUKAN label). Label enum selalu diambil dari SSOT /api/reference
// lewat useReference().labelOf agar tidak ada duplikasi vocabulary di frontend.

// Mode 1 — siklus penjualan: kunci = status unit, ditimpa tahap legal bila ada.
export const SALES_COLORS = {
  available: { fill: "#d1fae5", stroke: "#059669", dot: "#10b981", text: "#064e3b" },
  reserved: { fill: "#fef3c7", stroke: "#d97706", dot: "#f59e0b", text: "#78350f" },
  booked: { fill: "#e0e7ff", stroke: "#4f46e5", dot: "#6366f1", text: "#312e81" },
  ppjb: { fill: "#ede9fe", stroke: "#7c3aed", dot: "#8b5cf6", text: "#4c1d95" },
  akad: { fill: "#cffafe", stroke: "#0891b2", dot: "#06b6d4", text: "#164e63" },
  sold: { fill: "#e2e8f0", stroke: "#475569", dot: "#64748b", text: "#0f172a" },
};
export const SALES_ORDER = ["available", "reserved", "booked", "ppjb", "akad", "sold"];

// Mode 2 — progres pembangunan: gradasi 6 tingkat berbasis persentase per UNIT.
export const BUILD_BUCKETS = [
  { key: "b0", label: "Belum mulai", min: 0, max: 0, fill: "#f1f5f9", stroke: "#94a3b8", dot: "#94a3b8", text: "#334155" },
  { key: "b25", label: "1–25% (pondasi)", min: 1, max: 25, fill: "#fee2e2", stroke: "#dc2626", dot: "#ef4444", text: "#7f1d1d" },
  { key: "b50", label: "26–50% (struktur)", min: 26, max: 50, fill: "#fed7aa", stroke: "#ea580c", dot: "#f97316", text: "#7c2d12" },
  { key: "b75", label: "51–75% (arsitektur)", min: 51, max: 75, fill: "#fef08a", stroke: "#ca8a04", dot: "#eab308", text: "#713f12" },
  { key: "b99", label: "76–99% (finishing)", min: 76, max: 99, fill: "#bbf7d0", stroke: "#16a34a", dot: "#22c55e", text: "#14532d" },
  { key: "b100", label: "100% (siap serah terima)", min: 100, max: 100, fill: "#99f6e4", stroke: "#0d9488", dot: "#14b8a6", text: "#134e4a" },
];

// Mode 3 — heatmap HARGA: 5 pita kuantil (bukan lebar sama) supaya sebaran harga yang
// miring tetap terbaca; ambangnya dihitung dari data proyek aktif, bukan angka tetap.
export const PRICE_RAMP = [
  { key: "p1", fill: "#e0f2fe", stroke: "#0284c7", dot: "#38bdf8", text: "#0c4a6e" },
  { key: "p2", fill: "#c7e9fb", stroke: "#0369a1", dot: "#0ea5e9", text: "#0c4a6e" },
  { key: "p3", fill: "#bfdbfe", stroke: "#2563eb", dot: "#3b82f6", text: "#1e3a8a" },
  { key: "p4", fill: "#c7d2fe", stroke: "#4338ca", dot: "#6366f1", text: "#312e81" },
  { key: "p5", fill: "#ddd6fe", stroke: "#6d28d9", dot: "#8b5cf6", text: "#4c1d95" },
];

// Mode 4 — heatmap LAMA TAK TERJUAL (days on market): makin merah = makin lama menganggur.
export const DOM_BUCKETS = [
  { key: "m0", label: "Sudah laku (tidak dipasarkan)", fill: "#e2e8f0", stroke: "#475569", dot: "#64748b", text: "#0f172a" },
  { key: "m30", label: "≤ 30 hari", fill: "#dcfce7", stroke: "#16a34a", dot: "#22c55e", text: "#14532d" },
  { key: "m60", label: "31–60 hari", fill: "#fef9c3", stroke: "#ca8a04", dot: "#eab308", text: "#713f12" },
  { key: "m90", label: "61–90 hari", fill: "#fed7aa", stroke: "#ea580c", dot: "#f97316", text: "#7c2d12" },
  { key: "m180", label: "91–180 hari", fill: "#fecaca", stroke: "#dc2626", dot: "#ef4444", text: "#7f1d1d" },
  { key: "m999", label: "> 180 hari (perlu perhatian)", fill: "#fca5a5", stroke: "#991b1b", dot: "#b91c1c", text: "#450a0a" },
];
const DOM_EDGES = [30, 60, 90, 180];

// Warna konteks peta (jalan, taman, air, fasilitas) — statis, meniru site plan cetak.
export const KIND_STYLE = {
  boundary: { fill: "#f7fbf7", stroke: "#cbd5c0", width: 2, dash: "10 6" },
  road: { fill: "#eef1f4", stroke: "#d6dbe1", width: 1.5 },
  green: { fill: "#dcf0d7", stroke: "#a7cf9c", width: 1 },
  water: { fill: "#cfe8f7", stroke: "#8ec6e6", width: 1 },
  facility: { fill: "#e8e2f7", stroke: "#b7a7e0", width: 1 },
};

export const MODES = ["sales", "build", "price", "dom"];

/** Format rupiah ringkas untuk label legenda (mis. "Rp 1,2 M", "Rp 685 jt"). */
export function shortIDR(n) {
  const v = Number(n) || 0;
  if (v >= 1_000_000_000) {
    const m = v / 1_000_000_000;
    return `Rp ${(Math.round(m * 10) / 10).toLocaleString("id-ID")} M`;
  }
  if (v >= 1_000_000) return `Rp ${Math.round(v / 1_000_000).toLocaleString("id-ID")} jt`;
  return `Rp ${v.toLocaleString("id-ID")}`;
}

export function salesKey(unit) {
  const stage = String(unit?.legal_stage || "").toLowerCase();
  if (unit?.status === "sold") return "sold";
  if (stage.includes("ajb") || stage.includes("akad")) return "akad";
  if (stage.includes("ppjb")) return "ppjb";
  return SALES_COLORS[unit?.status] ? unit.status : "available";
}

export function buildBucket(unit) {
  const p = Math.max(0, Math.min(100, Number(unit?.construction_progress || 0)));
  return BUILD_BUCKETS.find((b) => p >= b.min && p <= b.max) || BUILD_BUCKETS[0];
}

/**
 * Skala heatmap yang dihitung SEKALI dari kumpulan kavling proyek aktif.
 * Dipakai bersama oleh peta, legenda, dan kartu ringkas supaya warna & label
 * tidak pernah berbeda antar komponen.
 */
export function makeScales(units = []) {
  const prices = units.map((u) => Number(u?.price) || 0).filter((v) => v > 0).sort((a, b) => a - b);
  const uniq = [...new Set(prices)];
  let bands = [];
  if (uniq.length && uniq.length <= PRICE_RAMP.length) {
    bands = uniq.map((v, i) => ({ key: `p${i + 1}`, lo: v, hi: v, exact: true }));
  } else if (uniq.length) {
    // Ambang kuantil dengan DUPLIKAT DIBUANG: bila banyak kavling berharga sama,
    // kuantil bisa menghasilkan pita kembar (mis. "Rp 850 jt – Rp 850 jt" berisi 0).
    const edges = [];
    for (let i = 1; i < PRICE_RAMP.length; i += 1) {
      const v = prices[Math.floor((i / PRICE_RAMP.length) * (prices.length - 1))];
      if (!edges.includes(v) && v < prices[prices.length - 1]) edges.push(v);
    }
    let lo = prices[0];
    edges.forEach((e, i) => { bands.push({ key: `p${i + 1}`, lo, hi: e }); lo = e; });
    bands.push({ key: `p${bands.length + 1}`, lo, hi: prices[prices.length - 1] });
  }
  return {
    price: { min: prices[0] || 0, max: prices[prices.length - 1] || 0, bands, n: prices.length },
  };
}

function priceIndex(unit, scales) {
  const bands = scales?.price?.bands || [];
  const v = Number(unit?.price) || 0;
  if (!bands.length || !v) return 0;
  const i = bands.findIndex((b) => v <= b.hi);
  return i === -1 ? bands.length - 1 : i;
}

export function priceBucket(unit, scales) {
  const bands = scales?.price?.bands || [];
  const i = priceIndex(unit, scales);
  const ramp = PRICE_RAMP[Math.min(i, PRICE_RAMP.length - 1)];
  return { ...ramp, key: bands[i]?.key || ramp.key };
}

export function domBucket(unit) {
  if (unit?.dom_open === false) return DOM_BUCKETS[0];
  const d = unit?.days_on_market;
  if (d === null || d === undefined) return DOM_BUCKETS[1];
  let i = 0;
  while (i < DOM_EDGES.length && Number(d) > DOM_EDGES[i]) i += 1;
  return DOM_BUCKETS[i + 1] || DOM_BUCKETS[DOM_BUCKETS.length - 1];
}

/** Warna satu kavling sesuai mode aktif. */
export function unitStyle(unit, mode, scales) {
  if (mode === "build") {
    const b = buildBucket(unit);
    return { fill: b.fill, stroke: b.stroke, text: b.text, key: b.key };
  }
  if (mode === "price") {
    const b = priceBucket(unit, scales);
    return { fill: b.fill, stroke: b.stroke, text: b.text, key: b.key };
  }
  if (mode === "dom") {
    const b = domBucket(unit);
    return { fill: b.fill, stroke: b.stroke, text: b.text, key: b.key };
  }
  const key = salesKey(unit);
  return { ...SALES_COLORS[key], key };
}

/** Kunci kategori kavling pada mode aktif (dipakai filter "sorot legenda"). */
export function unitKey(unit, mode, scales) {
  if (mode === "build") return buildBucket(unit).key;
  if (mode === "price") return priceBucket(unit, scales).key;
  if (mode === "dom") return domBucket(unit).key;
  return salesKey(unit);
}

function priceLegend(units, scales) {
  const bands = scales?.price?.bands || [];
  if (!bands.length) {
    return [{ key: "p1", dot: PRICE_RAMP[0].dot, label: "Belum ada harga", count: units.length }];
  }
  return bands.map((b, i) => {
    const ramp = PRICE_RAMP[Math.min(i, PRICE_RAMP.length - 1)];
    const label = b.exact ? shortIDR(b.hi)
      : i === 0 ? `≤ ${shortIDR(b.hi)}`
        : i === bands.length - 1 ? `> ${shortIDR(b.lo)}`
          : `${shortIDR(b.lo)} – ${shortIDR(b.hi)}`;
    return { key: b.key, dot: ramp.dot, label,
      count: units.filter((u) => priceBucket(u, scales).key === b.key).length };
  });
}

/** Definisi legenda + jumlah kavling per kategori untuk mode aktif. */
export function legendFor(mode, units, labelOf, scales) {
  if (mode === "build") {
    return BUILD_BUCKETS.map((b) => ({
      key: b.key, label: b.label, dot: b.dot,
      count: units.filter((u) => buildBucket(u).key === b.key).length,
    }));
  }
  if (mode === "price") return priceLegend(units, scales);
  if (mode === "dom") {
    return DOM_BUCKETS.map((b) => ({
      key: b.key, label: b.label, dot: b.dot,
      count: units.filter((u) => domBucket(u).key === b.key).length,
    }));
  }
  // Label diambil dari SSOT; bila grup tidak mengenal nilainya (labelOf memantulkan
  // nilai mentah), dipakai teks Indonesia yang jelas agar UI tidak pernah menampilkan
  // nilai teknis seperti "ppjb_signed".
  const ssot = (group, value, fallback) => {
    const l = labelOf(group, value);
    return !l || l === "-" || l === value ? fallback : l;
  };
  return SALES_ORDER.map((k) => ({
    key: k, dot: SALES_COLORS[k].dot,
    label: k === "ppjb" ? ssot("legal_stage", "ppjb_signed", "PPJB ditandatangani")
      : k === "akad" ? ssot("legal_stage", "ajb_signed", "Akad / AJB")
        : ssot("unit_status", k, k),
    count: units.filter((u) => salesKey(u) === k).length,
  }));
}
