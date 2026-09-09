import React, { useCallback, useEffect, useState } from "react";
import { Calculator, Coins, ListTree, ShieldCheck, Target, Plus, Trash2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import TabPage from "@/components/patterns/TabPage";
import MetricCard from "@/components/patterns/MetricCard";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import ProjectSelect from "@/components/construction/ProjectSelect";
import AddBoQItemDialog from "@/components/boq/AddBoQItemDialog";
import BoQStepMapDialog from "@/components/boq/BoQStepMapDialog";
import CostControlPanel from "@/components/boq/CostControlPanel";
import RabTypePanel from "@/components/boq/RabTypePanel";
import RabScopePanel from "@/components/boq/RabScopePanel";
import RabSummaryPanel from "@/components/boq/RabSummaryPanel";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { P80 } from "@/constants/testIds";
import BudgetItemsPanel from "@/components/budget/BudgetItemsPanel";
import RealizationPanel from "@/components/budget/RealizationPanel";
import TargetPanel from "@/components/budget/TargetPanel";
import { useAuth } from "@/context/AuthContext";
import { formatIDR, formatNumber } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PROCUREMENT, COST } from "@/constants/testIds";
import { useReference } from "@/context/ReferenceContext";

/**
 * BoQPage (`/boq`) — hub **RAB / Anggaran** dengan empat tab.
 *
 * Fase 45 menambah dua tab di SINI, bukan pintu sidebar baru: ledger pintu resmi
 * (`docs/v2/40` §7) menetapkan bahwa pekerjaan Target & Budget WAJIB masuk sebagai tab pada
 * hub yang sudah ada. Alasannya bukan kerapian belaka — setiap pintu menu baru menambah
 * beban orientasi, dan anggaran memang satu urusan dengan RAB.
 *
 *   Rincian RAB      → item pekerjaan (volume × harga satuan)
 *   Kendali Biaya    → RAB vs dikontrakkan vs terbukti vs ditagih (Fase 33)
 *   Target & Budget  → target unit/pendapatan (5 metode) + master item anggaran (Fase 45)
 *   Realisasi RAB    → realisasi 3 lapis + margin + biaya belum terpetakan (Fase 45)
 *
 * Tab sinkron ke URL (`?hub=`) supaya tautan drill dari dashboard & notifikasi
 * (mis. `/boq?hub=realisasi`) mendarat tepat di tempatnya dan bisa dibagikan.
 */
