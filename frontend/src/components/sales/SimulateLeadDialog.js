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
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/services/apiClient";
import PhoneInput from "@/components/patterns/PhoneInput";
import { LEADS } from "@/constants/testIds";

// Simulates an inbound omnichannel lead (Meta Lead Ads / WhatsApp) via public webhook.
export default function SimulateLeadDialog({ open, onOpenChange, onDone }) {
  const [channel, setChannel] = useState("meta");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [message, setMessage] = useState("Halo, saya tertarik. Berapa harga & cicilannya?");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!phone) { toast.error("Nomor telepon wajib diisi."); return; }
    setBusy(true);
    try {
      const path = channel === "wa" ? "/webhooks/wa" : "/webhooks/meta-lead";
      const res = await api.post(path, {
        name, phone, message, campaign: "cluster-a-simulasi",
      });
      const dup = res.data?.data?.duplicate;
      toast.success(dup ? "Lead sudah ada (dedup) — tidak diduplikasi." : "Lead masuk & task 'Hubungi ≤5 menit' dibuat.");
      onOpenChange(false);
      setName(""); setPhone("");
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengirim payload simulasi.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-primary" /> Simulasi Lead Masuk
          </DialogTitle>
          <DialogDescription>
            Mode SIMULASI — mengirim payload contoh ke webhook (tanpa kredensial Meta/WA).
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Kanal</Label>
            <Select value={channel} onValueChange={setChannel}>
              <SelectTrigger data-testid="simulate-channel-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="meta">Meta Lead Ads</SelectItem>
                <SelectItem value="wa">WhatsApp</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sname">Nama</Label>
            <Input id="sname" value={name} onChange={(e) => setName(e.target.value)} placeholder="Nama calon pembeli" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sphone">No. Telepon (WA)</Label>
            <PhoneInput id="sphone" value={phone} onChange={setPhone} testId="simulate-lead-phone-input" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="smsg">Pesan (opsional)</Label>
            <Textarea id="smsg" rows={2} value={message} onChange={(e) => setMessage(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={LEADS.simulateSubmit} onClick={submit} disabled={busy}>
            {busy ? "Mengirim..." : "Kirim Simulasi"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
