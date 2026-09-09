import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { HandCoins, Plus, Scissors } from "lucide-react";

import { Button } from "@/components/ui/button";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import MetricCard from "@/components/patterns/MetricCard";
import RefLabel from "@/components/patterns/RefLabel";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import StatusPill from "@/components/patterns/StatusPill";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { SUBFIN as T } from "@/constants/testIds";

/**
 * AdvancesPanel (Fase 48C) — uang muka & potongan termin subkon dalam satu layar kerja.
 *
 * Kenapa keduanya bersebelahan: uang muka yang dibayar HARUS diangsur lewat potongan termin.
 * Memisahkannya ke dua layar membuat orang lupa memotong — persis cara uang muka menguap di
 * proyek nyata. Potongan yang menunggu otomatis dipotong saat termin berikutnya disetujui,
 * dan angkanya tampil di sini sebelum itu terjadi.
 */
export default function AdvancesPanel() {
  const { can } = useAuth();
  const canCreate = can("subcon_finance", "create");
  const canManage = can("subcon_finance", "manage");
  const canPay = can("subcon_finance", "approve");
  const [advances, setAdvances] = useState(null);
  const [deductions, setDeductions] = useState(null);
  const [spks, setSpks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [advOpen, setAdvOpen] = useState(false);
  const [dedOpen, setDedOpen] = useState(false);
  const [decision, setDecision] = useState(null);   // {advance, approve}
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [a, d, s] = await Promise.all([
        api.get("/subcon/advances"),
        api.get("/subcon/deductions"),
        api.get("/subcon/spk"),
      ]);
      setAdvances(a.data); setDeductions(d.data); setSpks(s.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat uang muka & potongan.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const pay = async (adv) => {
    setBusy(adv.id);
    try {
      const r = await api.post(`/subcon/advances/${adv.id}/pay`, { note: null });
      toast.success(`Uang muka dibayar — jurnal ${r.data.data.journal_no || "tercatat"}.`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membayar uang muka.");
    } finally { setBusy(""); }
  };

  const cancelDeduction = async (row) => {
    const reason = window.prompt("Alasan pembatalan potongan (min. 10 huruf):");
    if (!reason) return;
    try {
      await api.post(`/subcon/deductions/${row.id}/cancel`, { reason });
      toast.success("Potongan dibatalkan.");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membatalkan potongan.");
    }
  };

  const sa = advances?.summary;
  const sd = deductions?.summary;
  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-6">
      <section data-testid={T.advancePanel} className="space-y-3">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Menunggu keputusan" value={sa?.waiting ?? 0} tone="amber" />
          <MetricCard label="Siap dibayar" value={sa?.to_pay ?? 0} tone="indigo" format="idr" />
          <MetricCard label="Sudah dibayar" value={sa?.paid ?? 0} tone="emerald" format="idr" />
          <MetricCard label="Sisa belum diangsur" value={sa?.outstanding ?? 0} tone="rose"
            format="idr" />
        </div>
        <div className="flex items-center justify-between">
          <h3 className="section-title">Uang muka subkontraktor</h3>
          {canCreate ? (
            <Button data-testid={T.advanceAddBtn} size="sm" onClick={() => setAdvOpen(true)}>
              <Plus className="mr-1.5 h-4 w-4" /> Ajukan uang muka
            </Button>
          ) : null}
        </div>
        {!advances?.data?.length ? (
          <EmptyState icon={HandCoins} title="Belum ada uang muka"
            description={"Uang muka mobilisasi dicatat sebagai HAK TAGIH (aset), bukan biaya, "
              + "lalu diangsur dari termin berikutnya — biaya proyek tidak dihitung dua kali."} />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Nomor / SPK</TableHead><TableHead>Subkontraktor</TableHead>
                <TableHead className="text-right">Nilai</TableHead>
                <TableHead className="text-right">Sisa</TableHead>
                <TableHead>Status</TableHead><TableHead className="col-actions-head text-right">Aksi</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {advances.data.map((a) => (
                  <TableRow key={a.id} data-testid={T.advanceRow} data-state={a.state}>
                    <TableCell>
                      <p className="font-mono text-xs">{a.advance_number}</p>
                      <p className="text-[11px] text-muted-foreground">{a.spk_number}</p>
                    </TableCell>
                    <TableCell className="text-sm">
                      <p>{a.subcontractor_name}</p>
                      <p className="max-w-xs truncate text-[11px] text-muted-foreground">
                        {a.reason}</p>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatIDR(a.amount)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatIDR(a.outstanding)}</TableCell>
                    <TableCell>
                      <StatusPill status={a.state} group="advance_state" /></TableCell>
                    <TableCell className="col-actions text-right">
                      <div className="flex justify-end gap-1.5">
                        {a.state === "draft" && canManage ? (
                          <>
                            <Button data-testid={T.advanceApproveBtn} size="sm" variant="outline"
                              onClick={() => setDecision({ advance: a, approve: true })}>
                              Setujui</Button>
                            <Button data-testid={T.advanceRejectBtn} size="sm" variant="ghost"
                              onClick={() => setDecision({ advance: a, approve: false })}>
                              Tolak</Button>
                          </>
                        ) : null}
                        {a.state === "approved" && canPay ? (
                          <Button data-testid={T.advancePayBtn} size="sm" disabled={busy === a.id}
                            onClick={() => pay(a)}>
                            {busy === a.id ? "Memproses…" : "Bayar"}</Button>
                        ) : null}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      <section data-testid={T.deductionPanel} className="space-y-3 border-t pt-6">
        <div className="grid grid-cols-3 gap-3">
          <MetricCard label="Menunggu dipotong" value={sd?.pending_value ?? 0} tone="amber"
            format="idr" />
          <MetricCard label="Sudah dipotong" value={sd?.applied_value ?? 0} tone="emerald"
            format="idr" />
          <MetricCard label="Denda tercatat" value={sd?.penalty_value ?? 0} tone="rose"
            format="idr" />
        </div>
        <div className="flex items-center justify-between">
          <h3 className="section-title">Potongan termin</h3>
          {canCreate ? (
            <Button data-testid={T.deductionAddBtn} size="sm" variant="outline"
              onClick={() => setDedOpen(true)}>
              <Plus className="mr-1.5 h-4 w-4" /> Catat potongan
            </Button>
          ) : null}
        </div>
        {!deductions?.data?.length ? (
          <EmptyState icon={Scissors} title="Belum ada potongan tercatat"
            description={"Angsuran uang muka, denda keterlambatan, dan bon material dicatat di "
              + "sini; potongan yang menunggu otomatis mengurangi termin berikutnya."} />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Jenis</TableHead><TableHead>SPK / Subkontraktor</TableHead>
                <TableHead className="text-right">Nilai</TableHead>
                <TableHead>Status</TableHead><TableHead>Alasan</TableHead><TableHead />
              </TableRow></TableHeader>
              <TableBody>
                {deductions.data.map((d) => (
                  <TableRow key={d.id} data-testid={T.deductionRow} data-state={d.state}>
                    <TableCell className="text-sm">
                      <RefLabel group="deduction_kind" value={d.kind} /></TableCell>
                    <TableCell className="text-sm">
                      <p>{d.subcontractor_name}</p>
                      <p className="font-mono text-[11px] text-muted-foreground">{d.spk_number}</p>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatIDR(d.amount)}</TableCell>
                    <TableCell>
                      <StatusPill status={d.state} group="deduction_state" /></TableCell>
                    <TableCell className="max-w-xs text-xs text-muted-foreground">{d.reason}</TableCell>
                    <TableCell className="col-actions text-right">
                      {d.state === "pending" && canCreate ? (
                        <Button data-testid={T.deductionCancelBtn} size="sm" variant="ghost"
                          onClick={() => cancelDeduction(d)}>Batalkan</Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      <AdvanceDialog open={advOpen} onOpenChange={setAdvOpen} spks={spks}
        onDone={() => { setAdvOpen(false); load(); }} />
      <DeductionDialog open={dedOpen} onOpenChange={setDedOpen} spks={spks}
        advances={(advances?.data || []).filter((a) => a.state === "paid" && a.outstanding > 0)}
        onDone={() => { setDedOpen(false); load(); }} />
      <DecisionDialog decision={decision} onOpenChange={() => setDecision(null)}
        onDone={() => { setDecision(null); load(); }} />
    </div>
  );
}

function AdvanceDialog({ open, onOpenChange, spks, onDone }) {
  const [spkId, setSpkId] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (open) { setSpkId(""); setAmount(""); setReason(""); } }, [open]);

  const submit = async () => {
    if (!spkId) { toast.error("Pilih SPK."); return; }
    if (!(Number(amount) > 0)) { toast.error("Nilai uang muka harus lebih dari 0."); return; }
    if (reason.trim().length < 10) {
      toast.error("Tulis keperluan uang muka minimal 10 huruf."); return;
    }
    setBusy(true);
    try {
      await api.post("/subcon/advances",
        { spk_id: spkId, amount: Math.round(Number(amount)), reason: reason.trim() });
      toast.success("Uang muka diajukan — menunggu keputusan manajer keuangan.");
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengajukan uang muka.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={T.advanceDialog} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Ajukan uang muka subkon</DialogTitle>
          <DialogDescription>
            Dibatasi 30% nilai kontrak. Setelah dibayar, uang muka WAJIB diangsur lewat potongan
            termin — tercatat sebagai hak tagih, bukan biaya.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>SPK</Label>
            <Select value={spkId} onValueChange={setSpkId}>
              <SelectTrigger data-testid={T.advanceSpkSelect}>
                <SelectValue placeholder="Pilih SPK…" /></SelectTrigger>
              <SelectContent>
                {spks.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.spk_number} · {s.subcontractor_name} ({formatIDR(s.contract_value)})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="adv-amount">Nilai uang muka (Rp)</Label>
            <RupiahInput id="adv-amount" data-testid={T.advanceAmount}
              value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="adv-reason">Keperluan</Label>
            <Textarea id="adv-reason" data-testid={T.advanceReason} rows={3} value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="mis. mobilisasi alat & upah minggu pertama di lokasi" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={T.advanceSubmit} onClick={submit} disabled={busy}>
            {busy ? "Mengajukan…" : "Ajukan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeductionDialog({ open, onOpenChange, spks, advances, onDone }) {
  const [spkId, setSpkId] = useState("");
  const [kind, setKind] = useState("penalty");
  const [advanceId, setAdvanceId] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setSpkId(""); setKind("penalty"); setAdvanceId(""); setAmount(""); setReason(""); }
  }, [open]);

  const submit = async () => {
    if (!spkId) { toast.error("Pilih SPK."); return; }
    if (kind === "advance" && !advanceId) {
      toast.error("Pilih uang muka yang diangsur."); return;
    }
    if (!(Number(amount) > 0)) { toast.error("Nilai potongan harus lebih dari 0."); return; }
    if (reason.trim().length < 10) {
      toast.error("Tulis dasar potongan minimal 10 huruf — angka ini mengurangi uang orang.");
      return;
    }
    setBusy(true);
    try {
      await api.post("/subcon/deductions", {
        spk_id: spkId, kind, amount: Math.round(Number(amount)), reason: reason.trim(),
        advance_id: kind === "advance" ? advanceId : null,
      });
      toast.success("Potongan tercatat — akan memotong termin berikutnya.");
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mencatat potongan.");
    } finally { setBusy(false); }
  };

  const spkAdvances = advances.filter((a) => a.spk_id === spkId);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={T.deductionDialog} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Catat potongan termin</DialogTitle>
          <DialogDescription>
            Potongan mengurangi PEMBAYARAN tanpa mengurangi nilai pekerjaan yang diakui, dan
            otomatis dipakai saat termin berikutnya disetujui.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>SPK</Label>
            <Select value={spkId} onValueChange={setSpkId}>
              <SelectTrigger data-testid="subcon-deduction-spk-select">
                <SelectValue placeholder="Pilih SPK…" /></SelectTrigger>
              <SelectContent>
                {spks.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.spk_number} · {s.subcontractor_name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Jenis potongan</Label>
            <ReferenceSelect group="deduction_kind" value={kind} onChange={setKind}
              testId={T.deductionKindSelect} />
          </div>
          {kind === "advance" ? (
            <div className="space-y-1.5">
              <Label>Uang muka yang diangsur</Label>
              <Select value={advanceId} onValueChange={setAdvanceId}>
                <SelectTrigger data-testid="subcon-deduction-advance-select">
                  <SelectValue placeholder={spkAdvances.length
                    ? "Pilih uang muka…" : "Belum ada uang muka terbayar di SPK ini"} />
                </SelectTrigger>
                <SelectContent>
                  {spkAdvances.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.advance_number} · sisa {formatIDR(a.outstanding)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="ded-amount">Nilai potongan (Rp)</Label>
            <RupiahInput id="ded-amount" data-testid={T.deductionAmount}
              value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ded-reason">Dasar potongan</Label>
            <Textarea id="ded-reason" data-testid={T.deductionReason} rows={3} value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="mis. denda keterlambatan 5 hari kalender pekerjaan struktur" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={T.deductionSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan potongan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DecisionDialog({ decision, onOpenChange, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setReason(""); }, [decision]);

  const submit = async () => {
    if (reason.trim().length < 5) { toast.error("Tulis dasar keputusan minimal 5 huruf."); return; }
    setBusy(true);
    try {
      await api.post(`/subcon/advances/${decision.advance.id}/decision`,
        { approve: decision.approve, reason: reason.trim() });
      toast.success(decision.approve ? "Uang muka disetujui." : "Uang muka ditolak.");
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan keputusan.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={!!decision} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{decision?.approve ? "Setujui" : "Tolak"} uang muka</DialogTitle>
          <DialogDescription>
            {decision?.advance?.advance_number} · {formatIDR(decision?.advance?.amount)} untuk{" "}
            {decision?.advance?.subcontractor_name}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="adv-dec-reason">Dasar keputusan</Label>
          <Textarea id="adv-dec-reason" data-testid={T.advanceDecisionReason} rows={3}
            value={reason} onChange={(e) => setReason(e.target.value)}
            placeholder="mis. sesuai kontrak pasal uang muka 20% setelah SPK ditandatangani" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={T.advanceDecisionSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan keputusan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
