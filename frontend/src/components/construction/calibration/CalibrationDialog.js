import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  AlertTriangle, CheckCircle2, Minus, Plus, ShieldCheck, SlidersHorizontal,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import RefLabel from "@/components/patterns/RefLabel";
import api from "@/services/apiClient";
import {
  KIND_DEFAULT, changeText, dayRange, durationText, needsDelta, newClientRef, rowShift,
  suggestedDelta, waitText,
} from "@/utils/calibrationUi";
import { CALIB } from "@/constants/testIds";

/**
 * KALIBRASI SEKALI KLIK (Fase 37) — satu dialog: pratinjau, alasan, terapkan.
 *
 * Sebelum ini rekomendasi Analitik Telat berujung pada kalimat "buka Template Jadwal lalu
 * ubah hari mulai/selesai": perencana harus pindah layar dan MENGETIK ULANG seluruh
 * template, sehingga dalam praktiknya kalibrasi tidak pernah dilakukan dan analitik jadi
 * hiasan. Di sini angkanya datang dari template itu sendiri, dampaknya dipratinjau lebih
 * dulu, dan yang ditampilkan pratinjau PERSIS sama dengan yang tersimpan (satu fungsi
 * hitung dipakai keduanya di backend).
 *
 * Kejujuran yang dijaga di layar: kalibrasi mengubah TEMPLATE, bukan jadwal rumah yang
 * sudah berjalan — bukti kerja tidak boleh bergeser. Angka baru berlaku untuk jadwal
 * berikutnya; menggeser tanggal jadwal berjalan tetap lewat "Geser jadwal" (Fase 34).
 */
