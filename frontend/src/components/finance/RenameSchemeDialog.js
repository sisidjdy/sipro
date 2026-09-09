import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import api from "@/services/apiClient";

/**
 * Ubah nama / status default skema pembayaran & komisi
 * (PUT /finance/config/payment-schemes|commission-schemes/{id}).
 * Backend mengunci perubahan isi termin/tier bila skema sudah dipakai transaksi.
 */
export default function RenameSchemeDialog({ kind, scheme, open, onOpenChange, onDone }) {
  const [name, setName] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open && scheme) { setName(scheme.name || ""); setIsDefault(Boolean(scheme.is_default)); }
  }, [open, scheme]);

  const submit = async () => {
    if (!name.trim()) { toast.error("Nama skema wajib diisi."); return; }
    setBusy(true);
    try {
      const body = { name, is_default: isDefault };
      const res = kind === "payment-schemes"
        ? await api.put(`/finance/config/payment-schemes/${scheme.id}`, body)
        : await api.put(`/finance/config/commission-schemes/${scheme.id}`, body);
      const synced = res.data?.denorm_synced || 0;
      toast.success(synced ? `Skema diperbarui. ${synced} transaksi ikut disamakan.` : "Skema diperbarui.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memperbarui skema."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Ubah Skema</DialogTitle>
          <DialogDescription>
            Nama baru otomatis disamakan pada tagihan/komisi yang sudah memakai skema ini.
            Isi termin/tier tidak bisa diubah bila skema sudah terpakai.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="renameschemedialog-nama-skema">Nama Skema</Label>
            <Input id="renameschemedialog-nama-skema" data-testid="scheme-edit-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={isDefault} onCheckedChange={(v) => setIsDefault(Boolean(v))} />
            Jadikan skema default
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid="scheme-edit-submit" onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
