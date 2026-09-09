import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Link2, ShieldCheck } from "lucide-react";

import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import MetricCard from "@/components/patterns/MetricCard";
import EmptyState from "@/components/patterns/EmptyState";
import RefLabel from "@/components/patterns/RefLabel";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import BoQStepMapDialog from "@/components/boq/BoQStepMapDialog";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { pctOf } from "@/utils/opnameUi";
import { COST } from "@/constants/testIds";

/**
 * KENDALI BIAYA (Fase 33).
 *
 * Menjawab pertanyaan direksi yang dulu tidak bisa dijawab aplikasi:
 * "anggaran RAB saya sudah dipakai ke mana, berapa yang sudah dikontrakkan ke subkon,
 * berapa yang fisiknya BENAR-BENAR terbukti, dan berapa yang sudah ditagihkan?"
 *
 * Angka "terverifikasi" berasal dari item jadwal yang lulus verifikasi (foto + checklist),
 * bukan dari persen yang diketik. Over-commit ditandai sebagai peringatan — bukan diblokir —
 * karena jalan resminya menambah anggaran/Change Order, bukan menyembunyikan angka.
 */
export default function CostControlPanel({ projectId, canManage, onMapped }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mapFor, setMapFor] = useState(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const r = await api.get("/boq/control", { params: { project_id: projectId } });
      setData(r.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat kendali biaya.");
    } finally { setLoading(false); }
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  if (!projectId) {
    return <EmptyState icon={ShieldCheck} title="Pilih proyek"
      description="Pilih proyek untuk melihat anggaran vs nilai yang dikontrakkan, terbukti, dan ditagih." />;
  }
  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;

  const t = data.totals || {};
  return (
    <div data-testid={COST.panel} className="space-y-4">
      <div data-testid={COST.metrics} className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Anggaran (RAB)" value={t.budget} format="idr" tone="primary" />
        <MetricCard label="Dikontrakkan ke subkon" value={t.contracted} format="idr"
          tone="indigo" hint={`${data.scope_lines} baris lingkup SPK`} />
        <MetricCard label="Terbukti (terverifikasi)" value={t.verified} format="idr"
          tone="emerald" hint="dari bukti foto + checklist" />
        <MetricCard label="Sudah ditagihkan" value={t.billed} format="idr" tone="amber"
          hint={`belum ditagih: ${formatIDR(t.unbilled_verified)}`} />
      </div>

      {(data.warnings || []).length ? (
        <div data-testid={COST.warning} className="space-y-1.5">
          {data.warnings.map((w, i) => (
            <p key={i}
              className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-[12px] text-amber-900">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {w}
            </p>
          ))}
        </div>
      ) : (
        <p className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-[12px] text-emerald-900">
          Tidak ada kategori yang melebihi anggaran, dan seluruh anggaran sudah dipetakan ke
          langkah jadwal.
        </p>
      )}

      <div>
        <p className="mb-2 text-sm font-semibold">Per kategori pekerjaan</p>
        <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Kategori</TableHead>
              <TableHead className="text-right">Anggaran</TableHead>
              <TableHead className="text-right">Dikontrakkan</TableHead>
              <TableHead className="text-right">Terbukti</TableHead>
              <TableHead className="text-right">Ditagih</TableHead>
              <TableHead className="text-right">Selisih</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {(data.categories || []).map((c) => (
                <TableRow key={c.key} data-testid={COST.categoryRow} data-over={c.over_commit}>
                  <TableCell className="font-medium">
                    <RefLabel group="work_category" value={c.key} />
                    <div className="mt-1 h-1.5 w-28 overflow-hidden rounded-full bg-secondary">
                      <div className="h-full rounded-full bg-emerald-500"
                        style={{ width: `${pctOf(c.verified, c.contracted || c.budget)}%` }} />
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(c.budget)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(c.contracted)}</TableCell>
                  <TableCell className="text-right tabular-nums text-emerald-700">
                    {formatIDR(c.verified)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(c.billed)}</TableCell>
                  <TableCell className={`text-right tabular-nums ${c.over_commit ? "font-semibold text-rose-600" : ""}`}>
                    {formatIDR(c.variance)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <div>
        <p className="mb-2 text-sm font-semibold">Per kode biaya RAB (pemetaan ke langkah jadwal)</p>
        <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Kode</TableHead><TableHead>Uraian</TableHead>
              <TableHead>Langkah terpetakan</TableHead>
              <TableHead className="text-right">Anggaran</TableHead>
              <TableHead className="text-right">Dikontrakkan</TableHead>
              <TableHead className="text-right">Terbukti</TableHead>
              {canManage ? <TableHead /> : null}
            </TableRow></TableHeader>
            <TableBody>
              {(data.cost_codes || []).map((c) => (
                <TableRow key={c.key} data-testid={COST.codeRow} data-mapped={!!c.mapped}>
                  <TableCell className="font-mono text-xs font-medium">{c.key}</TableCell>
                  <TableCell className="text-sm">{c.label}</TableCell>
                  <TableCell className="text-[11px]">
                    {c.steps?.length ? (
                      <span data-testid={COST.mapCount}>{c.steps.join(", ")}</span>
                    ) : (
                      <span className="text-amber-700">belum dipetakan</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(c.budget)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(c.contracted)}</TableCell>
                  <TableCell className="text-right tabular-nums text-emerald-700">
                    {formatIDR(c.verified)}
                  </TableCell>
                  {canManage ? (
                    <TableCell>
                      {c.boq_item_id ? (
                        <Button size="sm" variant="ghost" data-testid={COST.mapBtn}
                          onClick={() => setMapFor({ id: c.boq_item_id, code: c.key,
                            label: c.label, steps: c.steps || [] })}>
                          <Link2 className="mr-1 h-3.5 w-3.5" /> Petakan
                        </Button>
                      ) : null}
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <BoQStepMapDialog projectId={projectId} item={mapFor}
        open={!!mapFor} onOpenChange={(v) => !v && setMapFor(null)}
        onDone={() => { load(); onMapped && onMapped(); }} />
    </div>
  );
}
