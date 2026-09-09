import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";

/**
 * Ubah / nonaktifkan akun CoA (PUT /gl/accounts/{code}).
 * Backend menolak perubahan TIPE akun bila sudah dipakai jurnal, supaya laporan
 * keuangan periode lalu tidak berubah retroaktif.
 */
export default function EditAccountDialog({ account, open, onOpenChange, onDone }) {
  const [name, setName] = useState("");
  const [type, setType] = useState("expense");
  const [active, setActive] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open && account) {
      setName(account.name || "");
      setType(account.type || "expense");
      setActive(account.is_active !== false);
    }
  }, [open, account]);

  const submit = async () => {
    if (!name.trim()) { toast.error("Nama akun wajib diisi."); return; }
    setBusy(true);
    try {
      await api.put(`/gl/accounts/${account.code}`, { name, type, is_active: active });
      toast.success("Akun diperbarui.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memperbarui akun."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Ubah Akun {account?.code}</DialogTitle>
          <DialogDescription>
            Tipe akun terkunci otomatis bila akun sudah dipakai di jurnal.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="editaccountdialog-nama-akun">Nama Akun</Label>
            <Input id="editaccountdialog-nama-akun" data-testid="gl-edit-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Tipe</Label>
            <ReferenceSelect group="account_type" value={type} onChange={setType} testId="gl-edit-type" />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={active} onCheckedChange={(v) => setActive(Boolean(v))} />
            Akun aktif (bisa dipakai di jurnal baru)
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid="gl-edit-submit" onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
