import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Copy, FileStack, Pencil, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import ConfirmDialog from "@/components/patterns/ConfirmDialog";
import EmptyState from "@/components/patterns/EmptyState";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import RefLabel from "@/components/patterns/RefLabel";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import BuildTemplateEditor from "@/components/construction/BuildTemplateEditor";
import UnitTypePicker from "@/components/construction/UnitTypePicker";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { BUILD } from "@/constants/testIds";

/**
 * TEMPLATE JADWAL — sumber urutan pekerjaan, bobot, waktu tunggu, hold point, dan
 * checklist mutu untuk tiap TIPE unit. Tipe rumah berbeda boleh punya tahapan berbeda,
 * dan tiap perubahan hanya berlaku untuk jadwal BARU supaya bukti kerja yang sudah
 * diverifikasi tidak ikut bergeser.
 */
export default function BuildTemplatePanel({ projectId }) {
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  // Backend `build_router` menolak siapa pun di luar SUPERVISOR_ROLES; himpunan peran yang
  // sama persis = pemegang `construction:approve` (site engineer sengaja tak punya approve).
  const canConfigure = can("construction", "approve");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editId, setEditId] = useState(null);
  const [creating, setCreating] = useState(false);
  const [cloneSrc, setCloneSrc] = useState(null);
  const [killRow, setKillRow] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const r = await api.get("/build/templates");
      setRows(r.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat template jadwal.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const remove = async () => {
    if (!killRow) return;
    try {
      await api.delete(`/build/templates/${killRow.id}`);
      toast.success(`Template ${killRow.code} dihapus.`);
      setKillRow(null);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menghapus template.");
    }
  };

  return (
    <div data-testid={BUILD.templatePanel} className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
        <p className="max-w-2xl text-xs text-muted-foreground">
          Template menentukan <b>urutan pekerjaan, bobot progres, waktu tunggu (curing),
          hold point, dan checklist mutu</b>. Jadwal unit yang sudah dibuat tidak berubah
          saat template diedit — perubahan berlaku untuk jadwal berikutnya.
        </p>
        {canConfigure ? (
          <Button size="sm" data-testid={BUILD.templateNew} onClick={() => setCreating(true)}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Template baru
          </Button>
        ) : null}
      </div>

      {loading ? <LoadingCards count={2} />
        : error ? <ErrorState message={error} onRetry={load} />
          : !rows.length ? (
            <EmptyState icon={FileStack} title="Belum ada template jadwal"
              description="Template default rumah tapak dibuat otomatis saat sistem disiapkan. Buat template baru bila tipe unit Anda butuh tahapan berbeda." />
          ) : (
            <div className="space-y-3">
              {rows.map((t) => {
                const weightOff = Math.abs((t.total_weight || 0) - 100) > 0.5;
                return (
                  <div key={t.id} data-testid={BUILD.templateRow} data-template={t.code}
                    className="rounded-xl border bg-card p-3 shadow-sm">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                          <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[11px]">
                            {t.code}
                          </span>
                          {t.name}
                          {t.is_default ? (
                            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
                              DEFAULT
                            </span>
                          ) : null}
                          {t.cloned_from ? (
                            <span className="text-[11px] font-normal text-muted-foreground">
                              duplikat dari {t.cloned_from}
                            </span>
                          ) : null}
                        </p>
                        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
                          <span>{t.steps_count} item pekerjaan</span>
                          <span>{t.total_days} hari kerja</span>
                          <span className={weightOff ? "font-semibold text-rose-700" : ""}>
                            bobot total {t.total_weight}%
                          </span>
                          <span>
                            <RefLabel group="build_calendar_mode" value={t.calendar_mode} />
                            {" "}· {t.work_days_per_week} hari/minggu
                          </span>
                          <span>dipakai {t.used_by} jadwal unit</span>
                        </p>
                        <p className="mt-1 flex flex-wrap gap-1">
                          {(t.unit_types || []).length ? (t.unit_types || []).map((ut) => (
                            <span key={ut}
                              className="rounded-full border bg-background px-2 py-0.5 text-[10px]">
                              {ut}
                            </span>
                          )) : (
                            <span className="text-[11px] text-muted-foreground">
                              berlaku untuk semua tipe unit
                            </span>
                          )}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        <Button size="sm" variant="outline"
                          aria-label={`Lihat & ubah template ${t.code}`}
                          data-testid={BUILD.templateEdit} data-edit={t.code}
                          onClick={() => setEditId(t.id)}>
                          <Pencil className="mr-1 h-3.5 w-3.5" />
                          {canConfigure ? "Ubah" : "Lihat"}
                        </Button>
                        {canConfigure ? (
                          <Button size="sm" variant="ghost"
                            aria-label={`Duplikat template ${t.code}`}
                            data-testid={BUILD.templateClone} data-clone={t.code}
                            onClick={() => setCloneSrc(t)}>
                            <Copy className="mr-1 h-3.5 w-3.5" /> Duplikat
                          </Button>
                        ) : null}
                        {canConfigure && !t.used_by && !t.is_default ? (
                          <Button size="sm" variant="ghost"
                            aria-label={`Hapus template ${t.code}`}
                            data-testid={BUILD.templateDelete} data-delete={t.code}
                            onClick={() => setKillRow(t)}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        ) : null}
                      </div>
                    </div>
                    {weightOff ? (
                      <p data-testid={BUILD.templateWarning}
                        className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
                        Bobot total {t.total_weight}% (idealnya 100%) — progres unit akan
                        dihitung proporsional, tetapi sebaiknya dirapikan agar mudah dibaca.
                      </p>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}

      <BuildTemplateEditor templateId={editId} creating={creating}
        open={!!editId || creating}
        onOpenChange={(v) => { if (!v) { setEditId(null); setCreating(false); } }}
        onSaved={load} readOnly={!canConfigure} />
      <CloneDialog source={cloneSrc} projectId={projectId} open={!!cloneSrc}
        onOpenChange={(v) => !v && setCloneSrc(null)}
        onDone={(t) => { load(); setEditId(t?.id || null); }} />
      <ConfirmDialog open={!!killRow} onOpenChange={(v) => !v && setKillRow(null)}
        title="Hapus template jadwal?"
        description={`Template ${killRow?.code || ""} belum dipakai jadwal unit mana pun, `
          + "jadi aman dihapus."}
        confirmLabel="Hapus template" onConfirm={remove} />
    </div>
  );
}

/** Duplikasi template lalu arahkan ke tipe unit lain (tanpa mengubah template asal). */
function CloneDialog({ source, projectId, open, onOpenChange, onDone }) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [types, setTypes] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !source) return;
    setCode(`${source.code}-V2`);
    setName(`${source.name} (salinan)`);
    setTypes(source.unit_types || []);
  }, [open, source]);

  if (!source) return null;

  const run = async () => {
    if (code.trim().length < 2 || name.trim().length < 3) {
      toast.error("Kode minimal 2 karakter dan nama minimal 3 karakter.");
      return;
    }
    setBusy(true);
    try {
      const r = await api.post("/build/templates/clone", {
        clone_from: source.id, code: code.trim().toUpperCase(), name: name.trim(),
        unit_types: types, project_id: projectId || null,
      });
      toast.success(`Template ${r.data?.data?.code} dibuat — silakan sesuaikan tahapannya.`);
      onOpenChange(false);
      onDone && onDone(r.data?.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menduplikasi template.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-card sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Duplikat template {source.code}</DialogTitle>
          <DialogDescription>
            Salinan berisi {source.steps_count} item pekerjaan yang sama — ubah sesuai
            kebutuhan tipe unit lain tanpa mengganggu template asal.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="tcode">Kode template baru</Label>
            <Input id="tcode" data-testid={BUILD.templateCloneCode} value={code}
              onChange={(e) => setCode(e.target.value)} placeholder="mis. RUMAH-T54" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tname">Nama template baru</Label>
            <Input id="tname" data-testid={BUILD.templateCloneName} value={name}
              onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Berlaku untuk tipe unit</Label>
            <UnitTypePicker value={types} onChange={setTypes} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Batal
          </Button>
          <Button data-testid={BUILD.templateCloneSave} onClick={run} disabled={busy}>
            {busy ? "Menduplikasi…" : "Duplikat"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
