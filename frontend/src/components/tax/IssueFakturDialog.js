import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { TAX } from "@/constants/testIds";

export default function IssueFakturDialog({ open, onOpenChange, onDone }) {
  const [cands, setCands] = useState([]);
  const [dealId, setDealId] = useState("");
  const [npwp, setNpwp] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setDealId(""); setNpwp("");
    api.get("/tax/faktur-candidates").then((r) => setCands(r.data.data || [])).catch(() => setCands([]));
  }, [open]);

  const submit = async () => {
    if (!dealId) { toast.error("Pilih deal terlebih dahulu."); return; }
    setBusy(true);
    try {
      await api.post("/tax/faktur", { deal_id: dealId, buyer_npwp: npwp || null });
      toast.success("Faktur pajak berhasil diterbitkan.");
      onOpenChange(false);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menerbitkan faktur.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Terbitkan Faktur Pajak</DialogTitle>
          <DialogDescription>
            Pilih deal (harus sudah memiliki jadwal AR). DPP &amp; PPN dihitung otomatis dari harga unit.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label>Deal / Unit</Label>
            <Select value={dealId} onValueChange={setDealId}>
              <SelectTrigger data-testid={TAX.candidateSelect}>
                <SelectValue placeholder={cands.length ? "Pilih deal…" : "Tidak ada deal yang perlu difakturkan"} />
              </SelectTrigger>
              <SelectContent>
                {cands.map((c) => (
                  <SelectItem key={c.deal_id} value={c.deal_id}>
                    {(c.unit_code || "-")} · {c.buyer_name || "-"} · {formatIDR(c.price)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!cands.length ? (
              <p className="text-xs text-muted-foreground">Semua deal ber-AR sudah memiliki faktur pajak.</p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="issuefakturdialog-npwp-pembeli-opsional">NPWP Pembeli (opsional)</Label>
            <Input id="issuefakturdialog-npwp-pembeli-opsional" data-testid={TAX.npwpInput} value={npwp} onChange={(e) => setNpwp(e.target.value)}
              placeholder="mis. 09.123.456.7-011.000 (kosongkan untuk ambil dari data customer)" />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={TAX.issueFakturSubmit} onClick={submit} disabled={busy || !dealId}>
            {busy ? "Menerbitkan…" : "Terbitkan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
