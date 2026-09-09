import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Building2, Layers, Plus, PackagePlus, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { formatIDR } from "@/utils/formatters";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import EditProjectDialog from "@/components/projects/EditProjectDialog";
import EditUnitDialog from "@/components/projects/EditUnitDialog";
import EditPhaseDialog from "@/components/projects/EditPhaseDialog";
import { AddPhaseDialog, ApplyPhaseTemplateDialog } from "@/components/projects/PhaseDialogs";
import ConfirmDialog from "@/components/patterns/ConfirmDialog";
import DeleteEntityButton from "@/components/patterns/DeleteEntityButton";
import { PROJECTS, PROJECT_EDIT, PHASE_TPL } from "@/constants/testIds";

export default function ProjectsPage() {
  const navigate = useNavigate();
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  const canManage = can("projects", "create");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [addOpen, setAddOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/projects");
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat proyek.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid={PROJECTS.page} className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Building2 className="h-5 w-5 text-primary" />
          <h1 className="page-title">Proyek & Unit</h1>
        </div>
        {canManage ? (
          <Button data-testid={PROJECTS.addBtn} size="sm" onClick={() => setAddOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> Proyek Baru
          </Button>
        ) : null}
      </div>

      {loading ? <LoadingCards count={3} /> : error ? <ErrorState message={error} onRetry={load} /> :
        !data?.data?.length ? (
          <EmptyState icon={Building2} title="Belum ada proyek"
            description="Buat proyek untuk mulai mengelola unit, progres konstruksi, dan material." />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.data.map((p) => (
              <button key={p.id} data-testid={PROJECTS.card} onClick={() => setSelected(p.id)}
                className="rounded-xl border bg-card p-4 text-left shadow-sm transition-colors hover:border-primary/50">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-heading text-lg font-semibold">{p.name}</p>
                    <p className="text-xs text-muted-foreground">{p.code} · {p.location || "-"}</p>
                  </div>
                  <StatusPill status={p.status} group="project_status"
                    tone={p.status === "active" ? "active" : p.status} />
                </div>
                <div className="mt-3">
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="text-muted-foreground">Progres konstruksi</span>
                    <span className="font-semibold tabular-nums">{p.construction_progress || 0}%</span>
                  </div>
                  <Progress value={p.construction_progress || 0} className="h-2" />
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
                  <span className="rounded-full border bg-secondary px-2 py-0.5">{p.unit_total} unit</span>
                  <span className="rounded-full border px-2 py-0.5">Tersedia {p.unit_counts?.available ?? 0}</span>
                  <span className="rounded-full border px-2 py-0.5">Booked {p.unit_counts?.booked ?? 0}</span>
                  <span className="rounded-full border bg-secondary px-2 py-0.5">
                    {p.cluster_count ?? 0} cluster · {p.block_count ?? 0} blok
                  </span>
                </div>
                {/* Fase 39: struktur proyek (cluster → blok → unit) dikelola di halaman
                    kanonik `/projects/:id`, bukan lagi di drawer terbatas. */}
                <span data-testid="project-open-structure" data-project={p.id}
                  aria-label={`Kelola struktur & unit ${p.name}`}
                  className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-primary"
                  role="link" tabIndex={0}
                  onClick={(e) => { e.stopPropagation(); navigate(`/projects/${p.id}`); }}
                  onKeyDown={(e) => { if (e.key === "Enter") navigate(`/projects/${p.id}`); }}>
                  Kelola struktur & unit →
                </span>
              </button>
            ))}
          </div>
        )}

      <ProjectDetail projectId={selected} open={!!selected} onOpenChange={(v) => !v && setSelected(null)}
        canManage={canManage} onChanged={load} />
      <AddProjectDialog open={addOpen} onOpenChange={setAddOpen} onDone={load} />
    </div>
  );
}

