import React, { useCallback, useEffect, useState } from "react";
import { Coins, ListTree, NotebookPen, PencilLine, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import ConfirmDialog from "@/components/patterns/ConfirmDialog";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import BudgetItemDialog from "@/components/budget/BudgetItemDialog";
import ManualEntryDialog from "@/components/budget/ManualEntryDialog";
import RealizationDialog from "@/components/budget/RealizationDialog";
import ReviseDialog from "@/components/budget/ReviseDialog";
import { ExposureBar, HealthPill, MissingNote, Money, Pct, isNegative } from "@/components/budget/parts";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { BUDGET } from "@/constants/testIds";

/**
 * BudgetItemsPanel — MASTER item anggaran (keputusan D6: bisa ditambah user tanpa ubah kode).
 *
 * Tabel ini adalah tempat pemakai melihat pos biaya beserta angkanya sekaligus:
 * rencana, komitmen, realisasi, exposure, dan statusnya. Tombol “Dokumen” membuka lapis 3
 * (daftar dokumen penyusun angka) supaya tidak ada angka yang harus dipercaya begitu saja.
 */
export default function BudgetItemsPanel({ projectId, onChanged }) {
  const { can } = useAuth();
  const { labelOf } = useReference();
  const canCreate = can("budget", "create");
  const canUpdate = can("budget", "update");
  const canApprove = can("budget", "approve");
  const canDelete = can("budget", "delete");

  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [dialogFor, setDialogFor] = useState(undefined);
  const [drillFor, setDrillFor] = useState(null);
  const [reviseFor, setReviseFor] = useState(null);
  const [manualFor, setManualFor] = useState(null);
  const [confirmDel, setConfirmDel] = useState(null);
  const [rawItems, setRawItems] = useState([]);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const [s, it] = await Promise.all([
        api.get("/budget/summary", { params: { project_id: projectId } }),
        api.get("/budget/items", { params: { project_id: projectId } }),
      ]);
      setSummary(s.data.data);
      setRawItems(it.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat master anggaran.");
    } finally { setLoading(false); }
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  const refresh = () => { load(); onChanged && onChanged(); };

  const del = async (row) => {
    try {
      await api.delete(`/budget/items/${row.id}`);
      toast.success("Item anggaran dihapus.");
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menghapus item anggaran.");
    }
  };

  if (!projectId) {
    return <EmptyState icon={Coins} title="Pilih proyek"
      description="Pilih proyek untuk menyusun master anggaran (konstruksi, operasional, marketing, pajak, dan lain-lain)." />;
  }
  if (loading && !summary) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const items = summary?.items || [];
  const rawById = {};
  rawItems.forEach((r) => { rawById[r.id] = r; });

  return (
    <div data-testid={BUDGET.itemsPanel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold">Master item anggaran ({items.length})</p>
          <p className="text-[12px] text-muted-foreground">
            Kategori konstruksi meringkas RAB (rencananya read-only). Kategori lain dicocokkan
            ke akun buku besar, dokumen biaya, atau dicatat manual beralasan.
          </p>
        </div>
        {canCreate ? (
          <Button size="sm" data-testid={BUDGET.itemCreate} onClick={() => setDialogFor(null)}>
            <Plus className="mr-1.5 h-4 w-4" /> Tambah Item Anggaran
          </Button>
        ) : null}
      </div>

      <MissingNote items={summary?.missing} testId={`${BUDGET.itemsPanel}-missing`}
        title="Yang membuat angka anggaran belum lengkap:" />

      {!items.length ? (
        <EmptyState icon={Coins} title="Belum ada item anggaran"
          description="Tanpa item anggaran, realisasi &amp; overbudget tidak bisa dihitung. Mulai dari satu item konstruksi yang meringkas RAB, lalu tambahkan pos operasional."
          actionLabel={canCreate ? "Tambah Item Anggaran" : undefined}
          onAction={() => setDialogFor(null)} />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Kode</TableHead>
              <TableHead>Nama</TableHead>
              <TableHead>Kategori</TableHead>
              <TableHead>Pencocokan</TableHead>
              <TableHead className="text-right">Rencana</TableHead>
              <TableHead className="text-right">Komitmen</TableHead>
              <TableHead className="text-right">Realisasi</TableHead>
              <TableHead className="text-right">Exposure</TableHead>
              <TableHead className="text-right">Sisa</TableHead>
              <TableHead>Status</TableHead>
              <TableHead />
            </TableRow></TableHeader>
            <TableBody>
              {items.map((row) => (
                <TableRow key={row.id} data-testid={BUDGET.itemRow} data-code={row.code}
                  data-health={row.health}>
                  <TableCell className="whitespace-nowrap font-mono text-xs font-medium">
                    {row.code}
                  </TableCell>
                  <TableCell className="max-w-[200px] truncate text-sm" title={row.name}>
                    {row.name}
                    {row.missing?.length ? (
                      <span className="block text-[10px] text-amber-700">{row.missing[0]}</span>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-xs">
                    {labelOf("budget_category", row.category)}
                  </TableCell>
                  <TableCell className="text-[11px] text-muted-foreground">
                    {labelOf("budget_match_rule", row.match_rule)}
                    {row.gl_account ? ` · ${row.gl_account}` : ""}
                  </TableCell>
                  <TableCell className="text-right text-sm">
                    <Money value={row.planned} />
                    {row.planned_readonly ? (
                      <span className="block text-[10px] text-muted-foreground">dari RAB</span>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-right text-sm"><Money value={row.committed} /></TableCell>
                  <TableCell className="text-right text-sm text-emerald-700">
                    <Money value={row.realized} />
                  </TableCell>
                  <TableCell className="text-right text-sm font-medium">
                    <Money value={row.exposure} />
                    <ExposureBar exposure={row.exposure} planned={row.planned}
                      health={row.health} />
                  </TableCell>
                  <TableCell className={`text-right text-sm ${
                    isNegative(row.variance) ? "font-semibold text-rose-600" : ""}`}>
                    <Money value={row.variance} />
                  </TableCell>
                  <TableCell>
                    <HealthPill value={row.health} />
                    <span className="mt-1 block text-[10px] text-muted-foreground">
                      <Pct value={row.pct} />
                    </span>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center justify-end gap-1">
                      <Button size="sm" variant="ghost" data-testid={BUDGET.drillBtn}
                        className="h-7 px-2 text-[11px]"
                        onClick={() => setDrillFor(row)}>
                        <ListTree className="mr-1 h-3.5 w-3.5" /> Dokumen ({row.document_count})
                      </Button>
                      {canUpdate && row.match_rule === "manual" ? (
                        <Button size="sm" variant="ghost" data-testid={BUDGET.manualBtn}
                          className="h-7 px-2 text-[11px]"
                          onClick={() => setManualFor(row)}>
                          <NotebookPen className="mr-1 h-3.5 w-3.5" /> Catat
                        </Button>
                      ) : null}
                      {canApprove && !row.planned_readonly ? (
                        <Button size="sm" variant="ghost" data-testid={BUDGET.reviseBtn}
                          className="h-7 px-2 text-[11px]"
                          onClick={() => setReviseFor(row)}>
                          <PencilLine className="mr-1 h-3.5 w-3.5" /> Revisi
                        </Button>
                      ) : null}
                      {canUpdate ? (
                        <Button size="sm" variant="ghost" className="h-7 px-2 text-[11px]"
                          aria-label={`Ubah item anggaran ${row.code}`}
                          onClick={() => setDialogFor(rawById[row.id] || row)}>
                          Ubah
                        </Button>
                      ) : null}
                      {canDelete ? (
                        <Button size="icon" variant="ghost" data-testid={BUDGET.itemDelete}
                          className="h-7 w-7 text-rose-600"
                          aria-label={`Hapus item anggaran ${row.code}`}
                          onClick={() => setConfirmDel(row)}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <BudgetItemDialog projectId={projectId} item={dialogFor || null}
        open={dialogFor !== undefined} onOpenChange={(v) => !v && setDialogFor(undefined)}
        onDone={refresh} />
      <RealizationDialog item={drillFor} open={!!drillFor}
        onOpenChange={(v) => !v && setDrillFor(null)} />
      <ReviseDialog item={reviseFor} open={!!reviseFor}
        onOpenChange={(v) => !v && setReviseFor(null)} onDone={refresh} />
      <ManualEntryDialog item={manualFor} open={!!manualFor}
        onOpenChange={(v) => !v && setManualFor(null)} onDone={refresh} />
      <ConfirmDialog open={!!confirmDel} onOpenChange={(v) => !v && setConfirmDel(null)}
        title={`Hapus item anggaran ${confirmDel?.code}?`}
        description="Item yang sudah punya realisasi/komitmen tidak bisa dihapus — nonaktifkan saja supaya jejak biayanya tidak hilang dari laporan."
        confirmLabel="Hapus" destructive
        onConfirm={() => { del(confirmDel); setConfirmDel(null); }} />
    </div>
  );
}
