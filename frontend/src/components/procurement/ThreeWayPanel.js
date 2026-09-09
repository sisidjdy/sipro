import React, { useCallback, useEffect, useState } from "react";
import { ShieldCheck, ShieldAlert } from "lucide-react";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet";
import StatusPill from "@/components/patterns/StatusPill";
import MetricCard from "@/components/patterns/MetricCard";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PROCUREMENT, THREEWAY48 } from "@/constants/testIds";
import ReferenceItems from "@/components/patterns/ReferenceItems";

export default function ThreeWayPanel() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sel, setSel] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/procurement/threeway", { params: { status: status === "all" ? undefined : status } });
      setData(r.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat data 3-way match."); }
    finally { setLoading(false); }
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const s = data?.summary;
  const md = sel?.match_detail || {};
  return (
    <div className="space-y-4">
      {s ? (
        <div className="grid grid-cols-3 gap-3">
          <MetricCard label="Total Tagihan-PO" value={s.total} tone="primary" />
          <MetricCard label="Cocok (Matched)" value={s.matched} tone="emerald" />
          <MetricCard label="Ditandai (Flagged)" value={s.flagged} tone="rose" />
        </div>
      ) : null}
      <div className="flex items-center justify-between">
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua</SelectItem>
            <ReferenceItems group="threeway_status" />
          </SelectContent>
        </Select>
      </div>
      {loading ? <LoadingCards count={4} /> : error ? <ErrorState message={error} onRetry={load} /> :
        !data?.data?.length ? (
          <EmptyState icon={ShieldCheck} title="Belum ada tagihan berbasis PO"
            description="Tagihan yang dibuat dari Purchase Order akan otomatis melewati 3-way match (PO → GRN → Tagihan)." />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>No. PO</TableHead><TableHead>Vendor</TableHead>
                <TableHead className="text-right">Klaim</TableHead><TableHead>Status Bayar</TableHead><TableHead>3-Way</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.data.map((b) => (
                  <TableRow key={b.id} data-testid={PROCUREMENT.threewayRow} className="cursor-pointer" onClick={() => setSel(b)}>
                    <TableCell className="font-medium">{b.po_number || "-"}</TableCell>
                    <TableCell className="text-sm">{b.vendor}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatIDR(b.claimed)}</TableCell>
                    <TableCell><StatusPill status={b.status} group="threeway_status" /></TableCell>
                    <TableCell>
                      {b.match_state === "overridden" || b.override_by ? (
                        <span data-testid={THREEWAY48.overrideBadge}
                          className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-900">
                          Ditahan lalu diterobos
                        </span>
                      ) : b.match_status === "flagged" ? (
                        <span data-testid={THREEWAY48.heldBadge}
                          className="rounded-full border border-rose-300 bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-900">
                          Ditahan
                        </span>
                      ) : <StatusPill status="matched" label="Cocok" />}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      <Sheet open={!!sel} onOpenChange={(v) => !v && setSel(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-md">
          {sel ? (
            <>
              <SheetHeader>
                <SheetTitle className="flex items-center gap-2">
                  {sel.match_status === "flagged" ? <ShieldAlert className="h-5 w-5 text-rose-600" /> : <ShieldCheck className="h-5 w-5 text-emerald-600" />}
                  {sel.po_number}
                </SheetTitle>
                <SheetDescription>{sel.vendor} · 3-Way Match</SheetDescription>
              </SheetHeader>
              <div className="mt-5 space-y-4">
                <div className="rounded-xl border bg-card p-4 text-sm shadow-[var(--shadow-card)]">
                  <div className="flex justify-between py-1"><span className="text-muted-foreground">Nilai PO (Ordered)</span><span className="font-medium tabular-nums">{formatIDR(md.po_total)}</span></div>
                  <div className="flex justify-between py-1"><span className="text-muted-foreground">Diterima (GRN)</span><span className="font-medium tabular-nums">{formatIDR(md.received_value)}</span></div>
                  <div className="flex justify-between py-1"><span className="text-muted-foreground">Ditagih kumulatif</span><span className="font-medium tabular-nums">{formatIDR(md.billed_after)}</span></div>
                </div>
                <div className={`rounded-xl border p-4 text-sm ${sel.match_status === "flagged" ? "border-rose-200 bg-rose-50 text-rose-800" : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}>
                  <p className="font-semibold">{sel.match_status === "flagged" ? "Ditahan 3-way match" : "Cocok — tidak ada anomali"}</p>
                  {(md.reasons || []).length ? md.reasons.map((r, i) => <p key={i} className="mt-1 text-xs">• {r}</p>) :
                    <p className="mt-1 text-xs">Tagihan tidak melebihi nilai barang diterima maupun nilai PO.</p>}
                </div>
                {sel.override_by ? (
                  <div data-testid={THREEWAY48.reason}
                    className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                    <p className="font-semibold">Diterobos oleh {sel.override_by}</p>
                    <p className="mt-1 text-xs">{sel.override_reason}</p>
                    <p className="mt-1 text-[11px]">
                      Tagihan ini melebihi barang yang diterima dan hanya lolos karena keputusan
                      manajer keuangan — tugas tinjauan otomatis dibuat untuk keuangan.
                    </p>
                  </div>
                ) : null}
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
