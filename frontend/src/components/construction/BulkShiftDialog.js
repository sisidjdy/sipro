import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, CalendarClock, Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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

const newRef = () => `ui-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

/**
 * FASE 34 — GESER TANGGAL SERENTAK saat proyek mundur.
 *
 * Sebelum ini, satu-satunya cara memperbaiki tanggal adalah MENGHAPUS jadwal lalu
 * membuat ulang — yang membakar bukti kerja (foto + checklist + verifikasi).
 * Di sini penggeseran jadi operasi resmi: wajib beralasan, dampaknya dipratinjau,
 * dan pekerjaan yang sudah diverifikasi TIDAK ikut bergeser.
 */
export default function BulkShiftDialog({ projectId, open, onOpenChange, onDone }) {
  const [targets, setTargets] = useState([]);
  const [blocks, setBlocks] = useState([]);
  const [scope, setScope] = useState("project");
  const [block, setBlock] = useState("");
  const [picked, setPicked] = useState([]);
  const [days, setDays] = useState(14);
  const [cause, setCause] = useState("");
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [ref, setRef] = useState(newRef());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [t, b] = await Promise.all([
        api.get("/build/bulk/shift/targets",
          { params: { project_id: projectId || undefined } }),
        api.get("/build/bulk/blocks", { params: { project_id: projectId || undefined } }),
      ]);
      setTargets(t.data.data || []);
      setBlocks(b.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat jadwal yang bisa digeser.");
    }
  }, [projectId]);

  useEffect(() => {
    if (!open) return;
    setScope("project"); setBlock(""); setPicked([]); setDays(14); setCause("");
    setNote(""); setPreview(null); setResult(null); setRef(newRef());
    load();
  }, [open, load]);

  const scoped = useMemo(() => {
    if (scope === "block") return targets.filter((t) => t.block === block);
    if (scope === "selection") return targets.filter((t) => picked.includes(t.schedule_id));
    return targets;
  }, [scope, block, picked, targets]);

  const ids = scoped.map((t) => t.schedule_id);
  const problems = [];
  if (!ids.length) problems.push("Belum ada jadwal unit pada cakupan ini.");
  if (!Number(days)) problems.push("Isi jumlah hari geser (positif = mundur, negatif = maju).");
  if (!cause) problems.push("Pilih penyebab penggeseran dari daftar.");
  if (note.trim().length < 10) problems.push("Catatan minimal 10 karakter (jejak audit).");

  const toggle = (id) => {
    setPreview(null); setResult(null);
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  };

  const runPreview = async () => {
    if (!ids.length || !Number(days)) {
      toast.error("Pilih cakupan dan jumlah hari geser lebih dulu.");
      return;
    }
    setBusy(true); setResult(null);
    try {
      const r = await api.post("/build/bulk/shift/preview",
        { schedule_ids: ids, shift_days: Number(days) });
      setPreview({ rows: r.data.data || [], summary: r.data.summary || {} });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menghitung dampak penggeseran.");
    } finally { setBusy(false); }
  };

  const run = async () => {
    if (problems.length) { toast.error(problems[0]); return; }
    setBusy(true);
    try {
      const r = await api.post("/build/bulk/shift", {
        schedule_ids: ids, shift_days: Number(days), cause, note: note.trim(),
        client_ref: ref,
      });
      const d = r.data?.data || {};
      setResult(d);
      const s = d.summary || {};
      toast.success(`${s.shifted || 0} jadwal digeser ${Number(days) > 0 ? "+" : ""}`
        + `${days} hari. ${s.items_locked || 0} pekerjaan terverifikasi dipertahankan.`);
      onDone && onDone(d);
      load();
      setPreview(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menggeser jadwal.");
    } finally { setBusy(false); }
  };

  const sum = preview?.summary;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={BUILD.shiftDialog}
        className="max-h-[92vh] overflow-y-auto bg-card sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarClock className="h-5 w-5 text-primary" /> Geser jadwal serentak
          </DialogTitle>
          <DialogDescription>
            Saat proyek mundur, tenggat seluruh rumah bisa digeser sekali jalan — tanpa
            menghapus jadwal dan tanpa menghilangkan bukti kerja. Pekerjaan yang sudah
            diverifikasi tetap pada tanggal aslinya.
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 p-2 text-xs text-rose-800">
            {error}
          </p>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label>Cakupan</Label>
            <ReferenceSelect group="build_shift_scope" value={scope}
              onChange={(v) => { setScope(v); setPreview(null); }} testId={BUILD.shiftScope} />
          </div>
          {scope === "block" ? (
            <div className="space-y-1.5">
              <Label>Blok</Label>
              <Select value={block} onValueChange={(v) => { setBlock(v); setPreview(null); }}>
                <SelectTrigger data-testid={BUILD.shiftBlock} aria-label="Blok yang digeser">
                  <SelectValue placeholder="Pilih blok…" />
                </SelectTrigger>
                <SelectContent>
                  {blocks.map((b) => (
                    <SelectItem key={b.block} value={b.block}>
                      Blok {b.block} — {b.scheduled} terjadwal
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="shiftdays">Geser (hari)</Label>
            <Input id="shiftdays" type="number" data-testid={BUILD.shiftDays} value={days}
              onChange={(e) => { setDays(e.target.value); setPreview(null); }} />
            <p className="text-[11px] text-muted-foreground">
              Positif = mundur (terlambat) · negatif = maju (percepatan)
            </p>
          </div>
          <div className="space-y-1.5">
            <Label>Penyebab</Label>
            <ReferenceSelect group="build_delay_cause" value={cause} onChange={setCause}
              testId={BUILD.shiftCause} placeholder="Pilih penyebab…" />
          </div>
        </div>

        {scope === "selection" ? (
          <div className="rounded-xl border">
            <div className="flex items-center justify-between border-b bg-secondary px-3 py-2 text-xs">
              <span className="font-semibold">Pilih unit yang digeser</span>
              <span className="text-muted-foreground">{picked.length} dipilih</span>
            </div>
            <div className="max-h-48 divide-y overflow-y-auto">
              {targets.map((t) => (
                <label key={t.schedule_id} data-testid={BUILD.shiftTarget} data-unit={t.unit_code}
                  className="flex cursor-pointer items-center gap-3 px-3 py-2 text-xs hover:bg-secondary/60">
                  <Checkbox checked={picked.includes(t.schedule_id)}
                    onCheckedChange={() => toggle(t.schedule_id)}
                    data-testid={BUILD.shiftTargetCheck}
                    aria-label={`Pilih jadwal ${t.unit_code}`} />
                  <span className="flex-1">
                    <b>{t.unit_code}</b>{" "}
                    <span className="text-muted-foreground">
                      Blok {t.block} · {shortDate(t.start_date)} →
                      {" "}{shortDate(t.target_finish_date)} · {t.items_done}/{t.items_total} selesai
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </div>
        ) : (
          <p className="rounded-lg border bg-background p-2.5 text-[11px] text-muted-foreground">
            {ids.length} jadwal unit masuk cakupan ini
            {scoped.length ? `: ${scoped.slice(0, 10).map((t) => t.unit_code).join(", ")}` : ""}
            {scoped.length > 10 ? `, +${scoped.length - 10} lain` : ""}.
          </p>
        )}

        <div className="space-y-1.5">
          <Label htmlFor="shiftnote">Catatan (wajib — ini jejak audit)</Label>
          <Textarea id="shiftnote" rows={2} data-testid={BUILD.shiftNote} value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Contoh: Hujan tiga pekan berturut-turut, pekerjaan cor tidak bisa dikerjakan." />
        </div>

        {preview ? (
          <div data-testid={BUILD.shiftPreview} className="space-y-2 rounded-xl border bg-background p-3">
            <p data-testid={BUILD.shiftSummary} className="text-xs font-semibold">
              {sum.ready} jadwal siap digeser {sum.shift_days > 0 ? "+" : ""}{sum.shift_days} hari ·{" "}
              {sum.items_shifted} pekerjaan bergeser ·{" "}
              <span className="text-amber-700">
                <Lock className="mr-0.5 inline h-3 w-3" />{sum.items_locked} terverifikasi dipertahankan
              </span>
              {sum.skipped ? ` · ${sum.skipped} dilewati` : ""}
              {sum.new_last_finish ? ` · target terakhir ${shortDate(sum.new_last_finish)}` : ""}
            </p>
            {sum.blocked_by_conflict ? (
              <p data-testid={BUILD.shiftConflict}
                className="rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-800">
                <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />
                {sum.blocked_by_conflict} jadwal tidak bisa digeser sejauh itu karena akan
                menaruh pekerjaan yang belum selesai SEBELUM pekerjaan yang sudah
                diverifikasi. Kurangi jumlah harinya.
              </p>
            ) : null}
            <div className="max-h-52 overflow-y-auto">
              <table className="w-full text-[11px]">
                <thead className="text-muted-foreground">
                  <tr className="text-left">
                    <th className="py-1">Unit</th><th>Mulai</th><th>Target selesai</th>
                    <th className="text-right">Digeser</th><th className="text-right">Dikunci</th>
                    <th className="pl-3">Keterangan</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((r) => (
                    <tr key={r.schedule_id} data-testid={BUILD.shiftPreviewRow}
                      data-unit={r.unit_code} className="border-t">
                      <td className="py-1 font-medium">{r.unit_code}</td>
                      <td>{shortDate(r.old_start)} → <b>{shortDate(r.new_start)}</b></td>
                      <td>{shortDate(r.old_finish)} → <b>{shortDate(r.new_finish)}</b></td>
                      <td className="text-right tabular-nums">{r.items_shifted}</td>
                      <td data-testid={r.items_locked ? BUILD.shiftLocked : undefined}
                        className="text-right tabular-nums text-amber-700">{r.items_locked}</td>
                      <td className={`pl-3 ${r.ok ? "text-emerald-700" : "text-rose-700"}`}>
                        {r.ok ? (r.warning || "Siap digeser") : r.reason}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {result ? (
          <div data-testid={BUILD.shiftResult}
            className="space-y-1 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900">
            <p className="font-semibold">
              Selesai: {result.summary?.shifted || 0} jadwal digeser,{" "}
              {result.summary?.skipped || 0} dilewati. Alasan:{" "}
              {result.summary?.cause_label}.
            </p>
            <div className="max-h-40 overflow-y-auto">
              {(result.results || []).map((r) => (
                <p key={r.schedule_id} data-status={r.status}>
                  <b>{r.unit_code}</b> — {r.status === "shifted"
                    ? `${shortDate(r.old_start)} → ${shortDate(r.new_start)} (${r.items_shifted} pekerjaan digeser, ${r.items_locked} dipertahankan)`
                    : r.reason}
                </p>
              ))}
            </div>
          </div>
        ) : null}

        {problems.length ? (
          <p data-testid={BUILD.shiftHint}
            className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
            Lengkapi dulu: {problems.join(" · ")}
          </p>
        ) : null}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Tutup
          </Button>
          <Button variant="secondary" data-testid={BUILD.shiftPreviewBtn} onClick={runPreview}
            disabled={busy || !ids.length || !Number(days)}>
            {busy ? "Menghitung…" : "Periksa dampak"}
          </Button>
          <Button data-testid={BUILD.shiftRun} onClick={run}
            disabled={busy || problems.length > 0 || !preview || !(sum?.ready > 0)}>
            {busy ? "Menggeser…" : `Geser ${sum?.ready || ids.length} jadwal`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
