import React, { useState } from "react";
import { ChevronDown, ChevronUp, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { BUILD } from "@/constants/testIds";

/**
 * Satu ITEM pekerjaan pada template.
 *
 * Semua aturan yang menjaga mutu bangunan diatur di sini: pekerjaan pendahulu yang harus
 * diverifikasi lebih dulu, waktu tunggu (curing) dalam hari, hold point yang menahan
 * pekerjaan berikutnya, jumlah foto bukti minimal, dan checklist mutu (item kritis wajib
 * lulus sebelum hasil kerja bisa diajukan).
 */
export default function BuildStepEditor({ step, index, allCodes = [], onChange, onRemove,
  readOnly = false }) {
  const [open, setOpen] = useState(false);
  const set = (k, v) => onChange({ ...step, [k]: v });
  const checklist = step.checklist || [];
  const preds = step.predecessors || [];

  const setCheck = (i, next) => set("checklist",
    checklist.map((c, idx) => (idx === i ? next : c)));

  return (
    <div data-testid={BUILD.stepRow} data-step={step.code || `baru-${index}`}
      className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <Input aria-label={`Kode item ${index + 1}`} data-testid={`${BUILD.stepRow}-code`}
            data-code={step.code || index} className="h-8 w-24 font-mono text-xs"
            value={step.code || ""} disabled={readOnly}
            onChange={(e) => set("code", e.target.value)} />
          <Input aria-label={`Nama pekerjaan item ${index + 1}`} data-testid={BUILD.stepName}
            data-name={step.code || index} className="h-8 min-w-[12rem] flex-1"
            value={step.name || ""} disabled={readOnly}
            placeholder="mis. Pasangan bata merah"
            onChange={(e) => set("name", e.target.value)} />
        </div>
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="ghost" aria-label={`Rincian item ${step.code || index}`}
            data-testid={`${BUILD.stepRow}-toggle`} data-toggle={step.code || index}
            onClick={() => setOpen((v) => !v)}>
            {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
          {!readOnly ? (
            <Button size="sm" variant="ghost" aria-label={`Hapus item ${step.code || index}`}
              data-testid={BUILD.stepRemove} data-remove={step.code || index}
              onClick={onRemove}>
              <Trash2 className="h-4 w-4" />
            </Button>
          ) : null}
        </div>
      </div>

      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-5">
        <div className="space-y-1">
          <Label className="text-[11px]">Minggu</Label>
          <Input type="number" min={1} className="h-8" disabled={readOnly}
            aria-label={`Minggu item ${step.code || index}`}
            data-testid={`${BUILD.stepRow}-week`} data-week={step.code || index}
            value={step.week} onChange={(e) => set("week", e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label className="text-[11px]">Hari mulai</Label>
          <Input type="number" min={1} className="h-8" disabled={readOnly}
            aria-label={`Hari mulai item ${step.code || index}`}
            data-testid={BUILD.stepDayFrom} data-from={step.code || index}
            value={step.day_from} onChange={(e) => set("day_from", e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label className="text-[11px]">Hari selesai</Label>
          <Input type="number" min={1} className="h-8" disabled={readOnly}
            aria-label={`Hari selesai item ${step.code || index}`}
            data-testid={BUILD.stepDayTo} data-to={step.code || index}
            value={step.day_to} onChange={(e) => set("day_to", e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label className="text-[11px]">Bobot (%)</Label>
          <Input type="number" min={0.5} step={0.5} className="h-8" disabled={readOnly}
            aria-label={`Bobot progres item ${step.code || index}`}
            data-testid={BUILD.stepWeight} data-weight={step.code || index}
            value={step.weight} onChange={(e) => set("weight", e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label className="text-[11px]">Bidang pekerjaan</Label>
          <ReferenceSelect group="work_category" value={step.work_category || ""}
            disabled={readOnly} testId={BUILD.stepCategory}
            onChange={(v) => set("work_category", v)} placeholder="Pilih…" />
        </div>
      </div>

      {open ? (
        <div className="mt-3 space-y-3 border-t pt-3">
          <div className="grid gap-2 sm:grid-cols-3">
            <div className="space-y-1">
              <Label className="text-[11px]">Waktu tunggu (hari)</Label>
              <Input type="number" min={0} className="h-8" disabled={readOnly}
                aria-label={`Waktu tunggu item ${step.code || index}`}
                data-testid={BUILD.stepWait} data-wait={step.code || index}
                value={step.wait_days} onChange={(e) => set("wait_days", e.target.value)} />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label className="text-[11px]">Alasan waktu tunggu</Label>
              <Input className="h-8" disabled={readOnly}
                aria-label={`Alasan waktu tunggu item ${step.code || index}`}
                data-reason={step.code || index}
                placeholder="mis. mortar bata stabil, kurangi retak rambut"
                value={step.wait_reason || ""}
                onChange={(e) => set("wait_reason", e.target.value)} />
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-[11px]">Pekerjaan pendahulu (harus diverifikasi dulu)</Label>
            <div className="flex flex-wrap items-center gap-1.5">
              {!readOnly ? (
                <Select value="" onValueChange={(v) => {
                  if (v && !preds.includes(v)) set("predecessors", [...preds, v]);
                }}>
                  <SelectTrigger className="h-8 w-56" data-testid={BUILD.stepPred}
                    data-pred={step.code || index}
                    aria-label={`Tambah pendahulu item ${step.code || index}`}>
                    <SelectValue placeholder="Tambah pendahulu…" />
                  </SelectTrigger>
                  <SelectContent>
                    {allCodes.map((c) => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : null}
              {preds.map((p) => (
                <button key={p} type="button" data-predchip={p} disabled={readOnly}
                  aria-label={`Hapus pendahulu ${p}`}
                  onClick={() => set("predecessors", preds.filter((x) => x !== p))}
                  className="rounded-full border bg-background px-2 py-0.5 font-mono text-[11px] hover:bg-secondary">
                  {p} ×
                </button>
              ))}
              {!preds.length ? (
                <span className="text-[11px] text-muted-foreground">
                  Tanpa pendahulu = boleh dikerjakan sejak awal.
                </span>
              ) : null}
            </div>
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            <div className="space-y-1">
              <Label className="text-[11px]">Foto bukti minimal</Label>
              <Input type="number" min={0} max={10} className="h-8" disabled={readOnly}
                aria-label={`Jumlah foto minimal item ${step.code || index}`}
                data-testid={BUILD.stepPhotos} data-photos={step.code || index}
                value={step.min_photos} onChange={(e) => set("min_photos", e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-[11px]">Peran pelaksana</Label>
              <ReferenceSelect group="user_role" value={step.assignee_role || ""}
                disabled={readOnly} testId={`${BUILD.stepRow}-assignee`}
                onChange={(v) => set("assignee_role", v)} placeholder="Pilih…" />
            </div>
            <div className="space-y-1">
              <Label className="text-[11px]">Peran verifikator</Label>
              <ReferenceSelect group="user_role" value={step.verify_role || ""}
                disabled={readOnly} testId={`${BUILD.stepRow}-verifier`}
                onChange={(v) => set("verify_role", v)} placeholder="Pilih…" />
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-[11px]">Rincian pekerjaan (pisahkan dengan koma)</Label>
            <Input className="h-8" disabled={readOnly}
              aria-label={`Rincian pekerjaan item ${step.code || index}`}
              data-testid={BUILD.stepTasks} data-tasks={step.code || index}
              value={(step.tasks || []).join(", ")}
              placeholder="mis. galian pondasi, urugan pasir, pasangan batu belah"
              onChange={(e) => set("tasks", e.target.value.split(","))} />
          </div>

          <div className="space-y-2 rounded-lg border bg-background p-2.5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-medium">Hold point (menahan pekerjaan berikutnya)</p>
                <p className="text-[11px] text-muted-foreground">
                  Dipakai untuk titik yang paling sering menyebabkan cacat, mis. bekisting
                  dibuka terlalu cepat.
                </p>
              </div>
              <Switch checked={!!step.hold_point} disabled={readOnly}
                aria-label={`Hold point item ${step.code || index}`}
                data-testid={BUILD.stepHold}
                onCheckedChange={(v) => set("hold_point", v)} />
            </div>
            {step.hold_point ? (
              <Input className="h-8" disabled={readOnly}
                aria-label={`Catatan hold point item ${step.code || index}`}
                data-hold={step.code || index}
                placeholder="mis. tidak boleh lanjut sloof bila pondasi belum terkunci"
                value={step.hold_note || ""}
                onChange={(e) => set("hold_note", e.target.value)} />
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label className="text-[11px]">Checklist mutu</Label>
            {checklist.map((c, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <Input className="h-8 min-w-[14rem] flex-1" disabled={readOnly}
                  aria-label={`Poin checklist ${i + 1} item ${step.code || index}`}
                  data-testid={BUILD.stepCheckText} data-check={`${step.code || index}-${i}`}
                  value={c.text || ""} placeholder="mis. elevasi lantai aman dari jalan"
                  onChange={(e) => setCheck(i, { ...c, text: e.target.value })} />
                <label className="flex items-center gap-1.5 text-[11px]">
                  <Switch checked={!!c.critical} disabled={readOnly}
                    aria-label={`Kritis untuk checklist ${i + 1} item ${step.code || index}`}
                    onCheckedChange={(v) => setCheck(i, { ...c, critical: v })} />
                  kritis
                </label>
                {!readOnly ? (
                  <Button size="sm" variant="ghost"
                    aria-label={`Hapus checklist ${i + 1} item ${step.code || index}`}
                    onClick={() => set("checklist", checklist.filter((_, x) => x !== i))}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                ) : null}
              </div>
            ))}
            {!readOnly ? (
              <Button size="sm" variant="outline" data-testid={BUILD.stepCheckAdd}
                onClick={() => set("checklist", [...checklist, { text: "", critical: false }])}>
                <Plus className="mr-1 h-3.5 w-3.5" /> Tambah poin checklist
              </Button>
            ) : null}
          </div>

          <div className="flex items-start justify-between gap-3 rounded-lg border bg-background p-2.5">
            <div>
              <p className="text-xs font-medium">Gerbang serah terima</p>
              <p className="text-[11px] text-muted-foreground">
                Item terakhir sebelum akad/serah terima — dipakai untuk memastikan final
                check benar-benar dilakukan.
              </p>
            </div>
            <Switch checked={!!step.handover_gate} disabled={readOnly}
              aria-label={`Gerbang serah terima item ${step.code || index}`}
              onCheckedChange={(v) => set("handover_gate", v)} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
