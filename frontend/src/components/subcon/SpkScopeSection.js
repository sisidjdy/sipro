import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Coins, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import MetricCard from "@/components/patterns/MetricCard";
import StatusPill from "@/components/patterns/StatusPill";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import AddScopeItemsDialog from "@/components/subcon/AddScopeItemsDialog";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { pctOf, scopeTone } from "@/utils/opnameUi";
import { SCOPE } from "@/constants/testIds";

/**
 * LINGKUP SPK & OPNAME (Fase 33).
 *
 * Kenapa ada: dulu nilai termin subkontraktor lahir dari PERSEN yang diketik bebas,
 * tanpa ikatan ke pekerjaan yang benar-benar sudah diverifikasi. Panel ini membuat
 * pembayaran punya rincian: satu baris = satu item jadwal (unit + langkah) dengan nilai
 * borongan, statusnya jujur (belum selesai / menunggu verifikasi / siap ditagih / sudah
 * ditagih), dan pekerjaan yang sudah dibayar tidak bisa ditagih lagi.
 */
export default function SpkScopeSection({ spk, canManage, onChanged }) {
  const [rows, setRows] = useState(null);
  const [summary, setSummary] = useState(null);
  const [contract, setContract] = useState(null);
  const [spkPct, setSpkPct] = useState({ progress: 0, billed: 0 });
  const [blockers, setBlockers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!spk?.id) return;
    setLoading(true); setError("");
    try {
      const r = await api.get(`/subcon/spk/${spk.id}/scope`);
      setRows(r.data.data || []);
      setSummary(r.data.summary || null);
      setContract(r.data.contract || null);
      setBlockers(r.data.blockers || []);
      setSpkPct({
        progress: Number(r.data.spk?.progress_pct || 0),
        billed: Number(r.data.spk?.billed_pct || 0),
      });
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat lingkup pekerjaan SPK.");
    } finally { setLoading(false); }
  }, [spk?.id]);
  useEffect(() => { load(); }, [load]);

  const remove = async (row) => {
    setBusy(true);
    try {
      await api.delete(`/subcon/spk/${spk.id}/scope/${row.id}`);
      toast.success("Pekerjaan dikeluarkan dari lingkup SPK.");
      await load(); onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengeluarkan pekerjaan.");
    } finally { setBusy(false); }
  };

  const done = async () => { await load(); onChanged && onChanged(); };
  const hasRows = !!rows?.length;

  return (
    <div data-testid={SCOPE.section} className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="flex items-center gap-1.5 text-sm font-semibold">
            <Coins className="h-4 w-4 text-primary" /> Lingkup &amp; Opname
          </p>
          <p className="text-[11px] text-muted-foreground">
            Pembayaran mengikuti item jadwal yang sudah diverifikasi — bukan persen manual.
          </p>
        </div>
        {canManage ? (
          <Button size="sm" variant="outline" data-testid={SCOPE.addBtn}
            onClick={() => setAddOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> Tambah pekerjaan
          </Button>
        ) : null}
      </div>

      {loading ? <LoadingCards count={2} />
        : error ? <ErrorState message={error} onRetry={load} />
          : !hasRows ? (
            <div data-testid={SCOPE.lumpsumHint}
              className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-[12px] text-amber-900">
              <p className="font-semibold">SPK ini masih dibayar borongan lump-sum (persen manual).</p>
              <p className="mt-1">
                Susun lingkup dari item jadwal unit agar nilai termin dihitung dari pekerjaan
                yang benar-benar diverifikasi (foto + checklist mutu), dan satu pekerjaan tidak
                bisa dibayar dua kali.
              </p>
            </div>
          ) : (
            <>
              <div data-testid={SCOPE.metrics} className="grid grid-cols-2 gap-3">
                <MetricCard label="Nilai lingkup" value={summary.scope_value} format="idr"
                  tone="primary" hint={`${summary.items} pekerjaan`} />
                <MetricCard label="Terverifikasi" value={summary.verified_value} format="idr"
                  tone="emerald" hint={`${summary.verified_items} pekerjaan berbukti`} />
                <MetricCard label="Sudah ditagih" value={summary.billed_value} format="idr"
                  tone="indigo" hint={`${summary.billed_items} pekerjaan`} />
                <MetricCard label="Siap ditagih" value={summary.claimable_value} format="idr"
                  tone={summary.claimable_value ? "amber" : "muted"}
                  hint={`${summary.claimable_items} pekerjaan`} />
              </div>

              {contract ? (
                <div data-testid={SCOPE.contract} className="rounded-lg bg-secondary p-3 text-[12px]">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span>
                      Terurai <b className="tabular-nums">{formatIDR(contract.allocated)}</b> dari nilai
                      kontrak <b className="tabular-nums">{formatIDR(contract.contract_value)}</b>
                    </span>
                    <span className={contract.unallocated > 0 ? "text-amber-700" : "text-emerald-700"}>
                      {contract.unallocated > 0
                        ? `${formatIDR(contract.unallocated)} belum diurai menjadi pekerjaan`
                        : "Seluruh nilai kontrak sudah terurai"}
                    </span>
                  </div>
                  <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-background">
                    <div className="h-full rounded-full bg-primary"
                      style={{ width: `${pctOf(contract.allocated, contract.contract_value)}%` }} />
                  </div>
                  <p data-testid={SCOPE.progressNote} className="mt-2 text-muted-foreground">
                    Progres SPK <b>{spkPct.progress}%</b> (nilai terverifikasi) · sudah ditagih{" "}
                    <b>{spkPct.billed}%</b>. Angka ini dihitung sistem dan tidak bisa diketik.
                  </p>
                </div>
              ) : null}

              {blockers?.length ? (
                <div data-testid={SCOPE.blockers} className="space-y-1 text-[12px] text-muted-foreground">
                  {blockers.map((b) => (
                    <p key={b.state}>
                      • {b.items} pekerjaan <b>{String(b.label).toLowerCase()}</b> —{" "}
                      {formatIDR(b.value)} belum bisa ditagih
                    </p>
                  ))}
                </div>
              ) : null}

              {summary.regressed_items ? (
                <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-[12px] text-rose-900">
                  <AlertTriangle className="mt-0.5 h-4 w-4" />
                  <span>
                    {summary.regressed_items} pekerjaan sudah dibayar tetapi kemudian dikembalikan
                    untuk perbaikan — pertimbangkan potong retensi atau klaim balik.
                  </span>
                </div>
              ) : null}

              <div className="overflow-hidden rounded-lg border bg-card shadow-[var(--shadow-card)]">
                <Table className="min-w-[680px]">
                  <TableHeader><TableRow>
                    <TableHead>Unit</TableHead><TableHead>Langkah pekerjaan</TableHead>
                    <TableHead className="text-right">Nilai borongan</TableHead>
                    <TableHead>Status</TableHead><TableHead>Termin</TableHead>
                    {canManage ? <TableHead /> : null}
                  </TableRow></TableHeader>
                  <TableBody>
                    {rows.map((r) => (
                      <TableRow key={r.id} data-testid={SCOPE.row} data-state={r.state}>
                        <TableCell className="font-medium">{r.unit_code}</TableCell>
                        <TableCell className="text-sm">
                          <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px]">
                            {r.step_code}
                          </span>{" "}
                          {r.step_name}
                          {r.cost_code ? (
                            <span className="ml-1 text-[11px] text-muted-foreground">
                              (RAB {r.cost_code})
                            </span>
                          ) : null}
                          {r.exclude_reason ? (
                            <p className="mt-0.5 text-[11px] text-amber-700">
                              Pernah dikeluarkan opname: {r.exclude_reason}
                            </p>
                          ) : null}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{formatIDR(r.value)}</TableCell>
                        <TableCell>
                          <StatusPill status={r.state} group="scope_item_state"
                            tone={scopeTone(r.state)} />
                        </TableCell>
                        <TableCell className="text-[11px] text-muted-foreground">
                          {r.claim_number || (r.state === "pending" ? "dalam pengajuan" : "-")}
                        </TableCell>
                        {canManage ? (
                          <TableCell>
                            <Button variant="ghost" size="icon" data-testid={SCOPE.removeBtn}
                              className="h-8 w-8 text-rose-600" disabled={busy}
                              aria-label={`Keluarkan ${r.step_code} dari lingkup`}
                              onClick={() => remove(r)}>
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        ) : null}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          )}

      <AddScopeItemsDialog spk={spk} open={addOpen} onOpenChange={setAddOpen} onDone={done} />
    </div>
  );
}
