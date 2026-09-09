import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { MFEE } from "@/constants/testIds";

/** Pengajuan marketing fee dengan pratinjau perhitungan bruto/PPh/netto. */
export default function SubmitFeeDialog({ open, onOpenChange, onSaved }) {
  const [agents, setAgents] = useState([]);
  const [deals, setDeals] = useState([]);
  const [agentId, setAgentId] = useState("");
  const [dealId, setDealId] = useState("");
  const [basis, setBasis] = useState("percent");
  const [value, setValue] = useState("2.5");
  const [trigger, setTrigger] = useState("ppjb");
  const [pph, setPph] = useState("2");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [a, d] = await Promise.all([
        api.get("/marketing/agents?status=active"),
        api.get("/deals?limit=100"),
      ]);
      setAgents(a.data.data || []);
      setDeals(d.data.data || []);
    } catch (e) { setErr("Gagal memuat daftar agen atau deal."); }
  }, []);

  useEffect(() => { if (open) { load(); setErr(""); } }, [open, load]);

  const deal = useMemo(() => deals.find((d) => d.id === dealId), [deals, dealId]);
  const price = Number(deal?.price || 0);
  const gross = basis === "percent"
    ? Math.round(price * (Number(value) || 0) / 100)
    : Math.round(Number(value) || 0);
  const pphAmount = Math.round(gross * (Number(pph) || 0) / 100);

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      await api.post("/marketing/fees", {
        agent_id: agentId, deal_id: dealId, basis, value: Number(value), trigger,
        pph_pct: Number(pph) || 0, note: note || null,
      });
      toast.success("Pengajuan marketing fee terkirim ke finance.");
      onOpenChange(false); setNote(""); onSaved?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || "Gagal mengirim pengajuan fee.");
    } finally { setSaving(false); }
  };

  const valid = agentId && dealId && Number(value) > 0 && gross > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={MFEE.submitDialog} className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Ajukan Marketing Fee</DialogTitle>
          <DialogDescription>
            Satu agen hanya boleh punya satu pengajuan aktif per deal &amp; pemicu yang sama.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Agen / mitra</Label>
            <Select value={agentId} onValueChange={setAgentId}>
              <SelectTrigger data-testid={MFEE.submitAgent}>
                <SelectValue placeholder="Pilih agen aktif…" />
              </SelectTrigger>
              <SelectContent>
                {agents.map((a) => (
                  <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!agents.length ? (
              <p className="text-xs text-amber-700">
                Belum ada agen aktif. Tambahkan dulu di tab Master Agen.
              </p>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label>Unit / deal</Label>
            <Select value={dealId} onValueChange={setDealId}>
              <SelectTrigger data-testid={MFEE.submitDeal}>
                <SelectValue placeholder="Pilih deal…" />
              </SelectTrigger>
              <SelectContent>
                {deals.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {(d.unit_code || "Unit")} · {formatIDR(d.price)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Dasar perhitungan</Label>
              <ReferenceSelect group="scheme_basis" value={basis} onChange={setBasis}
                testId={MFEE.submitBasis} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mf-value">
                {basis === "percent" ? "Persentase (%)" : "Nominal tetap (Rp)"}
              </Label>
              <RupiahInput id="mf-value" data-testid={MFEE.submitValue}
                aria-label={basis === "percent" ? "Persentase fee" : "Nominal fee tetap"} value={value}
                onChange={(e) => setValue(e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Pemicu pembayaran</Label>
              <ReferenceSelect group="marketing_fee_trigger" value={trigger} onChange={setTrigger}
                testId={MFEE.submitTrigger} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mf-pph">PPh dipotong (%)</Label>
              <Input id="mf-pph" data-testid={MFEE.submitPph} type="number" min="0" max="30"
                step="0.5" value={pph} onChange={(e) => setPph(e.target.value)} />
            </div>
          </div>

          <div data-testid={MFEE.submitPreview} className="rounded-lg border bg-secondary/40 p-3 text-sm">
            <div className="flex justify-between"><span>Fee bruto</span>
              <span className="font-semibold tabular-nums">{formatIDR(gross)}</span></div>
            <div className="flex justify-between text-muted-foreground"><span>PPh dipotong</span>
              <span className="tabular-nums">{formatIDR(pphAmount)}</span></div>
            <div className="mt-1 flex justify-between border-t pt-1">
              <span>Netto dibayar ke mitra</span>
              <span className="font-semibold tabular-nums">{formatIDR(gross - pphAmount)}</span>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="mf-note">Catatan</Label>
            <Textarea id="mf-note" value={note} rows={2}
              placeholder="Mis. sesuai perjanjian kerja sama nomor …"
              onChange={(e) => setNote(e.target.value)} />
          </div>
          {err ? <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-700">{err}</p> : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={MFEE.submitConfirm} disabled={!valid || saving} onClick={submit}>
            {saving ? "Mengirim…" : "Kirim Pengajuan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
