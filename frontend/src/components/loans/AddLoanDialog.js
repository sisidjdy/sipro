import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { LOANS } from "@/constants/testIds";

/** Form fasilitas pembiayaan. Estimasi angsuran pertama dihitung lokal sebagai pratinjau. */
export default function AddLoanDialog({ open, onOpenChange, onSaved }) {
  const [lender, setLender] = useState("BCA");
  const [lenderType, setLenderType] = useState("bank");
  const [loanType, setLoanType] = useState("kredit_investasi");
  const [principal, setPrincipal] = useState("");
  const [rate, setRate] = useState("11.5");
  const [tenor, setTenor] = useState("36");
  const [method, setMethod] = useState("anuitas");
  const [start, setStart] = useState("");
  const [provision, setProvision] = useState("0");
  const [collateral, setCollateral] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { if (open) setErr(""); }, [open]);

  const p = Number(principal) || 0;
  const n = Number(tenor) || 0;
  const i = (Number(rate) || 0) / 1200;
  const firstInstallment = (() => {
    if (!p || !n) return 0;
    if (method === "anuitas") {
      return i > 0 ? Math.round(p * i / (1 - (1 + i) ** -n)) : Math.round(p / n);
    }
    return Math.round(p / n) + Math.round(p * i);
  })();

  const submit = async () => {
    setSaving(true); setErr("");
    try {
      await api.post("/corp-financing/loans", {
        lender, lender_type: lenderType, loan_type: loanType, principal: p,
        interest_rate_pct: Number(rate), tenor_months: n, amortization_method: method,
        start_date: start ? new Date(start).toISOString() : null,
        provision_fee: Number(provision) || 0,
        collateral: collateral || null, note: note || null,
      });
      toast.success("Fasilitas pembiayaan tersimpan sebagai draf. Cairkan untuk menerbitkan jadwal.");
      onOpenChange(false);
      setPrincipal(""); setProvision("0"); setCollateral(""); setNote("");
      onSaved?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || "Gagal menyimpan fasilitas pembiayaan.");
    } finally { setSaving(false); }
  };

  const valid = p > 0 && n >= 1 && Number(provision) < p;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={LOANS.addDialog} className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Tambah Fasilitas Pembiayaan</DialogTitle>
          <DialogDescription>
            Disimpan sebagai draf. Jadwal angsuran (pokok + bunga) diterbitkan saat pencairan,
            dan total pokok jadwal selalu sama dengan pokok pinjaman.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>Pemberi pinjaman</Label>
            <ReferenceSelect group="lender" value={lender} onChange={setLender}
              testId={LOANS.addLender} />
          </div>
          <div className="space-y-1.5">
            <Label>Jenis pemberi pinjaman</Label>
            <ReferenceSelect group="lender_type" value={lenderType} onChange={setLenderType}
              testId={LOANS.addLenderType} />
          </div>
          <div className="space-y-1.5">
            <Label>Jenis fasilitas</Label>
            <ReferenceSelect group="loan_type" value={loanType} onChange={setLoanType}
              testId={LOANS.addLoanType} />
          </div>
          <div className="space-y-1.5">
            <Label>Metode amortisasi</Label>
            <ReferenceSelect group="amortization_method" value={method} onChange={setMethod}
              testId={LOANS.addMethod} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ln-principal">Pokok pinjaman (Rp)</Label>
            <RupiahInput id="ln-principal" data-testid={LOANS.addPrincipal}
              value={principal} onChange={(e) => setPrincipal(e.target.value)} placeholder="0" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ln-rate">Bunga (% per tahun)</Label>
            <Input id="ln-rate" data-testid={LOANS.addRate} type="number" step="0.05" min="0"
              max="60" value={rate} onChange={(e) => setRate(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ln-tenor">Tenor (bulan)</Label>
            <Input id="ln-tenor" data-testid={LOANS.addTenor} type="number" min="1" max="360"
              value={tenor} onChange={(e) => setTenor(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ln-provision">Biaya provisi (Rp)</Label>
            <RupiahInput id="ln-provision" data-testid={LOANS.addProvision}
              value={provision} onChange={(e) => setProvision(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ln-start">Tanggal mulai</Label>
            <Input id="ln-start" data-testid={LOANS.addStart} type="date" value={start}
              onChange={(e) => setStart(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ln-collateral">Agunan</Label>
            <Input id="ln-collateral" data-testid={LOANS.addCollateral} value={collateral}
              placeholder="Mis. Sertifikat HGB induk Cluster Asri"
              onChange={(e) => setCollateral(e.target.value)} />
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor="ln-note">Catatan</Label>
            <Textarea id="ln-note" value={note} rows={2}
              onChange={(e) => setNote(e.target.value)} />
          </div>
        </div>

        <div className="rounded-lg border bg-secondary/40 p-3 text-sm">
          Estimasi angsuran pertama:{" "}
          <span className="font-semibold tabular-nums">{formatIDR(firstInstallment)}</span>
          <span className="text-xs text-muted-foreground">
            {" "}· pencairan bersih {formatIDR(Math.max(0, p - (Number(provision) || 0)))}
          </span>
        </div>
        {err ? <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-700">{err}</p> : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={LOANS.addSubmit} disabled={!valid || saving} onClick={submit}>
            {saving ? "Menyimpan…" : "Simpan Fasilitas"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
