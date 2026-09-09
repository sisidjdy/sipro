import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { ErrorState } from "@/components/patterns/StateViews";
import BuildStepEditor from "@/components/construction/BuildStepEditor";
import UnitTypePicker from "@/components/construction/UnitTypePicker";
import api from "@/services/apiClient";
import { BUILD } from "@/constants/testIds";

const BLANK = {
  code: "", name: "", unit_types: [], calendar_mode: "working_days",
  work_days_per_week: 6, holidays: [], description: "", steps: [],
};

const newStep = (n) => ({
  code: `W1-${String(n + 1).padStart(2, "0")}`, name: "", week: 1, day_from: 1, day_to: 1,
  weight: 5, work_category: "persiapan", predecessors: [], wait_days: 0, wait_reason: "",
  hold_point: false, hold_note: "", min_photos: 2, checklist: [], tasks: [],
  assignee_role: "site_engineer", verify_role: "project_manager", handover_gate: false,
});

/**
 * Editor template jadwal: tahapan pekerjaan, bobot, dependensi, waktu tunggu, hold point,
 * jumlah foto bukti minimal, dan checklist mutu — semuanya bisa dikonfigurasi per tipe unit.
 */
export default function BuildTemplateEditor({ templateId, creating, open, onOpenChange,
  onSaved, readOnly = false }) {
  const [form, setForm] = useState(BLANK);
  const [warnings, setWarnings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!open) return;
    if (creating || !templateId) { setForm(BLANK); setWarnings([]); setError(""); return; }
    setLoading(true);
    setError("");
    try {
      const r = await api.get(`/build/templates/${templateId}`);
      const d = r.data.data || {};
      setForm({
        ...BLANK, ...d,
        description: d.description || "",
        steps: (d.steps || []).map((s) => ({
          ...newStep(0), ...s,
          wait_reason: s.wait_reason || "", hold_note: s.hold_note || "",
          checklist: s.checklist || [], tasks: s.tasks || [],
          predecessors: s.predecessors || [],
        })),
      });
      setWarnings(r.data.warnings || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat template.");
    } finally { setLoading(false); }
  }, [open, creating, templateId]);

  useEffect(() => { load(); }, [load]);

  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }));
  const steps = form.steps || [];
  const totalWeight = Math.round(steps.reduce((a, s) => a + Number(s.weight || 0), 0) * 100) / 100;
  const totalDays = steps.reduce((a, s) => Math.max(a, Number(s.day_to || 0)), 0);

  const setStep = (i, next) => setForm((s) => ({
    ...s, steps: s.steps.map((x, idx) => (idx === i ? next : x)),
  }));
  const removeStep = (i) => setForm((s) => ({
    ...s, steps: s.steps.filter((_, idx) => idx !== i),
  }));
  const addStep = () => setForm((s) => ({ ...s, steps: [...s.steps, newStep(s.steps.length)] }));

  const save = async () => {
    if (form.code.trim().length < 2 || form.name.trim().length < 3) {
      toast.error("Kode minimal 2 karakter dan nama minimal 3 karakter.");
      return;
    }
    const bad = steps.find((s) => !s.code || s.name.trim().length < 3
      || Number(s.day_to) < Number(s.day_from) || Number(s.weight) <= 0);
    if (bad) {
      toast.error(`Periksa item '${bad.code || "tanpa kode"}': nama minimal 3 karakter, `
        + "hari selesai tidak boleh lebih awal dari hari mulai, bobot harus di atas 0.");
      return;
    }
    const payload = {
      code: form.code.trim().toUpperCase(), name: form.name.trim(),
      unit_types: form.unit_types || [], project_id: form.project_id || null,
      calendar_mode: form.calendar_mode, work_days_per_week: Number(form.work_days_per_week),
      holidays: form.holidays || [], description: form.description || null,
      steps: steps.map((s) => ({
        code: String(s.code).trim().toUpperCase(), name: s.name.trim(),
        week: Number(s.week) || 1, day_from: Number(s.day_from) || 1,
        day_to: Number(s.day_to) || Number(s.day_from) || 1, weight: Number(s.weight),
        work_category: s.work_category || null,
        predecessors: (s.predecessors || []).filter(Boolean),
        wait_days: Number(s.wait_days) || 0, wait_reason: s.wait_reason || null,
        hold_point: !!s.hold_point, hold_note: s.hold_note || null,
        min_photos: Number(s.min_photos) || 0,
        checklist: (s.checklist || []).filter((c) => (c.text || "").trim().length >= 3)
          .map((c, i) => ({
            code: c.code || `${String(s.code).toUpperCase()}-C${i + 1}`,
            text: c.text.trim(), critical: !!c.critical,
          })),
        assignee_role: s.assignee_role || null, verify_role: s.verify_role || null,
        handover_gate: !!s.handover_gate,
        tasks: (s.tasks || []).map((t) => String(t).trim()).filter(Boolean),
      })),
    };
    setBusy(true);
    try {
      const r = creating || !templateId
        ? await api.post("/build/templates", payload)
        : await api.put(`/build/templates/${templateId}`, payload);
      setWarnings(r.data.warnings || []);
      toast.success(creating ? `Template ${payload.code} dibuat.`
        : `Template ${payload.code} disimpan (versi ${r.data?.data?.version}).`);
      if (r.data?.note) toast.info(r.data.note);
      onSaved && onSaved();
      if (creating) onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan template.");
    } finally { setBusy(false); }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={BUILD.templateEditor}
        className="w-full overflow-y-auto bg-background sm:max-w-3xl">
        <SheetHeader className="sticky top-0 z-10 bg-background pb-2">
          <SheetTitle>
            {creating ? "Template jadwal baru" : `Template ${form.code || "—"}`}
          </SheetTitle>
          <SheetDescription>
            {steps.length} item · bobot total{" "}
            <b className={Math.abs(totalWeight - 100) > 0.5 ? "text-rose-700" : ""}>
              {totalWeight}%
            </b>{" "}· {totalDays} hari kerja
            {readOnly ? " · hanya bisa dilihat (butuh peran Manajer Proyek)" : ""}
          </SheetDescription>
        </SheetHeader>

        {error ? <ErrorState message={error} onRetry={load} /> : null}
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Memuat template…</p>
        ) : (
          <div className="space-y-4 pb-24">
            {warnings.length ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[11px] text-amber-900">
                <p className="font-semibold">Perlu diperiksa</p>
                {warnings.map((w, i) => <p key={i}>• {w}</p>)}
              </div>
            ) : null}

            <div className="grid gap-3 rounded-xl border bg-card p-3 sm:grid-cols-2 shadow-[var(--shadow-card)]">
              <div className="space-y-1.5">
                <Label htmlFor="tpcode">Kode template</Label>
                <Input id="tpcode" data-testid={BUILD.templateCode} value={form.code}
                  disabled={readOnly || !creating}
                  onChange={(e) => set("code", e.target.value)}
                  placeholder="mis. RUMAH-TAPAK-60" />
                {!creating ? (
                  <p className="text-[11px] text-muted-foreground">
                    Kode tidak bisa diubah agar jejak jadwal lama tetap terbaca.
                  </p>
                ) : null}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tpname">Nama template</Label>
                <Input id="tpname" data-testid={BUILD.templateName} value={form.name}
                  disabled={readOnly} onChange={(e) => set("name", e.target.value)}
                  placeholder="mis. Rumah tapak 9 minggu" />
              </div>
              <div className="space-y-1.5">
                <Label>Perhitungan hari</Label>
                <ReferenceSelect group="build_calendar_mode" value={form.calendar_mode}
                  disabled={readOnly} testId={BUILD.calendarMode}
                  onChange={(v) => set("calendar_mode", v)} />
              </div>
              <div className="space-y-1.5">
                <Label>Hari kerja per minggu</Label>
                <ReferenceSelect group="build_work_week"
                  value={String(form.work_days_per_week)} disabled={readOnly}
                  testId={BUILD.workWeek}
                  onChange={(v) => set("work_days_per_week", Number(v))} />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label>Berlaku untuk tipe unit</Label>
                <UnitTypePicker value={form.unit_types || []}
                  onChange={(v) => set("unit_types", v)} />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="tpdesc">Keterangan</Label>
                <Textarea id="tpdesc" rows={2} value={form.description || ""}
                  disabled={readOnly} onChange={(e) => set("description", e.target.value)}
                  placeholder="mis. standar rumah tapak 1 lantai, 60 hari kerja" />
              </div>
            </div>

            <div className="space-y-2">
              {steps.map((s, i) => (
                <BuildStepEditor key={`${s.code}-${i}`} step={s} index={i} readOnly={readOnly}
                  allCodes={steps.map((x) => x.code).filter((c) => c && c !== s.code)}
                  onChange={(next) => setStep(i, next)} onRemove={() => removeStep(i)} />
              ))}
              {!steps.length ? (
                <p className="rounded-xl border border-dashed bg-card p-6 text-center text-sm text-muted-foreground">
                  Belum ada item pekerjaan. Tambah item, atau duplikat template default
                  lalu sesuaikan.
                </p>
              ) : null}
              {!readOnly ? (
                <Button variant="outline" className="w-full" data-testid={BUILD.stepAdd}
                  onClick={addStep}>
                  <Plus className="mr-1 h-4 w-4" /> Tambah item pekerjaan
                </Button>
              ) : null}
            </div>
          </div>
        )}

        {!readOnly && !loading ? (
          <div className="sticky bottom-0 -mx-6 flex items-center justify-between gap-2 border-t bg-background px-6 py-3">
            <p className="text-[11px] text-muted-foreground">
              Jadwal unit yang sudah dibuat tidak berubah.
            </p>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
                Tutup
              </Button>
              <Button data-testid={BUILD.templateSave} onClick={save} disabled={busy}>
                <Save className="mr-1 h-4 w-4" /> {busy ? "Menyimpan…" : "Simpan template"}
              </Button>
            </div>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
