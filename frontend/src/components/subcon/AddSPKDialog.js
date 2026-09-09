import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PROCUREMENT } from "@/constants/testIds";

const EMPTY = { subcontractor_id: "", project_id: "", title: "", scope: "", contract_value: "0", retention_pct: "5", start_date: "", end_date: "" };

export default function AddSPKDialog({ open, onOpenChange, onDone }) {
  const [form, setForm] = useState(EMPTY);
  const [subs, setSubs] = useState([]);
  const [projects, setProjects] = useState([]);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (!open) return;
    setForm(EMPTY);
    Promise.all([api.get("/subcon/subcontractors", { params: { active: "true" } }), api.get("/projects")])
      .then(([rs, rp]) => { setSubs(rs.data.data || []); setProjects(rp.data.data || []); })
      .catch(() => {});
  }, [open]);

  const submit = async () => {
    if (!form.subcontractor_id || !form.project_id || !form.title.trim()) {
      toast.error("Pilih subkontraktor, proyek, dan isi judul."); return;
    }
    setBusy(true);
    try {
      await api.post("/subcon/spk", {
        subcontractor_id: form.subcontractor_id, project_id: form.project_id, title: form.title,
        scope: form.scope || null, contract_value: Math.round(Number(form.contract_value) || 0),
        retention_pct: Number(form.retention_pct) || 0,
        start_date: form.start_date ? new Date(form.start_date).toISOString() : null,
        end_date: form.end_date ? new Date(form.end_date).toISOString() : null,
      });
      toast.success("SPK dibuat.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat SPK."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Buat SPK (Surat Perintah Kerja)</DialogTitle>
          <DialogDescription>Ikat subkontraktor ke proyek dengan nilai kontrak.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5"><Label>Subkontraktor</Label>
            <Select value={form.subcontractor_id} onValueChange={(v) => set("subcontractor_id", v)}>
              <SelectTrigger data-testid="spk-form-sub"><SelectValue placeholder="Pilih…" /></SelectTrigger>
              <SelectContent>{subs.map((s) => <SelectItem key={s.id} value={s.id}>{s.name} ({s.code})</SelectItem>)}</SelectContent>
            </Select></div>
          <div className="space-y-1.5"><Label>Proyek</Label>
            <Select value={form.project_id} onValueChange={(v) => set("project_id", v)}>
              <SelectTrigger data-testid="spk-form-project"><SelectValue placeholder="Pilih…" /></SelectTrigger>
              <SelectContent>{projects.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
            </Select></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="addspkdialog-judul-pekerjaan">Judul Pekerjaan</Label><Input id="addspkdialog-judul-pekerjaan" value={form.title} onChange={(e) => set("title", e.target.value)} placeholder="mis. Pekerjaan Struktur Blok A" /></div>
          <div className="space-y-1.5"><Label htmlFor="addspkdialog-nilai-kontrak-rp">Nilai Kontrak (Rp)</Label><RupiahInput id="addspkdialog-nilai-kontrak-rp" value={form.contract_value} onChange={(e) => set("contract_value", e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="addspkdialog-retensi">Retensi (%)</Label><Input id="addspkdialog-retensi" type="number" value={form.retention_pct} onChange={(e) => set("retention_pct", e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="addspkdialog-mulai">Mulai</Label><Input id="addspkdialog-mulai" type="date" value={form.start_date} onChange={(e) => set("start_date", e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="addspkdialog-selesai">Selesai</Label><Input id="addspkdialog-selesai" type="date" value={form.end_date} onChange={(e) => set("end_date", e.target.value)} /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="addspkdialog-lingkup">Lingkup</Label><Textarea id="addspkdialog-lingkup" rows={2} value={form.scope} onChange={(e) => set("scope", e.target.value)} /></div>
        </div>
        <div className="rounded-lg bg-secondary p-3 text-sm">Nilai kontrak: <span className="font-semibold tabular-nums">{formatIDR(Number(form.contract_value) || 0)}</span></div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={PROCUREMENT.spkAddSubmit} onClick={submit} disabled={busy}>{busy ? "Menyimpan…" : "Simpan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
