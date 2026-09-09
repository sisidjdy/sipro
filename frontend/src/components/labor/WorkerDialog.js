import React, { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { LABOR } from "@/constants/testIds";

/**
 * WorkerDialog — master tenaga kerja harian.
 *
 * Sebelum Fase 47 tenaga kerja harian hanya sebuah ANGKA di buku harian
 * (`site_diaries.workforce`): tidak ada daftar orang, tidak ada tarif, sehingga upah yang
 * dibayar tidak pernah bisa dijelaskan per orang. Tarif harian di sini menjadi dasar hitung
 * upah, jadi ia wajib dan harus angka.
 */
export default function WorkerDialog({ open, onOpenChange, worker, projectId, onDone }) {
  const [form, setForm] = useState({
    name: "", role: "tukang", daily_wage: "", phone: "", note: "", is_active: true,
    project_ids: [],
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setError("");
    setForm({
      name: worker?.name || "", role: worker?.role || "tukang",
      daily_wage: worker?.daily_wage || "", phone: worker?.phone || "",
      note: worker?.note || "", is_active: worker?.is_active !== false,
      project_ids: worker?.project_ids || (projectId ? [projectId] : []),
    });
  }, [open, worker, projectId]);

  const save = async () => {
    setBusy(true); setError("");
    try {
      const body = {
        ...form, daily_wage: Number(form.daily_wage) || 0,
        phone: form.phone.trim() || null, note: form.note.trim() || null,
      };
      if (worker?.id) await api.put(`/labor/workers/${worker.id}`, body);
      else await api.post("/labor/workers", body);
      toast.success(worker?.id ? "Data tenaga kerja diperbarui." : "Tenaga kerja ditambahkan.");
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal menyimpan data tenaga kerja.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={LABOR.workerDialog} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{worker?.id ? "Ubah tenaga kerja" : "Tambah tenaga kerja harian"}</DialogTitle>
          <DialogDescription>
            Tarif harian dipakai untuk menghitung upah &amp; lembur — angka ini yang nanti
            dijelaskan ke orangnya.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="worker-name">Nama lengkap</Label>
            <Input id="worker-name" data-testid={LABOR.workerName} value={form.name}
              placeholder="Mis. Budi Santoso"
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          </div>
          <div className="space-y-1.5">
            <Label>Peran di lapangan</Label>
            <ReferenceSelect group="labor_role" value={form.role}
              testId={LABOR.workerRoleSelect}
              onChange={(v) => setForm((f) => ({ ...f, role: v }))} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="worker-wage">Upah harian (Rp)</Label>
              <RupiahInput id="worker-wage" data-testid={LABOR.workerWage}
                value={form.daily_wage}
                onChange={(e) => setForm((f) => ({ ...f, daily_wage: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="worker-phone">Nomor telepon</Label>
              <Input id="worker-phone" value={form.phone} placeholder="08…"
                onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="worker-note">Keterangan</Label>
            <Textarea id="worker-note" rows={2} value={form.note}
              onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={form.is_active}
              onCheckedChange={(v) => setForm((f) => ({ ...f, is_active: !!v }))} />
            Masih aktif bekerja (yang tidak aktif tidak bisa diabsen)
          </label>
          {error ? (
            <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={LABOR.workerSubmit} disabled={busy} onClick={save}>
            {busy ? "Menyimpan…" : "Simpan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
