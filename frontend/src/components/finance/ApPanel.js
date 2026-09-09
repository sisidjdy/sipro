import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Receipt, Plus, CheckCircle2, Banknote } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import AgingBuckets from "@/components/finance/AgingBuckets";
import PaymentsHistoryPanel from "@/components/finance/PaymentsHistoryPanel";
import { Switch } from "@/components/ui/switch";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { FINANCE, P49 } from "@/constants/testIds";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import CashAccountSelect from "@/components/cashBank/CashAccountSelect";

export default function ApPanel() {
  const [bills, setBills] = useState([]);
  const [aging, setAging] = useState(null);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [payBill, setPayBill] = useState(null);
  const [payKey, setPayKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [b, ag] = await Promise.all([
        api.get("/finance/ap/bills"),
        api.get("/finance/ap/aging"),
      ]);
      setBills(b.data.data || []);
      setAging(ag.data.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat data utang (AP).");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get("/projects").then((r) => setProjects(r.data.data || [])).catch(() => setProjects([]));
  }, []);

  const approve = async (bill) => {
    setBusyId(bill.id);
    try {
      await api.post(`/finance/ap/bills/${bill.id}/approve`, {});
      toast.success(`Tagihan ${bill.vendor} disetujui.`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyetujui tagihan."); }
    finally { setBusyId(null); }
  };

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={FINANCE.apPanel} className="space-y-5">
      <AgingBuckets buckets={aging?.buckets}
        title={`Aging Utang \u00b7 Total ${formatIDR(aging?.total || 0)} \u00b7 Retensi ditahan ${formatIDR(aging?.retention_held || 0)}`} />

      <div className="flex justify-end">
        <Button data-testid={FINANCE.billAddBtn} onClick={() => setAddOpen(true)}>
          <Plus className="mr-1.5 h-4 w-4" /> Tagihan Baru
        </Button>
      </div>

      {!bills.length ? (
        <EmptyState icon={Receipt} title="Belum ada tagihan AP"
          description="Catat tagihan subkontraktor/vendor beserta retensi, lalu proses approval & pembayaran."
          actionLabel="Tagihan Baru" onAction={() => setAddOpen(true)} />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Vendor</TableHead>
                <TableHead className="text-right">Klaim</TableHead>
                <TableHead className="text-right">Retensi</TableHead>
                <TableHead className="text-right">Net</TableHead>
                <TableHead className="text-right">Sisa</TableHead>
                <TableHead>Jatuh Tempo</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="col-actions-head text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {bills.map((b) => (
                <TableRow key={b.id} data-testid={FINANCE.billRow}>
                  <TableCell className="font-medium">{b.vendor}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(b.claimed)}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">{formatIDR(b.retention_held)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(b.net)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(b.outstanding)}</TableCell>
                  <TableCell className="text-muted-foreground">{formatDateWIB(b.due_date)}</TableCell>
                  <TableCell><StatusPill status={b.status} group="ap_status" /></TableCell>
                  <TableCell className="col-actions">
                    <div className="flex justify-end gap-1.5">
                      {b.status === "pending_approval" ? (
                        <Button size="sm" variant="outline" data-testid={FINANCE.billApproveBtn}
                          onClick={() => approve(b)} disabled={busyId === b.id}>
                          <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Setujui
                        </Button>
                      ) : null}
                      {["approved", "partial"].includes(b.status) ? (
                        <Button size="sm" data-testid={FINANCE.billPayBtn}
                          onClick={() => setPayBill(b)} disabled={busyId === b.id}>
                          <Banknote className="mr-1 h-3.5 w-3.5" /> Bayar
                        </Button>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <div className="mt-6 border-t pt-5">
        <PaymentsHistoryPanel refreshKey={payKey} />
      </div>

      <AddBillDialog open={addOpen} onOpenChange={setAddOpen} projects={projects} onDone={load} />
      <PayBillDialog bill={payBill} open={!!payBill} onOpenChange={(v) => !v && setPayBill(null)}
        onDone={() => { load(); setPayKey((k) => k + 1); }} />
    </div>
  );
}

function AddBillDialog({ open, onOpenChange, projects, onDone }) {
  const [vendor, setVendor] = useState("");
  const [projectId, setProjectId] = useState("none");
  const [claimed, setClaimed] = useState("");
  const [retention, setRetention] = useState("5");
  const [dueDate, setDueDate] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setVendor(""); setProjectId("none"); setClaimed(""); setRetention("5"); setDueDate(""); setNote(""); }
  }, [open]);

  const submit = async () => {
    if (!vendor.trim()) { toast.error("Nama vendor wajib diisi."); return; }
    const amt = Number(claimed);
    if (!amt || amt <= 0) { toast.error("Nilai klaim harus lebih dari 0."); return; }
    setBusy(true);
    try {
      await api.post("/finance/ap/bills", {
        vendor: vendor.trim(),
        project_id: projectId === "none" ? null : projectId,
        claimed: amt,
        retention_pct: Number(retention) || 0,
        due_date: dueDate ? new Date(dueDate).toISOString() : null,
        note: note || null,
      });
      toast.success("Tagihan AP dibuat (menunggu approval).");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat tagihan."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Tagihan AP Baru</DialogTitle>
          <DialogDescription>Catat klaim vendor/subkontraktor beserta retensi.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="vendor">Vendor</Label>
            <ReferenceSelect group="vendor" value={vendor} testId="ap-bill-vendor"
              onChange={setVendor} placeholder="Pilih vendor / subkontraktor…" />
          </div>
          <div className="space-y-1.5">
            <Label>Proyek (opsional)</Label>
            <Select value={projectId} onValueChange={setProjectId}>
              <SelectTrigger data-testid="ap-bill-project"><SelectValue placeholder="Pilih proyek" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">— Tanpa proyek —</SelectItem>
                {projects.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="claimed">Nilai Klaim (Rp)</Label>
              <RupiahInput id="claimed" value={claimed} data-testid="ap-bill-claimed"
                onChange={(e) => setClaimed(e.target.value)} placeholder="0" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ret">Retensi (%)</Label>
              <Input id="ret" type="number" value={retention}
                onChange={(e) => setRetention(e.target.value)} placeholder="5" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="due">Jatuh Tempo</Label>
            <Input id="due" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="apnote">Catatan (opsional)</Label>
            <Textarea id="apnote" value={note} onChange={(e) => setNote(e.target.value)} rows={2}
              placeholder="mis. Termin pondasi Blok A" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={FINANCE.billAddSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan\u2026" : "Simpan Tagihan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Bayar tagihan AP — satu dialog, dua kemungkinan yang JUJUR (Fase 49F).
 *
 * Cacat yang ditutup: pembayaran selalu dianggap bruto. Kalau perusahaan sebenarnya memotong
 * PPh jasa konstruksi/PPh 23, uang yang keluar dari bank lebih kecil daripada angka di sistem,
 * potongan yang menjadi kewajiban setor tidak pernah tercatat, dan bukti potong tidak bisa
 * diterbitkan karena tidak ada pasangannya di pembukuan. Dengan opsi “Potong PPh” di sini:
 * vendor menerima NETO, potongan masuk sebagai Utang Pajak, dan bukti potong bernomor terbit
 * otomatis (idempoten per pembayaran). Tarif diambil dari Pusat Konfigurasi — layar tidak
 * mengarang tarif pajak.
 */
function PayBillDialog({ bill, open, onOpenChange, onDone }) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [withhold, setWithhold] = useState(false);
  const [kind, setKind] = useState("pph4_2_konstruksi");
  const [rate, setRate] = useState("");
  const [base, setBase] = useState("");
  const [objectCode, setObjectCode] = useState("");
  const [rates, setRates] = useState(null);
  const [cashAccountId, setCashAccountId] = useState("");
  // Fase 26: pembayaran tidak boleh melebihi sisa tagihan (dulu tanpa guard -> 2-1100 negatif).
  const sisa = Number(bill?.outstanding || 0);
  const over = Number(amount) > sisa;
  const withheld = withhold
    ? Math.round((Number(base) || 0) * (Number(rate) || 0) / 100) : 0;
  const cashOut = (Number(amount) || 0) - withheld;
  const withholdInvalid = withhold && (withheld <= 0 || withheld >= (Number(amount) || 0));

  useEffect(() => {
    if (!open) return;
    setAmount(bill?.outstanding ? String(bill.outstanding) : "");
    setBase(bill?.outstanding ? String(bill.outstanding) : "");
    setNote(""); setWithhold(false); setObjectCode("");
    setKind("pph4_2_konstruksi");
    // Tarif bawaan datang dari setelan pajak; bila peran ini tidak berhak melihat setelan
    // pajak, kolom tarif tetap bisa diisi manual (tidak memblokir pembayaran biasa).
    api.get("/tax/compliance/withholding/config")
      .then((r) => {
        const cfg = r.data.data || {};
        setRates(cfg.rates || null);
        setRate(String(cfg.rates?.pph4_2_konstruksi ?? ""));
      })
      .catch(() => { setRates(null); setRate(""); });
  }, [open, bill]);

  const pickKind = (value) => {
    setKind(value);
    const auto = rates?.[value];
    if (auto) setRate(String(auto));
  };

  const submit = async () => {
    if (!bill?.id) return;
    const amt = Number(amount);
    if (!amt || amt <= 0) { toast.error("Jumlah bayar harus lebih dari 0."); return; }
    if (amt > sisa) {
      toast.error(`Pembayaran melebihi sisa tagihan ${formatIDR(sisa)}.`);
      return;
    }
    setBusy(true);
    try {
      if (withhold) {
        const res = await api.post(`/finance/ap/bills/${bill.id}/pay-withholding`, {
          bill_id: bill.id,
          amount: amt,
          kind,
          rate: Number(rate),
          base: Number(base) || amt,
          object_code: objectCode.trim() || null,
          note: note || null,
          cash_account_id: cashAccountId || null,
        });
        toast.success(res.data?.data?.detail || "Pembayaran dengan potong PPh dicatat.");
      } else {
        await api.post(`/finance/ap/bills/${bill.id}/pay`, { amount: amt, note: note || null,
          cash_account_id: cashAccountId || null });
        toast.success("Pembayaran AP dicatat.");
      }
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membayar tagihan."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Bayar Tagihan AP</DialogTitle>
          <DialogDescription>
            {bill ? `${bill.vendor} \u00b7 Sisa ${formatIDR(bill.outstanding || 0)}` : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="payamt">Jumlah (Rp)</Label>
            <RupiahInput id="payamt" value={amount} data-testid="ap-pay-amount"
              onChange={(e) => setAmount(e.target.value)} placeholder="0" />
            {over ? (
              <p data-testid="ap-pay-over-warning" className="text-[12px] font-medium text-rose-700">
                Melebihi sisa tagihan {formatIDR(sisa)}. Bayar vendor tidak boleh lebih dari nilai bersih tagihan.
              </p>
            ) : null}
          </div>
          <CashAccountSelect value={cashAccountId} onChange={setCashAccountId} kind="bank"
            label="Bayar dari rekening" testId="ap-pay-cash-account" />

          <div className="space-y-3 rounded-xl border bg-secondary/40 p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-medium">Potong PPh dari pembayaran ini</p>
                <p className="text-[11px] text-muted-foreground">
                  Vendor menerima NETO, potongan menjadi Utang Pajak, dan bukti potong bernomor
                  terbit otomatis.
                </p>
              </div>
              <Switch checked={withhold} onCheckedChange={setWithhold}
                data-testid={P49.payWithholdToggle} aria-label="Potong PPh dari pembayaran ini" />
            </div>

            {withhold ? (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label>Jenis pemotongan PPh</Label>
                  <ReferenceSelect group="withholding_kind" value={kind} onChange={pickKind}
                    testId={P49.payWithholdKind} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="pay-wh-base">Dasar pengenaan (Rp)</Label>
                    <RupiahInput id="pay-wh-base" value={base}
                      data-testid={P49.payWithholdBase} onChange={(e) => setBase(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="pay-wh-rate">Tarif (%)</Label>
                    <Input id="pay-wh-rate" type="number" step="0.01" value={rate}
                      data-testid={P49.payWithholdRate} onChange={(e) => setRate(e.target.value)} />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label>Kode objek pajak (opsional, bisa diisi manual)</Label>
                  <ReferenceSelect group="withholding_object_code" value={objectCode}
                    onChange={setObjectCode} testId={P49.payWithholdObject} allowEmpty
                    emptyLabel="— belum ada kode —" />
                </div>
                <div data-testid={P49.payWithholdPreview}
                  className={`rounded-lg border p-3 text-xs ${withholdInvalid
                    ? "border-rose-200 bg-rose-50 text-rose-900"
                    : "border-sky-200 bg-sky-50 text-sky-900"}`}>
                  <p>
                    Potongan PPh: <span className="font-semibold tabular-nums">{formatIDR(withheld)}</span>
                    {" \u00b7 "}Kas keluar ke vendor:{" "}
                    <span className="font-semibold tabular-nums">{formatIDR(cashOut)}</span>
                  </p>
                  {withholdInvalid ? (
                    <p className="mt-1 font-medium">
                      Potongan tidak boleh Rp 0 maupun sama/lebih besar dari nilai pembayaran.
                      Periksa dasar pengenaan dan tarifnya.
                    </p>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="paynote">Catatan (opsional)</Label>
            <Textarea id="paynote" value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" data-testid={P49.payCancel}
            onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={FINANCE.billPaySubmit} onClick={submit}
            disabled={busy || over || withholdInvalid}>
            {busy ? "Memproses\u2026" : withhold ? "Bayar NETO & terbitkan bukti potong" : "Bayar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
