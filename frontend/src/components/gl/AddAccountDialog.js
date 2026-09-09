import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { GL } from "@/constants/testIds";

const EMPTY = { code: "", name: "", type: "expense" };

export default function AddAccountDialog({ open, onOpenChange, onDone }) {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  useEffect(() => { if (open) setForm(EMPTY); }, [open]);

  const submit = async () => {
    if (!form.code.trim() || !form.name.trim()) { toast.error("Isi kode & nama akun."); return; }
    setBusy(true);
    try {
      await api.post("/gl/accounts", { code: form.code, name: form.name, type: form.type });
      toast.success("Akun ditambahkan.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menambah akun."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Tambah Akun</DialogTitle>
          <DialogDescription>Tambahkan akun ke bagan akun (CoA).</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="space-y-1.5"><Label htmlFor="addaccountdialog-kode-akun">Kode Akun</Label><Input id="addaccountdialog-kode-akun" value={form.code} onChange={(e) => set("code", e.target.value)} placeholder="mis. 6-1400" /></div>
          <div className="space-y-1.5"><Label htmlFor="addaccountdialog-nama-akun">Nama Akun</Label><Input id="addaccountdialog-nama-akun" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="mis. Beban Sewa" /></div>
          <div className="space-y-1.5"><Label>Tipe</Label>
            <ReferenceSelect group="account_type" value={form.type}
              onChange={(v) => set("type", v)} testId="gl-form-type" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={GL.accountAddSubmit} onClick={submit} disabled={busy}>{busy ? "Menyimpan…" : "Simpan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
