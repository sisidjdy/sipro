import { BUILD_BUCKETS, SALES_COLORS, SALES_ORDER, buildBucket, salesKey } from "@/components/siteplan/planStyles";

/**
 * Palet warna Studio — dua status paralel pada tiap rumah:
 *  • sales  = tahapan kepemilikan/customer (tersedia → booking → PPJB → akad → terjual → serah terima)
 *  • build  = tahapan pembangunan (0% … 100%) dari `construction_progress`
 * Bawaan diambil dari planStyles; override per organisasi disimpan di server (`/site-plan-studio/palette`).
 */
export const COLOR_MODES = [
  { key: "mapping", label: "Pemetaan", hint: "Kavling sudah/belum punya unit" },
  { key: "sales", label: "Status penjualan", hint: "Tahapan customer: tersedia, booking, PPJB, akad, terjual, serah terima" },
  { key: "build", label: "Progres pembangunan", hint: "Tahapan konstruksi dari 0% sampai siap serah terima" },
  { key: "dual", label: "Gabungan", hint: "Dua status sekaligus: warna isi penjualan, garis tebal progres bangun" },
];

/** Label tahap penjualan: dari Kamus Data `unit_status` (SSOT) bila ada; ppjb/akad adalah tahap kontrak khusus palet. */
export const salesLabel = (k, labelOf) => {
  const v = labelOf ? labelOf("unit_status", k) : null;
  if (v && v !== k && v !== "-") return v;
  if (k === "ppjb") return "PPJB";
  if (k === "akad") return "Akad";
  return k;
};

export function defaultPalette(labelOf) {
  return {
    sales: {
      ...Object.fromEntries(SALES_ORDER.map((k) => [k, { label: salesLabel(k, labelOf), fill: SALES_COLORS[k].fill, stroke: SALES_COLORS[k].stroke, text: SALES_COLORS[k].text }])),
      handed_over: { label: salesLabel("handed_over", labelOf), fill: "#ccfbf1", stroke: "#0f766e", text: "#134e4a" },
    },
    build: Object.fromEntries(BUILD_BUCKETS.map((b) => [b.key, { label: b.label, fill: b.fill, stroke: b.stroke, text: b.text }])),
    mapping: {
      mapped: { label: "Terpetakan", fill: "#bbf7d0", stroke: "#15803d", text: "#14532d" },
      unmapped: { label: "Belum terpetakan", fill: "#fff7ed", stroke: "#f59e0b", text: "#9a3412" },
      none: { label: "Tanpa unit", fill: "#f8fafc", stroke: "#94a3b8", text: "#64748b" },
    },
  };
}
export const DEFAULT_PALETTE = defaultPalette();
export const SALES_KEYS = [...SALES_ORDER, "handed_over"];
export const BUILD_KEYS = BUILD_BUCKETS.map((b) => b.key);

/** Gabungkan bawaan + override server (hanya kunci yang ada). `labelOf` = useReference().labelOf untuk label SSOT. */
export function mergePalette(override = {}, labelOf) {
  const base = defaultPalette(labelOf);
  const out = {};
  for (const g of Object.keys(base)) {
    out[g] = {};
    for (const k of Object.keys(base[g])) out[g][k] = { ...base[g][k], ...(override?.[g]?.[k] || {}) };
  }
  return out;
}

export function salesKeyOf(unit) {
  if (!unit) return null;
  if (unit.status === "handed_over") return "handed_over";
  return salesKey(unit);
}
export const buildKeyOf = (unit) => (unit ? buildBucket(unit).key : null);

/** Gaya kavling: { fill, stroke, text, strokeWidth, sub } menurut mode & palet. */
export function lotStyle(unit, mode, palette) {
  const P = palette || DEFAULT_PALETTE;
  if (mode === "mapping") return { ...(unit ? P.mapping.mapped : P.mapping.unmapped), strokeWidth: 1.4 };
  if (!unit) return { ...P.mapping.none, strokeWidth: 1.4, dash: "5 3" };
  const sales = P.sales[salesKeyOf(unit)] || P.sales.available;
  const build = P.build[buildKeyOf(unit)] || P.build.b0;
  if (mode === "sales") return { ...sales, strokeWidth: 1.4 };
  if (mode === "build") return { ...build, strokeWidth: 1.4, sub: `${Number(unit.construction_progress || 0)}%` };
  return { fill: sales.fill, text: sales.text, stroke: build.stroke, strokeWidth: 4, sub: `${Number(unit.construction_progress || 0)}%` };
}

/** Item legenda (dengan hitungan) untuk mode aktif. */
export function legendItems(mode, lots, unitsById, palette) {
  const P = palette || DEFAULT_PALETTE;
  const units = lots.map((s) => unitsById[s.unit_id]);
  const count = (fn) => units.filter(fn).length;
  const none = { key: "none", ...P.mapping.none, n: count((u) => !u) };
  if (mode === "mapping") {
    return [{ key: "mapped", ...P.mapping.mapped, n: count((u) => !!u) }, { key: "unmapped", ...P.mapping.unmapped, n: none.n }];
  }
  const sales = SALES_KEYS.map((k) => ({ key: k, ...P.sales[k], n: count((u) => u && salesKeyOf(u) === k) }))
    .filter((it) => it.n > 0 || it.key !== "handed_over");
  const build = BUILD_KEYS.map((k) => ({ key: k, ...P.build[k], n: count((u) => u && buildKeyOf(u) === k) }));
  if (mode === "sales") return [...sales, none];
  if (mode === "build") return [...build, none];
  return [{ group: "Penjualan (isi)", items: [...sales, none] }, { group: "Pembangunan (garis)", items: build, asStroke: true }];
}
