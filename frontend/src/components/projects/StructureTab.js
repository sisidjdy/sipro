import React, { useState } from "react";
import { toast } from "sonner";
import { Boxes, ChevronDown, ChevronRight, FileUp, Layers, Plus, Trash2, Wand2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import ConfirmDialog from "@/components/patterns/ConfirmDialog";
import { UnitTypeField } from "@/components/projects/UnitTypeField";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { MASTERPLAN } from "@/constants/testIds";

const CSV_HINT = "cluster_code,block_code,no,unit_type_code,price\nHL5,D,12,T30-60,166000000";

/** Tab STRUKTUR: kelola cluster → blok → unit (Fase 39, menutup CR-05). */
export default function StructureTab({ tree, projectId, onChanged, canManage }) {
  const [open, setOpen] = useState(() => new Set((tree?.clusters || []).map((c) => c.id)));
  const [clusterForm, setClusterForm] = useState(null);
  const [blockForm, setBlockForm] = useState(null);
  const [genForm, setGenForm] = useState(null);
  const [importForm, setImportForm] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [mapReport, setMapReport] = useState(null);

  // Konsistensi peta ↔ unit: unit baru yang belum digambar di site plan harus terlihat,
  // bukan diam-diam hilang dari peta (temuan wiring site plan pada audit V2).
  React.useEffect(() => {
    let alive = true;
    api.get(`/masterplan/projects/${projectId}/siteplan-consistency`)
      .then((r) => { if (alive) setMapReport(r.data.data); })
      .catch(() => { if (alive) setMapReport(null); });
    return () => { alive = false; };
  }, [projectId, tree]);

  const toggle = (id) => setOpen((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const saveCluster = async () => {
    try {
      if (clusterForm.id) {
        await api.put(`/masterplan/clusters/${clusterForm.id}`, {
          name: clusterForm.name, price_multiplier: Number(clusterForm.price_multiplier) || 1,
          unit_target: Number(clusterForm.unit_target) || null, status: clusterForm.status,
        });
      } else {
        await api.post(`/masterplan/projects/${projectId}/clusters`, {
          code: clusterForm.code, name: clusterForm.name,
          price_multiplier: Number(clusterForm.price_multiplier) || 1,
          unit_target: Number(clusterForm.unit_target) || null,
          status: clusterForm.status || "selling",
        });
      }
      toast.success("Cluster disimpan.");
      setClusterForm(null); onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan cluster."); }
  };

  const saveBlock = async () => {
    try {
      await api.post(`/masterplan/clusters/${blockForm.cluster_id}/blocks`, {
        code: blockForm.code, name: blockForm.name || undefined,
      });
      toast.success("Blok dibuat.");
      setBlockForm(null); onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat blok."); }
  };

  const runGenerate = async () => {
    try {
      const res = await api.post(`/masterplan/blocks/${genForm.block_id}/units/generate`, {
        unit_type_code: genForm.unit_type_code,
        count: Number(genForm.count) || 1,
        start_no: Number(genForm.start_no) || 1,
        price: genForm.price ? Number(genForm.price) : undefined,
        hook_numbers: (genForm.hooks || "").split(",").map((s) => Number(s.trim()))
          .filter((n) => n > 0),
      });
      const d = res.data.data;
      toast.success(`${d.created.length} unit dibuat` + (d.skipped.length
        ? `, ${d.skipped.length} dilewati (kode sudah ada)` : ""));
      setGenForm(null); onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat unit."); }
  };

  const parseCsv = (text) => {
    const lines = (text || "").trim().split(/\r?\n/).filter(Boolean);
    if (!lines.length) return [];
    const head = lines[0].split(",").map((h) => h.trim().toLowerCase());
    return lines.slice(1).map((line) => {
      const cells = line.split(",").map((c) => c.trim());
      const row = {};
      head.forEach((h, i) => { row[h] = cells[i]; });
      return {
        cluster_code: row.cluster_code, block_code: row.block_code, no: row.no,
        unit_type_code: row.unit_type_code || undefined,
        price: row.price ? Number(row.price) : undefined,
        land_area: row.land_area ? Number(row.land_area) : undefined,
        building_area: row.building_area ? Number(row.building_area) : undefined,
        is_hook: String(row.is_hook || "").toLowerCase() === "true",
      };
    });
  };

  const runImport = async (dryRun) => {
    try {
      const rows = parseCsv(importForm.text);
      if (!rows.length) { toast.error("Tidak ada baris terbaca."); return; }
      const res = await api.post("/masterplan/units/import",
        { project_id: projectId, rows, dry_run: dryRun });
      setImportForm({ ...importForm, result: res.data.data });
      if (!dryRun) { toast.success(`${res.data.data.inserted} unit diimpor.`); onChanged(); }
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengimpor unit."); }
  };

  const removeCluster = async (cluster) => {
    try {
      await api.delete(`/masterplan/clusters/${cluster.id}`);
      toast.success("Cluster dihapus."); setConfirm(null); onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menghapus cluster."); }
  };

  const removeBlock = async (block) => {
    try {
      await api.delete(`/masterplan/blocks/${block.id}`);
      toast.success("Blok dihapus."); setConfirm(null); onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menghapus blok."); }
  };

  const clusters = tree?.clusters || [];

  return (
    <div data-testid={MASTERPLAN.structurePanel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2 text-sm">
          <span className="rounded-md border bg-secondary px-2 py-1">
            {tree?.totals?.clusters || 0} cluster
          </span>
          <span className="rounded-md border bg-secondary px-2 py-1">
            {tree?.totals?.blocks || 0} blok
          </span>
          <span className="rounded-md border bg-secondary px-2 py-1">
            {tree?.totals?.units || 0} unit
          </span>
          {tree?.totals?.unmapped_units ? (
            <span className="rounded-md border bg-amber-50 px-2 py-1 text-amber-800">
              {tree.totals.unmapped_units} unit belum punya cluster
            </span>
          ) : null}
        </div>
        {canManage ? (
          <div className="flex gap-2">
            <Button data-testid={MASTERPLAN.importOpen} size="sm" variant="outline"
              onClick={() => setImportForm({ text: CSV_HINT, result: null })}>
              <FileUp className="mr-1.5 h-4 w-4" /> Impor unit (CSV)
            </Button>
            <Button data-testid={MASTERPLAN.clusterAdd} size="sm"
              onClick={() => setClusterForm({ code: "", name: "", price_multiplier: 1,
                unit_target: "", status: "selling" })}>
              <Plus className="mr-1.5 h-4 w-4" /> Cluster baru
            </Button>
          </div>
        ) : null}
      </div>

      {mapReport?.has_plan && (mapReport.unmapped_count || (mapReport.dangling_shapes || []).length) ? (
        <div data-testid="masterplan-map-warning"
          className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {mapReport.unmapped_count ? (
            <div>
              <strong>{mapReport.unmapped_count} unit belum digambar di Site Plan:</strong>{" "}
              {mapReport.unmapped_units.map((u) => u.code).join(", ")}. Buka Site Plan untuk
              menempatkan kavlingnya agar peta dan data cocok.
            </div>
          ) : null}
          {(mapReport.dangling_shapes || []).length ? (
            <div>
              {mapReport.dangling_shapes.length} bentuk di peta menunjuk unit yang tidak ada
              ({mapReport.dangling_shapes.map((d) => d.label || d.shape_id).join(", ")}).
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="space-y-3">
        {clusters.map((c) => (
          <div key={c.id} data-testid={MASTERPLAN.clusterRow}
            className="rounded-lg border bg-card shadow-[var(--shadow-card)]">
            <div className="flex flex-wrap items-center justify-between gap-2 p-3">
              <button type="button" className="flex items-center gap-2 text-left"
                onClick={() => toggle(c.id)}>
                {open.has(c.id) ? <ChevronDown className="h-4 w-4" />
                  : <ChevronRight className="h-4 w-4" />}
                <Layers className="h-4 w-4 text-primary" />
                <span className="font-medium">{c.code} · {c.name}</span>
                <span className="text-xs text-muted-foreground">{c.status_label}</span>
              </button>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded border bg-secondary px-2 py-0.5">
                  {c.stats?.units || 0} unit · {c.stats?.available || 0} tersedia
                </span>
                <span className="rounded border bg-secondary px-2 py-0.5">
                  absorpsi {c.stats?.absorption_pct || 0}%
                </span>
                <span className="rounded border bg-secondary px-2 py-0.5">
                  nilai {formatIDR(c.stats?.value || 0)}
                </span>
                {c.unit_target ? (
                  <span className="rounded border bg-secondary px-2 py-0.5">
                    target {c.unit_target} unit
                  </span>
                ) : null}
                {canManage ? (
                  <>
                    <Button size="sm" variant="ghost"
                      onClick={() => setClusterForm({ ...c })}>Ubah</Button>
                    <Button data-testid={MASTERPLAN.blockAdd} size="sm" variant="secondary"
                      onClick={() => setBlockForm({ cluster_id: c.id, code: "", name: "" })}>
                      <Plus className="mr-1 h-3.5 w-3.5" /> Blok
                    </Button>
                    <Button data-testid={MASTERPLAN.clusterDelete} size="sm" variant="ghost"
                      onClick={() => setConfirm({ kind: "cluster", row: c })}>
                      <Trash2 className="h-3.5 w-3.5 text-rose-600" />
                    </Button>
                  </>
                ) : null}
              </div>
            </div>
            {open.has(c.id) ? (
              <div className="border-t bg-secondary/40 p-3">
                {(c.blocks || []).length ? (
                  <div className="overflow-x-auto rounded-md border bg-card shadow-[var(--shadow-card)]">
                    <table className="w-full text-sm">
                      <thead className="bg-secondary text-left">
                        <tr>
                          <th className="px-3 py-2 font-medium">Blok</th>
                          <th className="px-3 py-2 font-medium">Nama</th>
                          <th className="px-3 py-2 text-right font-medium">Unit</th>
                          <th className="px-3 py-2 text-right font-medium">Tersedia</th>
                          <th className="px-3 py-2 text-right font-medium">Aksi</th>
                        </tr>
                      </thead>
                      <tbody>
                        {c.blocks.map((b) => (
                          <tr key={b.id} data-testid={MASTERPLAN.blockRow} className="border-t">
                            <td className="px-3 py-2 font-mono text-xs">{b.code}</td>
                            <td className="px-3 py-2">{b.name || "-"}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{b.units_count}</td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {b.available_count}
                            </td>
                            <td className="px-3 py-2 text-right">
                              {canManage ? (
                                <div className="flex justify-end gap-1">
                                  <Button data-testid={MASTERPLAN.genOpen} size="sm"
                                    variant="secondary"
                                    onClick={() => setGenForm({ block_id: b.id, block: b.code,
                                      unit_type_code: "", count: 6, start_no: 1, price: "",
                                      hooks: "" })}>
                                    <Wand2 className="mr-1 h-3.5 w-3.5" /> Buat unit
                                  </Button>
                                  <Button data-testid={MASTERPLAN.blockDelete} size="sm"
                                    variant="ghost"
                                    onClick={() => setConfirm({ kind: "block", row: b })}>
                                    <Trash2 className="h-3.5 w-3.5 text-rose-600" />
                                  </Button>
                                </div>
                              ) : null}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Boxes className="h-4 w-4" /> Belum ada blok pada cluster ini.
                  </p>
                )}
              </div>
            ) : null}
          </div>
        ))}
      </div>

      {/* ---------- dialog cluster ---------- */}
      <Dialog open={!!clusterForm} onOpenChange={(o) => { if (!o) setClusterForm(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{clusterForm?.id ? "Ubah cluster" : "Cluster baru"}</DialogTitle>
            <DialogDescription>
              Pengali harga dipakai saat membuat unit (harga tipe × pengali).
            </DialogDescription>
          </DialogHeader>
          {clusterForm ? (
            <div className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="cl-code">Kode cluster</Label>
                  <Input id="cl-code" data-testid={MASTERPLAN.clusterFormCode}
                    value={clusterForm.code} disabled={!!clusterForm.id} placeholder="otomatis dari aturan penomoran bila kosong"
                    onChange={(e) => setClusterForm({ ...clusterForm,
                      code: e.target.value.toUpperCase() })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="cl-name">Nama cluster</Label>
                  <Input id="cl-name" data-testid={MASTERPLAN.clusterFormName}
                    value={clusterForm.name} placeholder="Harmony Land 5"
                    onChange={(e) => setClusterForm({ ...clusterForm, name: e.target.value })} />
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="space-y-1.5">
                  <Label htmlFor="cl-mult">Pengali harga</Label>
                  <Input id="cl-mult" data-testid={MASTERPLAN.clusterFormMultiplier}
                    type="number" step="0.01" value={clusterForm.price_multiplier ?? 1}
                    onChange={(e) => setClusterForm({ ...clusterForm,
                      price_multiplier: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="cl-target">Target unit</Label>
                  <Input id="cl-target" data-testid={MASTERPLAN.clusterFormTarget} type="number"
                    value={clusterForm.unit_target ?? ""}
                    onChange={(e) => setClusterForm({ ...clusterForm,
                      unit_target: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label>Status cluster</Label>
                  <ReferenceSelect group="cluster_status" value={clusterForm.status}
                    testId="masterplan-cluster-status"
                    onChange={(v) => setClusterForm({ ...clusterForm, status: v })} />
                </div>
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setClusterForm(null)}>Batal</Button>
            <Button data-testid={MASTERPLAN.clusterSubmit} onClick={saveCluster}
              disabled={!clusterForm?.name}>Simpan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ---------- dialog blok ---------- */}
      <Dialog open={!!blockForm} onOpenChange={(o) => { if (!o) setBlockForm(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Blok baru</DialogTitle>
            <DialogDescription>Kode blok menjadi awalan kode unit (mis. D → D-01).</DialogDescription>
          </DialogHeader>
          {blockForm ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="bl-code">Kode blok</Label>
                <Input id="bl-code" data-testid={MASTERPLAN.blockFormCode} value={blockForm.code}
                  placeholder="otomatis dari aturan penomoran bila kosong (mis. D)"
                  onChange={(e) => setBlockForm({ ...blockForm,
                    code: e.target.value.toUpperCase() })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="bl-name">Nama blok (opsional)</Label>
                <Input id="bl-name" data-testid={MASTERPLAN.blockFormName}
                  value={blockForm.name} placeholder="Blok D"
                  onChange={(e) => setBlockForm({ ...blockForm, name: e.target.value })} />
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setBlockForm(null)}>Batal</Button>
            <Button data-testid={MASTERPLAN.blockSubmit} onClick={saveBlock}
              >Simpan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ---------- dialog generate unit ---------- */}
      <Dialog open={!!genForm} onOpenChange={(o) => { if (!o) setGenForm(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Buat unit di blok {genForm?.block}</DialogTitle>
            <DialogDescription>
              Kode unit dibuat otomatis: {genForm?.block}-01, {genForm?.block}-02, dst.
              Unit yang kodenya sudah ada akan dilewati (aman diulang).
            </DialogDescription>
          </DialogHeader>
          {genForm ? (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label>Tipe unit</Label>
                <UnitTypeField value={genForm.unit_type_code} testId={MASTERPLAN.genType}
                  onChange={(v) => setGenForm({ ...genForm, unit_type_code: v })} />
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="space-y-1.5">
                  <Label htmlFor="gn-count">Jumlah unit</Label>
                  <Input id="gn-count" data-testid={MASTERPLAN.genCount} type="number"
                    value={genForm.count}
                    onChange={(e) => setGenForm({ ...genForm, count: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="gn-start">Nomor awal</Label>
                  <Input id="gn-start" data-testid={MASTERPLAN.genStart} type="number"
                    value={genForm.start_no}
                    onChange={(e) => setGenForm({ ...genForm, start_no: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="gn-price">Harga (Rp, opsional)</Label>
                  <RupiahInput id="gn-price" data-testid={MASTERPLAN.genPrice}
                    value={genForm.price} placeholder="kosong = harga tipe × pengali"
                    onChange={(e) => setGenForm({ ...genForm, price: e.target.value })} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="gn-hooks">Nomor unit hook/sudut (pisah koma)</Label>
                <Input id="gn-hooks" data-testid={MASTERPLAN.genHooks} value={genForm.hooks}
                  placeholder="1, 6"
                  onChange={(e) => setGenForm({ ...genForm, hooks: e.target.value })} />
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setGenForm(null)}>Batal</Button>
            <Button data-testid={MASTERPLAN.genSubmit} onClick={runGenerate}
              disabled={!genForm?.unit_type_code}>Buat unit</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ---------- dialog impor ---------- */}
      <Dialog open={!!importForm} onOpenChange={(o) => { if (!o) setImportForm(null); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Impor unit dari CSV</DialogTitle>
            <DialogDescription>
              Tempel isi CSV. Jalankan <strong>Pratinjau</strong> dulu — tidak ada data yang
              ditulis sebelum Anda menekan Impor.
            </DialogDescription>
          </DialogHeader>
          {importForm ? (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="imp-text">Isi CSV</Label>
                <Textarea id="imp-text" data-testid={MASTERPLAN.importText} rows={8}
                  className="font-mono text-xs" value={importForm.text}
                  onChange={(e) => setImportForm({ ...importForm, text: e.target.value })} />
              </div>
              {importForm.result ? (
                <div className="space-y-2 rounded-md border bg-secondary p-3 text-sm">
                  <div>
                    Valid: <strong>{importForm.result.valid}</strong> · Tidak valid:{" "}
                    <strong>{importForm.result.invalid}</strong> · Ditulis:{" "}
                    <strong>{importForm.result.inserted}</strong>
                  </div>
                  {(importForm.result.errors || []).length ? (
                    <ul className="list-inside list-disc text-xs text-rose-700">
                      {importForm.result.errors.map((er, i) => (
                        <li key={i}>Baris {er.row}: {er.reason}</li>
                      ))}
                    </ul>
                  ) : null}
                  {(importForm.result.preview || []).length ? (
                    <div className="text-xs">
                      Contoh: {importForm.result.preview.map((p) => p.code).join(", ")}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setImportForm(null)}>Tutup</Button>
            <Button data-testid={MASTERPLAN.importDry} variant="secondary"
              onClick={() => runImport(true)}>Pratinjau</Button>
            <Button data-testid={MASTERPLAN.importCommit} onClick={() => runImport(false)}
              disabled={!importForm?.result || !importForm?.result?.valid}>Impor</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog open={!!confirm} onOpenChange={(o) => { if (!o) setConfirm(null); }}
        title={confirm?.kind === "cluster" ? "Hapus cluster?" : "Hapus blok?"}
        description={`${confirm?.row?.code} akan dihapus. Tidak bisa dihapus bila masih ada unit.`}
        confirmLabel="Hapus"
        onConfirm={() => (confirm.kind === "cluster"
          ? removeCluster(confirm.row) : removeBlock(confirm.row))} />
    </div>
  );
}
