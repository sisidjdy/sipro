import React, { useState } from "react";
import { AlertTriangle, CheckCircle2, CircleSlash, PencilLine, PlusCircle, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import { DATAMGMT } from "@/constants/testIds";

const ACTION = {
  insert: { label: "Baru", cls: "bg-emerald-50 text-emerald-800", Icon: PlusCircle },
  update: { label: "Perbarui", cls: "bg-sky-50 text-sky-800", Icon: PencilLine },
  skip: { label: "Lewati", cls: "bg-secondary text-muted-foreground", Icon: CircleSlash },
  error: { label: "Error", cls: "bg-rose-50 text-rose-800", Icon: XCircle },
};

/** Hasil pratinjau/impor per sheet, baris bermasalah ditampilkan paling atas. */
export default function ImportReport({ report }) {
  if (!report) {
    return (
      <div className="rounded-xl border border-dashed bg-card/50 p-8 text-center text-sm text-muted-foreground h-full flex items-center justify-center">
        Hasil validasi akan tampil di sini setelah Anda menekan "Pratinjau".
      </div>
    );
  }
  const t = report.totals;
  const cards = [
    ["Baris", t.rows, "text-foreground"], ["Baru", t.insert, "text-emerald-700"],
    ["Perbarui", t.update, "text-sky-700"], ["Lewati", t.skip, "text-muted-foreground"],
    ["Error", t.error, t.error ? "text-rose-700" : "text-muted-foreground"],
    ["Peringatan", t.warning, t.warning ? "text-amber-700" : "text-muted-foreground"],
  ];
  return (
    <div data-testid={DATAMGMT.report} className="space-y-4">
      <div className="rounded-xl border bg-card p-5 shadow-[var(--shadow-card)]">
        <div className="flex items-center gap-2 mb-3">
          {report.dry_run
            ? <span className="text-xs font-semibold uppercase tracking-wide text-amber-700 bg-amber-50 px-2 py-0.5 rounded">Pratinjau — belum ditulis</span>
            : <span className="text-xs font-semibold uppercase tracking-wide text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded inline-flex items-center gap-1"><CheckCircle2 className="h-3 w-3" /> Impor selesai</span>}
          <span className="text-xs text-muted-foreground truncate">{report.filename} · mode {report.mode}</span>
        </div>
        <div data-testid={DATAMGMT.reportTotals} className="grid grid-cols-3 sm:grid-cols-6 gap-3">
          {cards.map(([l, v, c]) => (
            <div key={l}><p className="text-[11px] uppercase text-muted-foreground">{l}</p>
              <p className={cn("text-xl font-semibold tabular-nums", c)}>{v}</p></div>
          ))}
        </div>
        {report.unknown_sheets?.length ? (
          <p className="mt-3 text-xs text-amber-700 flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" /> Sheet diabaikan (tidak dikenal): {report.unknown_sheets.join(", ")}
          </p>
        ) : null}
      </div>
      {report.entities.map((e) => <EntityReport key={e.key} entity={e} />)}
    </div>
  );
}

function EntityReport({ entity: e }) {
  const [showAll, setShowAll] = useState(false);
  const rows = [...e.rows].sort((a, b) => (b.errors.length + b.warnings.length) - (a.errors.length + a.warnings.length));
  const visible = showAll ? rows : rows.slice(0, 8);
  return (
    <div data-testid={`${DATAMGMT.reportEntity}-${e.key}`} className="rounded-xl border bg-card overflow-hidden shadow-[var(--shadow-card)]">
      <div className="flex items-center justify-between px-4 py-2.5 border-b">
        <h4 className="font-semibold text-sm">{e.sheet} <span className="text-muted-foreground font-normal">· {e.total} baris</span></h4>
        <div className="flex gap-1.5 text-[11px]">
          {e.insert ? <Chip a="insert" n={e.insert} /> : null}
          {e.update ? <Chip a="update" n={e.update} /> : null}
          {e.skip ? <Chip a="skip" n={e.skip} /> : null}
          {e.error ? <Chip a="error" n={e.error} /> : null}
          {e.warning ? <span className="rounded px-1.5 py-0.5 bg-amber-50 text-amber-800">{e.warning} peringatan</span> : null}
        </div>
      </div>
      <ul className="divide-y text-sm">
        {visible.map((r) => {
          const A = ACTION[r.action] || ACTION.error;
          return (
            <li key={r.row} data-testid={`${DATAMGMT.reportRow}-${e.key}-${r.row}`} className="px-4 py-2 flex gap-3">
              <span className="w-14 shrink-0 text-xs text-muted-foreground tabular-nums pt-0.5">baris {r.row}</span>
              <span className={cn("shrink-0 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] h-5", A.cls)}>
                <A.Icon className="h-3 w-3" /> {A.label}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-xs">{r.key || "—"}</p>
                {r.errors.map((m, i) => <p key={`e${i}`} className="text-xs text-rose-700">{m}</p>)}
                {r.warnings.map((m, i) => <p key={`w${i}`} className="text-xs text-amber-700">{m}</p>)}
              </div>
            </li>
          );
        })}
      </ul>
      {rows.length > 8 ? (
        <button type="button" className="w-full py-2 text-xs text-primary hover:bg-accent/40"
          onClick={() => setShowAll((s) => !s)}>
          {showAll ? "Sembunyikan" : `Tampilkan semua ${rows.length} baris`}
        </button>
      ) : null}
    </div>
  );
}

function Chip({ a, n }) {
  const A = ACTION[a];
  return <span className={cn("rounded px-1.5 py-0.5", A.cls)}>{n} {A.label.toLowerCase()}</span>;
}
