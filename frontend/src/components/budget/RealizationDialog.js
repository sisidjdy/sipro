import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";

import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import MetricCard from "@/components/patterns/MetricCard";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { HealthPill, MissingNote, Money, Pct } from "@/components/budget/parts";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { BUDGET } from "@/constants/testIds";

/**
 * RealizationDialog — **LAPIS 3** dari tiga lapis yang diminta owner: dari angka item
 * langsung ke DAFTAR DOKUMEN penyusunnya (PO, tagihan vendor, lingkup SPK, termin, jurnal,
 * kas bon, fee mitra, pencatatan manual).
 *
 * Bagian terpenting dialog ini bukan tabelnya, tetapi **baris pemeriksaan tie-out**: Σ dokumen
 * realisasi harus sama dengan realisasi item, dan Σ dokumen komitmen sama dengan komitmennya.
 * Kalau tidak sama, dialog ini MENGATAKANNYA — karena angka yang tidak bisa ditelusuri adalah
 * cacat, bukan sekadar tampilan yang kurang rapi.
 */
export default function RealizationDialog({ item, open, onOpenChange }) {
  const { labelOf } = useReference();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!item?.id) return;
    setLoading(true); setError("");
    try {
      const r = await api.get(`/budget/items/${item.id}/realization`);
      setData(r.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat rincian dokumen.");
    } finally { setLoading(false); }
  }, [item]);
  useEffect(() => { if (open) load(); }, [open, load]);

  const checks = data?.checks;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={BUDGET.drillDialog}
        className="max-h-[88vh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>
            Dokumen sumber — {item?.code} {item?.name ? `· ${item.name}` : ""}
          </DialogTitle>
          <DialogDescription>
            Setiap rupiah pada kartu &amp; tabel kategori berasal dari dokumen di bawah ini.
            Tidak ada angka tanpa asal.
          </DialogDescription>
        </DialogHeader>

        {loading ? <LoadingCards count={4} />
          : error ? <ErrorState message={error} onRetry={load} />
            : data ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <MetricCard label="Rencana" value={data.planned} format="idr" tone="primary"
                    hint={data.planned_readonly ? "dihitung dari item RAB" : undefined} />
                  <MetricCard label="Realisasi" value={data.realized} format="idr"
                    tone="emerald" />
                  <MetricCard label="Komitmen" value={data.committed} format="idr"
                    tone="indigo" />
                  <MetricCard label="Exposure (realisasi + komitmen)" value={data.exposure}
                    format="idr" tone={data.health === "overbudget" ? "rose" : "amber"}
                    hint={data.pct !== null ? `${data.pct}% dari rencana` : "persen belum bisa dihitung"} />
                </div>

                <div className="flex flex-wrap items-center gap-2 text-[12px]">
                  <HealthPill value={data.health} />
                  <span className="text-muted-foreground">
                    Cara pencocokan: {labelOf("budget_match_rule", data.match_rule)}
                    {data.gl_account ? ` · akun ${data.gl_account}` : ""}
                  </span>
                </div>

                {checks ? (
                  <p data-testid={BUDGET.drillTieOut} data-ok={checks.tie_out_ok ? "true" : "false"}
                    className={`flex items-start gap-2 rounded-lg border p-3 text-[12px] ${
                      checks.tie_out_ok
                        ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                        : "border-rose-200 bg-rose-50 text-rose-900"}`}>
                    {checks.tie_out_ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                      : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
                    <span>
                      Pemeriksaan penjumlahan: Σ dokumen realisasi{" "}
                      <Money value={checks.documents_realisasi} /> vs realisasi item{" "}
                      <Money value={data.realized} /> · Σ dokumen komitmen{" "}
                      <Money value={checks.documents_komitmen} /> vs komitmen item{" "}
                      <Money value={data.committed} />.{" "}
                      {checks.tie_out_ok ? "Cocok." : "TIDAK COCOK — laporkan sebagai cacat."}
                    </span>
                  </p>
                ) : null}

                <MissingNote items={data.missing} />

                {(data.by_source || []).length ? (
                  <div className="flex flex-wrap gap-2">
                    {data.by_source.map((s) => (
                      <span key={s.source} data-testid={BUDGET.drillSource}
                        className="rounded-full border bg-card px-3 py-1 text-[11px] shadow-[var(--shadow-card)]">
                        <span className="text-muted-foreground">
                          {labelOf("cost_source", s.source)}:
                        </span>{" "}
                        <span className="font-medium tabular-nums">
                          <Money value={s.amount} />
                        </span>{" "}
                        <span className="text-muted-foreground">({s.count})</span>
                      </span>
                    ))}
                  </div>
                ) : null}

                {!(data.documents || []).length ? (
                  <p className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-[12px] text-slate-700">
                    Belum ada dokumen biaya yang menyusun angka item ini.
                  </p>
                ) : (
                  <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
                    <Table>
                      <TableHeader><TableRow>
                        <TableHead>Jenis dokumen</TableHead>
                        <TableHead>Nomor</TableHead>
                        <TableHead>Keterangan</TableHead>
                        <TableHead>Tanggal</TableHead>
                        <TableHead>Sifat</TableHead>
                        <TableHead className="text-right">Nilai</TableHead>
                        <TableHead />
                      </TableRow></TableHeader>
                      <TableBody>
                        {data.documents.map((d, i) => (
                          <TableRow key={`${d.source}-${d.ref}-${i}`} data-testid={BUDGET.drillDoc}
                            data-kind={d.kind}>
                            <TableCell className="text-xs">
                              {labelOf("cost_source", d.source)}
                            </TableCell>
                            <TableCell className="font-mono text-[11px]">{d.ref || "-"}</TableCell>
                            <TableCell className="max-w-[260px] truncate text-xs" title={d.label}>
                              {d.label}
                              {d.note ? (
                                <span className="block text-[10px] text-muted-foreground">
                                  {d.note}
                                </span>
                              ) : null}
                            </TableCell>
                            <TableCell className="text-[11px]">{d.date || "-"}</TableCell>
                            <TableCell className="text-[11px]">
                              <span className={`rounded px-1.5 py-0.5 ${
                                d.kind === "realisasi" ? "bg-emerald-100 text-emerald-800"
                                  : d.kind === "komitmen" ? "bg-indigo-100 text-indigo-800"
                                    : "bg-slate-100 text-slate-700"}`}>
                                {d.kind}
                              </span>
                            </TableCell>
                            <TableCell className="text-right text-xs font-medium">
                              <Money value={d.amount} />
                            </TableCell>
                            <TableCell>
                              {d.link ? (
                                <Link to={d.link} className="text-primary"
                                  aria-label={`Buka sumber ${d.ref || d.source}`}>
                                  <ExternalLink className="h-3.5 w-3.5" />
                                </Link>
                              ) : null}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}

                {data.material_usage ? (
                  <div data-testid={BUDGET.materialInfo}
                    className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-[12px] text-sky-900">
                    <p className="font-medium">
                      Pemakaian material (angka pengendalian, TIDAK dijumlahkan ke realisasi)
                    </p>
                    <p className="mt-0.5">
                      Nilai pemakaian: <Money value={data.material_usage.value} /> dari{" "}
                      {data.material_usage.transactions} transaksi keluar.
                    </p>
                    <p className="mt-0.5">{data.material_usage.note}</p>
                    {(data.material_usage.missing || []).map((m, i) => (
                      <p key={i} className="mt-0.5 text-amber-800">{m}</p>
                    ))}
                  </div>
                ) : null}

                {(data.revision || []).length ? (
                  <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                    <p className="text-sm font-semibold">Riwayat revisi anggaran</p>
                    <ul className="mt-1.5 space-y-1 text-[12px]">
                      {[...data.revision].reverse().map((r, i) => (
                        <li key={i}>
                          <span className="font-mono text-[11px] text-muted-foreground">
                            {String(r.at || "").slice(0, 16).replace("T", " ")}
                          </span>{" "}
                          <span className="font-medium">{r.by}</span>:{" "}
                          <Money value={r.from} /> → <Money value={r.to} /> — {r.reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {(data.alerts || []).length ? (
                  <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                    <p className="text-sm font-semibold">Riwayat peringatan</p>
                    <ul className="mt-1.5 space-y-1 text-[12px]">
                      {[...data.alerts].reverse().map((a, i) => (
                        <li key={i} className="flex flex-wrap items-center gap-1.5">
                          <span className="font-mono text-[11px] text-muted-foreground">
                            {String(a.at || "").slice(0, 16).replace("T", " ")}
                          </span>
                          <HealthPill value={a.level} testId={`${BUDGET.healthPill}-alert`} />
                          <Pct value={a.pct} />
                          <span className="text-muted-foreground">
                            → {(a.notified || []).join(", ") || "tidak ada penerima"}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : null}
      </DialogContent>
    </Dialog>
  );
}