function BoQItemsTab({ projectId }) {
  const { labelOf } = useReference();
  const { can } = useAuth();
  const canManage = can("boq", "create");
  const [items, setItems] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [mapFor, setMapFor] = useState(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const [ri, rs] = await Promise.all([
        api.get("/boq/items", { params: { project_id: projectId } }),
        api.get("/boq/summary", { params: { project_id: projectId } }),
      ]);
      setItems(ri.data); setSummary(rs.data.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat data RAB."); }
    finally { setLoading(false); }
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  const del = async (id) => {
    try { await api.delete(`/boq/items/${id}`); toast.success("Item dihapus."); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menghapus item."); }
  };

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-5">
      {summary ? (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <MetricCard label="Anggaran (RAB)" value={summary.budget} tone="primary" format="idr" />
            <MetricCard label="Komitmen (PO)" value={summary.committed} tone="indigo" format="idr" />
            <MetricCard label="Realisasi (Tagihan)" value={summary.actual} tone="amber" format="idr" />
            <MetricCard label="Sisa Anggaran" value={summary.remaining} tone={summary.remaining < 0 ? "rose" : "emerald"} format="idr" />
          </div>
          {summary.over_budget ? (
            <div data-testid="boq-over-budget" className="flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
              <AlertTriangle className="h-4 w-4" /> Komitmen PO melebihi anggaran RAB proyek ini.
            </div>
          ) : null}
          {summary.categories?.length ? (
            <div className="flex flex-wrap gap-2">
              {summary.categories.map((c) => (
                <span key={c.category} className="rounded-full border bg-card px-3 py-1 text-xs shadow-[var(--shadow-card)]">
                  <span className="text-muted-foreground">{labelOf("work_category", c.category)}:</span>{" "}
                  <span className="font-medium tabular-nums">{formatIDR(c.amount)}</span>
                </span>
              ))}
            </div>
          ) : null}
        </>
      ) : null}

      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Rincian Item ({items?.total || 0})</p>
        {canManage ? (
          <Button data-testid={PROCUREMENT.boqAddBtn} size="sm" onClick={() => setAddOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> Tambah Item
          </Button>
        ) : null}
      </div>

      {!items?.data?.length ? (
        <EmptyState icon={Calculator} title="Belum ada item RAB"
          description="Tambahkan item pekerjaan (kode biaya, volume, harga satuan) untuk menyusun anggaran."
          actionLabel={canManage ? "Tambah Item" : undefined} onAction={() => setAddOpen(true)} />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Kode</TableHead><TableHead>Kategori</TableHead><TableHead>Uraian</TableHead>
              <TableHead>Langkah jadwal</TableHead>
              <TableHead className="text-right">Volume</TableHead><TableHead className="text-right">Harga Satuan</TableHead>
              <TableHead className="text-right">Jumlah</TableHead>{canManage ? <TableHead /> : null}
            </TableRow></TableHeader>
            <TableBody>
              {items.data.map((it) => (
                <TableRow key={it.id} data-testid={PROCUREMENT.boqRow}>
                  <TableCell className="font-medium">{it.cost_code || "-"}</TableCell>
                  <TableCell className="text-sm">{labelOf("work_category", it.category)}</TableCell>
                  <TableCell className="text-sm">{it.description}</TableCell>
                  <TableCell className="text-[11px]">
                    {(it.step_codes || []).length ? (
                      <button type="button" data-testid={COST.mapBtn}
                        className="rounded bg-secondary px-1.5 py-0.5 font-mono hover:underline"
                        disabled={!canManage}
                        onClick={() => setMapFor({ id: it.id, code: it.cost_code,
                          label: it.description, steps: it.step_codes || [] })}>
                        {(it.step_codes || []).join(", ")}
                      </button>
                    ) : canManage ? (
                      <Button size="sm" variant="ghost" data-testid={COST.mapBtn}
                        className="h-7 text-[11px] text-amber-700"
                        onClick={() => setMapFor({ id: it.id, code: it.cost_code,
                          label: it.description, steps: [] })}>
                        Petakan ke langkah
                      </Button>
                    ) : <span className="text-amber-700">belum dipetakan</span>}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{formatNumber(it.quantity)} {it.uom}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{formatIDR(it.unit_price)}</TableCell>
                  <TableCell className="text-right tabular-nums font-medium">{formatIDR(it.amount)}</TableCell>
                  {canManage ? (
                    <TableCell>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-rose-600"
                        aria-label={`Hapus item ${it.cost_code || it.description}`}
                        onClick={() => del(it.id)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <AddBoQItemDialog projectId={projectId} open={addOpen} onOpenChange={setAddOpen} onDone={load} />
      <BoQStepMapDialog projectId={projectId} item={mapFor} open={!!mapFor}
        onOpenChange={(v) => !v && setMapFor(null)} onDone={load} />
    </div>
  );
}

export default function BoQPage() {
  const { can } = useAuth();
  const canManage = can("boq", "create");
  const canBudget = can("budget", "view");
  const canTarget = can("targets", "view");
  const [projectId, setProjectId] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const header = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 className="page-title flex items-center gap-2">
          <Calculator className="h-5 w-5 text-primary" /> RAB / Anggaran Proyek
        </h1>
        <p className="max-w-3xl text-[12px] text-muted-foreground">
          Satu tempat untuk rencana biaya (RAB), target penjualan, master anggaran, dan
          realisasinya — semua angka bisa ditelusuri sampai dokumen sumbernya.
        </p>
      </div>
      <ProjectSelect value={projectId} onChange={setProjectId}
        testId={PROCUREMENT.boqProjectSelect} />
    </div>
  );

  if (!projectId) {
    return (
      <div data-testid={PROCUREMENT.boqPage} className="space-y-5">
        {header}
        <EmptyState icon={Calculator} title="Pilih proyek"
          description="Pilih proyek untuk melihat anggaran biaya (RAB), target penjualan, dan realisasi anggarannya." />
      </div>
    );
  }

  return (
    <div data-testid={PROCUREMENT.boqPage}>
      <TabPage paramKey="hub" header={header} tabs={[
        { key: "items", label: "Rincian RAB", icon: Calculator,
          content: (
            <Tabs defaultValue="unit" className="space-y-4">
              <TabsList className="flex-wrap">
                <TabsTrigger data-testid={P80.tabUnit} value="unit">RAB Unit (per tipe)</TabsTrigger>
                <TabsTrigger data-testid={P80.tabFasum} value="fasum">Fasum / Fasos</TabsTrigger>
                <TabsTrigger data-testid={P80.tabUmum} value="umum">Umum</TabsTrigger>
                <TabsTrigger data-testid={P80.tabSummary} value="summary">Ringkasan & HPP</TabsTrigger>
                <TabsTrigger value="legacy">Item RAB proyek (lama)</TabsTrigger>
              </TabsList>
              <TabsContent value="unit"><RabTypePanel onChanged={() => setReloadKey((k) => k + 1)} /></TabsContent>
              <TabsContent value="fasum"><RabScopePanel projectId={projectId} scope="fasum" onChanged={() => setReloadKey((k) => k + 1)} /></TabsContent>
              <TabsContent value="umum"><RabScopePanel projectId={projectId} scope="umum" onChanged={() => setReloadKey((k) => k + 1)} /></TabsContent>
              <TabsContent value="summary"><RabSummaryPanel projectId={projectId} reloadKey={reloadKey} /></TabsContent>
              <TabsContent value="legacy"><BoQItemsTab projectId={projectId} /></TabsContent>
            </Tabs>
          ) },
        { key: "kendali", label: "Kendali Biaya", icon: ShieldCheck,
          content: <CostControlPanel projectId={projectId} canManage={canManage}
            onMapped={() => setReloadKey((k) => k + 1)} /> },
        canTarget || canBudget ? {
          key: "target", label: "Target & Budget", icon: Target,
          content: (
            <div className="space-y-6">
              {canTarget ? <TargetPanel projectId={projectId} /> : null}
              {canBudget ? (
                <BudgetItemsPanel key={reloadKey} projectId={projectId}
                  onChanged={() => setReloadKey((k) => k + 1)} />
              ) : null}
            </div>
          ),
        } : null,
        canBudget ? {
          key: "realisasi", label: "Realisasi RAB", icon: ListTree,
          content: <RealizationPanel key={reloadKey} projectId={projectId} />,
        } : null,
      ].filter(Boolean)} />
    </div>
  );
}
