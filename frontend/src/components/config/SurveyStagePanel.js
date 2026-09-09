import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ArrowDown, ArrowUp, ListChecks, Plus, Save, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { SURVEY_STAGES } from "@/constants/testIds";

/**
 * TAHAPAN SURVEY — langkah berurutan yang diikuti sales saat mencatat survey lokasi.
 * Tiap tahap punya poin pemeriksaan; poin "wajib" harus dinilai sebelum survey bisa
 * diselesaikan. Berlaku untuk survey BARU; survey berjalan memakai tahapan saat dibuat.
 */
export default function SurveyStagePanel() {
  const { can } = useAuth();
  const canEdit = can("settings", "update");
  const [stages, setStages] = useState([]);
  const [meta, setMeta] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/survey-stages");
      setStages(r.data.data.stages || []);
      setMeta({ version: r.data.data.version, updated_by: r.data.data.updated_by, warnings: r.data.data.warnings });
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat tahapan survey."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const setStage = (i, patch) => setStages((s) => s.map((st, j) => (j === i ? { ...st, ...patch } : st)));
  const setItem = (i, k, patch) => setStage(i, { items: stages[i].items.map((it, m) => (m === k ? { ...it, ...patch } : it)) });
  const moveStage = (i, d) => setStages((s) => {
    const arr = [...s]; const j = i + d;
    if (j < 0 || j >= arr.length) return s;
    [arr[i], arr[j]] = [arr[j], arr[i]];
    return arr;
  });

  const save = async () => {
    if (!stages.length) { toast.error("Minimal satu tahap."); return; }
    if (stages.some((s) => (s.name || "").trim().length < 2)) { toast.error("Setiap tahap harus punya nama."); return; }
    if (stages.some((s) => s.items.some((it) => (it.label || "").trim().length < 2))) { toast.error("Setiap poin harus punya label."); return; }
    setBusy(true);
    try {
      const r = await api.put("/survey-stages", { stages: stages.map((s) => ({
        name: s.name.trim(), description: s.description || null,
        items: s.items.map((it) => ({ label: it.label.trim(), required: !!it.required, hint: it.hint || null })) })) });
      (r.data.warnings || []).forEach((w) => toast.warning(w));
      toast.success(r.data.note || "Tahapan survey disimpan.");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan tahapan survey."); }
    finally { setBusy(false); }
  };

  if (loading) return <LoadingCards count={2} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={SURVEY_STAGES.panel} className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
        <p className="max-w-2xl text-xs text-muted-foreground">
          Sales mengisi survey <b>tahap demi tahap</b> mengikuti urutan di sini. Poin bertanda
          <b> wajib</b> harus dinilai sebelum survey boleh diselesaikan. Versi {meta.version || 1}
          {meta.updated_by ? ` · diubah ${meta.updated_by}` : ""}.
        </p>
        {canEdit ? (
          <Button size="sm" data-testid={SURVEY_STAGES.save} onClick={save} disabled={busy}>
            <Save className="mr-1 h-3.5 w-3.5" /> {busy ? "Menyimpan…" : "Simpan tahapan"}
          </Button>
        ) : null}
      </div>
      {(meta.warnings || []).map((w) => <p key={w} className="text-xs text-amber-700">{w}</p>)}
      {stages.map((s, i) => (
        <div key={s.key || i} data-testid={SURVEY_STAGES.stage} className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
          <div className="flex items-start gap-2">
            <span className="mt-2 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">{i + 1}</span>
            <div className="flex-1 space-y-1.5">
              <Input data-testid={SURVEY_STAGES.stageName} aria-label={`Nama tahap ${i + 1}`} className="h-9 font-medium" value={s.name}
                disabled={!canEdit} onChange={(e) => setStage(i, { name: e.target.value })} placeholder="Nama tahap" />
              <Input data-testid={SURVEY_STAGES.stageDesc} aria-label={`Keterangan tahap ${i + 1}`} className="h-8 text-xs" value={s.description || ""}
                disabled={!canEdit} onChange={(e) => setStage(i, { description: e.target.value })} placeholder="Keterangan singkat untuk sales (opsional)" />
            </div>
            {canEdit ? (
              <div className="flex gap-0.5">
                <Button size="icon" variant="ghost" className="h-7 w-7" data-testid={SURVEY_STAGES.stageUp} aria-label={`Naikkan tahap ${i + 1}`} onClick={() => moveStage(i, -1)}><ArrowUp className="h-3.5 w-3.5" /></Button>
                <Button size="icon" variant="ghost" className="h-7 w-7" data-testid={SURVEY_STAGES.stageDown} aria-label={`Turunkan tahap ${i + 1}`} onClick={() => moveStage(i, 1)}><ArrowDown className="h-3.5 w-3.5" /></Button>
                <Button size="icon" variant="ghost" className="h-7 w-7" data-testid={SURVEY_STAGES.stageRemove} aria-label={`Hapus tahap ${i + 1}`} disabled={stages.length <= 1}
                  onClick={() => setStages((st) => st.filter((_, j) => j !== i))}><Trash2 className="h-3.5 w-3.5 text-destructive" /></Button>
              </div>
            ) : null}
          </div>
          <div className="mt-3 space-y-1.5 pl-8">
            {s.items.map((it, k) => (
              <div key={it.key || k} data-testid={SURVEY_STAGES.item} className="flex items-center gap-2 rounded-lg border bg-background p-1.5">
                <ListChecks className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <Input data-testid={SURVEY_STAGES.itemLabel} aria-label={`Poin ${k + 1} tahap ${i + 1}`} className="h-8 flex-1 text-sm" value={it.label}
                  disabled={!canEdit} onChange={(e) => setItem(i, k, { label: e.target.value })} placeholder="Poin pemeriksaan / catatan" />
                <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Switch data-testid={SURVEY_STAGES.itemRequired} aria-label={`Wajib poin ${k + 1} tahap ${i + 1}`} checked={!!it.required}
                    disabled={!canEdit} onCheckedChange={(v) => setItem(i, k, { required: v })} /> Wajib
                </label>
                {canEdit ? (
                  <Button size="icon" variant="ghost" className="h-7 w-7" data-testid={SURVEY_STAGES.itemRemove} aria-label={`Hapus poin ${k + 1} tahap ${i + 1}`}
                    onClick={() => setStage(i, { items: s.items.filter((_, m) => m !== k) })}><Trash2 className="h-3.5 w-3.5 text-destructive" /></Button>
                ) : null}
              </div>
            ))}
            {canEdit ? (
              <Button size="sm" variant="outline" data-testid={SURVEY_STAGES.itemAdd} aria-label={`Tambah poin tahap ${i + 1}`}
                onClick={() => setStage(i, { items: [...s.items, { label: "", required: false }] })}>
                <Plus className="mr-1 h-3.5 w-3.5" /> Tambah poin
              </Button>
            ) : null}
          </div>
        </div>
      ))}
      {canEdit ? (
        <Button variant="outline" data-testid={SURVEY_STAGES.stageAdd}
          onClick={() => setStages((st) => [...st, { name: "", description: "", items: [{ label: "", required: false }] }])}>
          <Plus className="mr-1 h-3.5 w-3.5" /> Tambah tahap
        </Button>
      ) : null}
    </div>
  );
}
