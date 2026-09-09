import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ReceiptText, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { TAX } from "@/constants/testIds";
import { useReference } from "@/context/ReferenceContext";
import CashAccountSelect from "@/components/cashBank/CashAccountSelect";


export default function TaxRecordsPanel() {
  const { labelOf, options } = useReference();
  const TYPE_FILTERS = [{ v: "all", l: "Semua jenis" },
    ...options("tax_type").map((o) => ({ v: o.value, l: o.label }))];
  const STATUSES = options("tax_status").map((o) => o.value);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [edit, setEdit] = useState(null); // record being edited
  const [form, setForm] = useState({ status: "pending", ntpn: "", report_date: "", paid_date: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = { limit: 200 };
      if (typeFilter !== "all") params.type = typeFilter;
      const res = await api.get("/tax/records", { params });
      setRows(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat catatan pajak.");
    } finally { setLoading(false); }
  }, [typeFilter]);

  useEffect(() => { load(); }, [load]);

  const openEdit = (r) => {
    setEdit(r);
    setForm({
      status: r.status || "pending", ntpn: r.ntpn || "",
      report_date: (r.report_date || "").slice(0, 10), paid_date: (r.paid_date || "").slice(0, 10),
    });
  };

  const save = async () => {
    if (!edit) return;
    if (form.status === "paid" && !form.ntpn.trim()) {
      toast.error("NTPN wajib diisi untuk menandai pajak sudah disetor.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.put(`/tax/records/${edit.id}`, {
        status: form.status,
        ntpn: form.ntpn || null,
        report_date: form.report_date || null,
        paid_date: form.paid_date || null,
        cash_account_id: form.cash_account_id || null,
      });
      const je = res?.data?.data?.gl_setor_entry_no;
      toast.success(je ? `Pajak disetor — jurnal GL ${je} diposting.` : "Status pajak diperbarui.");
      setEdit(null);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memperbarui status.");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid={TAX.recordsPanel} className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">Kelola pelaporan &amp; penyetoran per catatan pajak.</p>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger data-testid={TAX.recordTypeFilter} className="h-9 w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            {TYPE_FILTERS.map((t) => <SelectItem key={t.v} value={t.v}>{t.l}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {loading ? <LoadingCards count={3} /> : error ? <ErrorState message={error} onRetry={load} /> : (
        !rows.length ? (
          <EmptyState icon={ReceiptText} title="Belum ada catatan pajak"
            description="Catatan PPN/PPh/BPHTB dihitung otomatis saat jadwal AR dibuat untuk sebuah deal." />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Jenis</TableHead>
                  <TableHead>Unit</TableHead>
                  <TableHead>Pembeli</TableHead>
                  <TableHead className="text-right">DPP / Dasar</TableHead>
                  <TableHead className="text-right">Tarif</TableHead>
                  <TableHead className="text-right">Nilai Pajak</TableHead>
                  <TableHead>NTPN</TableHead>
                  <TableHead>Jurnal GL</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="col-actions-head text-right">Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.id} data-testid={TAX.recordRow}>
                    <TableCell className="font-medium">{labelOf("tax_type", r.type)}</TableCell>
                    <TableCell>{r.unit_code || "-"}</TableCell>
                    <TableCell className="text-muted-foreground">{r.buyer_name || "-"}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatIDR(r.base)}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.rate}%</TableCell>
                    <TableCell className="text-right tabular-nums font-semibold text-primary">{formatIDR(r.amount)}</TableCell>
                    <TableCell className="tabular-nums text-muted-foreground">{r.ntpn || "-"}</TableCell>
                    <TableCell>
                      {r.gl_setor_entry_no ? (
                        <span data-testid={TAX.recordGlLink}
                          className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-mono text-[11px] text-emerald-700">
                          {r.gl_setor_entry_no}
                        </span>
                      ) : <span className="text-xs text-muted-foreground">-</span>}
                    </TableCell>
                    <TableCell><StatusPill status={r.status} group="tax_status" /></TableCell>
                    <TableCell className="col-actions">
                      <div className="flex justify-end">
                        <Button size="sm" variant="outline" data-testid={TAX.recordStatusBtn} onClick={() => openEdit(r)}>
                          <Settings2 className="mr-1 h-3.5 w-3.5" /> Status
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )
      )}

      <Dialog open={!!edit} onOpenChange={(v) => !v && setEdit(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Perbarui Status Pajak</DialogTitle>
            <DialogDescription>
              {edit ? `${labelOf("tax_type", edit.type)} · ${formatIDR(edit.amount)}` : ""}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Status</Label>
              <Select value={form.status} onValueChange={(v) => setForm((f) => ({ ...f, status: v }))}>
                <SelectTrigger data-testid={TAX.recordStatusSelect}><SelectValue /></SelectTrigger>
                <SelectContent>
                  {STATUSES.map((s) => <SelectItem key={s} value={s}>{s === "pending" ? "Menunggu" : s === "reported" ? "Dilaporkan" : "Disetor"}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="taxrecordspanel-tgl-lapor">Tgl. Lapor</Label>
                <Input id="taxrecordspanel-tgl-lapor" type="date" value={form.report_date} onChange={(e) => setForm((f) => ({ ...f, report_date: e.target.value }))} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="taxrecordspanel-tgl-setor">Tgl. Setor</Label>
                <Input id="taxrecordspanel-tgl-setor" type="date" value={form.paid_date} onChange={(e) => setForm((f) => ({ ...f, paid_date: e.target.value }))} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>NTPN{form.status === "paid" ? " *" : ""}</Label>
              <Input data-testid={TAX.recordNtpnInput} value={form.ntpn}
                onChange={(e) => setForm((f) => ({ ...f, ntpn: e.target.value }))}
                placeholder="Nomor Transaksi Penerimaan Negara" />
            </div>
            {form.status === "paid" ? (
              <CashAccountSelect value={form.cash_account_id || ""}
                onChange={(v) => setForm((f) => ({ ...f, cash_account_id: v }))} kind="bank"
                label="Setor dari rekening" testId="tax-paid-cash-account" />
            ) : null}
            {form.status === "reported" ? (
              <p className="rounded-lg bg-muted/50 p-2 text-[11px] text-muted-foreground">
                Menyimpan status "Dilaporkan" akan memposting jurnal akrual: Dr Beban Pajak / Cr Utang Pajak.
              </p>
            ) : null}
            {form.status === "paid" ? (
              <p className="rounded-lg bg-emerald-50 p-2 text-[11px] text-emerald-700">
                Menyimpan status "Disetor" akan memposting jurnal setoran: Dr Utang Pajak / Cr Kas-Bank (NTPN wajib).
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEdit(null)}>Batal</Button>
            <Button data-testid={TAX.recordStatusSave} onClick={save} disabled={busy}>
              {busy ? "Menyimpan…" : "Simpan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
