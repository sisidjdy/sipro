import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Save } from "lucide-react";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import PrintDocButton from "@/components/patterns/PrintDocButton";
import SendDocWaButton from "@/components/patterns/SendDocWaButton";
import SpkAttachmentsSection from "@/components/subcon/SpkAttachmentsSection";
import ChangeOrdersSection from "@/components/subcon/ChangeOrdersSection";
import SpkScopeSection from "@/components/subcon/SpkScopeSection";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PROCUREMENT, P61 } from "@/constants/testIds";
import { useReference } from "@/context/ReferenceContext";


function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value || "-"}</span>
    </div>
  );
}

export default function SPKDetailSheet({ spk, open, canManage, onOpenChange, onChanged }) {
  const { labelOf, options } = useReference();
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (spk) { setStatus(spk.status); setProgress(spk.progress_pct || 0); } }, [spk]);
  if (!spk) return null;
  const itemBased = spk.scope_mode === "items";

  const saveStatus = async () => {
    setBusy(true);
    try {
      await api.post(`/subcon/spk/${spk.id}/status`, { status });
      toast.success(`Status SPK → ${labelOf("spk_status", status)}.`);
      onOpenChange(false); onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengubah status."); }
    finally { setBusy(false); }
  };
  const saveProgress = async () => {
    setBusy(true);
    try {
      await api.put(`/subcon/spk/${spk.id}`, { progress_pct: Number(progress) || 0 });
      toast.success("Progres SPK diperbarui.");
      onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memperbarui progres."); }
    finally { setBusy(false); }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={PROCUREMENT.spkDetail} className="w-full overflow-y-auto sm:max-w-3xl">
        <SheetHeader>
          <SheetTitle>{spk.spk_number}</SheetTitle>
          <SheetDescription>{spk.title}</SheetDescription>
        </SheetHeader>
        <div className="mt-3 flex flex-wrap gap-2">
          <PrintDocButton url={`/subcon/spk/${spk.id}/pdf`} testId={P61.spkPdf}
            filename={spk.spk_number} label="Cetak SPK (PDF)" />
          <SendDocWaButton kind="spk" id={spk.id} label="Kirim SPK via WhatsApp" />
        </div>
        <div className="mt-5 space-y-5">
          <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
            <div className="mb-2"><StatusPill status={spk.status} group="spk_status" /></div>
            <Row label="Subkontraktor" value={spk.subcontractor_name} />
            <Row label="Proyek" value={spk.project_name} />
            <Row label="Nilai Kontrak" value={formatIDR(spk.contract_value)} />
            <Row label="Retensi" value={`${spk.retention_pct}%`} />
            <Row label="Mulai" value={spk.start_date ? formatDateWIB(spk.start_date) : "-"} />
            <Row label="Selesai" value={spk.end_date ? formatDateWIB(spk.end_date) : "-"} />
            <Row label="Progres" value={`${spk.progress_pct}%${itemBased ? " (dari bukti kerja)" : ""}`} />
            {itemBased ? (
              <Row label="Sudah ditagih" value={`${spk.billed_pct || 0}% · ${formatIDR(spk.scope_billed_value)}`} />
            ) : null}
            {spk.scope ? <p className="mt-2 rounded-lg bg-secondary p-3 text-sm">{spk.scope}</p> : null}
          </div>

          {spk.rab_lines?.length ? (
            <div data-testid="spk-rab-lines" className="rounded-lg border p-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Dasar RAB ({spk.spk_kind}) · RAB {formatIDR(spk.rab_total)} → kontrak {formatIDR(spk.contract_value)}
                {spk.override_count ? ` · ${spk.override_count} baris dioverride` : ""}
                {spk.unit_codes?.length ? ` · unit ${spk.unit_codes.join(", ")}` : ""}
              </p>
              <ul className="divide-y text-xs">
                {spk.rab_lines.map((l, i) => (
                  <li key={i} className="flex items-start justify-between gap-2 py-1">
                    <span className="min-w-0 truncate">{l.unit_code ? <b>{l.unit_code} · </b> : null}{l.description}
                      {l.override ? <span className="ml-1 rounded bg-amber-50 px-1 text-[10px] text-amber-800">override: {l.override_reason}</span> : null}</span>
                    <span className="shrink-0 tabular-nums">{l.override ? <s className="mr-1 text-muted-foreground">{formatIDR(l.rab_amount)}</s> : null}{formatIDR(l.value)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <SpkScopeSection spk={spk} canManage={canManage} onChanged={onChanged} />

          <SpkAttachmentsSection spk={spk} canManage={canManage} onChanged={onChanged} />

          {canManage ? (
            <div className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
              <p className="text-sm font-semibold">Kelola SPK</p>
              {itemBased ? (
                <p className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-[12px] text-emerald-900">
                  Progres SPK ini <b>dihitung otomatis</b> dari pekerjaan yang sudah diverifikasi
                  ({spk.progress_pct}%), jadi tidak bisa diketik manual. Untuk menaikkannya:
                  verifikasi pekerjaan di Progres &amp; Mutu Konstruksi.
                </p>
              ) : (
                <div className="space-y-1.5"><Label>Progres (%)</Label>
                  <div className="flex gap-2">
                    <Input type="number" value={progress} aria-label="Progres SPK"
                      onChange={(e) => setProgress(e.target.value)} />
                    <Button variant="outline" disabled={busy} onClick={saveProgress}>Simpan</Button>
                  </div>
                </div>
              )}
              <div className="space-y-1.5"><Label>Status</Label>
                <Select value={status} onValueChange={setStatus}>
                  <SelectTrigger data-testid={PROCUREMENT.spkStatusSelect}><SelectValue /></SelectTrigger>
                  <SelectContent>{options("spk_status").map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <Button data-testid={PROCUREMENT.spkStatusSubmit} className="w-full" disabled={busy || status === spk.status} onClick={saveStatus}>
                <Save className="mr-1.5 h-4 w-4" /> Simpan Status
              </Button>
            </div>
          ) : null}

          <ChangeOrdersSection spk={spk} onChanged={onChanged} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
