import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Building2, Plus, ArrowRightLeft, CheckCircle2, Users2, Sparkles, Pause, Play, Pencil,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatNumber } from "@/utils/formatters";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { ADMIN } from "@/constants/testIds";

function Stat({ label, value }) {
  return (
    <div className="rounded-lg border bg-background/60 p-2 text-center">
      <p className="text-base font-semibold tabular-nums">{formatNumber(value)}</p>
      <p className="text-[11px] text-muted-foreground">{label}</p>
    </div>
  );
}

export default function OrganizationsPage() {
  const { user, switchOrg, refresh } = useAuth();
  const isSuper = user?.role === "super_admin";
  const [rows, setRows] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [homeId, setHomeId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [form, setForm] = useState({ name: "", owner_name: "", owner_email: "", owner_password: "" });
  const [editing, setEditing] = useState(null);
  const [editName, setEditName] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/admin/orgs");
      setRows(res.data.data || []);
      setActiveId(res.data.active_org_id);
      setHomeId(res.data.home_org_id);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat organisasi.");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.name.trim() || !form.owner_name.trim() || !form.owner_email.trim()) {
      toast.error("Nama organisasi, nama & email owner wajib diisi."); return;
    }
    if ((form.owner_password || "").length < 6) { toast.error("Kata sandi owner minimal 6 karakter."); return; }
    setSaving(true);
    try {
      const res = await api.post("/admin/orgs", form);
      toast.success(`Tenant '${res.data.data.name}' berhasil dibuat.`);
      setOpen(false);
      setForm({ name: "", owner_name: "", owner_email: "", owner_password: "" });
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat organisasi."); }
    finally { setSaving(false); }
  };

  const doSwitch = async (org) => {
    setBusyId(org.id);
    try {
      toast.info(`Beralih ke ${org.name}…`);
      await switchOrg(org.id); // hard-reloads on success
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal beralih organisasi."); setBusyId(null); }
  };

  const openEdit = (org) => { setEditing(org); setEditName(org.name || ""); };

  const saveName = async () => {
    const name = editName.trim();
    if (name.length < 2) { toast.error("Nama organisasi minimal 2 karakter."); return; }
    setSaving(true);
    try {
      await api.put(`/admin/orgs/${editing.id}`, { name });
      toast.success(`Nama organisasi diubah menjadi '${name}'.`);
      setEditing(null);
      await load();
      refresh?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengubah nama organisasi."); }
    finally { setSaving(false); }
  };

  const toggleStatus = async (org) => {
    const next = org.status === "suspended" ? "active" : "suspended";
    setBusyId(org.id);
    try {
      await api.put(`/admin/orgs/${org.id}`, { status: next });
      toast.success(next === "active" ? "Organisasi diaktifkan." : "Organisasi dinonaktifkan.");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memperbarui status."); }
    finally { setBusyId(null); }
  };

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={ADMIN.orgsPage} className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Building2 className="h-5 w-5 text-primary" />
          <h1 className="page-title">Organisasi (Tenant)</h1>
          <span className="rounded-full bg-secondary px-2 py-0.5 text-xs tabular-nums text-muted-foreground">{rows.length}</span>
        </div>
        {isSuper ? (
          <Button data-testid={ADMIN.orgAddBtn} size="sm" onClick={() => setOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> Onboard Tenant
          </Button>
        ) : null}
      </div>

      <div className="flex items-start gap-2 rounded-xl border border-primary/20 bg-primary/5 p-3 text-sm">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <p className="text-muted-foreground">
          {isSuper
            ? "Sebagai super admin Anda dapat mengelola semua tenant dan beralih konteks untuk melihat/mengelola data tiap organisasi. Semua data terisolasi per organisasi."
            : "Menampilkan organisasi Anda. Pengelolaan lintas-tenant hanya untuk super admin."}
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {rows.length === 0 ? (
          <EmptyState icon={Building2} title="Belum ada organisasi" description="Onboard tenant pertama." />
        ) : rows.map((org) => {
          const isActive = org.id === activeId;
          const isHome = org.id === homeId;
          const s = org.stats || {};
          return (
            <div key={org.id} data-testid={ADMIN.orgRow}
              className={`rounded-2xl border bg-card p-4 transition-shadow ${isActive ? "ring-2 ring-primary/40" : "hover:shadow-sm"}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p data-testid={ADMIN.orgNameText} className="section-title">{org.name}</p>
                    <StatusPill status={org.status === "suspended" ? "sold" : "available"}
                      label={org.status === "suspended" ? "Nonaktif" : "Aktif"} />
                    {isActive ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                        <CheckCircle2 className="h-3 w-3" /> Konteks Aktif
                      </span>
                    ) : null}
                    {isHome ? <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px]">Home</span> : null}
                  </div>
                  <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{org.id}</p>
                </div>
              </div>

              <div className="mt-3 grid grid-cols-4 gap-2">
                <Stat label="Pengguna" value={s.users} />
                <Stat label="Lead" value={s.leads} />
                <Stat label="Deal" value={s.deals} />
                <Stat label="Proyek" value={s.projects} />
              </div>

              {isSuper ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button data-testid={ADMIN.orgSwitchBtn} size="sm" variant={isActive ? "outline" : "default"}
                    disabled={isActive || busyId === org.id} onClick={() => doSwitch(org)}>
                    <ArrowRightLeft className="mr-1.5 h-4 w-4" />
                    {isActive ? "Sedang aktif" : (isHome ? "Kembali ke Home" : "Beralih")}
                  </Button>
                  <Button data-testid={ADMIN.orgEditBtn} size="sm" variant="outline"
                    disabled={busyId === org.id} onClick={() => openEdit(org)}>
                    <Pencil className="mr-1.5 h-4 w-4" /> Ubah nama
                  </Button>
                  <Button data-testid={ADMIN.orgStatusToggle} size="sm" variant="ghost"
                    disabled={busyId === org.id || isHome}
                    className={org.status === "suspended" ? "text-emerald-600" : "text-rose-600"}
                    onClick={() => toggleStatus(org)}>
                    {org.status === "suspended"
                      ? <><Play className="mr-1.5 h-4 w-4" /> Aktifkan</>
                      : <><Pause className="mr-1.5 h-4 w-4" /> Nonaktifkan</>}
                  </Button>
                </div>
              ) : (
                <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Users2 className="h-3.5 w-3.5" /> Organisasi Anda
                </p>
              )}
            </div>
          );
        })}
      </div>

      <Dialog open={!!editing} onOpenChange={(v) => { if (!v) setEditing(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ubah Nama Organisasi</DialogTitle>
            <DialogDescription>Nama ini tampil di bilah atas, dokumen, dan laporan.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="organizationspage-edit-nama">Nama Organisasi</Label>
            <Input id="organizationspage-edit-nama" data-testid={ADMIN.orgEditName} value={editName}
              onChange={(e) => setEditName(e.target.value)} placeholder="mis. Harmony Land 5"
              onKeyDown={(e) => { if (e.key === "Enter") saveName(); }} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)} disabled={saving}>Batal</Button>
            <Button data-testid={ADMIN.orgEditSubmit} onClick={saveName} disabled={saving}>
              {saving ? "Menyimpan..." : "Simpan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Onboard Tenant Baru</DialogTitle>
            <DialogDescription>Buat organisasi baru beserta akun owner pertamanya. Data akan terisolasi penuh.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="organizationspage-nama-organisasi">Nama Organisasi</Label>
              <Input id="organizationspage-nama-organisasi" data-testid={ADMIN.orgName} value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="mis. PT Griya Asri" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="organizationspage-nama-owner">Nama Owner</Label>
                <Input id="organizationspage-nama-owner" data-testid={ADMIN.orgOwnerName} value={form.owner_name}
                  onChange={(e) => setForm({ ...form, owner_name: e.target.value })} placeholder="Nama lengkap" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="organizationspage-email-owner">Email Owner</Label>
                <Input id="organizationspage-email-owner" data-testid={ADMIN.orgOwnerEmail} type="email" value={form.owner_email}
                  onChange={(e) => setForm({ ...form, owner_email: e.target.value })} placeholder="owner@tenant.co.id" />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="organizationspage-kata-sandi-owner">Kata Sandi Owner</Label>
              <Input id="organizationspage-kata-sandi-owner" data-testid={ADMIN.orgOwnerPassword} type="password" value={form.owner_password}
                onChange={(e) => setForm({ ...form, owner_password: e.target.value })} placeholder="Min. 6 karakter" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>Batal</Button>
            <Button data-testid={ADMIN.orgCreateSubmit} onClick={create} disabled={saving}>
              {saving ? "Membuat..." : "Buat Tenant"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
