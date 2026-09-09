import React, { useState } from "react";
import { toast } from "sonner";
import { Zap } from "lucide-react";

import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import PhoneInput from "@/components/patterns/PhoneInput";
import api from "@/services/apiClient";
import { P94 } from "@/constants/testIds";
import ReferenceItems from "@/components/patterns/ReferenceItems";

/** Simulasi pesan masuk berbentuk payload Meta ASLI → diproses jalur webhook yang sama. */
export default function WaSimulateInboundDialog({ open, onOpenChange, onDone, defaultPhone = "" }) {
  const [phone, setPhone] = useState(defaultPhone);
  const [name, setName] = useState("");
  const [mtype, setMtype] = useState("text");
  const [message, setMessage] = useState("Halo, saya tertarik dengan unitnya. Boleh info harga?");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!phone) { toast.error("Nomor WA wajib diisi."); return; }
    setBusy(true);
    try {
      const res = await api.post("/wa/simulate/inbound", { phone, name, message, mtype });
      const r = res.data.data.result || {};
      if (r.skipped) toast.warning(`Pesan dilewati: ${r.skipped}`);
      else if (r.captured) toast.success("Pesan masuk → lead otomatis dibuat (setting auto-capture NYALA).");
      else if (r.lead_id) toast.success("Pesan masuk tercatat di percakapan lead yang sudah ada.");
      else toast.success("Pesan masuk tercatat — kontak masuk antrean 'Kontak WA → Lead'.");
      onOpenChange(false); setName("");
      onDone?.(res.data.data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengirim simulasi."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Zap className="h-4 w-4 text-primary" /> Simulasi pesan WhatsApp masuk</DialogTitle>
          <DialogDescription>
            Payload dibentuk persis seperti webhook Meta (object <code>whatsapp_business_account</code>) dan
            diproses jalur yang sama — saat kredensial dipasang, tidak ada kode yang berubah.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="wa-sim-phone">Nomor pengirim (WA)</Label>
            <PhoneInput id="wa-sim-phone" value={phone} onChange={setPhone} testId={P94.simulatePhone} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="wa-sim-name">Nama profil WA (opsional)</Label>
            <Input id="wa-sim-name" data-testid={P94.simulateName} value={name} onChange={(e) => setName(e.target.value)} placeholder="Nama di profil WhatsApp" />
          </div>
          <div className="space-y-1.5">
            <Label>Jenis pesan</Label>
            <Select value={mtype} onValueChange={setMtype}>
              <SelectTrigger aria-label="Jenis pesan"><SelectValue /></SelectTrigger>
              <SelectContent>
                <ReferenceItems group="wa_inbound_type" />
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="wa-sim-msg">Isi pesan / caption</Label>
            <Textarea id="wa-sim-msg" data-testid={P94.simulateMessage} rows={3} value={message} onChange={(e) => setMessage(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={P94.simulateSubmit} onClick={submit} disabled={busy}>{busy ? "Mengirim…" : "Kirim simulasi"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
