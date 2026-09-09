import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { CalendarRange, Layers, ListChecks } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { shortDate } from "@/utils/buildUi";
import { BUILD } from "@/constants/testIds";

const todayIso = () => new Date().toISOString().slice(0, 10);
const newRef = () => `ui-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

/**
 * FASE 34 — JADWAL MASSAL per blok/cluster.
 *
 * Menjadwalkan rumah satu-satu tidak mungkin untuk proyek puluhan unit, sehingga
 * banyak rumah berjalan TANPA tenggat, pengingat, maupun eskalasi. Dialog ini
 * memilih banyak unit sekaligus, menghitung PRATINJAU (tanggal & jumlah pekerjaan
 * per rumah) lebih dulu, baru dijalankan — dan tidak pernah menimpa jadwal berjalan.
 */
export default function BulkScheduleDialog({ projectId, open, onOpenChange, onDone }) {
  const [rows, setRows] = useState([]);
  const [blocks, setBlocks] = useState([]);
  const [block, setBlock] = useState("");
  const [unitType, setUnitType] = useState("");
  const [picked, setPicked] = useState([]);
  const [start, setStart] = useState(todayIso());
  const [wave, setWave] = useState("same");
  const [stagger, setStagger] = useState(3);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [ref, setRef] = useState(newRef());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [c, b] = await Promise.all([
        api.get("/build/bulk/candidates", {
          params: { project_id: projectId || undefined, block: block || undefined },
        }),
        api.get("/build/bulk/blocks", { params: { project_id: projectId || undefined } }),
      ]);
      setRows(c.data.data || []);
      setBlocks(b.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat daftar rumah belum terjadwal.");
    }
  }, [projectId, block]);

  useEffect(() => {
    if (!open) return;
    setPicked([]); setPreview(null); setResult(null); setStart(todayIso());
    setWave("same"); setStagger(3); setRef(newRef());
    load();
  }, [open, load]);

  const types = useMemo(
    () => [...new Set(rows.map((r) => r.type).filter(Boolean))].sort(), [rows],
  );
  const shown = useMemo(
    () => rows.filter((r) => (!unitType || r.type === unitType)), [rows, unitType],
  );
  const ready = shown.filter((r) => r.schedulable);
  const allPicked = ready.length > 0 && ready.every((r) => picked.includes(r.id));

  const toggle = (id) => {
    setPreview(null); setResult(null);
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  };
  const toggleAll = () => {
    setPreview(null); setResult(null);
    setPicked(allPicked ? [] : ready.map((r) => r.id));
  };

  const body = () => ({
    unit_ids: picked, start_date: start, wave,
    stagger_days: wave === "same" ? 0 : Number(stagger) || 0,
  });

  const runPreview = async () => {
    if (!picked.length) { toast.error("Pilih minimal satu rumah."); return; }
    setBusy(true); setResult(null);
    try {
      const r = await api.post("/build/bulk/schedules/preview", body());
      setPreview({ rows: r.data.data || [], summary: r.data.summary || {} });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menghitung pratinjau.");
    } finally { setBusy(false); }
  };

  const run = async () => {
    setBusy(true);
    try {
      const r = await api.post("/build/bulk/schedules", { ...body(), client_ref: ref });
      const d = r.data?.data || {};
      setResult(d);
      const s = d.summary || {};
      toast.success(`${s.created || 0} jadwal dibuat (${s.items_total || 0} pekerjaan).`
        + (s.skipped ? ` ${s.skipped} unit dilewati.` : ""));
      onDone && onDone(d);
      load();
      setPicked([]); setPreview(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menjalankan jadwal massal.");
    } finally { setBusy(false); }
  };

  const sum = preview?.summary;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={BUILD.bulkDialog}
        className="max-h-[92vh] overflow-y-auto bg-card sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-primary" /> Jadwal massal per blok/cluster
          </DialogTitle>
          <DialogDescription>
            Rumah tanpa jadwal berjalan tanpa tenggat, pengingat, dan eskalasi. Pilih
            rumahnya, periksa pratinjau, baru jalankan. Jadwal yang sudah berjalan tidak
            akan ditimpa.
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 p-2 text-xs text-rose-800">
            {error}
          </p>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label>Blok / cluster</Label>
            <Select value={block || "__all__"}
              onValueChange={(v) => { setBlock(v === "__all__" ? "" : v); setPicked([]); }}>
              <SelectTrigger data-testid={BUILD.bulkBlock} aria-label="Blok">
                <SelectValue placeholder="Semua blok" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Semua blok</SelectItem>
                {blocks.map((b) => (
                  <SelectItem key={b.block} value={b.block}>
                    Blok {b.block} — {b.unscheduled} belum terjadwal
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Tipe unit</Label>
            <Select value={unitType || "__all__"}
              onValueChange={(v) => { setUnitType(v === "__all__" ? "" : v); setPicked([]); }}>
              <SelectTrigger data-testid={BUILD.bulkType} aria-label="Tipe unit">
                <SelectValue placeholder="Semua tipe" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Semua tipe</SelectItem>
                {types.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bulkstart">Tanggal mulai</Label>
            <Input id="bulkstart" type="date" data-testid={BUILD.bulkStart} value={start}
              onChange={(e) => { setStart(e.target.value); setPreview(null); }} />
          </div>
          <div className="space-y-1.5">
            <Label>Pola mulai</Label>
            <ReferenceSelect group="build_bulk_wave" value={wave}
              onChange={(v) => { setWave(v); setPreview(null); }} testId={BUILD.bulkWave} />
          </div>
        </div>

        {wave !== "same" ? (
          <div className="flex items-end gap-3 rounded-lg border bg-background p-2.5">
            <div className="w-40 space-y-1.5">
              <Label htmlFor="bulkstagger">Jeda (hari)</Label>
              <Input id="bulkstagger" type="number" min={0} max={60}
                data-testid={BUILD.bulkStagger} value={stagger}
                onChange={(e) => { setStagger(e.target.value); setPreview(null); }} />
            </div>
            <p className="text-[11px] text-muted-foreground">
              Tukang & material tidak bisa masuk ke semua rumah pada hari yang sama.
              Jeda ini menggeser tanggal mulai tiap {wave === "per_block" ? "blok" : "unit"}.
            </p>
          </div>
        ) : null}

        {/* `bg-card`: panel berbingkai WAJIB punya latar sendiri. Tanpa itu daftar rumah di
            dalam dialog terlihat "menggantung" tanpa kartu — temuan D1 ui_audit_dialogs. */}
        <div className="rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <div className="flex items-center justify-between border-b bg-secondary px-3 py-2">
            <label className="flex items-center gap-2 text-xs font-semibold">
              <Checkbox checked={allPicked} onCheckedChange={toggleAll}
                data-testid={BUILD.bulkSelectAll}
                aria-label="Pilih semua rumah yang bisa dijadwalkan" />
              Pilih semua yang bisa dijadwalkan ({ready.length})
            </label>
            <span className="text-[11px] text-muted-foreground">
              {picked.length} dipilih dari {shown.length} rumah belum terjadwal
            </span>
          </div>
          <div className="max-h-64 overflow-y-auto divide-y">
            {!shown.length ? (
              <p data-testid={BUILD.bulkEmpty} className="p-4 text-center text-xs text-muted-foreground">
                Semua rumah pada saringan ini sudah punya jadwal.
              </p>
            ) : shown.map((r) => (
              <label key={r.id} data-testid={BUILD.bulkCandidate} data-unit={r.code}
                className={`flex items-start gap-3 px-3 py-2 text-xs ${r.schedulable
                  ? "cursor-pointer hover:bg-secondary/60" : "opacity-70"}`}>
                <Checkbox className="mt-0.5" disabled={!r.schedulable}
                  checked={picked.includes(r.id)} onCheckedChange={() => toggle(r.id)}
                  data-testid={BUILD.bulkCandidateCheck}
                  aria-label={`Pilih unit ${r.code}`} />
                <span className="flex-1">
                  <b>{r.code}</b> <span className="text-muted-foreground">· {r.type}</span>
                  <span className="ml-1 rounded bg-secondary px-1 py-0.5 text-[10px]">
                    Blok {r.block}
                  </span>
                  {r.schedulable ? (
                    <span className="block text-[11px] text-muted-foreground">
                      Template {r.template_code} — {r.template_items} pekerjaan /{" "}
                      {r.template_days} hari
                    </span>
                  ) : (
                    <span className="block text-[11px] text-amber-700">{r.reason}</span>
                  )}
                </span>
              </label>
            ))}
          </div>
        </div>

        {preview ? (
          <div data-testid={BUILD.bulkPreview} className="space-y-2 rounded-xl border bg-background p-3">
            <p data-testid={BUILD.bulkPreviewSummary} className="text-xs font-semibold">
              <ListChecks className="mr-1 inline h-3.5 w-3.5" />
              {sum.ready} rumah siap dijadwalkan · {sum.items_total} pekerjaan · mulai{" "}
              {shortDate(sum.first_start)} → target selesai terakhir{" "}
              {shortDate(sum.last_finish)}
              {sum.skipped ? ` · ${sum.skipped} dilewati` : ""}
            </p>
            <div className="max-h-48 overflow-y-auto">
              <table className="w-full text-[11px]">
                <thead className="text-muted-foreground">
                  <tr className="text-left">
                    <th className="py-1">Unit</th><th>Mulai</th><th>Target selesai</th>
                    <th className="text-right">Pekerjaan</th><th className="pl-3">Keterangan</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((r) => (
                    <tr key={r.unit_id} data-testid={BUILD.bulkPreviewRow} data-unit={r.unit_code}
                      className="border-t">
                      <td className="py-1 font-medium">{r.unit_code}</td>
                      <td>{shortDate(r.start_date)}</td>
                      <td>{r.ok ? shortDate(r.target_finish_date) : "-"}</td>
                      <td className="text-right tabular-nums">{r.ok ? r.items : "-"}</td>
                      <td className={`pl-3 ${r.ok ? "text-emerald-700" : "text-amber-700"}`}>
                        {r.ok ? `Template ${r.template_code}` : r.reason}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {result ? (
          <div data-testid={BUILD.bulkResult}
            className="space-y-1 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900">
            <p className="font-semibold">
              Selesai: {result.summary?.created || 0} jadwal dibuat,{" "}
              {result.summary?.skipped || 0} dilewati,{" "}
              {result.summary?.failed || 0} gagal.
            </p>
            <div className="max-h-40 overflow-y-auto">
              {(result.results || []).map((r) => (
                <p key={r.unit_id} data-testid={BUILD.bulkResultRow} data-status={r.status}>
                  <b>{r.unit_code}</b> — {r.status === "created"
                    ? `dijadwalkan ${shortDate(r.start_date)} → ${shortDate(r.target_finish_date)} (${r.items} pekerjaan)`
                    : r.reason}
                </p>
              ))}
            </div>
          </div>
        ) : null}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Tutup
          </Button>
          <Button variant="secondary" data-testid={BUILD.bulkPreviewBtn} onClick={runPreview}
            disabled={busy || !picked.length}>
            <CalendarRange className="mr-1 h-3.5 w-3.5" />
            {busy ? "Menghitung…" : "Periksa pratinjau"}
          </Button>
          <Button data-testid={BUILD.bulkRun} onClick={run}
            disabled={busy || !preview || !(sum?.ready > 0)}>
            {busy ? "Menjalankan…" : `Jalankan (${sum?.ready || 0} rumah)`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
