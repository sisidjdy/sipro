import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowUpRight, ChevronRight, Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import { downloadCsv } from "@/utils/tableCsv";
import api from "@/services/apiClient";
import { P91, P93 } from "@/constants/testIds";

// Kolom CSV = persis yang terlihat di popup (judul, keterangan, status, nilai, skor, tautan).
const CSV_COLUMNS = [
  { key: "title", header: "Item" },
  { key: "subtitle", header: "Keterangan" },
  { key: "status", header: "Status" },
  { key: "amount", header: "Nilai" },
  { key: "score", header: "Skor" },
  { key: "href", header: "Tautan", exportValue: (r) => (r.href ? `${window.location.origin}${r.href}` : "") },
];

/**
 * DrilldownDialog — popup rincian SATU angka KPI (pola yang sama di Beranda, Lead,
 * Pembangunan, Keuangan). `target = { key, params, label }` → GET /drilldown/{key}.
 * Klik baris → navigasi ke `row.href`; tombol bawah → tabel terfilter (`href_all`).
 */
export default function DrilldownDialog({ target, onOpenChange, onRow }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!target) return;
    setData(null); setError("");
    api.get(`/drilldown/${target.key}`, { params: target.params || {} })
      .then((r) => setData(r.data.data))
      .catch((e) => setError(e?.response?.data?.detail || "Gagal memuat rincian."));
  }, [target]);

  const go = (href) => { onOpenChange(false); if (href) navigate(href); };
  const click = (r) => { if (onRow) { onOpenChange(false); onRow(r); } else go(r.href); };
  // Metrik non-uang (klik, impresi, lead platform) tidak boleh dirender sebagai rupiah.
  const fmt = (v, r) => ((r?.unit || data?.unit) === "count" ? Number(v || 0).toLocaleString("id-ID") : formatIDR(v));

  return (
    <Dialog open={!!target} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid={P91.kpiDialog}>
        <DialogHeader>
          <DialogTitle>{data?.title || target?.label || "Rincian"}</DialogTitle>
          <DialogDescription>
            {data ? <>{data.count} baris{data.total ? <> · total <b className="tabular-nums text-foreground">{fmt(data.total)}</b></> : null}</>
              : "Memuat baris penyusun angka ini…"}
          </DialogDescription>
        </DialogHeader>
        {error ? <ErrorState message={error} /> : null}
        {!data && !error ? <LoadingCards count={2} /> : null}
        {data ? (
          <div className="max-h-[55vh] space-y-1.5 overflow-y-auto pr-1">
            {!data.rows.length ? (
              <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground" data-testid={P91.kpiDialogEmpty}>
                Tidak ada baris — angka ini nol saat ini.
              </p>
            ) : data.rows.map((r) => (
              <button key={r.id} type="button" onClick={() => click(r)} data-testid={`${P91.kpiDialogRow}-${r.id}`}
                className="group flex w-full items-center gap-3 rounded-lg border bg-card px-3 py-2 text-left transition-colors hover:border-primary/40 hover:bg-accent/50 shadow-[var(--shadow-card)]">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{r.title}</p>
                  {r.subtitle ? <p className="truncate text-xs text-muted-foreground">{r.subtitle}</p> : null}
                </div>
                {r.score != null ? <StatusPill status={r.score_band} label={`${r.score}`} /> : null}
                {r.status ? <StatusPill status={r.status} group={r.status_group || undefined} /> : null}
                {r.amount != null ? <span className="w-36 shrink-0 text-right text-sm font-semibold tabular-nums">{fmt(r.amount, r)}</span> : null}
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
              </button>
            ))}
          </div>
        ) : null}
        {data?.href_all || data?.rows?.length ? (
          <div className="flex flex-wrap items-center justify-end gap-2">
            {data?.rows?.length ? (
              <Button size="sm" variant="outline" data-testid={P93.drillCsv}
                onClick={() => downloadCsv(CSV_COLUMNS, data.rows, `rincian-${(data.key || "kpi").replace(/[^a-z0-9_-]/gi, "-")}`)}>
                <Download className="mr-1 h-4 w-4" /> Unduh CSV
              </Button>
            ) : null}
            {data?.href_all ? (
              <Button size="sm" onClick={() => go(data.href_all)} data-testid={P91.kpiDialogAll}>
                Buka tabel terfilter <ArrowUpRight className="ml-1 h-4 w-4" />
              </Button>
            ) : null}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
