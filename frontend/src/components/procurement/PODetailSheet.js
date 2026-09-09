import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, XCircle, PackagePlus, ReceiptText, ShieldAlert } from "lucide-react";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import PrintDocButton from "@/components/patterns/PrintDocButton";
import SendDocWaButton from "@/components/patterns/SendDocWaButton";
import { LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PROCUREMENT, P61 } from "@/constants/testIds";

const APPROVE = ["owner", "super_admin", "finance"];
const CREATE = ["owner", "super_admin", "project_manager", "site_engineer", "finance"];
const CANCEL = ["owner", "super_admin", "project_manager"];

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium tabular-nums">{value}</span>
    </div>
  );
}

export default function PODetailSheet({ poId, open, onOpenChange, onChanged }) {
  const { user } = useAuth();
  const role = user?.nav_role || user?.role;
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState(null); // 'grn' | 'bill'
  const [grnQty, setGrnQty] = useState({});
  const [bill, setBill] = useState({ claimed: "", retention_pct: "5", due_date: "", grn_id: "" });
  const [match, setMatch] = useState(null);

  const load = useCallback(async () => {
    if (!poId) return;
    setLoading(true); setMatch(null); setMode(null);
    try { const r = await api.get(`/procurement/pos/${poId}`); setD(r.data); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal memuat PO."); }
    finally { setLoading(false); }
  }, [poId]);
  useEffect(() => { if (open) load(); }, [open, load]);

  if (!open) return null;
  const po = d?.data;

  const doApprove = async () => {
    setBusy(true);
    try { await api.post(`/procurement/pos/${po.id}/approve`, {}); toast.success("PO disetujui."); await load(); onChanged && onChanged(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyetujui PO."); }
    finally { setBusy(false); }
  };
  const doCancel = async () => {
    setBusy(true);
    try { await api.post(`/procurement/pos/${po.id}/cancel`, {}); toast.success("PO dibatalkan."); await load(); onChanged && onChanged(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal membatalkan PO."); }
    finally { setBusy(false); }
  };
  const submitGrn = async () => {
    const items = Object.entries(grnQty).map(([idx, q]) => ({ po_item_index: Number(idx), qty_received: Number(q) || 0 })).filter((x) => x.qty_received > 0);
    if (!items.length) { toast.error("Isi qty diterima > 0."); return; }
    setBusy(true);
    try { await api.post("/procurement/grns", { po_id: po.id, items }); toast.success("Barang diterima (GRN dibuat)."); setGrnQty({}); await load(); onChanged && onChanged(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat GRN."); }
    finally { setBusy(false); }
  };
  const submitBill = async () => {
    if (!(Number(bill.claimed) > 0)) { toast.error("Isi nilai klaim."); return; }
    setBusy(true);
    try {
      const r = await api.post("/procurement/bills", {
        po_id: po.id, grn_id: bill.grn_id || null, claimed: Math.round(Number(bill.claimed)),
        retention_pct: Number(bill.retention_pct) || 0,
        due_date: bill.due_date ? new Date(bill.due_date).toISOString() : null });
      setMatch(r.data.match);
      if (r.data.match.status === "flagged") toast.warning("Tagihan DITANDAI oleh 3-way match.");
      else toast.success("Tagihan dibuat & cocok (matched).");
      setBill({ claimed: "", retention_pct: "5", due_date: "", grn_id: "" });
      await load(); onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat tagihan."); }
    finally { setBusy(false); }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={PROCUREMENT.poDetail} className="w-full overflow-y-auto sm:max-w-lg">
        {loading || !po ? <LoadingCards count={3} /> : (
          <>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">{po.po_number}
                <StatusPill status={po.status} group="po_status" /></SheetTitle>
              <SheetDescription>{po.vendor} · {po.project_name}</SheetDescription>
            </SheetHeader>
            <div className="mt-5 space-y-5">
              <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
                <Row label="Nilai PO" value={formatIDR(po.total)} />
                <Row label="Diterima (GRN)" value={formatIDR(po.received_value)} />
                <Row label="Sudah Ditagih" value={formatIDR(po.billed_value)} />
                {po.high_value ? <p className="mt-2 rounded-md bg-rose-50 p-2 text-xs text-rose-700">Nilai tinggi — persetujuan Owner.</p> : null}
              </div>

              <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
                <p className="mb-2 text-sm font-semibold">Item</p>
                {po.items.map((it, i) => (
                  <div key={i} className="flex items-center justify-between border-t py-1.5 text-sm first:border-t-0">
                    <div><p className="font-medium">{it.description}</p>
                      <p className="text-xs text-muted-foreground tabular-nums">{it.qty} {it.uom} × {formatIDR(it.unit_price)} · diterima {it.received_qty}</p></div>
                    <span className="tabular-nums font-medium">{formatIDR(it.amount)}</span>
                  </div>
                ))}
              </div>

              {/* Actions */}
              <div className="flex flex-wrap gap-2">
                <PrintDocButton url={`/procurement/pos/${po.id}/pdf`} testId={P61.poPdf}
                  filename={po.po_number} label="Cetak PO (PDF)" />
                <SendDocWaButton kind="po" id={po.id} label="Kirim PO via WhatsApp" />
                {po.status === "draft" && APPROVE.includes(role) ? (
                  <Button data-testid={PROCUREMENT.poApprove} disabled={busy} onClick={doApprove}>
                    <CheckCircle2 className="mr-1.5 h-4 w-4" /> Setujui
                  </Button>
                ) : null}
                {["draft", "approved", "partially_received"].includes(po.status) && CANCEL.includes(role) ? (
                  <Button data-testid={PROCUREMENT.poCancel} variant="outline" disabled={busy} onClick={doCancel}>
                    <XCircle className="mr-1.5 h-4 w-4" /> Batalkan
                  </Button>
                ) : null}
                {["approved", "partially_received"].includes(po.status) && CREATE.includes(role) ? (
                  <Button data-testid={PROCUREMENT.grnBtn} variant="outline" onClick={() => setMode(mode === "grn" ? null : "grn")}>
                    <PackagePlus className="mr-1.5 h-4 w-4" /> Terima Barang
                  </Button>
                ) : null}
                {["approved", "partially_received", "received"].includes(po.status) && CREATE.includes(role) ? (
                  <Button data-testid={PROCUREMENT.billBtn} variant="outline" onClick={() => setMode(mode === "bill" ? null : "bill")}>
                    <ReceiptText className="mr-1.5 h-4 w-4" /> Buat Tagihan
                  </Button>
                ) : null}
              </div>

              {mode === "grn" ? (
                <div className="space-y-2 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
                  <p className="text-sm font-semibold">Penerimaan Barang (GRN)</p>
                  {po.items.map((it, i) => {
                    const remaining = (it.qty || 0) - (it.received_qty || 0);
                    return (
                      <div key={i} className="flex items-center justify-between gap-2 text-sm">
                        <span className="flex-1">{it.description} <span className="text-xs text-muted-foreground">(sisa {remaining} {it.uom})</span></span>
                        <Input className="h-9 w-28" type="number" value={grnQty[i] || ""} disabled={remaining <= 0}
                          aria-label={`Qty diterima untuk ${it.description}`}
                          onChange={(e) => setGrnQty((g) => ({ ...g, [i]: e.target.value }))} placeholder="0" />
                      </div>
                    );
                  })}
                  <Button data-testid={PROCUREMENT.grnSubmit} className="w-full" disabled={busy} onClick={submitGrn}>Simpan Penerimaan</Button>
                </div>
              ) : null}

              {mode === "bill" ? (
                <div className="space-y-2 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
                  <p className="text-sm font-semibold">Buat Tagihan (3-Way Match)</p>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1"><Label className="text-xs">Nilai Klaim (Rp)</Label><RupiahInput value={bill.claimed} onChange={(e) => setBill((b) => ({ ...b, claimed: e.target.value }))} /></div>
                    <div className="space-y-1"><Label className="text-xs">Retensi (%)</Label><Input type="number" value={bill.retention_pct} onChange={(e) => setBill((b) => ({ ...b, retention_pct: e.target.value }))} /></div>
                    <div className="space-y-1"><Label className="text-xs">Jatuh Tempo</Label><Input type="date" value={bill.due_date} onChange={(e) => setBill((b) => ({ ...b, due_date: e.target.value }))} /></div>
                    <div className="space-y-1"><Label className="text-xs">GRN (opsional)</Label>
                      <Select value={bill.grn_id} onValueChange={(v) => setBill((b) => ({ ...b, grn_id: v }))}>
                        <SelectTrigger className="h-9"><SelectValue placeholder="—" /></SelectTrigger>
                        <SelectContent>{(d.grns || []).map((g) => <SelectItem key={g.id} value={g.id}>{g.grn_number}</SelectItem>)}</SelectContent>
                      </Select></div>
                  </div>
                  <Button data-testid={PROCUREMENT.billSubmit} className="w-full" disabled={busy} onClick={submitBill}>Kirim Tagihan</Button>
                </div>
              ) : null}

              {match ? (
                <div data-testid={PROCUREMENT.matchResult} className={`rounded-xl border p-4 text-sm ${match.status === "flagged" ? "border-rose-200 bg-rose-50 text-rose-800" : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}>
                  <div className="flex items-center gap-2 font-semibold">
                    {match.status === "flagged" ? <ShieldAlert className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
                    {match.status === "flagged" ? "3-Way Match: DITANDAI" : "3-Way Match: Cocok"}
                  </div>
                  <p className="mt-1 text-xs">PO {formatIDR(match.po_total)} · Diterima {formatIDR(match.received_value)} · Ditagih {formatIDR(match.billed_after)}</p>
                  {match.reasons?.map((r, i) => <p key={i} className="mt-1 text-xs">• {r}</p>)}
                </div>
              ) : null}

              {d.grns?.length ? (
                <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
                  <p className="mb-2 text-sm font-semibold">Penerimaan ({d.grns.length})</p>
                  {d.grns.map((g) => (
                    <div key={g.id} className="flex justify-between border-t py-1.5 text-sm first:border-t-0">
                      <span>{g.grn_number}</span><span className="tabular-nums">{formatIDR(g.received_value)}</span>
                    </div>
                  ))}
                </div>
              ) : null}
              {d.bills?.length ? (
                <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
                  <p className="mb-2 text-sm font-semibold">Tagihan ({d.bills.length})</p>
                  {d.bills.map((b) => (
                    <div key={b.id} className="flex items-center justify-between border-t py-1.5 text-sm first:border-t-0">
                      <span className="tabular-nums">{formatIDR(b.claimed)}</span>
                      <div className="flex items-center gap-2">
                        <StatusPill status={b.status} group="ap_status" />
                        {b.match_status ? <StatusPill status={b.match_status} label={b.match_status === "flagged" ? "Ditandai" : "Cocok"} /> : null}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
