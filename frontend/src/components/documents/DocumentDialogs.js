import React, { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/services/apiClient";
import { DOCS } from "@/constants/testIds";
import ReferenceItems from "@/components/patterns/ReferenceItems";

/** Dialog “Buat SPR” — SPR resmi dari KONTRAK (varian sesuai skema deal; angka = tagihan Finance). */
export function CreateSprDialog({ open, onOpenChange, onDone }) {
  const [contracts, setContracts] = useState([]);
  const [contractId, setContractId] = useState("");
  const [avail, setAvail] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setContractId(""); setAvail(null);
    (async () => {
      try {
        const res = await api.get("/contracts", { params: { limit: 100 } });
        setContracts(res.data.data || []);
      } catch { setContracts([]); }
    })();
  }, [open]);

  useEffect(() => {
    if (!contractId) { setAvail(null); return; }
    api.get(`/contracts/${contractId}/documents/available`)
      .then((res) => setAvail(res.data))
      .catch((e) => { setAvail(null); toast.error(e?.response?.data?.detail || "Gagal memuat template."); });
  }, [contractId]);

  const tpl = (avail?.data || []).find((t) => t.code === avail?.recommended_code);

  const submit = async () => {
    if (!contractId) { toast.error("Pilih kontrak (pembeli) terlebih dahulu."); return; }
    if (!tpl) { toast.error("Skema kontrak belum ditetapkan — pilih skema dulu."); return; }
    setBusy(true);
    try {
      const res = await api.post(`/contracts/${contractId}/documents`, { template_code: tpl.code });
      toast.success(`${tpl.name} ${res.data.data.doc_number} diterbitkan (draft).`);
      onOpenChange(false);
      onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menerbitkan SPR."); }
    finally { setBusy(false); }
  };

  const label = (c) => [c.customer_name || c.lead_name || "Pembeli",
    c.unit_code ? `Unit ${c.unit_code}` : null,
    c.scheme ? c.scheme.toUpperCase() : null].filter(Boolean).join(" — ");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-background">
        <DialogHeader>
          <DialogTitle>Terbitkan SPR</DialogTitle>
          <DialogDescription>
            SPR resmi lahir dari kontrak: variannya mengikuti skema pembayaran deal dan angkanya
            sama dengan tagihan Finance. Deal yang belum menjadi Pembeli belum punya SPR.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="spr-deal">Kontrak / pembeli</Label>
          <Select value={contractId} onValueChange={setContractId}>
            <SelectTrigger id="spr-deal" data-testid="spr-deal-select" aria-label="Pilih kontrak">
              <SelectValue placeholder="Pilih pembeli / unit" />
            </SelectTrigger>
            <SelectContent>
              {contracts.map((c) => (
                <SelectItem key={c.id} value={c.id}>{label(c)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {!contracts.length ? (
            <p className="text-xs text-muted-foreground">Belum ada kontrak — jadikan deal yang sudah booking sebagai Pembeli dulu.</p>
          ) : null}
          {tpl ? (
            <p data-testid="spr-dialog-template" className="text-xs text-muted-foreground">
              Akan diterbitkan: <b>{tpl.name}</b>{tpl.existing ? ` (sudah ada ${tpl.existing})` : ""}.
              {!tpl.can_generate ? (
                <span data-testid="spr-dialog-blocked" className="text-rose-700"> {(tpl.blocks || []).map((b) => b.detail).join(" ")}</span>
              ) : null}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid="spr-dialog-submit" onClick={submit} disabled={busy || !tpl || !tpl.can_generate}>
            {busy ? "Memproses..." : "Terbitkan SPR"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Dialog tanda tangan dokumen. */
export function SignDialog({ doc, onOpenChange, onDone }) {
  const [role, setRole] = useState("buyer");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const open = !!doc;

  useEffect(() => { if (open) { setRole("buyer"); setName(""); } }, [open]);

  const submit = async () => {
    if (!name.trim()) { toast.error("Nama penandatangan wajib diisi."); return; }
    setBusy(true);
    try {
      await api.post(`/documents/${doc.id}/sign`, { role, name });
      toast.success("Dokumen ditandatangani.");
      onOpenChange(false);
      onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menandatangani."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-background">
        <DialogHeader>
          <DialogTitle>Tandatangani Dokumen</DialogTitle>
          <DialogDescription>{doc?.doc_number}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="sign-role">Peran</Label>
            <Select value={role} onValueChange={setRole}>
              <SelectTrigger id="sign-role" aria-label="Peran penandatangan">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <ReferenceItems group="signer_role" only={["buyer", "seller", "sales"]} />
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="signer">Nama Penandatangan</Label>
            <Input id="signer" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={DOCS.signSubmit} onClick={submit} disabled={busy}>
            {busy ? "Memproses..." : "Tandatangani"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
