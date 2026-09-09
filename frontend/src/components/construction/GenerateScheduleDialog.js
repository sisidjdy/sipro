import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/services/apiClient";
import { BUILD } from "@/constants/testIds";

const todayIso = () => new Date().toISOString().slice(0, 10);

/**
 * Menetapkan JADWAL pembangunan satu unit dari template tipe unitnya.
 *
 * Tanggal mulai wajib karena seluruh tenggat, pengingat, dan eskalasi dihitung dari
 * tanggal ini — bukan dari persen yang diketik manual seperti versi lama.
 */
export default function GenerateScheduleDialog({ projectId, open, onOpenChange, onDone,
  presetUnitId = null }) {
  const [units, setUnits] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [unitId, setUnitId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [start, setStart] = useState(todayIso());
  const [regenerate, setRegenerate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [u, t] = await Promise.all([
        api.get("/build/unscheduled", { params: { project_id: projectId || undefined } }),
        api.get("/build/templates", { params: { project_id: projectId || undefined } }),
      ]);
      setUnits(u.data.data || []);
      setTemplates(t.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat daftar unit/template.");
    }
  }, [projectId]);

  useEffect(() => {
    if (!open) return;
    setUnitId(presetUnitId || "");
    setTemplateId("");
    setStart(todayIso());
    setRegenerate(false);
    load();
  }, [open, presetUnitId, load]);

  const unit = units.find((u) => u.id === unitId);
  const norm = (v) => String(v || "").trim().toLowerCase();
  const matching = unit
    ? templates.filter((t) => !(t.unit_types || []).length
      || (t.unit_types || []).some((x) => [norm(unit.type), norm(unit.unit_type_code)]
        .includes(norm(x))))
    : templates;

  const submit = async () => {
    if (!unitId) { toast.error("Pilih unit yang akan dijadwalkan."); return; }
    if (!start) { toast.error("Tanggal mulai wajib diisi."); return; }
    setBusy(true);
    try {
      const res = await api.post("/build/schedules", {
        unit_id: unitId, start_date: start,
        template_id: templateId || null, regenerate,
      });
      const d = res.data?.data || {};
      toast.success(`Jadwal unit ${d.unit_code} dibuat: ${d.items_total} pekerjaan, `
        + `target selesai ${d.target_finish_date}.`);
      onOpenChange(false);
      onDone && onDone(d);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membuat jadwal.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={BUILD.generateDialog} className="bg-card sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarPlus className="h-5 w-5 text-primary" /> Buat jadwal pembangunan unit
          </DialogTitle>
          <DialogDescription>
            Tenggat, pengingat, dan eskalasi dihitung dari tanggal mulai + template tipe unit.
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 p-2 text-xs text-rose-800">
            {error}
          </p>
        ) : null}

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Unit rumah</Label>
            <Select value={unitId} onValueChange={setUnitId}>
              <SelectTrigger data-testid={BUILD.generateUnit}
                aria-label="Unit yang akan dijadwalkan">
                <SelectValue placeholder={units.length
                  ? "Pilih unit belum terjadwal…" : "Semua unit sudah terjadwal"} />
              </SelectTrigger>
              <SelectContent>
                {units.map((u) => (
                  <SelectItem key={u.id} value={u.id} disabled={!u.buildable}>
                    {u.code} — {u.type}{u.buildable ? "" : " (dijual sebagai tanah)"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!units.length ? (
              <p className="text-[11px] text-muted-foreground">
                Semua unit pada proyek ini sudah punya jadwal.
              </p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label>Template jadwal</Label>
            <Select value={templateId} onValueChange={setTemplateId}>
              <SelectTrigger data-testid={BUILD.generateTemplate}
                aria-label="Template jadwal pembangunan">
                <SelectValue placeholder="Otomatis sesuai tipe unit" />
              </SelectTrigger>
              <SelectContent>
                {matching.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.code} — {t.name} ({t.steps_count} item / {t.total_days} hari)
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-muted-foreground">
              Dibiarkan kosong berarti memakai template default tipe{" "}
              {unit?.type || "unit"} yang berlaku.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="bstart">Tanggal mulai pembangunan</Label>
            <Input id="bstart" type="date" data-testid={BUILD.generateStart} value={start}
              onChange={(e) => setStart(e.target.value)} />
          </div>

          <div className="flex items-start justify-between gap-3 rounded-lg border bg-background p-2.5">
            <div>
              <p className="text-xs font-medium">Buat ulang bila sudah ada jadwal</p>
              <p className="text-[11px] text-muted-foreground">
                Hanya boleh bila belum ada pekerjaan yang diverifikasi.
              </p>
            </div>
            <Switch checked={regenerate} onCheckedChange={setRegenerate}
              aria-label="Buat ulang jadwal yang sudah ada" />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Batal
          </Button>
          <Button data-testid={BUILD.generateSubmit} onClick={submit} disabled={busy}>
            {busy ? "Membuat…" : "Buat jadwal"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