function ProjectDetail({ projectId, open, onOpenChange, canManage, onChanged }) {
  const { can } = useAuth();
  const canDelete = can("projects", "delete");
  const canDeleteUnit = can("units", "delete");
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [addUnitOpen, setAddUnitOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editUnit, setEditUnit] = useState(null);
  const [editPhase, setEditPhase] = useState(null);
  const [applyOpen, setApplyOpen] = useState(false);
  const [addPhaseOpen, setAddPhaseOpen] = useState(false);
  const [delUnit, setDelUnit] = useState(null);
  const [delBusy, setDelBusy] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const res = await api.get(`/projects/${projectId}`);
      setDetail(res.data.data);
    } catch { toast.error("Gagal memuat detail proyek."); }
    finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const refresh = () => { load(); onChanged && onChanged(); };

  const removeUnit = async () => {
    const u = delUnit;
    if (!u) return;
    setDelBusy(true);
    try {
      await api.delete(`/projects/${projectId}/units/${u.id}`);
      toast.success(`Unit ${u.code} dihapus.`);
      setDelUnit(null);
      refresh();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menghapus unit."); }
    finally { setDelBusy(false); }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={PROJECTS.detail} className="w-full overflow-y-auto sm:max-w-xl">
        {loading || !detail ? (
          <>
            <SheetHeader className="sr-only"><SheetTitle>Detail proyek</SheetTitle><SheetDescription>Memuat detail proyek</SheetDescription></SheetHeader>
            <div className="py-10 text-center text-sm text-muted-foreground">Memuat…</div>
          </>
        ) : (
          <>
            <SheetHeader>
              <SheetTitle className="font-heading text-xl">{detail.project.name}</SheetTitle>
              <SheetDescription>{detail.project.code} · {detail.project.location || "-"}</SheetDescription>
            </SheetHeader>
            {canManage || canDelete ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {canManage ? (
                  <Button data-testid={PROJECT_EDIT.editBtn} size="sm" variant="outline"
                    onClick={() => setEditOpen(true)}>
                    <Pencil className="mr-1.5 h-3.5 w-3.5" /> Ubah Proyek
                  </Button>
                ) : null}
                {canDelete ? (
                  <DeleteEntityButton entity="Proyek" name={detail.project.code} testId="project-delete"
                    checkUrl={`/projects/${projectId}/delete-check`} deleteUrl={`/projects/${projectId}`}
                    onDeleted={() => { onOpenChange(false); onChanged && onChanged(); }} />
                ) : null}
              </div>
            ) : null}

            <div className="mt-4">
              <div className="mb-1 flex justify-between text-sm">
                <span className="text-muted-foreground">Progres konstruksi</span>
                <span className="font-semibold tabular-nums">{detail.project.construction_progress || 0}%</span>
              </div>
              <Progress value={detail.project.construction_progress || 0} className="h-2.5" />
            </div>

            {/* Phases */}
            <div className="mt-5">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold">Fase Konstruksi (berbobot)</h3>
                {canManage ? (
                  <div className="flex gap-1">
                    <Button size="sm" variant="outline" className="h-7 text-xs" data-testid={PHASE_TPL.applyOpen}
                      onClick={() => setApplyOpen(true)}><Layers className="mr-1 h-3.5 w-3.5" /> Terapkan template</Button>
                    <Button size="sm" variant="outline" className="h-7 text-xs" data-testid={PHASE_TPL.addOpen}
                      onClick={() => setAddPhaseOpen(true)}><Plus className="mr-1 h-3.5 w-3.5" /> Tambah fase</Button>
                  </div>
                ) : null}
              </div>
              {!detail.phases.length ? (
                <p data-testid={PHASE_TPL.emptyState} className="rounded-lg border border-dashed bg-card p-3 text-xs text-muted-foreground">
                  Belum ada fase kawasan — progres proyek tidak bisa dicatat sampai fase dibuat.
                  {canManage ? " Terapkan template tahapan atau tambah fase manual." : " Minta Manajer Proyek menerapkan template tahapan."}
                </p>
              ) : null}
              <div className="space-y-2">
                {detail.phases.map((ph) => (
                  <div key={ph.id} data-testid="project-phase-row"
                    data-phase-name={ph.name} data-phase-progress={ph.progress ?? 0}
                    className="rounded-lg border bg-card p-2.5 shadow-[var(--shadow-card)]">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium">{ph.name} <span className="text-xs text-muted-foreground">(bobot {ph.weight}%)</span></span>
                      <span className="flex items-center gap-1.5">
                        <span className="text-xs font-semibold tabular-nums text-muted-foreground">{ph.progress ?? 0}%</span>
                        <StatusPill status={ph.status} group="construction_status"
                          tone={ph.status === "not_started" ? "draft" : ph.status === "done" ? "completed" : ph.status === "qc_hold" ? "lost" : "in_progress"} />
                        {canManage ? (
                          <Button data-testid="phase-edit-btn" data-phase-name={ph.name}
                            aria-label={`Ubah fase ${ph.name}`} title={`Ubah fase ${ph.name}`}
                            size="icon" variant="ghost" className="h-7 w-7"
                            onClick={() => setEditPhase(ph)}>
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                        ) : null}
                      </span>
                    </div>
                    <div className="mt-1.5"><Progress value={ph.progress} className="h-1.5" /></div>
                  </div>
                ))}
              </div>
            </div>

            {/* Units */}
            <div className="mt-5">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold">Unit ({detail.units.length})</h3>
                {canManage ? (
                  <Button data-testid={PROJECTS.addUnitBtn} size="sm" variant="outline" onClick={() => setAddUnitOpen(true)}>
                    <PackagePlus className="mr-1.5 h-4 w-4" /> Tambah Unit
                  </Button>
                ) : null}
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {detail.units.map((u) => (
                  <div key={u.id} data-testid="project-unit-card"
                    data-unit-code={u.code} data-unit-status={u.status}
                    className="rounded-lg border bg-card p-2.5 text-sm shadow-[var(--shadow-card)]">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold">{u.code}</span>
                      <StatusPill status={u.status} group="unit_status" />
                    </div>
                    <p className="text-[11px] text-muted-foreground">{u.type} · {formatIDR(u.price)}</p>
                    <p className="mt-1 text-[11px] text-muted-foreground">Konstruksi {u.construction_progress || 0}%</p>
                    {canManage ? (
                      <div className="mt-1 flex gap-1">
                        <Button data-testid={PROJECT_EDIT.unitEditBtn} data-unit-code={u.code}
                          aria-label={`Ubah unit ${u.code}`} title={`Ubah unit ${u.code}`}
                          size="sm" variant="ghost"
                          className="h-7 px-2 text-[11px]" onClick={() => setEditUnit(u)}>
                          <Pencil className="mr-1 h-3 w-3" /> Ubah
                        </Button>
                        {canDeleteUnit ? (
                          <Button data-testid="unit-delete-btn" data-unit-code={u.code}
                            aria-label={`Hapus unit ${u.code}`} title={`Hapus unit ${u.code}`}
                            size="sm" variant="ghost"
                            className="h-7 px-2 text-[11px] text-rose-700" onClick={() => setDelUnit(u)}>
                            <Trash2 className="mr-1 h-3 w-3" /> Hapus
                          </Button>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>

            <AddUnitsDialog projectId={projectId} open={addUnitOpen} onOpenChange={setAddUnitOpen} onDone={refresh} />
          </>
        )}
        <EditProjectDialog project={detail?.project} open={editOpen} onOpenChange={setEditOpen}
          onDone={refresh} />
        <EditUnitDialog projectId={projectId} unit={editUnit} open={!!editUnit}
          onOpenChange={(v) => !v && setEditUnit(null)} onDone={refresh} />
        <EditPhaseDialog phase={editPhase} open={!!editPhase}
          onOpenChange={(v) => !v && setEditPhase(null)} onDone={refresh} />
        <ApplyPhaseTemplateDialog projectId={projectId} open={applyOpen} onOpenChange={setApplyOpen} onDone={refresh} />
        <AddPhaseDialog projectId={projectId} open={addPhaseOpen} onOpenChange={setAddPhaseOpen} onDone={refresh}
          nextOrder={(detail?.phases || []).length + 1} />
        <ConfirmDialog open={!!delUnit} onOpenChange={(v) => !v && setDelUnit(null)}
          title={`Hapus unit ${delUnit?.code || ""}?`}
          description="Unit yang dihapus tidak bisa dikembalikan. Hanya unit berstatus tersedia (belum ada booking/deal) yang boleh dihapus."
          confirmLabel="Ya, hapus unit" busy={delBusy} onConfirm={removeUnit}
          testId="unit-delete-confirm" />
      </SheetContent>
    </Sheet>
  );
}

function AddProjectDialog({ open, onOpenChange, onDone }) {
  const [form, setForm] = useState({ name: "", code: "", location: "", marketing_office: "" });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const submit = async () => {
    if (!form.name) { toast.error("Nama proyek wajib diisi."); return; }
    setBusy(true);
    try {
      await api.post("/projects", form);
      toast.success("Proyek dibuat.");
      onOpenChange(false); setForm({ name: "", code: "", location: "", marketing_office: "" });
      onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat proyek."); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Proyek Baru</DialogTitle>
          <DialogDescription>Anda otomatis menjadi anggota proyek.</DialogDescription></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5"><Label htmlFor="pn">Nama Proyek</Label>
            <Input id="pn" value={form.name} onChange={(e) => set("name", e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="pc">Kode</Label>
            <Input id="pc" value={form.code} onChange={(e) => set("code", e.target.value.toUpperCase())} placeholder="otomatis dari aturan penomoran bila kosong" /></div>
          <div className="space-y-1.5"><Label htmlFor="pl">Lokasi</Label>
            <Input id="pl" value={form.location} onChange={(e) => set("location", e.target.value)} /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="pmo">Alamat kantor pemasaran</Label>
            <Input id="pmo" data-testid="project-form-marketing-office" value={form.marketing_office}
              placeholder="Lokasi bawaan survei lead (boleh dikosongkan)"
              onChange={(e) => set("marketing_office", e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={PROJECTS.createSubmit} onClick={submit} disabled={busy}>{busy ? "Menyimpan..." : "Buat Proyek"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AddUnitsDialog({ projectId, open, onOpenChange, onDone }) {
  const [form, setForm] = useState({ prefix: "B", type: "Tipe 45/90", price: "650000000", count: "3", start_index: "1" });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const submit = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/projects/${projectId}/units`, {
        prefix: form.prefix, type: form.type, price: Number(form.price) || 0,
        count: Number(form.count) || 1, start_index: Number(form.start_index) || 1,
      });
      toast.success(`${res.data.data.count} unit dibuat.`);
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat unit."); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Tambah Unit</DialogTitle>
          <DialogDescription>Generate unit berurutan (mis. B-01, B-02, ...).</DialogDescription></DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5"><Label htmlFor="projectspage-prefix">Prefix</Label>
            <Input id="projectspage-prefix" value={form.prefix} onChange={(e) => set("prefix", e.target.value.toUpperCase())} /></div>
          <div className="space-y-1.5"><Label>Tipe</Label>
            <ReferenceSelect group="unit_type" value={form.type}
              onChange={(v) => set("type", v)} testId="unit-gen-type" /></div>
          <div className="space-y-1.5"><Label htmlFor="projectspage-harga-rp">Harga (Rp)</Label>
            <RupiahInput id="projectspage-harga-rp" value={form.price} onChange={(e) => set("price", e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="projectspage-jumlah">Jumlah</Label>
            <Input id="projectspage-jumlah" type="number" value={form.count} onChange={(e) => set("count", e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="projectspage-mulai-index">Mulai Index</Label>
            <Input id="projectspage-mulai-index" type="number" value={form.start_index} onChange={(e) => set("start_index", e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={PROJECTS.unitGenSubmit} onClick={submit} disabled={busy}>{busy ? "Memproses..." : "Generate"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
