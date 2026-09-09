import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Database, Download, Sigma } from "lucide-react";

import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  MetricNote, MetricStateBadge, MetricValue, formatMetric,
} from "@/components/bi/MetricValue";
import { TrendDelta } from "@/components/bi/MetricSpark";
import MetricChart from "@/components/bi/MetricChart";
import { formatNumber } from "@/utils/formatters";
import { BI } from "@/constants/testIds";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

/**
 * MetricDetailDialog — rincian satu metrik yang benar-benar bisa DIPERIKSA, bukan sekadar
 * tabel mentah (keluhan pemakai: "detailnya dangkal, kurang informatif"). Isinya:
 * nilai + tren, grafik pecahan/deret, tabel dengan kontribusi % & total, bahan mentah
 * perhitungan (`inputs`), sumber datanya (`requires`), dan tautan ke daftar barisnya.
 * Ekspor CSV tetap mengambil dari server — bukan menyalin tampilan.
 */

// Nama kolom teknis diterjemahkan; kolom `key` (id internal) tidak layak tampil.
const COL_LABELS = { label: "Kategori", value: "Nilai", count: "Banyaknya", pct: "Persentase" };
const humanize = (k) => COL_LABELS[k]
  || k.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());

function InputsPanel({ inputs }) {
  const entries = Object.entries(inputs || {});
  if (!entries.length) return null;
  return (
    <div className="rounded-lg border p-3">
      <p className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">
        Bahan perhitungan
      </p>
      <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
        {entries.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2 border-b border-dashed py-1">
            <dt className="text-muted-foreground">{humanize(k)}</dt>
            <dd className="text-right font-medium tabular-nums">
              {typeof v === "number" ? formatNumber(v)
                : typeof v === "object" ? JSON.stringify(v) : String(v)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function SourcesPanel({ metric }) {
  const requires = metric.requires || [];
  const missing = metric.missing || [];
  if (!requires.length && !missing.length && !metric.coverage) return null;
  return (
    <div className="rounded-lg border p-3 text-xs">
      <p className="mb-1.5 flex items-center gap-1 font-semibold uppercase text-muted-foreground">
        <Database className="h-3 w-3" /> Sumber & cakupan data
      </p>
      {requires.length ? (
        <p className="text-muted-foreground">
          Dihitung dari koleksi:{" "}
          {requires.map((r) => (
            <code key={r} className="mr-1 rounded bg-secondary px-1 py-0.5">{r}</code>
          ))}
        </p>
      ) : null}
      {metric.coverage ? (
        <p className="mt-1 text-muted-foreground">
          Cakupan: <strong className="text-foreground">
            {formatNumber(metric.coverage.rows)} dari {formatNumber(metric.coverage.total)}
          </strong> baris punya data lengkap — sisanya tidak ikut dihitung, bukan dianggap 0.
        </p>
      ) : null}
      {missing.length ? (
        <ul className="mt-1 list-inside list-disc text-amber-700 dark:text-amber-400">
          {missing.map((m) => <li key={m}>{m}</li>)}
        </ul>
      ) : null}
    </div>
  );
}

export default function MetricDetailDialog({ metric, open, onOpenChange, range }) {
  const rows = useMemo(() => (metric?.breakdown || []), [metric]);
  // Kontribusi % hanya untuk satuan yang totalnya bermakna (jumlah/uang); untuk persen,
  // hari, atau rasio, menjumlah baris justru menghasilkan angka bohong.
  const additive = !["pct", "days", "hours", "ratio", "text"].includes(metric?.unit);
  const numericRows = rows.filter((r) => typeof r?.value === "number");
  const total = additive ? numericRows.reduce((s, r) => s + r.value, 0) : null;
  // Beberapa metrik memecah dirinya dalam SATUAN LAIN (mis. SLS-01 hitung unit, tapi
  // rinciannya harga rupiah per tipe). Menjumlahkan/mempersenkan pecahan seperti itu
  // menghasilkan "total" yang tidak ada hubungannya dengan angka utamanya — dideteksi dari
  // selisih orde besaran, lalu Kontribusi/Total disembunyikan.
  const unitMismatch = typeof metric?.value === "number" && metric.value !== 0
    && total !== null && total !== 0
    && (Math.abs(total / metric.value) > 100 || Math.abs(total / metric.value) < 0.01);
  const showShare = total !== null && total !== 0 && !unitMismatch;
  const showTotal = total !== null && !unitMismatch;
  const magnitude = (row) => (Number.isFinite(Number(row?.value)) ? Math.abs(Number(row.value)) : -1);
  const sorted = useMemo(() => [...rows].sort((a, b) => magnitude(b) - magnitude(a)), [rows]);
  const extraKeys = useMemo(() => Array.from(rows.reduce((set, row) => {
    Object.keys(row || {}).forEach((k) => {
      if (!["key", "label", "value"].includes(k)) set.add(k);
    });
    return set;
  }, new Set())), [rows]);

  if (!metric) return null;
  const exportUrl = `${BACKEND}/api/analytics/export/${encodeURIComponent(metric.code)}`
    + (range?.from ? `?date_from=${range.from}&date_to=${range.to}` : "");
  const hasSeries = (metric.series || []).length >= 2;
  const maxAbs = Math.max(...numericRows.map((r) => Math.abs(r.value)), 0) || 1;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={BI.detailDialog}
        className="max-h-[88vh] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            {metric.label}
            <span className="text-xs font-normal text-muted-foreground">{metric.code}</span>
            <MetricStateBadge state={metric.state} coverage={metric.coverage} />
          </DialogTitle>
          <DialogDescription>
            Rincian metrik dashboard {metric.persona ? `“${metric.persona}”` : ""}
            {range?.from ? ` · rentang ${range.from} → ${range.to}` : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-3 rounded-lg border bg-secondary/40 p-3">
            <div className="space-y-1">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                Nilai pada rentang ini
              </p>
              <div className="flex flex-wrap items-baseline gap-2">
                <MetricValue metric={metric} className="text-3xl" />
                <TrendDelta series={metric.series} unit={metric.unit} />
              </div>
              {metric.formula ? (
                <p className="flex items-start gap-1 text-xs text-muted-foreground">
                  <Sigma className="mt-0.5 h-3 w-3 shrink-0" />
                  <span>{metric.formula.replace(/^Σ\s*/u, "")}</span>
                </p>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              {metric.drill ? (
                <Button size="sm" variant="secondary" asChild data-testid={BI.detailDrill}>
                  <Link to={metric.drill} onClick={() => onOpenChange?.(false)}>
                    Buka daftar barisnya <ArrowUpRight className="ml-1 h-3.5 w-3.5" />
                  </Link>
                </Button>
              ) : null}
              <Button size="sm" variant="outline" asChild data-testid={BI.detailExport}>
                <a href={exportUrl} target="_blank" rel="noreferrer">
                  <Download className="mr-1.5 h-3.5 w-3.5" /> Ekspor CSV
                </a>
              </Button>
            </div>
          </div>
          <MetricNote metric={metric} />

          {hasSeries ? (
            <MetricChart metric={metric} kind="series" height={240}
              title="Pergerakan pada rentang ini"
              description="Deret waktu yang sama dengan sparkline di kartunya." />
          ) : null}
          {rows.length >= 2 ? (
            // `kind="bar"` EKSPLISIT (bukan "auto"): "auto" memilih deret waktu bila metrik
            // punya series, sehingga judul "Pecahan per kategori" pernah menggambar grafik
            // deret satu titik (temuan uji LED-01/USR-01).
            <MetricChart metric={metric}
              kind={rows.length <= 6 && showShare ? "pie" : "bar"}
              title="Pecahan per kategori"
              description={showShare
                ? "Irisan/bar dihitung dari nilai tiap kategori terhadap totalnya."
                : "Tiap kategori berdiri sendiri — satuannya tidak bisa dijumlahkan."} />
          ) : null}

          {rows.length ? (
            <div data-testid={BI.detailTable}
              className="overflow-x-auto rounded-lg border bg-card shadow-[var(--shadow-card)]">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 text-left">Kategori</th>
                    <th className="px-3 py-2 text-right">Nilai</th>
                    {extraKeys.map((k) => (
                      <th key={k} className="px-3 py-2 text-right">{humanize(k)}</th>
                    ))}
                    {showShare ? <th className="w-[34%] px-3 py-2 text-left">Kontribusi</th> : null}
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((row, i) => {
                    const v = row?.value;
                    const share = showShare && typeof v === "number" ? (v / total) * 100 : null;
                    return (
                      <tr key={row.key || i} data-testid={BI.detailRow} className="border-t">
                        <td className="px-3 py-2">{row.label}</td>
                        <td className="px-3 py-2 text-right font-medium tabular-nums">
                          {v === null || v === undefined ? (
                            <span className="text-xs italic text-muted-foreground">
                              belum ada data
                            </span>
                          ) : formatMetric(v, metric.unit)}
                        </td>
                        {extraKeys.map((k) => (
                          <td key={k} className="px-3 py-2 text-right tabular-nums">
                            {row[k] === null || row[k] === undefined ? (
                              <span className="text-xs italic text-muted-foreground">
                                belum ada data
                              </span>
                            ) : typeof row[k] === "number" ? formatNumber(row[k])
                              : typeof row[k] === "object" ? JSON.stringify(row[k])
                                : String(row[k])}
                          </td>
                        ))}
                        {showShare ? (
                          <td className="px-3 py-2">
                            {share === null ? null : (
                              <span className="flex items-center gap-2">
                                <span className="h-1.5 w-full max-w-[9rem] overflow-hidden rounded-full bg-secondary">
                                  <span className="block h-full rounded-full bg-[hsl(var(--chart-1))]"
                                    style={{ width: `${(Math.abs(v) / maxAbs) * 100}%` }} />
                                </span>
                                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                                  {formatNumber(Math.round(share * 10) / 10)}%
                                </span>
                              </span>
                            )}
                          </td>
                        ) : null}
                      </tr>
                    );
                  })}
                </tbody>
                {showTotal ? (
                  <tfoot>
                    <tr className="border-t bg-muted/30 font-medium">
                      <td className="px-3 py-2">Total</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {formatMetric(total, metric.unit)}
                      </td>
                      {extraKeys.map((k) => <td key={k} />)}
                      {showShare ? <td className="px-3 py-2 text-xs text-muted-foreground">100%</td> : null}
                    </tr>
                  </tfoot>
                ) : null}
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Metrik ini belum punya rincian untuk ditampilkan.
            </p>
          )}

          <div className="grid gap-3 md:grid-cols-2">
            <InputsPanel inputs={metric.inputs} />
            <SourcesPanel metric={metric} />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
