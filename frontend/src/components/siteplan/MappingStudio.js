import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Upload, Sparkles, Trash2, MapPinned } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import api from "@/services/apiClient";
import { SITE_PLAN } from "@/constants/testIds";

const KINDS = ["lot", "road", "green", "water", "facility", "boundary"];
const KIND_TEXT = {
  lot: "Kavling", road: "Jalan", green: "Taman", water: "Air/Danau",
  facility: "Fasilitas", boundary: "Batas lahan",
};

/**
 * Studio Pemetaan — menyiapkan peta SVG proyek:
 * 1) bangkitkan peta realistis (sementara, sebelum SVG arsitek tersedia), atau
 * 2) unggah SVG asli lalu cocokkan setiap bentuk ke unit (otomatis + manual).
 */
export default function MappingStudio({ open, onOpenChange, projectId, plan, units, onChanged }) {
  const [busy, setBusy] = useState("");
  const [pending, setPending] = useState({});

  useEffect(() => { if (open) setPending({}); }, [open]);

  const shapes = plan?.shapes || [];
  const lots = useMemo(() => shapes.filter((s) => s.kind === "lot"), [shapes]);
  const mappedUnitIds = useMemo(
    () => new Set(shapes.map((s) => s.unit_id).filter(Boolean)), [shapes]);
  const unmappedUnits = useMemo(
    () => units.filter((u) => !mappedUnitIds.has(u.id)), [units, mappedUnitIds]);
  const unmappedLots = useMemo(() => lots.filter((s) => !s.unit_id), [lots]);

  const call = useCallback(async (label, fn) => {
    setBusy(label);
    try {
      await fn();
      await onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Aksi peta gagal diproses.");
    } finally { setBusy(""); }
  }, [onChanged]);

  const generate = () => call("generate", async () => {
    const res = await api.post(`/site-plan/${projectId}/generate`);
    const st = res.data?.data?.stats;
    toast.success(`Peta dibangkitkan: ${st?.total_lots || 0} kavling, cakupan ${st?.coverage_pct || 0}%.`);
  });

  const upload = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      await call("upload", async () => {
        const res = await api.post(`/site-plan/${projectId}/svg`, {
          svg: String(reader.result || ""), filename: file.name,
        });
        const d = res.data?.data;
        toast.success(`SVG terbaca: ${d?.stats?.total_shapes || 0} bentuk, ${d?.auto_matched || 0} kavling tercocokkan otomatis.`);
      });
    };
    reader.readAsText(file);
  };

  const savePending = () => call("save", async () => {
    const items = Object.entries(pending).map(([shape_id, v]) => ({ shape_id, ...v }));
    if (!items.length) return;
    const res = await api.put(`/site-plan/${projectId}/mapping`, { items });
    setPending({});
    toast.success(`Pemetaan tersimpan. Cakupan ${res.data?.data?.stats?.coverage_pct || 0}%.`);
  });

  const removePlan = () => call("delete", async () => {
    await api.delete(`/site-plan/${projectId}/plan`);
    toast.success("Peta SVG dihapus — kembali ke tata letak blok otomatis.");
  });

  const setPick = (shapeId, patch) =>
    setPending((p) => ({ ...p, [shapeId]: { ...(p[shapeId] || {}), ...patch } }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={SITE_PLAN.studio} className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <MapPinned className="h-4 w-4 text-primary" /> Studio Pemetaan Site Plan
          </DialogTitle>
          <DialogDescription>
            Peta memakai geometri SVG (kavling, jalan, taman, fasilitas). Selama SVG asli
            dari arsitek belum ada, bangkitkan peta realistis agar semua fitur tetap bisa dipakai.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
              <p className="text-[11px] uppercase text-muted-foreground">Sumber peta</p>
              <p className="text-sm font-semibold">
                {plan ? (plan.source === "uploaded" ? `SVG unggahan${plan.filename ? ` (${plan.filename})` : ""}` : "Dibangkitkan sistem") : "Belum ada peta"}
              </p>
            </div>
            <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
              <p className="text-[11px] uppercase text-muted-foreground">Cakupan pemetaan</p>
              <p data-testid={SITE_PLAN.coverage} className="text-sm font-semibold">
                {plan?.stats?.mapped || 0} / {units.length} kavling ({plan?.stats?.coverage_pct || 0}%)
              </p>
            </div>
            <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
              <p className="text-[11px] uppercase text-muted-foreground">Bentuk terbaca</p>
              <p className="text-sm font-semibold">
                {plan?.stats?.total_shapes || 0} bentuk · {plan?.stats?.total_lots || 0} kavling
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-3 rounded-lg border bg-secondary/30 p-3">
            <Button data-testid={SITE_PLAN.generateBtn} disabled={busy === "generate"}
              onClick={generate}>
              <Sparkles className="mr-1.5 h-4 w-4" />
              {busy === "generate" ? "Membangkitkan…" : plan ? "Bangkitkan Ulang" : "Bangkitkan Peta Realistis"}
            </Button>
            <div className="space-y-1">
              <Label htmlFor="svg-file">Berkas SVG site plan (opsional)</Label>
              <Input id="svg-file" data-testid={SITE_PLAN.uploadInput} type="file" accept=".svg,image/svg+xml"
                className="w-64" onChange={(e) => upload(e.target.files?.[0])} />
            </div>
            {plan ? (
              <Button variant="outline" data-testid={SITE_PLAN.deletePlanBtn}
                disabled={busy === "delete"} onClick={removePlan}>
                <Trash2 className="mr-1.5 h-4 w-4" /> Hapus Peta
              </Button>
            ) : null}
          </div>

          {plan ? (
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase text-muted-foreground">
                Bentuk kavling belum terpetakan ({unmappedLots.length})
              </p>
              {unmappedLots.length ? (
                <div className="max-h-56 space-y-1.5 overflow-y-auto rounded-lg border bg-card p-2 shadow-[var(--shadow-card)]">
                  {unmappedLots.slice(0, 60).map((s) => (
                    <div key={s.shape_id} data-testid={SITE_PLAN.shapeRow}
                      className="flex flex-wrap items-center gap-2 rounded-md bg-card px-2 py-1.5">
                      <span className="min-w-[140px] truncate text-xs font-medium">
                        {s.label || s.shape_id}
                      </span>
                      <Select value={pending[s.shape_id]?.unit_id || ""}
                        onValueChange={(v) => setPick(s.shape_id, { unit_id: v })}>
                        <SelectTrigger data-testid={SITE_PLAN.shapeUnitSelect} className="h-8 w-48">
                          <SelectValue placeholder="Pilih unit…" />
                        </SelectTrigger>
                        <SelectContent>
                          {unmappedUnits.map((u) => (
                            <SelectItem key={u.id} value={u.id}>{u.code}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Select value={pending[s.shape_id]?.kind || s.kind}
                        onValueChange={(v) => setPick(s.shape_id, { kind: v })}>
                        <SelectTrigger className="h-8 w-36">
                          <SelectValue placeholder="Jenis bentuk" />
                        </SelectTrigger>
                        <SelectContent>
                          {KINDS.map((k) => (
                            <SelectItem key={k} value={k}>{KIND_TEXT[k]}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="rounded-lg border bg-emerald-50 p-2.5 text-sm text-emerald-800">
                  Semua bentuk kavling sudah terpetakan ke unit.
                </p>
              )}
              {unmappedUnits.length ? (
                <p className="text-xs text-amber-700">
                  {unmappedUnits.length} unit belum punya bentuk di peta:{" "}
                  {unmappedUnits.slice(0, 12).map((u) => u.code).join(", ")}
                  {unmappedUnits.length > 12 ? ", …" : ""}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Tutup</Button>
          <Button data-testid={SITE_PLAN.saveMappingBtn} onClick={savePending}
            disabled={!Object.keys(pending).length || busy === "save"}>
            {busy === "save" ? "Menyimpan…" : `Simpan Pemetaan (${Object.keys(pending).length})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
