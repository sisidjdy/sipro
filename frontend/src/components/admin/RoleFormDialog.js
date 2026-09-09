import React, { useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import api from "@/services/apiClient";
import { ADMIN } from "@/constants/testIds";
import { RoleMenuList, useRolePerms } from "./RoleMenuPreview";

const NONE = "__none__";
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^[^a-z]+/, "").replace(/_+$/, "").slice(0, 32);

/** Dialog tambah/ubah peran kustom. `role` null = buat baru; `copyFrom` = peran yang izinnya disalin. */
export default function RoleFormDialog({ role, copyFrom, scopeOnly = false, baseOptions, baseLabels, scopeMeta, onClose, onSaved }) {
  const isEdit = !!role;
  const [f, setF] = useState({
    label: role?.label || (copyFrom ? `${copyFrom.label} (Salinan)` : ""),
    code: role?.code || (copyFrom ? slug(`${copyFrom.code}_salinan`) : ""),
    description: role?.description || copyFrom?.description || "",
    inherits: role?.inherits || copyFrom?.inherits || NONE,
    scope: role?.scope || copyFrom?.scope || "all",
  });
  const [codeTouched, setCodeTouched] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const { perms } = useRolePerms(true);
  // Pratinjau: peran yang sedang diubah = dirinya; peran baru = sumber salinan atau peran induk.
  const previewRole = isEdit ? role.code : (copyFrom?.code || (f.inherits !== NONE ? f.inherits : null));
  const previewNote = isEdit ? "Menu yang dilihat peran ini saat ini."
    : copyFrom ? `Menu yang akan dilihat, sama seperti ${copyFrom.label} (izin disalin).`
      : f.inherits !== NONE ? "Menu yang akan dilihat berdasarkan izin peran induk; centang di matriks bisa menambah/mencabutnya."
        : "Tanpa peran induk: menu hanya muncul setelah izinnya dicentang di matriks.";
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const labelOf = (code) => baseLabels.find((r) => r.code === code)?.label || code;

  const submit = async (e) => {
    e.preventDefault();
    const body = scopeOnly ? { scope: f.scope }
      : { label: f.label.trim(), description: f.description.trim() || null,
        inherits: f.inherits === NONE ? null : f.inherits, scope: f.scope };
    setSaving(true);
    try {
      if (isEdit) await api.put(`/admin/roles/${role.code}`, body);
      else await api.post("/admin/roles", { ...body, code: f.code.trim(), copy_from: copyFrom?.code || null });
      toast.success(scopeOnly ? `Lingkup data peran ${role.label} diperbarui — berlaku pada permintaan berikutnya.`
        : isEdit ? "Peran diperbarui." : copyFrom
          ? `Peran "${body.label}" dibuat dengan izin yang sama seperti ${copyFrom.label}.`
          : `Peran "${body.label}" dibuat — atur izinnya di matriks.`);
      onSaved?.();
      onClose();
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Gagal menyimpan peran.");
    } finally {
      setSaving(false);
    }
  };

  if (scopeOnly) {
    return (
      <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
        <DialogContent data-testid={ADMIN.roleForm} className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Lingkup data: {role.label}</DialogTitle>
            <DialogDescription>
              Peran bawaan — nama & izinnya diatur lewat matriks; di sini hanya lingkup baris data yang
              boleh dilihat (bawaan: <b>{scopeMeta?.[role.scope_default]?.label || role.scope_default}</b>).
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label>Lingkup data</Label>
              <Select value={f.scope} onValueChange={(v) => set("scope", v)}>
                <SelectTrigger data-testid={ADMIN.roleFormScope} aria-label="Lingkup data"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(scopeMeta).map(([k, m]) => (
                    <SelectItem key={k} value={k} data-testid={`${ADMIN.roleFormScope}-opt-${k}`}>
                      {m.label}{k === role.scope_default ? " (bawaan)" : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground">{scopeMeta?.[f.scope]?.help}</p>
            </div>
            <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-900">
              Dipakai {role.users} pengguna. Lingkup berlaku pada permintaan berikutnya tanpa masuk ulang —
              "Seluruh data organisasi" membuat peran ini melihat baris milik siapa pun.
            </p>
            <DialogFooter>
              <Button type="button" variant="outline" data-testid={ADMIN.roleFormCancel} onClick={onClose}>Batal</Button>
              <Button type="submit" data-testid={ADMIN.roleFormSubmit} disabled={saving || f.scope === role.scope}>
                {saving ? "Menyimpan…" : "Simpan Lingkup"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent data-testid={ADMIN.roleForm} className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? `Ubah peran: ${role.label}` : copyFrom ? `Duplikat peran: ${copyFrom.label}` : "Tambah Peran Baru"}</DialogTitle>
          <DialogDescription>
            {copyFrom
              ? `Seluruh centang izin "${copyFrom.label}" disalin ke peran baru sebagai baris matriks sendiri, lalu bisa diubah bebas.`
              : "Peran menentukan menu dan izin yang tersedia. Izin diatur per resource di matriks setelah peran dibuat."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="role-label">Nama peran</Label>
              <Input id="role-label" data-testid={ADMIN.roleFormLabel} value={f.label} required minLength={3} maxLength={60}
                placeholder="mis. Admin Gudang"
                onChange={(e) => { set("label", e.target.value); if (!codeTouched) set("code", slug(e.target.value)); }} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="role-code">Kode (unik, tidak bisa diubah)</Label>
              <Input id="role-code" data-testid={ADMIN.roleFormCode} value={f.code} required disabled={isEdit}
                pattern="^[a-z][a-z0-9_]{2,31}$" title="huruf kecil, angka, garis bawah; diawali huruf; 3–32 karakter"
                placeholder="admin_gudang" className="font-mono"
                onChange={(e) => { setCodeTouched(true); set("code", e.target.value.toLowerCase()); }} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role-desc">Keterangan (opsional)</Label>
            <Textarea id="role-desc" data-testid={ADMIN.roleFormDesc} rows={2} maxLength={300} value={f.description}
              placeholder="Tugas utama peran ini…" onChange={(e) => set("description", e.target.value)} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Mewarisi izin dari</Label>
              <Select value={f.inherits} onValueChange={(v) => set("inherits", v)}>
                <SelectTrigger data-testid={ADMIN.roleFormInherits} aria-label="Peran induk"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE} data-testid={`${ADMIN.roleFormInherits}-opt-none`}>Tidak mewarisi (mulai dari nol)</SelectItem>
                  {baseOptions.map((c) => (
                    <SelectItem key={c} value={c} data-testid={`${ADMIN.roleFormInherits}-opt-${c}`}>{labelOf(c)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground">Izin & menu peran induk berlaku otomatis; bisa ditimpa di matriks.</p>
            </div>
            <div className="space-y-1.5">
              <Label>Lingkup data</Label>
              <Select value={f.scope} onValueChange={(v) => set("scope", v)}>
                <SelectTrigger data-testid={ADMIN.roleFormScope} aria-label="Lingkup data"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(scopeMeta).map(([k, m]) => (
                    <SelectItem key={k} value={k} data-testid={`${ADMIN.roleFormScope}-opt-${k}`}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground">{scopeMeta?.[f.scope]?.help}</p>
            </div>
          </div>
          <details data-testid={ADMIN.roleFormPreview} className="rounded-md border bg-secondary/40 px-3 py-2" open>
            <summary className="cursor-pointer text-xs font-medium">Pratinjau menu — {previewNote}</summary>
            <div className="mt-2">
              {previewRole ? <RoleMenuList role={previewRole} perms={perms} compact /> : (
                <p className="text-xs text-muted-foreground">Hanya <b>Beranda</b>, <b>Notifikasi</b>, dan menu yang izinnya dicentang kemudian.</p>
              )}
            </div>
          </details>
          <DialogFooter>
            <Button type="button" variant="outline" data-testid={ADMIN.roleFormCancel} onClick={onClose}>Batal</Button>
            <Button type="submit" data-testid={ADMIN.roleFormSubmit} disabled={saving}>
              {saving ? "Menyimpan…" : isEdit ? "Simpan Perubahan" : "Buat Peran"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
