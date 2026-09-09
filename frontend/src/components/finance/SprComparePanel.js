import React, { useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle, FileSearch } from "lucide-react";

import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";

const TONE = {
  cocok: "border-emerald-200 bg-emerald-50 text-emerald-900",
  beda: "border-rose-200 bg-rose-50 text-rose-900",
  beda_sudah_ttd: "border-rose-300 bg-rose-100 text-rose-950",
  belum_terbit: "border-slate-200 bg-slate-50 text-slate-800",
  tanpa_kontrak: "border-slate-200 bg-slate-50 text-slate-700",
};

function Cell({ row, side }) {
  const v = row[side];
  if (row.kind === "count") return <span className="tabular-nums">{v ?? "—"}×</span>;
  const due = row[`${side}_due`];
  return (
    <span className="tabular-nums">
      {v === null || v === undefined ? "—" : formatIDR(v)}
      {due ? <span className="block text-[10px] text-muted-foreground">{due}</span> : null}
    </span>
  );
}

/** SPR vs Tagihan Finance — baris per baris, dibaca SEBELUM SPR ditandatangani.
 *  `url` bisa dialihkan ke `/contracts/{id}/spr-compare` (Sales tanpa akses Finance);
 *  `compact` hanya menampilkan verdict + baris yang BEDA (tabel penuh bisa dibuka). */
export default function SprComparePanel({ dealId, url, refreshKey, compact = false, title = "SPR vs Tagihan Finance" }) {
  const [cmp, setCmp] = useState(null);
  const [state, setState] = useState("loading");
  const [showAll, setShowAll] = useState(false);
  const endpoint = url || (dealId ? `/finance/ar/${dealId}/spr-compare` : null);

  useEffect(() => {
    if (!endpoint) return undefined;
    let hidup = true;
    setState("loading");
    api.get(endpoint)
      .then((res) => { if (hidup) { setCmp(res.data.data); setState("ok"); } })
      .catch(() => { if (hidup) setState("gagal"); });
    return () => { hidup = false; };
  }, [endpoint, refreshKey]);

  if (state === "loading") return <LoadingCards count={1} />;
  if (state === "gagal" || !cmp) return <p className="text-xs text-muted-foreground">Perbandingan SPR tidak bisa dimuat.</p>;

  const doc = cmp.document;
  const Icon = cmp.all_match ? CheckCircle2 : cmp.state === "cocok" ? CheckCircle2 : cmp.rows.length ? AlertTriangle : FileSearch;
  const visibleRows = compact && !showAll ? cmp.rows.filter((r) => !r.match) : cmp.rows;
  return (
    <section data-testid="spr-compare-panel" data-state={cmp.state} className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-heading text-sm font-semibold">{title}</h4>
        {doc ? (
          <span data-testid="spr-compare-doc" className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            {doc.is_addendum ? <span className="rounded-full bg-indigo-50 px-1.5 text-[10px] text-indigo-800">Adendum dari {doc.parent_doc_number}</span> : null}
            <span className="font-mono">{doc.doc_number}</span>
            <StatusPill status={doc.status} group="document_status" />
          </span>
        ) : null}
      </div>
      <div data-testid="spr-compare-verdict" className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-xs ${TONE[cmp.state] || TONE.belum_terbit}`}>
        <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <div>
          <p className="font-medium">{cmp.verdict || cmp.reason}</p>
          {cmp.provisional?.length ? (
            <p data-testid="spr-compare-provisional" className="mt-0.5 opacity-80">
              Total SPR masih sementara: {cmp.provisional.join(", ")} belum ditetapkan & belum ditagih.
            </p>
          ) : null}
          {doc && !doc.has_snapshot ? (
            <p className="mt-0.5 opacity-80">SPR ini terbit sebelum pembanding ada — kolom SPR dihitung ulang dari kontrak saat ini.</p>
          ) : null}
          {cmp.older_documents ? <p className="mt-0.5 opacity-80">{cmp.older_documents} SPR lebih lama diabaikan (hanya yang terbaru dibandingkan).</p> : null}
        </div>
      </div>
      {cmp.rows.length && (visibleRows.length || !compact) ? (
        <div className="overflow-hidden rounded-lg border bg-card shadow-[var(--shadow-card)]">
          <table className="w-full text-xs">
            <thead className="bg-muted/60 text-[10px] uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-2.5 py-1.5 text-left">Baris</th>
                <th className="px-2.5 py-1.5 text-right">SPR</th>
                <th className="px-2.5 py-1.5 text-right">Finance</th>
                <th className="px-2 py-1.5 text-center">≡</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((r) => (
                <tr key={r.key} data-testid="spr-compare-row" data-key={r.key} data-match={r.match ? "1" : "0"}
                  className={`border-t ${r.match ? "" : "bg-rose-50/70"} ${/^(terms_total|total_bill|costs_total)$/.test(r.key) ? "font-semibold" : ""}`}>
                  <td className="px-2.5 py-1.5">
                    {r.label}
                    {r.note ? <span className="block text-[10px] font-normal text-muted-foreground">{r.note}</span> : null}
                  </td>
                  <td className="px-2.5 py-1.5 text-right"><Cell row={r} side="spr" /></td>
                  <td className="px-2.5 py-1.5 text-right"><Cell row={r} side="finance" /></td>
                  <td className="px-2 py-1.5 text-center">
                    {r.match
                      ? <CheckCircle2 className="inline h-3.5 w-3.5 text-emerald-600" />
                      : <AlertTriangle className="inline h-3.5 w-3.5 text-rose-600" />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {compact && cmp.rows.length ? (
        <button type="button" data-testid="spr-compare-toggle" onClick={() => setShowAll((v) => !v)}
          className="text-[11px] font-medium text-primary underline-offset-2 hover:underline">
          {showAll ? "Sembunyikan tabel lengkap" : `Lihat semua ${cmp.rows.length} baris perbandingan`}
        </button>
      ) : null}
    </section>
  );
}
