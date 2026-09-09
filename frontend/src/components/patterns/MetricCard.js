import React, { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { formatIDR } from "@/utils/formatters";
import { HOME } from "@/constants/testIds";

const TONE = {
  primary: "text-primary", amber: "text-amber-600", rose: "text-rose-600",
  indigo: "text-indigo-600", emerald: "text-emerald-600", muted: "text-muted-foreground",
  violet: "text-violet-600", sky: "text-sky-700", slate: "text-slate-700",
};
const DOT = {
  primary: "bg-primary", amber: "bg-amber-500", rose: "bg-rose-500",
  indigo: "bg-indigo-500", emerald: "bg-emerald-500", muted: "bg-slate-400",
  violet: "bg-violet-500", sky: "bg-sky-500", slate: "bg-slate-400",
};
const SIZES = ["text-2xl", "text-xl", "text-lg", "text-base", "text-sm", "text-xs"];

/**
 * Perkecil huruf angka SAMPAI MUAT di kartunya — jangan pernah memotong atau melipat angka.
 *
 * Cacat nyata yang ditutup (terlihat di layar Keuangan): "Rp 680.000.000" pada kartu grid
 * 6 kolom hanya punya ~115 px, sehingga angkanya meluber keluar bingkai lalu — setelah
 * dipaksa membungkus — pecah menjadi "Rp 680.000.00" + "0" di baris berikutnya. Pembaca
 * bisa salah membaca nilai uang, dan kartunya terlihat rusak.
 *
 * Cara kerja: ukur lebar isi vs lebar kartu, turunkan satu tingkat ukuran huruf, ulangi
 * sampai muat (paling kecil `text-xs`). Saat kartunya berubah lebar (putar layar / ubah
 * ukuran jendela) ukuran dihitung ulang dari awal supaya tidak selamanya kecil.
 */
function useFitText(text, startIdx = 0) {
  const ref = useRef(null);
  const lastWidth = useRef(0);
  const [idx, setIdx] = useState(startIdx);

  useEffect(() => { setIdx(startIdx); }, [text, startIdx]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    if (el.scrollWidth > el.clientWidth + 1 && idx < SIZES.length - 1) {
      setIdx((i) => Math.min(i + 1, SIZES.length - 1));
      return undefined;
    }
    lastWidth.current = el.clientWidth;
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth;
      if (Math.abs(w - lastWidth.current) > 4) {
        lastWidth.current = w;
        setIdx(startIdx);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [idx, text, startIdx]);

  return [ref, SIZES[idx]];
}

/**
 * KARTU ANGKA — satu-satunya bentuk kartu KPI di seluruh aplikasi.
 *
 * Sebelumnya hampir setiap halaman menulis kartu angkanya sendiri (9 salinan
 * `function Metric`) dengan ukuran huruf, padding, dan ukuran label berbeda-beda: itulah
 * sumber keluhan "font tidak konsisten" dan "kartu terlihat rusak" antar halaman. Sekarang
 * semuanya memakai komponen ini — satu tipografi, satu jarak, satu perilaku saat teks
 * panjang, dan label/keterangan panjang tetap terbaca (dua baris + tooltip).
 *
 * `tone` boleh nama nada (primary/amber/rose/…) ATAU kelas warna teks langsung
 * (mis. "text-rose-700") supaya halaman lama ikut tanpa mengubah maknanya.
 */
export default function MetricCard({
  label, value, tone = "primary", hint, hintTone, format, testId = HOME.metricCard,
  dot = true, icon: Icon, compact = false, className,
}) {
  const display = format === "idr" ? formatIDR(value) : value;
  const text = String(display ?? "");
  const [valueRef, valueSize] = useFitText(text, compact ? 3 : 0);
  const custom = typeof tone === "string" && tone.startsWith("text-");
  const valueTone = custom ? tone : (TONE[tone] || TONE.primary);
  const dotTone = custom
    ? tone.replace("text-", "bg-").replace(/-(\d00)$/, "-500")
    : (DOT[tone] || DOT.primary);
  return (
    <div data-testid={testId}
      className={cn("min-w-0 rounded-xl border bg-card shadow-sm transition-shadow",
        compact ? "p-2.5" : "p-3.5 hover:shadow-md", className)}>
      <div className="flex items-center gap-1.5">
        {Icon ? <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          : (dot ? <span className={cn("h-2 w-2 shrink-0 rounded-full", dotTone)} /> : null)}
        <p data-testid="metric-card-label" title={typeof label === "string" ? label : undefined}
          className="clamp-2 text-xs font-medium leading-snug text-muted-foreground">
          {label}
        </p>
      </div>
      <p ref={valueRef} data-testid="metric-card-value" title={text}
        className={cn("mt-1.5 truncate font-heading font-semibold leading-tight tabular-nums",
          valueSize, valueTone)}>
        {display}
      </p>
      {hint ? (
        <p title={typeof hint === "string" ? hint : undefined}
          className={cn("clamp-2 mt-1 text-[11px] leading-snug",
            hintTone || "text-muted-foreground")}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}
