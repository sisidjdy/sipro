import React from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import { formatIDR, formatDateTimeWIB } from "@/utils/formatters";
import { PETTY } from "@/constants/testIds";

function Row({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b py-2 last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-right text-sm font-medium">{value}</span>
    </div>
  );
}

/** Detail kas bon + jejak persetujuan/pencairan + rincian pertanggungjawaban. */
export default function AdvanceDetailSheet({ advance, onClose }) {
  if (!advance) return null;
  const a = advance;
  return (
    <Sheet open onOpenChange={(v) => { if (!v) onClose(); }}>
      <SheetContent data-testid={PETTY.detailSheet} className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            Kas Bon {a.no} <StatusPill status={a.status} group="cashbon_status" />
          </SheetTitle>
          <SheetDescription>{a.purpose}</SheetDescription>
        </SheetHeader>

        <div className="mt-4 space-y-4">
          <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
            <Row label="Pemohon" value={a.requester_name || a.requested_by} />
            <Row label="Kategori" value={<RefLabel group="cashbon_category" value={a.category} />} />
            <Row label="Proyek" value={a.project_name || "—"} />
            <Row label="Nominal diajukan" value={formatIDR(a.amount_requested)} />
            <Row label="Tanggal dibutuhkan" value={a.needed_date ? formatDateTimeWIB(a.needed_date) : "—"} />
            <Row label="Catatan" value={a.note || "—"} />
          </div>

          <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
            <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Jejak proses</p>
            <Row label="Diajukan" value={formatDateTimeWIB(a.created_at)} />
            <Row label="Disetujui"
              value={a.approved_at ? `${formatDateTimeWIB(a.approved_at)} · ${a.approved_by}` : "—"} />
            <Row label="Ditolak"
              value={a.rejected_at ? `${formatDateTimeWIB(a.rejected_at)} · ${a.reject_reason || "-"}` : "—"} />
            <Row label="Dicairkan"
              value={a.disbursed_at
                ? `${formatIDR(a.disbursed_amount)} · ${formatDateTimeWIB(a.disbursed_at)}`
                : "—"} />
            <Row label="Sumber kas"
              value={a.source ? <RefLabel group="cash_source" value={a.source} /> : "—"} />
            <Row label="Dipertanggungjawabkan"
              value={a.settled_at ? formatDateTimeWIB(a.settled_at) : "—"} />
            <Row label="Jurnal terkait" value={`${(a.journal_ids || []).length} jurnal`} />
          </div>

          {(a.expenses || []).length ? (
            <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
              <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                Rincian pengeluaran
              </p>
              <div className="space-y-1.5">
                {a.expenses.map((e) => (
                  <div key={e.id} className="flex items-center justify-between gap-2 text-sm">
                    <div>
                      <p>{e.description}</p>
                      <p className="text-[11px] text-muted-foreground">
                        <RefLabel group="cashbon_category" value={e.category} />
                      </p>
                    </div>
                    <span className="tabular-nums">{formatIDR(e.amount)}</span>
                  </div>
                ))}
              </div>
              <div className="mt-2 border-t pt-2">
                <Row label="Total realisasi" value={formatIDR(a.expense_total)} />
                <Row label="Sisa dikembalikan" value={formatIDR(a.returned_amount)} />
                <Row label="Penggantian" value={formatIDR(a.reimburse_amount)} />
              </div>
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