export default function CalibrationDialog({
  open, onOpenChange, target, initialKind, initialDelta, source, canCalibrate = true, onDone,
}) {
  const [kind, setKind] = useState(KIND_DEFAULT);
  const [delta, setDelta] = useState(1);
  const [cause, setCause] = useState("");
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewErr, setPreviewErr] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [ref, setRef] = useState(newClientRef());
  const timer = useRef(null);

  const cur = target?.current || null;

  useEffect(() => {
    if (!open || !target) return;
    const k = initialKind || KIND_DEFAULT;
    setKind(k);
    setDelta(suggestedDelta(k, target, initialDelta));
    setCause("");
    setNote("");
    setPreview(null);
    setPreviewErr("");
    setResult(null);
    setRef(newClientRef());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, target?.template_id, target?.step_code, initialKind, initialDelta]);

  const runPreview = useCallback(async () => {
    if (!target) return;
    setBusy(true);
    setPreviewErr("");
    try {
      const r = await api.post("/build/calibration/preview", {
        template_id: target.template_id,
        step_code: target.step_code,
        kind,
        delta_days: needsDelta(kind) ? Number(delta || 0) : 0,
      });
      setPreview(r.data?.data || null);
    } catch (e) {
      setPreview(null);
      setPreviewErr(e?.response?.data?.detail
        || "Gagal menghitung dampak kalibrasi. Coba lagi.");
    } finally { setBusy(false); }
  }, [target, kind, delta]);

  // Pratinjau ikut berubah otomatis: perencana tidak boleh sempat melihat angka lama
  // sementara pilihannya sudah berubah (itu sumber salah tekan yang mahal).
  useEffect(() => {
    if (!open || !target || result) return;
    if (needsDelta(kind) && !Number(delta)) { setPreview(null); return; }
    clearTimeout(timer.current);
    timer.current = setTimeout(runPreview, 320);
    return () => clearTimeout(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, kind, delta, target?.template_id, target?.step_code, result]);

  const problems = [];
  if (needsDelta(kind) && !Number(delta)) problems.push("isi jumlah hari perubahan");
  if (!preview) problems.push("tunggu pratinjau dampak selesai dihitung");
  if (!cause) problems.push("pilih alasan kalibrasi");
  if (note.trim().length < 10) problems.push("catatan minimal 10 karakter (jejak audit)");

  const apply = async () => {
    if (problems.length) { toast.error(`Lengkapi dulu: ${problems[0]}.`); return; }
    setBusy(true);
    try {
      const r = await api.post("/build/calibration/apply", {
        template_id: target.template_id,
        step_code: target.step_code,
        kind,
        delta_days: needsDelta(kind) ? Number(delta || 0) : 0,
        cause,
        note: note.trim(),
        client_ref: ref,
        source: source || "calibration_page",
      });
      setResult({ ...(r.data?.data || {}), message: r.data?.message, replayed: r.data?.replayed });
      toast.success(r.data?.message || "Kalibrasi template diterapkan.");
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menerapkan kalibrasi.");
    } finally { setBusy(false); }
  };

  const bump = (n) => { setResult(null); setDelta((v) => Number(v || 0) + n); };
  const imp = preview?.impact || {};

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={CALIB.dialog}
        className="max-h-[92vh] overflow-y-auto bg-card sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            <SlidersHorizontal className="h-5 w-5 text-primary" />
            Kalibrasi langkah{" "}
            <span className="font-mono text-sm">{target?.step_code}</span>
            <span className="text-sm font-normal text-muted-foreground">
              {target?.step_name}
            </span>
          </DialogTitle>
          <DialogDescription>
            Mengubah angka pada template <b>{target?.template_code}</b>. Jadwal rumah yang
            sudah dibuat TIDAK diubah — bukti kerja tidak boleh bergeser; angka baru berlaku
            untuk jadwal berikutnya.
          </DialogDescription>
        </DialogHeader>

        {cur ? (
          <div className="grid gap-2 rounded-xl border bg-background p-3 text-xs sm:grid-cols-3">
            <Fact label="Rencana sekarang" value={durationText(cur)} hint={dayRange(cur)} />
            <Fact label="Waktu tunggu wajib" value={waitText(cur)}
              hint={cur.wait_reason || "tidak ada syarat tunggu"} />
            <Fact label="Bukti keterlambatan"
              value={target.late
                ? `${target.late.units_late}/${target.late.units_total} rumah telat`
                : "belum ada bukti telat"}
              hint={target.late
                ? `rata-rata ${target.late.avg_days} hari · maksimal ${target.late.max_days} hari`
                : "langkah ini belum pernah tercatat telat"} />
          </div>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Jenis kalibrasi</Label>
            <ReferenceSelect group="calibration_kind" value={kind}
              onChange={(v) => { setResult(null); setKind(v); setDelta(suggestedDelta(v, target)); }}
              testId={CALIB.dialogKind} disabled={!!result} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="calib-delta">Jumlah hari perubahan</Label>
            {needsDelta(kind) ? (
              <div className="flex items-center gap-1.5">
                <Button type="button" variant="outline" size="icon" className="h-9 w-9"
                  data-testid={CALIB.dialogMinus} aria-label="Kurangi satu hari"
                  disabled={!!result} onClick={() => bump(-1)}>
                  <Minus className="h-4 w-4" />
                </Button>
                <Input id="calib-delta" type="number" className="text-center"
                  data-testid={CALIB.dialogDelta} value={delta} disabled={!!result}
                  onChange={(e) => { setResult(null); setDelta(e.target.value); }} />
                <Button type="button" variant="outline" size="icon" className="h-9 w-9"
                  data-testid={CALIB.dialogPlus} aria-label="Tambah satu hari"
                  disabled={!!result} onClick={() => bump(1)}>
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <p className="rounded-lg border bg-secondary px-2.5 py-2 text-[11px] text-muted-foreground">
                Dihitung sistem dari kekurangan jeda pada template — tidak perlu (dan tidak
                boleh) diketik manual.
              </p>
            )}
            {needsDelta(kind) && target?.late ? (
              <p className="text-[11px] text-muted-foreground">
                Bukti: rata-rata telat {target.late.avg_days} hari (maksimal{" "}
                {target.late.max_days} hari) pada {target.late.units_late} dari{" "}
                {target.late.units_total} rumah — putuskan sendiri berapa hari yang wajar.
              </p>
            ) : null}
          </div>
        </div>

        {previewErr ? (
          <p data-testid={CALIB.dialogError}
            className="rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-900">
            <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />{previewErr}
          </p>
        ) : null}

        {preview ? (
          <div data-testid={CALIB.dialogPreview} className="space-y-2.5 rounded-xl border bg-background p-3">
            <p data-testid={CALIB.dialogExplain} className="text-xs font-medium">
              {preview.explain}
            </p>
            <div className="flex flex-wrap gap-2 text-[11px]">
              <Chip tone="border-sky-200 bg-sky-50 text-sky-900">
                Total durasi template {preview.total_days_before} →{" "}
                <b>{preview.total_days_after}</b> hari kerja
              </Chip>
              <Chip tone={preview.shifted_count
                ? "border-amber-200 bg-amber-50 text-amber-900"
                : "border-emerald-200 bg-emerald-50 text-emerald-900"}>
                {preview.shifted_count} langkah setelahnya ikut bergeser
              </Chip>
              <Chip tone={preview.moves_planned_dates
                ? "border-violet-200 bg-violet-50 text-violet-900"
                : "border-slate-200 bg-slate-50 text-slate-800"}>
                {preview.moves_planned_dates
                  ? "tanggal rencana bergeser"
                  : "tanggal rencana tidak bergeser"}
              </Chip>
            </div>

            <div data-testid={CALIB.dialogImpact}
              className="space-y-1 rounded-lg border border-emerald-200 bg-emerald-50 p-2.5 text-[11px] text-emerald-900">
              <p><ShieldCheck className="mr-1 inline h-3.5 w-3.5" />
                {imp.schedules_unchanged_note}</p>
              <p>
                Angka baru dipakai saat jadwal dibuat untuk{" "}
                <b>{imp.units_unscheduled ?? 0} rumah</b> yang belum dijadwalkan
                {(imp.unit_types || []).length
                  ? ` (tipe ${(imp.unit_types || []).join(", ")}, ${imp.units_matching} rumah cocok)`
                  : ""}.
              </p>
            </div>

            <div className="max-h-52 overflow-y-auto">
              <table className="w-full text-[11px]">
                <thead className="sticky top-0 bg-background text-left text-muted-foreground">
                  <tr>
                    <th className="py-1">Langkah</th>
                    <th>Sebelum → sesudah</th>
                    <th className="text-right">Peran</th>
                  </tr>
                </thead>
                <tbody>
                  {(preview.rows || []).map((r) => (
                    <tr key={r.code} data-testid={CALIB.dialogPreviewRow} data-step={r.code}
                      className="border-t">
                      <td className="py-1 pr-2">
                        <span className="font-mono font-semibold">{r.code}</span>
                        <span className="ml-1.5 text-muted-foreground">{r.name}</span>
                      </td>
                      <td className="tabular-nums">{rowShift(r)}</td>
                      <td className="text-right">
                        {r.is_target ? (
                          <span className="rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 font-medium text-sky-900">
                            dikalibrasi
                          </span>
                        ) : (
                          <span className="text-muted-foreground">ikut bergeser</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {!result && canCalibrate ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Alasan kalibrasi</Label>
              <ReferenceSelect group="calibration_cause" value={cause} onChange={setCause}
                testId={CALIB.dialogCause} placeholder="Pilih alasan…" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="calib-note">Catatan (wajib — ini jejak audit)</Label>
              <Textarea id="calib-note" rows={2} data-testid={CALIB.dialogNote} value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Contoh: tiga rumah terakhir selalu telat 3 hari pada langkah ini karena pengiriman keramik." />
              <p className="text-[11px] text-muted-foreground">
                {note.trim().length}/10 karakter minimal
              </p>
            </div>
          </div>
        ) : null}

        {result ? (
          <div data-testid={CALIB.dialogResult}
            className="space-y-1 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900">
            <p className="font-semibold">
              <CheckCircle2 className="mr-1 inline h-4 w-4" />
              {result.replayed ? "Kalibrasi ini sudah tercatat sebelumnya (tidak digandakan)."
                : "Kalibrasi tersimpan."}
            </p>
            <p>{result.message || result.explain}</p>
            <p className="text-[11px]">
              Template versi {result.template_version_before} →{" "}
              {result.template_version_after} · alasan{" "}
              <RefLabel group="calibration_cause" value={result.cause} /> ·{" "}
              {changeText(result)} · bisa dibatalkan dari panel Riwayat kalibrasi.
            </p>
          </div>
        ) : null}

        {!result && canCalibrate && problems.length ? (
          <p data-testid={CALIB.dialogHint}
            className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
            Lengkapi dulu: {problems.join(" · ")}.
          </p>
        ) : null}

        {!canCalibrate ? (
          <p className="rounded-lg border bg-secondary p-2.5 text-[11px] text-muted-foreground">
            Anda bisa melihat dampaknya, tetapi hanya admin/direksi/Manajer Proyek yang boleh
            menerapkan kalibrasi — durasi &amp; waktu tunggu template menjadi dasar seluruh
            tenggat, pengingat, dan eskalasi pekerjaan.
          </p>
        ) : null}

        <DialogFooter className="gap-2">
          <Button variant="outline" data-testid={CALIB.dialogClose} disabled={busy}
            onClick={() => onOpenChange(false)}>
            {result ? "Selesai" : "Tutup"}
          </Button>
          {!result ? (
            <>
              <Button variant="secondary" data-testid={CALIB.dialogPreviewBtn} disabled={busy}
                onClick={runPreview}>
                {busy ? "Menghitung…" : "Hitung ulang dampak"}
              </Button>
              {canCalibrate ? (
                <Button data-testid={CALIB.dialogApply} onClick={apply}
                  disabled={busy || problems.length > 0}>
                  {busy ? "Menerapkan…" : "Terapkan kalibrasi"}
                </Button>
              ) : null}
            </>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Fact({ label, value, hint }) {
  return (
    <div>
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="font-medium">{value}</p>
      {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function Chip({ children, tone }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 ${tone}`}>{children}</span>
  );
}
