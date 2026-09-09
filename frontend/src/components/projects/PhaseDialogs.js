import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Layers, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/services/apiClient";
import { PHASE_TPL } from "@/constants/testIds";

/** Terapkan template tahapan (Pusat Konfigurasi) ke fase proyek — nama yang sudah ada dilewati. */
export function ApplyPhaseTemplateDialog({ projectId, open, onOpenChange, onDone }) {
  const [templates, setTemplates] = useState([]);
  const [templateId, setTemplateId] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get("/construction/phase-templates").then((r) => {
      const rows = r.data.data || [];
      setTemplates(rows);
      setTemplateId(rows.find((t) => t.is_default)?.id || rows[0]?.id || "");
    }).catch(() => toast.error("Gagal memuat template tahapan."));
  }, [open]);

  const chosen = templates.find((t) => t.id === templateId);
  const apply = async () => {
    if (!templateId) return;
    setBusy(true);
    try {
      const r = await api.post(`/construction/project/${projectId}/phases/apply`, { template_id: templateId });
      toast.success(r.data.note || "Fase dibuat dari template.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menerapkan template."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Terapkan template tahapan</DialogTitle>
          <DialogDescription>Fase kawasan dibuat mengikuti urutan & bobot template. Fase dengan nama yang sudah ada dilewati.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label>Template</Label>
          <Select value={templateId} onValueChange={setTemplateId}>
            <SelectTrigger data-testid={PHASE_TPL.applySelect} aria-label="Template tahapan"><SelectValue placeholder="Pilih template" /></SelectTrigger>
            <SelectContent>
              {templates.map((t) => <SelectItem key={t.id} value={t.id}>{t.code} — {t.name} ({t.phases_count} fase)</SelectItem>)}
            </SelectContent>
          </Select>
          {chosen ? (
            <ol className="flex flex-wrap gap-1.5 text-xs">
              {chosen.phases.map((p) => <li key={p.order} className="rounded border bg-secondary px-2 py-0.5">{p.order}. {p.name} ({p.weight}%)</li>)}
            </ol>
          ) : null}
          <p className="text-[11px] text-muted-foreground">Kelola template di Pusat Konfigurasi › Tahapan Pembangunan.</p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={PHASE_TPL.applySubmit} onClick={apply} disabled={busy || !templateId}>
            <Layers className="mr-1 h-4 w-4" /> {busy ? "Menerapkan…" : "Terapkan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Tambah satu fase manual (POST /construction/phases — dulu tidak pernah dipanggil layar mana pun). */
export function AddPhaseDialog({ projectId, nextOrder = 1, open, onOpenChange, onDone }) {
  const [form, setForm] = useState({ name: "", weight: "10", planned_pct: "0" });
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setForm({ name: "", weight: "10", planned_pct: "0" }); }, [open]);

  const save = async () => {
    if (form.name.trim().length < 2) { toast.error("Nama fase wajib diisi."); return; }
    setBusy(true);
    try {
      await api.post("/construction/phases", { project_id: projectId, name: form.name.trim(),
        weight: Number(form.weight) || 0, planned_pct: Number(form.planned_pct) || 0, order: nextOrder });
      toast.success(`Fase "${form.name.trim()}" ditambahkan.`);
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menambah fase."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Tambah fase konstruksi</DialogTitle>
          <DialogDescription>Fase kawasan baru pada urutan ke-{nextOrder}.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="space-y-1"><Label htmlFor="addphase-name">Nama fase</Label>
            <Input id="addphase-name" data-testid={PHASE_TPL.addName} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1"><Label htmlFor="addphase-weight">Bobot (%)</Label>
              <Input id="addphase-weight" data-testid={PHASE_TPL.addWeight} type="number" min={1} max={100} value={form.weight} onChange={(e) => setForm({ ...form, weight: e.target.value })} /></div>
            <div className="space-y-1"><Label htmlFor="addphase-planned">Target rencana (%)</Label>
              <Input id="addphase-planned" data-testid={PHASE_TPL.addPlanned} type="number" min={0} max={100} value={form.planned_pct} onChange={(e) => setForm({ ...form, planned_pct: e.target.value })} /></div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={PHASE_TPL.addSubmit} onClick={save} disabled={busy}><Plus className="mr-1 h-4 w-4" /> {busy ? "Menyimpan…" : "Tambah"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
