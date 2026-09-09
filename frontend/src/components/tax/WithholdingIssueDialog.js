import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P49 } from "@/constants/testIds";

const today = () => new Date().toISOString().slice(0, 10);

/**
 * Terbitkan bukti potong MANUAL (Fase 49F) — untuk potongan yang terjadi di luar sistem
 * (mis. dipotong lewat transfer bank langsung). Potongan yang lahir dari pembayaran tagihan
 * atau fee mitra TIDAK perlu lewat sini: bukti potongnya terbit otomatis, dan bila belum,
 * potongannya muncul sebagai “kandidat” yang bisa diterbitkan sekali klik.
 *
 * Tarif diambil dari Pusat Konfigurasi (bukan dihitung ulang layar) supaya angka pajak
 * perusahaan hanya punya SATU sumber.
 */
export default function WithholdingIssueDialog({ open, onOpenChange, config, onDone }) {
  const [kind, setKind] = useState("pph23");
  const [partyKind, setPartyKind] = useState("company");
  const [party, setParty] = useState("");
  const [npwp, setNpwp] = useState("");
  const [base, setBase] = useState("");
  const [rate, setRate] = useState("");
  const [objectCode, setObjectCode] = useState("");
  const [date, setDate] = useState(today());
  const [refLabel, setRefLabel] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setKind("pph23"); setPartyKind("company"); setParty(""); setNpwp("");
    setBase(""); setObjectCode(""); setDate(today()); setRefLabel(""); setNote("");
    setRate(String(config?.rates?.pph23 ?? ""));
  }, [open, config]);

  const pickKind = (value) => {
    setKind(value);
    const auto = config?.rates?.[value];
    if (auto) setRate(String(auto));
  };

  const amount = Math.round((Number(base) || 0) * (Number(rate) || 0) / 100);

  const submit = async () => {
    if (party.trim().length < 3) { toast.error("Nama pihak yang dipotong wajib diisi."); return; }
    if (!Number(base)) { toast.error("Dasar pengenaan pajak harus lebih dari 0."); return; }
    if (!Number(rate)) { toast.error("Tarif potongan harus lebih dari 0."); return; }
    setBusy(true);
    try {
      const res = await api.post("/tax/compliance/withholding/issue", {
        kind,
        basis: "manual",
        party_name: party.trim(),
        party_npwp: npwp.trim() || null,
        party_kind: partyKind,
        base: Number(base),
        rate: Number(rate),
        object_code: objectCode.trim() || null,
        date,
        ref_label: refLabel.trim() || null,
        note: note.trim() || null,
      });
      const doc = res.data.data || {};
      toast.success(doc.idempotent
        ? `Bukti potong ${doc.number} sudah ada sebelumnya — tidak diterbitkan dua kali.`
        : `Bukti potong ${doc.number} terbit senilai ${formatIDR(doc.amount)}.`);
      onOpenChange(false);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menerbitkan bukti potong.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={P49.bupotIssueDialog} className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Terbitkan Bukti Potong (manual)</DialogTitle>
          <DialogDescription>
            Untuk potongan PPh yang buktinya datang dari luar sistem. Nomor bukti dibuat otomatis
            dari seri {config?.series || "01"}; nomor itu TIDAK berubah walau nanti dibetulkan.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Jenis pemotongan PPh</Label>
              <ReferenceSelect group="withholding_kind" value={kind} onChange={pickKind}
                testId={P49.bupotIssueKind} />
            </div>
            <div className="space-y-1.5">
              <Label>Bentuk pihak yang dipotong</Label>
              <ReferenceSelect group="withholding_party_kind" value={partyKind}
                onChange={setPartyKind} testId={P49.bupotIssuePartyKind} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="p49-bupot-party">Nama pihak yang dipotong</Label>
            <Input id="p49-bupot-party" value={party} data-testid={P49.bupotIssueParty}
              onChange={(e) => setParty(e.target.value)} placeholder="mis. PT Karya Bangun Sejahtera" />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="p49-bupot-npwp">NPWP/NIK pihak dipotong</Label>
              <Input id="p49-bupot-npwp" value={npwp} data-testid={P49.bupotIssueNpwp}
                onChange={(e) => setNpwp(e.target.value)} placeholder="16 digit" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p49-bupot-date">Tanggal potongan</Label>
              <Input id="p49-bupot-date" type="date" value={date} data-testid={P49.bupotIssueDate}
                onChange={(e) => setDate(e.target.value)} />
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="p49-bupot-base">Dasar pengenaan (Rp)</Label>
              <RupiahInput id="p49-bupot-base" value={base} data-testid={P49.bupotIssueBase}
                onChange={(e) => setBase(e.target.value)} placeholder="0" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p49-bupot-rate">Tarif (%)</Label>
              <Input id="p49-bupot-rate" type="number" step="0.01" value={rate}
                data-testid={P49.bupotIssueRate} onChange={(e) => setRate(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Kode objek pajak (boleh diisi manual NN-NNN-NN)</Label>
            <ReferenceSelect group="withholding_object_code" value={objectCode}
              onChange={setObjectCode} testId={P49.bupotIssueObject} allowEmpty
              emptyLabel="— belum ada kode —" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="p49-bupot-ref">Keterangan sumber (opsional)</Label>
            <Input id="p49-bupot-ref" value={refLabel}
              onChange={(e) => setRefLabel(e.target.value)}
              placeholder="mis. Transfer bank 12 Agu 2026 atas invoice INV-221" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="p49-bupot-note">Catatan (opsional)</Label>
            <Textarea id="p49-bupot-note" rows={2} value={note}
              onChange={(e) => setNote(e.target.value)} />
          </div>
          <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900">
            Potongan yang akan dicatat: <span className="font-semibold tabular-nums">{formatIDR(amount)}</span>
            {" "}({formatIDR(Number(base) || 0)} × {Number(rate) || 0}%). Pihak yang dipotong menerima
            bukti ini untuk mengkreditkan pajaknya.
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" disabled={busy} data-testid={P49.bupotIssueCancel}
            onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={P49.bupotIssueSubmit} onClick={submit}
            disabled={busy || !amount || party.trim().length < 3}>
            {busy ? "Memproses…" : "Terbitkan bukti potong"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
