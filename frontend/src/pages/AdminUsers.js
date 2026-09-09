import React, { useCallback, useEffect, useState } from "react";
import { Users2, UserPlus, ShieldCheck, Pencil } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import EmptyState from "@/components/patterns/EmptyState";
import { roleLabel } from "@/utils/formatters";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { ADMIN } from "@/constants/testIds";
import { useReference } from "@/context/ReferenceContext";
import { RolePreviewButton } from "@/components/admin/RoleMenuPreview";

function RoleSelect({ id, value, onChange, testId }) {
  const { options, labelOf } = useReference();
  const base = options("user_role");
  const roles = value && !base.some((r) => r.value === value)
    ? [...base, { value, label: roleLabel(value) }] : base;
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger id={id} aria-label="Peran" data-testid={testId}><SelectValue placeholder="Pilih peran" /></SelectTrigger>
      <SelectContent>
        {roles.map((r) => <SelectItem key={r.value} value={r.value} data-testid={`${testId}-opt-${r.value}`}>{r.label || labelOf("user_role", r.value) || roleLabel(r.value)}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

/** Dialog ubah pengguna: nama, telepon, peran, sandi baru (opsional). Backend: PUT /admin/users/{id}. */
function EditUserDialog({ user, onClose, onSaved }) {
  const { labelOf } = useReference();
  const [form, setForm] = useState({ name: user.name || "", phone: user.phone || "", role: user.role, password: "" });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const save = async () => {
    setSaving(true); setErr("");
    try {
      const body = { name: form.name, phone: form.phone || null, role: form.role };
      if (form.password) body.password = form.password;
      await api.put(`/admin/users/${user.id}`, body);
      toast.success(`Pengguna ${form.name} diperbarui.`);
      onSaved();
    } catch (e) { setErr(e?.response?.data?.detail || "Gagal menyimpan pengguna."); }
    finally { setSaving(false); }
  };
  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent data-testid="user-edit-dialog">
        <DialogHeader><DialogTitle>Ubah Pengguna</DialogTitle></DialogHeader>
        {err ? <p data-testid="user-edit-error" className="text-sm text-rose-600">{err}</p> : null}
        <div className="space-y-3">
          <p className="font-mono text-xs text-muted-foreground">{user.email}</p>
          <div className="space-y-1.5"><Label htmlFor="edit-name">Nama</Label>
            <Input id="edit-name" data-testid="user-edit-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div className="space-y-1.5"><Label htmlFor="edit-phone">Telepon / WhatsApp</Label>
            <Input id="edit-phone" data-testid="user-edit-phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="+628…" /></div>
          <div className="space-y-1.5"><Label htmlFor="edit-role">Peran</Label>
            <div className="flex items-center gap-2">
              <div className="flex-1"><RoleSelect id="edit-role" testId="user-edit-role" value={form.role} onChange={(v) => setForm({ ...form, role: v })} /></div>
              <RolePreviewButton role={form.role} label={labelOf("user_role", form.role) || roleLabel(form.role)} testId="user-edit-role-preview" />
            </div></div>
          <div className="space-y-1.5"><Label htmlFor="edit-password">Kata sandi baru (kosongkan bila tidak diubah)</Label>
            <Input id="edit-password" data-testid="user-edit-password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="minimal 6 karakter" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button data-testid="user-edit-save" onClick={save} disabled={saving || !form.name.trim()}>{saving ? "Menyimpan..." : "Simpan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function AdminUsers() {
  const { can } = useAuth();
  const { labelOf, reload: reloadReference } = useReference();
  // Peran kustom yang baru dibuat di Hak Akses harus langsung tersedia di dropdown peran.
  useEffect(() => { reloadReference(); }, [reloadReference]);
  const canCreate = can("users", "create");
  const canUpdate = can("users", "update");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "sales" });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.get("/admin/users", { params: { limit: 100 } });
      setRows(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat pengguna.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    setSaving(true);
    setFormError("");
    try {
      await api.post("/admin/users", form);
      setOpen(false);
      setForm({ name: "", email: "", password: "", role: "sales" });
      load();
    } catch (e) {
      setFormError(e?.response?.data?.detail || "Gagal membuat pengguna.");
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (u) => {
    try { await api.put(`/admin/users/${u.id}`, { is_active: !u.is_active }); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengubah status."); }
  };

  return (
    <div data-testid={ADMIN.usersPage} className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users2 className="h-5 w-5 text-primary" />
          <h1 className="page-title">Pengguna</h1>
          <span className="rounded-full bg-secondary px-2 py-0.5 text-xs text-muted-foreground tabular-nums">{rows.length}</span>
        </div>
        {canCreate ? (
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button size="sm" data-testid="user-add-btn"><UserPlus className="h-4 w-4 mr-1.5" /> Tambah Pengguna</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Tambah Pengguna</DialogTitle></DialogHeader>
            {formError ? <p className="text-sm text-rose-600">{formError}</p> : null}
            <div className="space-y-3">
              <div className="space-y-1.5"><Label htmlFor="user-name">Nama</Label>
                <Input id="user-name" data-testid="user-form-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="mis. Budi Santoso" /></div>
              <div className="space-y-1.5"><Label htmlFor="user-email">Email</Label>
                <Input id="user-email" data-testid="user-form-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="nama@sipro.co.id" /></div>
              <div className="space-y-1.5"><Label htmlFor="user-password">Kata Sandi</Label>
                <Input id="user-password" data-testid="user-form-password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="minimal 8 karakter" /></div>
              <div className="space-y-1.5"><Label htmlFor="user-role">Peran</Label>
                <div className="flex items-center gap-2">
                  <div className="flex-1"><RoleSelect id="user-role" testId="user-form-role" value={form.role} onChange={(v) => setForm({ ...form, role: v })} /></div>
                  <RolePreviewButton role={form.role} label={labelOf("user_role", form.role) || roleLabel(form.role)} testId="user-form-role-preview" />
                </div>
                <p className="text-[11px] text-muted-foreground">Klik ikon mata untuk melihat menu yang akan dilihat peran ini sebelum akun dibuat.</p>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>Batal</Button>
              <Button data-testid="user-form-save" onClick={create} disabled={saving}>{saving ? "Menyimpan..." : "Simpan"}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        ) : null}
      </div>

      {!canUpdate ? (
        <p data-testid="users-readonly-note" className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900">
          Peran Anda hanya boleh MELIHAT daftar pengguna. Mengubah pengguna butuh izin <b>users:update</b> di Hak Akses (RBAC).
        </p>
      ) : null}

      {loading ? <LoadingCards count={5} /> : error ? <ErrorState message={error} onRetry={load} /> :
        rows.length === 0 ? (
          <EmptyState icon={Users2} title="Belum ada pengguna" description="Tambahkan pengguna pertama untuk organisasi ini." actionLabel="Tambah Pengguna" onAction={() => setOpen(true)} />
        ) : (
        <div data-testid={ADMIN.usersTable} className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead className="bg-secondary/60 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 font-medium">Nama</th>
                <th className="px-4 py-2.5 font-medium">Email</th>
                <th className="px-4 py-2.5 font-medium">Peran</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium text-right">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((u) => (
                <tr key={u.id} data-testid="user-row" data-email={u.email} className="hover:bg-secondary/30">
                  <td className="px-4 py-2.5 font-medium">{u.name}{u.phone ? <p className="text-[11px] font-normal text-muted-foreground">{u.phone}</p> : null}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">{u.email}</td>
                  <td className="px-4 py-2.5">
                    <span data-testid="user-role-badge" data-email={u.email} className="inline-flex items-center gap-1 rounded-full border bg-accent/50 px-2 py-0.5 text-xs">
                      <ShieldCheck className="h-3 w-3" /> {labelOf("user_role", u.role) !== u.role ? labelOf("user_role", u.role) : roleLabel(u.role)}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`status-pill ${u.is_active ? "status-available" : "status-sold"}`}>
                      {u.is_active ? "Aktif" : "Nonaktif"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {canUpdate ? (
                      <div className="inline-flex gap-1.5">
                        <Button size="sm" variant="outline" data-testid="user-edit-btn" data-email={u.email} aria-label={`Ubah ${u.email}`} onClick={() => setEditing(u)}>
                          <Pencil className="mr-1 h-3.5 w-3.5" /> Ubah
                        </Button>
                        <Button size="sm" variant="outline" data-testid="user-toggle-btn" data-email={u.email} aria-label={`${u.is_active ? "Nonaktifkan" : "Aktifkan"} ${u.email}`} onClick={() => toggleActive(u)}>
                          {u.is_active ? "Nonaktifkan" : "Aktifkan"}
                        </Button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing ? <EditUserDialog user={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} /> : null}
    </div>
  );
}
