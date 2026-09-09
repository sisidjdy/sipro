import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import api from "@/services/apiClient";
import { PHASE_TPL } from "@/constants/testIds";

const emptyRow = () => ({ name: "", weight: 10, planned_pct: 0, work_category: "" });

export default function PhaseTemplateEditor({ template, open, onOpenChange, onSaved }) {
  const [form, setForm] = useState({ code: "", name: "", description: "", phases: [emptyRow()] });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (template) setForm({ code: template.code, name: template.name, description: template.description || "",
      phases: (template.phases || []).map((p) => ({ name: p.name, weight: p.weight, planned_pct: p.planned_pct || 0, work_category: p.work_category || "" })) });
    else setForm({ code: "", name: "", description: "", phases: [emptyRow()] });
  }, [template]);

  const total = form.phases.reduce((a, p) => a + (Number(p.weight) || 0), 0);
  const setRow = (i, k, v) => setForm((f) => ({ ...f, phases: f.phases.map((p, j) => (j === i ? { ...p, [k]: v } : p)) }));
  const move = (i, d) => setForm((f) => {
    const arr = [...f.phases]; const j = i + d;
    if (j < 0 || j >= arr.length) return f;
    [arr[i], arr[j]] = [arr[j], arr[i]];
    return { ...f, phases: arr };
  });

  const save = async () => {
    if (!form.code.trim() || form.name.trim().length < 3) { toast.error("Kode & nama template wajib diisi."); return; }
    if (form.phases.some((p) => p.name.trim().length < 2)) { toast.error("Setiap fase harus punya nama."); return; }
    setBusy(true);
    const payload = { code: form.code.trim().toUpperCase(), name: form.name.trim(), description: form.description || null,
      phases: form.phases.map((p) => ({ name: p.name.trim(), weight: Number(p.weight) || 0, planned_pct: Number(p.planned_pct) || 0, work_category: p.work_category || null })) };
    try {
      const r = template ? await api.put(`/construction/phase-templates/${template.id}`, payload)
        : await api.post("/construction/phase-templates", payload);
      (r.data.warnings || []).forEach((w) => toast.warning(w));
      toast.success(template ? "Template tahapan diperbarui." : "Template tahapan dibuat.");
      onSaved && onSaved();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan template."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{template ? `Ubah template ${template.code}` : "Template tahapan baru"}</DialogTitle>
          <DialogDescription>Urutan fase kawasan proyek beserta bobot progres (ideal total 100%) dan target rencana.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="ptpl-code">Kode</Label>
            <Input id="ptpl-code" data-testid={PHASE_TPL.formCode} value={form.code} disabled={!!template}
              onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="RUKO-2LT" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ptpl-name">Nama template</Label>
            <Input id="ptpl-name" data-testid={PHASE_TPL.formName} value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ruko 2 lantai — 7 fase" />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="ptpl-desc">Keterangan</Label>
            <Input id="ptpl-desc" data-testid={PHASE_TPL.formDesc} value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium">Fase (urut dari atas)</p>
            <span data-testid={PHASE_TPL.totalWeight} className={`text-xs font-semibold ${total === 100 ? "text-emerald-700" : "text-amber-700"}`}>
              Total bobot {total}%
            </span>
          </div>
          {form.phases.map((p, i) => (
            <div key={i} className="grid grid-cols-[1.5rem_1fr_5rem_5rem_10rem_auto] items-center gap-2 rounded-lg border bg-card p-2">
              <span className="text-xs font-semibold text-primary">{i + 1}.</span>
              <Input data-testid={PHASE_TPL.rowName} aria-label={`Nama fase ${i + 1}`} className="h-8" value={p.name}
                onChange={(e) => setRow(i, "name", e.target.value)} placeholder="Nama fase" />
              <Input data-testid={PHASE_TPL.rowWeight} aria-label={`Bobot fase ${i + 1}`} className="h-8" type="number" min={1} max={100}
                value={p.weight} onChange={(e) => setRow(i, "weight", e.target.value)} title="Bobot (%)" />
              <Input data-testid={PHASE_TPL.rowPlanned} aria-label={`Target rencana fase ${i + 1}`} className="h-8" type="number" min={0} max={100}
                value={p.planned_pct} onChange={(e) => setRow(i, "planned_pct", e.target.value)} title="Target rencana (%)" />
              <ReferenceSelect group="work_category" value={p.work_category || ""} allowEmpty emptyLabel="Manual (tanpa sinkron)"
                testId={`${PHASE_TPL.rowName}-category-${i}`} className="h-8"
                onChange={(v) => setRow(i, "work_category", v)} />
              <div className="flex gap-0.5">
                <Button size="icon" variant="ghost" className="h-7 w-7" data-testid={PHASE_TPL.rowUp} aria-label={`Naikkan fase ${i + 1}`} onClick={() => move(i, -1)}><ArrowUp className="h-3.5 w-3.5" /></Button>
                <Button size="icon" variant="ghost" className="h-7 w-7" data-testid={PHASE_TPL.rowDown} aria-label={`Turunkan fase ${i + 1}`} onClick={() => move(i, 1)}><ArrowDown className="h-3.5 w-3.5" /></Button>
                <Button size="icon" variant="ghost" className="h-7 w-7" data-testid={PHASE_TPL.rowRemove} aria-label={`Hapus fase ${i + 1}`} disabled={form.phases.length <= 1}
                  onClick={() => setForm((f) => ({ ...f, phases: f.phases.filter((_, j) => j !== i) }))}><Trash2 className="h-3.5 w-3.5 text-destructive" /></Button>
              </div>
            </div>
          ))}
          <p className="text-[11px] text-muted-foreground">Kolom: nama · bobot (%) · target rencana (%) · <b>kategori pekerjaan unit</b> — bila diisi, progres fase dihitung otomatis dari langkah Template Jadwal unit berkategori sama (tidak ada dua angka untuk satu pekerjaan); kosong = diisi manual.</p>
          <Button size="sm" variant="outline" data-testid={PHASE_TPL.rowAdd}
            onClick={() => setForm((f) => ({ ...f, phases: [...f.phases, emptyRow()] }))}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Tambah fase
          </Button>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={PHASE_TPL.submit} onClick={save} disabled={busy}>{busy ? "Menyimpan…" : "Simpan template"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
