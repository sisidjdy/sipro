import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { PETTY } from "@/constants/testIds";

/** Form pengajuan kas bon. Semua field pilihan memakai daftar SSOT (/api/reference). */
export default function RequestAdvanceDialog({ open, onOpenChange, onSaved }) {
  const [purpose, setPurpose] = useState("");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("biaya_proyek");
  const [projectId, setProjectId] = useState("");
  const [neededDate, setNeededDate] = useState("");
  const [note, setNote] = useState("");
  const [projects, setProjects] = useState([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const loadProjects = useCallback(async () => {
    try {
      const res = await api.get("/projects?limit=100");
      setProjects(res.data.data || []);
    } catch (e) { setProjects([]); }
  }, []);

  useEffect(() => { if (open) { loadProjects(); setErr(""); } }, [open, loadProjects]);

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      await api.post("/petty-cash/advances", {
        purpose, amount: Number(amount), category,
        project_id: projectId || null,
        needed_date: neededDate ? new Date(neededDate).toISOString() : null,
        note: note || null,
      });
      toast.success("Pengajuan kas bon terkirim ke finance.");
      onOpenChange(false);
      setPurpose(""); setAmount(""); setProjectId(""); setNeededDate(""); setNote("");
      onSaved?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || "Gagal mengirim pengajuan kas bon.");
    } finally { setSaving(false); }
  };

  const valid = purpose.trim().length >= 3 && Number(amount) > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={PETTY.requestDialog} className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Ajukan Kas Bon</DialogTitle>
          <DialogDescription>
            Kas bon dicatat sebagai uang muka karyawan, bukan beban. Anda wajib
            mempertanggungjawabkannya setelah dipakai.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="pc-purpose">Keperluan</Label>
            <Input id="pc-purpose" data-testid={PETTY.requestPurpose} value={purpose}
              placeholder="Mis. retribusi & material kecil drainase Blok A"
              onChange={(e) => setPurpose(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="pc-amount">Nominal diajukan (Rp)</Label>
              <RupiahInput id="pc-amount" data-testid={PETTY.requestAmount}
                value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0" />
            </div>
            <div className="space-y-1.5">
              <Label>Kategori</Label>
              <ReferenceSelect group="cashbon_category" value={category} onChange={setCategory}
                testId={PETTY.requestCategory} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Proyek (opsional)</Label>
              <Select value={projectId || "__none__"}
                onValueChange={(v) => setProjectId(v === "__none__" ? "" : v)}>
                <SelectTrigger data-testid={PETTY.requestProject}>
                  <SelectValue placeholder="Tanpa proyek" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Tanpa proyek</SelectItem>
                  {projects.map((p) => (
                    <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pc-date">Tanggal dibutuhkan</Label>
              <Input id="pc-date" data-testid={PETTY.requestDate} type="date" value={neededDate}
                onChange={(e) => setNeededDate(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pc-note">Catatan</Label>
            <Textarea id="pc-note" data-testid={PETTY.requestNote} value={note} rows={2}
              placeholder="Rincian singkat rencana penggunaan"
              onChange={(e) => setNote(e.target.value)} />
          </div>
          {err ? <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-700">{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={PETTY.requestSubmit} disabled={!valid || saving} onClick={submit}>
            {saving ? "Mengirim…" : "Kirim Pengajuan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
