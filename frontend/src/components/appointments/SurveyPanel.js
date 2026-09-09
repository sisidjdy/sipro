import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ClipboardCheck, Camera, Save, CheckCircle2, Play, ImageIcon, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import { ErrorState } from "@/components/patterns/StateViews";
import api, { API, TOKEN_KEY } from "@/services/apiClient";
import { SURVEY, SURVEY_STAGES } from "@/constants/testIds";
import { SurveyStepper, groupByStage } from "@/components/appointments/SurveyStepper";
import { useReference } from "@/context/ReferenceContext";
import { useAuth } from "@/context/AuthContext";
import { Link } from "react-router-dom";


export default function SurveyPanel({ appointment, onChanged }) {
  const { options, labelOf } = useReference();
  const { can } = useAuth();
  const canConfig = can("settings", "update");
  const [survey, setSurvey] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState("recommended");
  const [summary, setSummary] = useState("");
  const [step, setStep] = useState(0);
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    if (!appointment?.id) return;
    setLoading(true); setError("");
    try {
      const res = await api.get("/surveys", { params: { appointment_id: appointment.id } });
      const found = (res.data.data || [])[0];
      if (found) {
        const det = await api.get(`/surveys/${found.id}`);
        setSurvey(det.data.data);
        setSummary(det.data.data.summary || "");
        setStep(Math.min(det.data.data.current_stage || 0, Math.max(0, (det.data.data.stages || []).length - 1)));
        if (det.data.data.result) setResult(det.data.data.result);
      } else {
        setSurvey(null);
      }
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat survey.");
    } finally { setLoading(false); }
  }, [appointment?.id]);

  useEffect(() => { load(); }, [load]);

  const startSurvey = async () => {
    setBusy(true);
    try {
      const res = await api.post("/surveys", {
        lead_id: appointment.lead_id, appointment_id: appointment.id, location: appointment.location,
      });
      setSurvey(res.data.data);
      toast.success("Survey dimulai.");
      onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memulai survey."); }
    finally { setBusy(false); }
  };

  const setItem = (idx, key, val) => {
    setSurvey((s) => {
      const cl = s.checklist.map((c, i) => (i === idx ? { ...c, [key]: val } : c));
      return { ...s, checklist: cl };
    });
  };

  const saveDraft = async () => {
    setBusy(true);
    try {
      await api.put(`/surveys/${survey.id}`, { checklist: survey.checklist, summary, current_stage: step });
      toast.success("Survey disimpan.");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan."); }
    finally { setBusy(false); }
  };

  const onPickFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await api.post(`/surveys/${survey.id}/photos`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Foto diunggah.");
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Gagal mengunggah foto.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const goTo = async (next) => {
    setStep(next);
    try { await api.put(`/surveys/${survey.id}`, { checklist: survey.checklist, summary, current_stage: next }); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan tahap."); }
  };

  const finalize = async () => {
    setBusy(true);
    try {
      await api.post(`/surveys/${survey.id}/result`, { result, summary });
      toast.success("Survey diselesaikan.");
      load();
      onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyelesaikan survey."); }
    finally { setBusy(false); }
  };

  const fileUrl = (fid) => `${API}/files/${fid}?auth=${localStorage.getItem(TOKEN_KEY)}`;

  if (loading) return <p className="text-sm text-muted-foreground">Memuat survey…</p>;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const completed = survey?.status === "completed";
  const groups = survey ? groupByStage(survey) : [];
  const cur = groups[Math.min(step, Math.max(0, groups.length - 1))] || { items: [] };
  const isLast = step >= groups.length - 1;
  const unfinishedRequired = (survey?.checklist || []).filter((c) => c.required && c.status === "na");

  return (
    <section data-testid={SURVEY.section} className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <ClipboardCheck className="h-4 w-4 text-primary" /> Survey Lokasi
        </h3>
        <div className="flex items-center gap-2">
          {canConfig ? (
            <Link to="/config?tab=survey" data-testid="survey-config-link"
              className="text-[11px] text-primary underline-offset-2 hover:underline">
              Atur poin & tahapan
            </Link>
          ) : null}
          {survey ? <StatusPill status={survey.status} group="survey_status" /> : null}
        </div>
      </div>

      {!survey ? (
        <div className="space-y-3 text-sm">
          <p className="text-muted-foreground">Belum ada survey untuk janji temu ini.</p>
          <Button data-testid={SURVEY.startBtn} size="sm" onClick={startSurvey} disabled={busy}>
            <Play className="mr-1.5 h-4 w-4" /> {busy ? "Memulai…" : "Mulai Survey"}
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Tahapan (wizard) — urutan & poin dari Pusat Konfigurasi › Tahapan Survey */}
          {groups.length > 1 ? <SurveyStepper groups={groups} current={step} onSelect={(i) => (completed ? setStep(i) : goTo(i))} /> : null}
          <div className="space-y-2">
            <div className="flex items-baseline justify-between gap-2">
              <p data-testid={SURVEY_STAGES.stepTitle} className="text-sm font-semibold">
                <span className="mr-1 text-primary">{step + 1}/{groups.length}</span>{cur.name}
              </p>
              {cur.description ? <p className="text-[11px] text-muted-foreground">{cur.description}</p> : null}
            </div>
            {!cur.items.length ? <p className="text-xs text-muted-foreground">Tahap ini tidak punya poin pemeriksaan.</p> : null}
            {cur.items.map((c) => (
              <div key={c.key} data-testid={SURVEY.checklistItem} data-stage={c.stage_key || ""}
                className="rounded-lg border bg-card p-2.5 shadow-[var(--shadow-card)]">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium">
                    {c.label}
                    {c.required ? <span data-testid={SURVEY_STAGES.requiredBadge} className="ml-1.5 rounded bg-rose-50 px-1 py-0.5 text-[10px] font-semibold text-rose-700">wajib</span> : null}
                  </span>
                  {completed ? (
                    <StatusPill status={c.status === "ok" ? "recommended" : c.status === "issue" ? "not_recommended" : "draft"}
                      label={labelOf("survey_check_status", c.status)} />
                  ) : (
                    <Select value={c.status} onValueChange={(v) => setItem(c.idx, "status", v)}>
                      <SelectTrigger data-testid={SURVEY.checklistSelect} aria-label={`Status ${c.label}`} className="h-8 w-36">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {options("survey_check_status").map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  )}
                </div>
                {c.hint && !completed ? <p className="mt-1 text-[11px] text-muted-foreground">{c.hint}</p> : null}
                {completed ? (
                  c.note ? <p className="mt-1 text-xs text-muted-foreground">{c.note}</p> : null
                ) : (
                  <Input className="mt-2 h-8 text-sm" placeholder="Catatan (opsional)" aria-label={`Catatan ${c.label}`}
                    value={c.note || ""} onChange={(e) => setItem(c.idx, "note", e.target.value)} />
                )}
              </div>
            ))}
            {groups.length > 1 ? (
              <div className="flex items-center justify-between pt-1">
                <Button size="sm" variant="ghost" data-testid={SURVEY_STAGES.prevBtn} disabled={step === 0}
                  onClick={() => (completed ? setStep(step - 1) : goTo(step - 1))}><ChevronLeft className="mr-1 h-4 w-4" /> Sebelumnya</Button>
                {!isLast ? (
                  <Button size="sm" data-testid={SURVEY_STAGES.nextBtn}
                    onClick={() => (completed ? setStep(step + 1) : goTo(step + 1))}>Tahap berikutnya <ChevronRight className="ml-1 h-4 w-4" /></Button>
                ) : null}
              </div>
            ) : null}
          </div>

          {/* Photos */}
          {isLast || completed ? (<>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-sm font-medium">
                <Camera className="h-4 w-4 text-primary" /> Foto ({(survey.photos || []).length})
              </span>
              {!completed ? (
                <>
                  <input ref={fileRef} data-testid={SURVEY.photoInput} type="file" accept="image/*"
                    className="hidden" onChange={onPickFile} />
                  <Button data-testid={SURVEY.photoUploadBtn} size="sm" variant="outline"
                    disabled={uploading} onClick={() => fileRef.current?.click()}>
                    <Camera className="mr-1.5 h-4 w-4" /> {uploading ? "Mengunggah…" : "Tambah Foto"}
                  </Button>
                </>
              ) : null}
            </div>
            {(survey.photos || []).length === 0 ? (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <ImageIcon className="h-3.5 w-3.5" /> Belum ada foto.
              </p>
            ) : (
              <div className="grid grid-cols-3 gap-2">
                {survey.photos.map((p) => (
                  <a key={p.id} data-testid={SURVEY.photoRow} href={fileUrl(p.id)} target="_blank" rel="noreferrer"
                    className="group relative overflow-hidden rounded-lg border">
                    <img src={fileUrl(p.id)} alt={p.original_filename}
                      className="h-20 w-full object-cover transition-transform group-hover:scale-105" />
                  </a>
                ))}
              </div>
            )}
          </div>

          {/* Summary + result */}
          <div className="space-y-1.5">
            <Label className="text-xs">Ringkasan / Rekomendasi</Label>
            <Textarea data-testid={SURVEY.summaryInput} rows={2} value={summary}
              disabled={completed} onChange={(e) => setSummary(e.target.value)}
              placeholder="Kesimpulan survey…" />
          </div>

          {completed ? (
            <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm">
              <CheckCircle2 className="h-4 w-4 text-emerald-700" />
              <span>Hasil: <b><StatusPill status={survey.result} group="survey_result" /></b></span>
            </div>
          ) : (
            <div className="flex flex-wrap items-end gap-2 border-t pt-3">
              {unfinishedRequired.length ? (
                <p className="w-full text-xs text-amber-700">{unfinishedRequired.length} poin wajib belum dinilai: {unfinishedRequired.slice(0, 3).map((c) => c.label).join(", ")}{unfinishedRequired.length > 3 ? "…" : ""}</p>
              ) : null}
              <Button data-testid={SURVEY.saveBtn} size="sm" variant="outline" onClick={saveDraft} disabled={busy}>
                <Save className="mr-1.5 h-4 w-4" /> Simpan
              </Button>
              <div className="flex-1 space-y-1 min-w-[10rem]">
                <Label className="text-xs">Hasil survey</Label>
                <Select value={result} onValueChange={setResult}>
                  <SelectTrigger data-testid={SURVEY.resultSelect} className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {options("survey_result").map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <Button data-testid={SURVEY.finalizeBtn} size="sm" onClick={finalize} disabled={busy || unfinishedRequired.length > 0}>
                <CheckCircle2 className="mr-1.5 h-4 w-4" /> Selesaikan
              </Button>
            </div>
          )}
          </>) : (
            <div className="flex justify-end border-t pt-3">
              <Button data-testid={SURVEY.saveBtn} size="sm" variant="outline" onClick={saveDraft} disabled={busy}>
                <Save className="mr-1.5 h-4 w-4" /> Simpan
              </Button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
