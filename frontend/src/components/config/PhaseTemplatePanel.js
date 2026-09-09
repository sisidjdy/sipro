import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { Layers, Pencil, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import ConfirmDialog from "@/components/patterns/ConfirmDialog";
import EmptyState from "@/components/patterns/EmptyState";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import PhaseTemplateEditor from "@/components/config/PhaseTemplateEditor";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { PHASE_TPL } from "@/constants/testIds";

/**
 * TAHAPAN PEMBANGUNAN — template urutan fase kawasan proyek (nama, bobot, target %).
 * Diterapkan ke proyek lewat "Terapkan template" di detail proyek; fase yang sudah ada
 * tidak berubah saat template diedit.
 */
export default function PhaseTemplatePanel() {
  const { can } = useAuth();
  const canEdit = can("construction", "update");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null);
  const [killRow, setKillRow] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/construction/phase-templates");
      setRows(r.data.data || []);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat template tahapan."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const remove = async () => {
    try {
      await api.delete(`/construction/phase-templates/${killRow.id}`);
      toast.success(`Template ${killRow.code} dihapus.`);
      setKillRow(null); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menghapus template."); }
  };

  if (loading) return <LoadingCards count={2} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={PHASE_TPL.panel} className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
        <div className="max-w-2xl space-y-1 text-xs text-muted-foreground">
          <p>
            Template menentukan <b>urutan fase kawasan, bobot progres, dan target rencana</b> untuk
            proyek baru. Terapkan dari detail proyek (Master Proyek). Mengubah template tidak
            mengubah fase proyek yang sudah dibuat.
          </p>
          <p data-testid="phase-tpl-build-link">
            Langkah pekerjaan <b>per unit</b> (W1-01 Persiapan, W1-02 Pondasi, dst. — bobot, hari ke-N,
            hold point, checklist mutu, foto minimal) diatur di{" "}
            <Link to="/construction?tab=templates" className="font-medium text-primary underline-offset-2 hover:underline">
              Pembangunan › Template Jadwal
            </Link>
            . Kode langkah itulah yang dipakai RAB / BoQ (kolom <code>step_code</code>) dan SPK borongan
            untuk menempel ke item pekerjaan.
          </p>
        </div>
        {canEdit ? (
          <Button size="sm" data-testid={PHASE_TPL.newBtn} onClick={() => setEditing({})}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Template baru
          </Button>
        ) : null}
      </div>
      {!rows.length ? (
        <EmptyState icon={Layers} title="Belum ada template tahapan"
          description="Buat template pertama supaya proyek baru punya urutan fase." />
      ) : rows.map((t) => (
        <div key={t.id} data-testid={PHASE_TPL.row} data-code={t.code}
          className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[11px]">{t.code}</span>
                <p className="font-medium">{t.name}</p>
                {t.is_default ? <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">BAWAAN</span> : null}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {t.phases_count} fase · bobot total {t.total_weight}%{t.description ? ` · ${t.description}` : ""}
              </p>
              {(t.warnings || []).map((w) => <p key={w} className="mt-1 text-xs text-amber-700">{w}</p>)}
            </div>
            {canEdit ? (
              <div className="flex gap-1">
                <Button size="sm" variant="outline" data-testid={PHASE_TPL.editBtn} aria-label={`Ubah ${t.code}`}
                  onClick={() => setEditing(t)}><Pencil className="mr-1 h-3.5 w-3.5" /> Ubah</Button>
                <Button size="sm" variant="ghost" data-testid={PHASE_TPL.deleteBtn} aria-label={`Hapus ${t.code}`}
                  onClick={() => setKillRow(t)}><Trash2 className="h-3.5 w-3.5 text-destructive" /></Button>
              </div>
            ) : null}
          </div>
          <ol className="mt-2 flex flex-wrap gap-1.5">
            {(t.phases || []).map((p) => (
              <li key={p.order} className="rounded-md border bg-background px-2 py-1 text-xs">
                <span className="mr-1 font-semibold text-primary">{p.order}.</span>{p.name}
                <span className="ml-1 text-muted-foreground">({p.weight}%)</span>
              </li>
            ))}
          </ol>
        </div>
      ))}
      {editing !== null ? (
        <PhaseTemplateEditor template={editing.id ? editing : null} open
          onOpenChange={(v) => !v && setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      ) : null}
      <ConfirmDialog open={!!killRow} onOpenChange={(v) => !v && setKillRow(null)}
        title={`Hapus template ${killRow?.code}?`} onConfirm={remove}
        description="Fase proyek yang sudah diterapkan tidak ikut terhapus." />
    </div>
  );
}
