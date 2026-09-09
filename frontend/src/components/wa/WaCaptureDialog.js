import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { UserPlus } from "lucide-react";

import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/services/apiClient";
import { useAuth } from "@/context/AuthContext";
import { P94 } from "@/constants/testIds";

/**
 * WaCaptureDialog — jadikan kontak WA menjadi lead dengan kebijakan duplikat eksplisit.
 * target: { ids?, rows?, all_new?, phones?, count }
 */
export default function WaCaptureDialog({ open, onOpenChange, target, onDone }) {
  const { can } = useAuth();
  const [policyLead, setPolicyLead] = useState("link");
  const [policyCustomer, setPolicyCustomer] = useState("create");
  const [assignee, setAssignee] = useState("");
  const [campaign, setCampaign] = useState("");
  const [owners, setOwners] = useState([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const canAssign = can("leads", "assign");

  useEffect(() => {
    if (!open) { setResult(null); return; }
    setPolicyLead("link"); setPolicyCustomer("create"); setAssignee(""); setCampaign("");
    if (canAssign) api.get("/leads/owners").then((r) => setOwners(r.data.data || [])).catch(() => setOwners([]));
  }, [open, canAssign]);

  const dupLead = useMemo(() => (target?.rows || []).filter((r) => r.match_lead_id).length, [target]);
  const dupCust = useMemo(() => (target?.rows || []).filter((r) => r.match_customer_id && !r.match_lead_id).length, [target]);

  const submit = async () => {
    setBusy(true);
    try {
      const res = await api.post("/wa/contacts/capture", {
        ids: target?.ids || [], all_new: !!target?.all_new, phones: target?.phones || [],
        policy_lead: policyLead, policy_customer: policyCustomer,
        assigned_to: assignee || null, campaign: campaign || null,
      });
      setResult(res.data.data);
      const d = res.data.data;
      toast.success(`${d.created} lead baru, ${d.linked} ditautkan, ${d.skipped} dilewati.`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menjadikan lead."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={P94.captureDialog} className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><UserPlus className="h-4 w-4 text-primary" /> Jadikan lead</DialogTitle>
          <DialogDescription>
            {target?.all_new ? `Semua ${target.count} kontak berstatus Menunggu` : `${target?.count || 0} kontak terpilih`}
            {dupLead ? ` · ${dupLead} duplikat lead` : ""}{dupCust ? ` · ${dupCust} sudah customer` : ""}.
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div data-testid={P94.captureResult} className="space-y-2 rounded-lg border bg-secondary/40 p-3 text-sm">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[["created", "Lead baru"], ["linked", "Ditautkan"], ["skipped", "Dilewati"], ["invalid", "Tidak valid"]].map(([k, l]) => (
                <div key={k}><p className="text-[11px] text-muted-foreground">{l}</p><p className="text-xl font-semibold tabular-nums">{result[k]}</p></div>
              ))}
            </div>
            {result.errors?.length ? <p className="text-xs text-rose-600">{result.errors.length} gagal: {result.errors[0].error}</p> : null}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Bila nomor SUDAH menjadi lead</Label>
              <Select value={policyLead} onValueChange={setPolicyLead}>
                <SelectTrigger data-testid={P94.capturePolicyLead}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="link">Tautkan ke lead lama (percakapan & sentuhan baru dicatat)</SelectItem>
                  <SelectItem value="skip">Lewati (tandai duplikat, tidak diubah)</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground">
                Nomor lead unik per organisasi — lead kembar untuk nomor yang sama tidak bisa dibuat.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label>Bila nomor SUDAH menjadi customer (pembeli lama)</Label>
              <Select value={policyCustomer} onValueChange={setPolicyCustomer}>
                <SelectTrigger data-testid={P94.capturePolicyCustomer}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="create">Buat lead baru (peluang beli ulang, ditandai customer lama)</SelectItem>
                  <SelectItem value="skip">Lewati</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {canAssign ? (
              <div className="space-y-1.5">
                <Label>PIC (opsional — kosong = round-robin otomatis)</Label>
                <Select value={assignee || "__auto__"} onValueChange={(v) => setAssignee(v === "__auto__" ? "" : v)}>
                  <SelectTrigger data-testid={P94.captureAssignee}><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__auto__">Otomatis (round-robin)</SelectItem>
                    {owners.map((o) => <SelectItem key={o.value || o.email} value={o.value || o.email}>{o.label || o.name || o.email}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
            <div className="space-y-1.5">
              <Label htmlFor="wa-capture-campaign">Kampanye (opsional)</Label>
              <Input id="wa-capture-campaign" value={campaign} onChange={(e) => setCampaign(e.target.value)} placeholder="mis. wa-organik" />
            </div>
          </div>
        )}

        <DialogFooter>
          {result ? (
            <Button onClick={() => onDone?.(result)}>Selesai</Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
              <Button data-testid={P94.captureSubmit} onClick={submit} disabled={busy}>
                {busy ? "Memproses…" : "Jadikan lead"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
