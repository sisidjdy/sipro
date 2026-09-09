import React, { useCallback, useEffect, useState } from "react";
import { UserCog, Plus, Pencil, Trash2, Users2, GitBranch, Copy, Eye } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import api from "@/services/apiClient";
import { ADMIN } from "@/constants/testIds";
import RoleFormDialog from "./RoleFormDialog";
import { RoleMenuPreviewDialog } from "./RoleMenuPreview";
import { useReference } from "@/context/ReferenceContext";

/** Daftar peran (bawaan + kustom) dengan tombol Tambah/Ubah/Hapus peran kustom. */
export default function RolesManager({ editable, onChanged }) {
  const { reload: reloadReference } = useReference();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState(null);      // null | {} (baru) | role (ubah)
  const [confirmDel, setConfirmDel] = useState(null);
  const [preview, setPreview] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await api.get("/admin/roles");
      setData(res.data);
      setError("");
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat daftar peran.");
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  // Dropdown "Peran" di halaman Pengguna membaca kamus reference (`user_role`) yang dimuat
  // sekali saat login — tanpa penyegaran ini peran kustom baru tidak muncul sampai reload.
  const afterChange = async () => { await load(); reloadReference(); onChanged?.(); };

  const remove = async () => {
    const code = confirmDel?.code;
    setConfirmDel(null);
    try {
      await api.delete(`/admin/roles/${code}`);
      toast.success(`Peran "${confirmDel.label}" dihapus.`);
      await afterChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menghapus peran.");
    }
  };

  const rows = data?.data || [];
  const custom = rows.filter((r) => r.custom);
  const scopeLabel = (s) => data?.scope_meta?.[s]?.label || s;

  return (
    <section data-testid={ADMIN.rolesPanel} className="rounded-xl border bg-card shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <UserCog className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold">Daftar Peran</h2>
          <span data-testid={ADMIN.rolesCount} className="rounded-full bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">
            {rows.length} peran · {custom.length} kustom
          </span>
        </div>
        {editable ? (
          <Button data-testid={ADMIN.rolesAdd} size="sm" onClick={() => setForm({})}>
            <Plus className="mr-1.5 h-4 w-4" /> Tambah Peran
          </Button>
        ) : null}
      </div>
      {error ? <p data-testid={ADMIN.rolesError} className="px-4 py-3 text-sm text-destructive">{error}</p> : null}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-secondary/60 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-2 font-medium">Peran</th>
              <th className="px-3 py-2 font-medium">Kode</th>
              <th className="px-3 py-2 font-medium">Mewarisi izin</th>
              <th className="px-3 py-2 font-medium">Lingkup data</th>
              <th className="px-3 py-2 font-medium">Pengguna</th>
              <th className="px-3 py-2 font-medium text-right">Aksi</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((r) => (
              <tr key={r.code} data-testid={ADMIN.rolesRow} data-role={r.code} className={r.custom ? "bg-primary/[0.03]" : ""}>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{r.label}</span>
                    {r.custom ? (
                      <span className="rounded-full border border-primary/40 bg-primary/10 px-1.5 py-px text-[10px] font-semibold text-primary">kustom</span>
                    ) : r.full_access ? (
                      <span className="rounded-full border px-1.5 py-px text-[10px] text-muted-foreground">akses penuh</span>
                    ) : null}
                  </div>
                  {r.description ? <p className="mt-0.5 text-xs text-muted-foreground">{r.description}</p> : null}
                </td>
                <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{r.code}</td>
                <td className="px-3 py-2 text-xs">
                  {r.inherits ? (
                    <span className="inline-flex items-center gap-1"><GitBranch className="h-3 w-3" /> {rows.find((x) => x.code === r.inherits)?.label || r.inherits}</span>
                  ) : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="px-3 py-2 text-xs">
                  {r.full_access ? "Semua" : scopeLabel(r.scope)}
                  {r.scope_overridden ? (
                    <span data-testid={ADMIN.rolesScopeOverridden} data-role={r.code} className="ml-1 rounded-full border border-amber-300 bg-amber-50 px-1.5 py-px text-[10px] text-amber-800" title={`Bawaan: ${scopeLabel(r.scope_default)}`}>diubah</span>
                  ) : null}
                </td>
                <td className="px-3 py-2 text-xs">
                  <span className="inline-flex items-center gap-1"><Users2 className="h-3 w-3" /> {r.users}</span>
                </td>
                <td className="px-3 py-2 text-right">
                  <div className="inline-flex gap-1">
                    <Button data-testid={ADMIN.rolesPreview} data-role={r.code} variant="ghost" size="icon" className="h-7 w-7" aria-label="Pratinjau menu" title="Lihat menu yang akan dilihat peran ini" onClick={() => setPreview(r)}>
                      <Eye className="h-3.5 w-3.5" />
                    </Button>
                    {editable && !r.full_access ? (
                      <Button data-testid={ADMIN.rolesCopy} data-role={r.code} variant="ghost" size="icon" className="h-7 w-7" aria-label="Duplikat peran" title="Duplikat: peran baru dengan izin yang sama" onClick={() => setForm({ copyFrom: r })}>
                        <Copy className="h-3.5 w-3.5" />
                      </Button>
                    ) : null}
                    {r.custom && editable ? (
                      <>
                        <Button data-testid={ADMIN.rolesEdit} data-role={r.code} variant="ghost" size="icon" className="h-7 w-7" aria-label="Ubah peran" onClick={() => setForm(r)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button data-testid={ADMIN.rolesDelete} data-role={r.code} variant="ghost" size="icon" className="h-7 w-7 text-destructive" aria-label="Hapus peran" onClick={() => setConfirmDel(r)}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </>
                    ) : null}
                    {!r.custom && !r.full_access && editable ? (
                      <Button data-testid={ADMIN.rolesEditScope} data-role={r.code} variant="ghost" size="icon" className="h-7 w-7" aria-label="Ubah lingkup data" title="Ubah lingkup data peran bawaan" onClick={() => setForm({ ...r, scopeOnly: true })}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="px-4 py-2 text-xs text-muted-foreground">
        Peran baru muncul sebagai kolom di matriks di bawah; centang izinnya di sana. Bila peran mewarisi peran induk,
        izin induk berlaku otomatis sampai Anda menimpanya di matriks.
      </p>

      {form ? <RoleFormDialog role={form.code ? form : null} copyFrom={form.copyFrom || null} scopeOnly={!!form.scopeOnly} baseOptions={data?.base_options || []} baseLabels={rows} scopeMeta={data?.scope_meta || {}} onClose={() => setForm(null)} onSaved={afterChange} /> : null}

      {preview ? <RoleMenuPreviewDialog role={preview.code} label={preview.label} onClose={() => setPreview(null)} /> : null}

      <AlertDialog open={!!confirmDel} onOpenChange={(o) => { if (!o) setConfirmDel(null); }}>
        <AlertDialogContent data-testid={ADMIN.rolesDeleteConfirm}>
          <AlertDialogHeader>
            <AlertDialogTitle>Hapus peran "{confirmDel?.label}"?</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmDel?.users ? `Peran ini masih dipakai ${confirmDel.users} pengguna; pindahkan mereka dulu — penghapusan akan ditolak server.` : "Baris matriks izin milik peran ini ikut dibuang. Tindakan tidak bisa dibatalkan."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid={ADMIN.rolesDeleteCancel}>Batal</AlertDialogCancel>
            <AlertDialogAction data-testid={ADMIN.rolesDeleteOk} onClick={remove} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Hapus</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
