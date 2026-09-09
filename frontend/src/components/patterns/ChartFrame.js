import React from "react";
import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/patterns/StateViews";
import { downloadCsv } from "@/utils/tableCsv";
import { cn } from "@/lib/utils";
import { CHART } from "@/constants/testIds";

/**
 * ChartFrame — bingkai standar grafik: judul, keterangan, state kosong/galat yang jujur,
 * dan unduh data mentahnya.
 *
 * Kenapa unduh data: grafik tanpa akses ke angkanya memaksa pemakai “membaca” piksel.
 * Kolom unduhan dideskripsikan pemanggil (`csvColumns`) agar isinya sama dengan yang dilihat.
 */
export default function ChartFrame({
  title, description, children, rows = [], csvColumns = null, csvName = "grafik",
  loading = false, error = "", onRetry, emptyText = "Belum ada data untuk digambarkan.",
  className, testId, actions = null, height = "h-72",
}) {
  const isEmpty = !loading && !error && (!rows || rows.length === 0);
  // CACAT NYATA yang ditutup di sini (dilaporkan pemakai: "visualisasi data terlalu kecil,
  // tumpang tindih dengan cards"): `height` DULU hanya dipakai untuk kotak kerangka saat
  // memuat, sementara grafiknya dirender tanpa kotak bertinggi sama sekali. Grafik recharts
  // yang memakai `<ResponsiveContainer height="100%">` di dalam wadah tanpa tinggi akan
  // dihitung setinggi ~0 px: SVG-nya tergencet menjadi garis tipis dan bagian yang
  // diposisikan absolut (tooltip/legend) menumpuk kartu di sebelahnya. Sejak sekarang isi
  // grafik SELALU mendapat kotak bertinggi — kelas Tailwind (`"h-72"`) atau angka piksel.
  const isPx = typeof height === "number";
  const box = isPx ? undefined : height;
  return (
    <section data-testid={testId || CHART.frame}
      className={cn("rounded-lg border bg-card p-4", className)}>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2 sm:flex-nowrap">
        <div className="min-w-0">
          <h3 data-testid={CHART.title} className="section-title">
            {title}
          </h3>
          {description ? (
            <p className="text-xs text-muted-foreground">{description}</p>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {actions}
          {csvColumns && rows?.length ? (
            <Button size="sm" variant="outline" data-testid={CHART.download}
              onClick={() => downloadCsv(csvColumns, rows, csvName)}>
              <Download className="mr-1.5 h-3.5 w-3.5" /> Data
            </Button>
          ) : null}
        </div>
      </div>
      {error ? <ErrorState message={error} onRetry={onRetry} /> : null}
      {loading ? (
        <div className={cn("animate-pulse rounded-md bg-secondary", box)}
          style={isPx ? { height } : undefined} />
      ) : null}
      {isEmpty ? (
        <p data-testid={CHART.empty}
          className="rounded-md border border-dashed bg-secondary/40 p-6 text-center text-sm text-muted-foreground">
          {emptyText}
        </p>
      ) : null}
      {!loading && !error && !isEmpty ? (
        <div className={cn("w-full overflow-hidden", box)}
          style={isPx ? { height } : undefined}>
          {children}
        </div>
      ) : null}
    </section>
  );
}
