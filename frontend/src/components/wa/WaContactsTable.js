import React, { useMemo } from "react";
import { toast } from "sonner";
import { ExternalLink, MessageCircleReply, RotateCcw, SkipForward, UserPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/patterns/DataTable";
import StatusPill from "@/components/patterns/StatusPill";
import api from "@/services/apiClient";
import { fromNow } from "@/utils/formatters";
import { P94, P97 } from "@/constants/testIds";

const STATUS_LABEL = {
  new: "Menunggu", captured: "Jadi lead", linked: "Ditautkan", skipped: "Dilewati", invalid: "Tidak valid",
};
const STATUS_TONE = { new: "new", captured: "approved", linked: "sent", skipped: "simulation", invalid: "failed" };
const contactOriginText = { webhook: "Pesan WA masuk", import: "Impor", manual: "Manual" };
const STATUS_OPTS = [
  { v: "new", l: "Menunggu" }, { v: "skipped", l: "Dilewati" }, { v: "captured,linked", l: "Selesai" },
  { v: "invalid", l: "Tidak valid" }, { v: "", l: "Semua" },
];
const dupFilterOptions = [
  { v: "", l: "Semua duplikasi" }, { v: "lead", l: "Duplikat lead" },
  { v: "customer", l: "Sudah customer" }, { v: "none", l: "Nomor baru" },
];

export function DupBadge({ c }) {
  if (c.match_lead_id) {
    return (
      <span data-testid={P94.dupBadge} className="inline-flex flex-col rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800">
        <span className="font-semibold">Duplikat lead</span>
        <span className="truncate">{c.match_lead_name} · {c.match_lead_stage || "-"}{c.match_lead_owner ? ` · ${c.match_lead_owner}` : ""}</span>
      </span>
    );
  }
  if (c.match_customer_id) {
    return (
      <span data-testid={P94.dupBadge} className="inline-flex flex-col rounded-md border border-violet-200 bg-violet-50 px-2 py-0.5 text-[11px] text-violet-800">
        <span className="font-semibold">Sudah customer</span>
        <span className="truncate">{c.match_customer_name}</span>
      </span>
    );
  }
  return <span data-testid={P94.dupBadge} className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">Nomor baru</span>;
}

export default function WaContactsTable({ rows, total, loading, error, filters, onFilters, onRefresh,
  canCreate, canReply, onCapture, onOpenLead, onReply }) {
  const act = async (path, ok) => {
    try { await api.post(path); toast.success(ok); onRefresh(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal memproses kontak."); }
  };

  const columns = useMemo(() => [
    {
      key: "name", header: "Kontak", width: "22%",
      render: (c) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{c.name || <span className="italic text-muted-foreground">Tanpa nama</span>}</p>
          <p className="text-xs text-muted-foreground">{c.phone}{c.opt_out ? <span className="ml-1 text-rose-600">· opt-out</span> : null}</p>
        </div>
      ),
      exportValue: (c) => `${c.name || ""} (${c.phone})`,
    },
    { key: "dup", header: "Duplikasi", render: (c) => <DupBadge c={c} />,
      exportValue: (c) => (c.match_lead_id ? "lead" : c.match_customer_id ? "customer" : "baru") },
    {
      key: "source", header: "Sumber",
      render: (c) => (
        <div>
          <p className="text-sm">{contactOriginText[c.source] || c.source}</p>
          {c.import_batch?.label ? <p className="truncate text-[11px] text-muted-foreground">{c.import_batch.label}</p> : null}
        </div>
      ),
    },
    {
      key: "first_message", header: "Pesan pertama", width: "24%",
      render: (c) => (
        <div className="min-w-0">
          <p className="truncate text-sm">{c.first_message || <span className="text-muted-foreground">—</span>}</p>
          {c.message_count ? <p className="text-[11px] text-muted-foreground">{c.message_count} pesan · {c.last_message_at ? fromNow(c.last_message_at) : ""}</p> : null}
        </div>
      ),
    },
    {
      key: "status", header: "Status",
      render: (c) => (
        <div className="space-y-0.5">
          <StatusPill status={STATUS_TONE[c.status] || c.status} label={STATUS_LABEL[c.status] || c.status} />
          {c.skip_reason && c.status === "skipped" ? <p className="text-[11px] text-muted-foreground">{c.skip_reason}</p> : null}
        </div>
      ),
    },
    {
      key: "actions", header: "Aksi", align: "right", sticky: true,
      render: (c) => (
        <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
          {canReply && c.status !== "invalid" ? (
            <Button data-testid={P97.replyBtn} size="sm" variant="outline" onClick={() => onReply(c)} title="Balas cepat via WhatsApp">
              <MessageCircleReply className="h-4 w-4" />
            </Button>
          ) : null}
          {c.lead_id ? (
            <Button size="sm" variant="ghost" onClick={() => onOpenLead(c.lead_id)} title="Buka profil lead">
              <ExternalLink className="h-4 w-4" />
            </Button>
          ) : null}
          {c.status === "new" && canCreate ? (
            <>
              <Button size="sm" variant="secondary" onClick={() => onCapture([c])} title="Jadikan lead">
                <UserPlus className="mr-1 h-4 w-4" /> Jadikan lead
              </Button>
              <Button data-testid={P94.skipBtn} size="sm" variant="ghost" title="Lewati"
                onClick={() => act(`/wa/contacts/${c.id}/skip`, "Kontak dilewati.")}>
                <SkipForward className="h-4 w-4" />
              </Button>
            </>
          ) : null}
          {c.status === "skipped" && canCreate ? (
            <Button data-testid={P94.restoreBtn} size="sm" variant="ghost" title="Kembalikan ke antrean"
              onClick={() => act(`/wa/contacts/${c.id}/restore`, "Kontak kembali ke antrean.")}>
              <RotateCcw className="h-4 w-4" />
            </Button>
          ) : null}
        </div>
      ),
    },
  ], [canCreate, canReply, onCapture, onOpenLead, onReply, onRefresh]); // eslint-disable-line react-hooks/exhaustive-deps

  const filterBar = (
    <div className="flex flex-wrap gap-2">
      <select data-testid={P94.statusFilter} aria-label="Filter status" value={filters.status}
        onChange={(e) => onFilters({ ...filters, status: e.target.value })}
        className="h-9 rounded-md border bg-background px-2 text-sm">
        {STATUS_OPTS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
      </select>
      <select aria-label="Filter duplikasi" value={filters.dup}
        onChange={(e) => onFilters({ ...filters, dup: e.target.value })}
        className="h-9 rounded-md border bg-background px-2 text-sm">
        {dupFilterOptions.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
      </select>
    </div>
  );

  const bulkActions = canCreate ? [{
    key: "capture", label: "Jadikan lead (terpilih)…", testId: P94.captureSelectedBtn,
    onRun: (selected, clear) => {
      const eligible = selected.filter((r) => r.status === "new");
      if (!eligible.length) { toast.error("Pilih kontak berstatus Menunggu."); return; }
      onCapture(eligible); clear();
    },
  }] : [];

  return (
    <DataTable testId={P94.table} testIds={{ row: P94.row, search: P94.search }}
      columns={columns} rows={rows} total={total} loading={loading} error={error}
      query={{ q: filters.q, limit: 200, skip: 0 }}
      onQueryChange={(q) => { if (q.q !== undefined && q.q !== filters.q) onFilters({ ...filters, q: q.q }); }}
      filters={filterBar} bulkActions={bulkActions} label="kontak"
      searchPlaceholder="Cari nama / nomor / pesan…" exportName="kontak-wa" onRefresh={onRefresh}
      emptyTitle={filters.status === "new" ? "Antrean kosong" : "Tidak ada kontak"}
      emptyDescription="Kontak muncul saat ada pesan WhatsApp masuk (webhook Meta / simulasi) atau setelah impor daftar nomor." />
  );
}
