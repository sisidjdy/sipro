import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { RefreshCcw, Save } from "lucide-react";
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
import { formatDateWIB } from "@/utils/formatters";
import { expiryText, HEALTH_TONE } from "@/utils/permitUi";
import api from "@/services/apiClient";
import { PERMITS, PERMIT_COVERAGE } from "@/constants/testIds";
import { useReference } from "@/context/ReferenceContext";


function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value || "-"}</span>
    </div>
  );
}

/**
 * Detail izin. Fase 46 menambahkan tiga hal yang dulu tidak terlihat sama sekali:
 * objek yang dilekati izin (proyek/cluster/blok/unit), KESEHATAN masa berlaku, dan
 * tombol perpanjangan yang menyimpan riwayat (bukan menimpa tanggal diam-diam).
 */
export default function PermitDetailSheet({ permit, open, canManage, onOpenChange, onChanged }) {
  const { labelOf, options } = useReference();
  const [status, setStatus] = useState("");
  const [expiry, setExpiry] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (permit) { setStatus(permit.status); setExpiry(""); } }, [permit]);
  if (!permit) return null;

  const saveStatus = async () => {
    setBusy(true);
    try {
      await api.post(`/permits/${permit.id}/status`, { status });
      toast.success(`Status → ${labelOf("permit_status", status)}.`);
      onOpenChange(false); onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengubah status."); }
    finally { setBusy(false); }
  };

  const renew = async () => {
    if (!expiry) { toast.error("Isi masa berlaku baru."); return; }
    setBusy(true);
    try {
      const r = await api.post(`/permits/${permit.id}/renew`,
        { expiry_at: new Date(expiry).toISOString() });
      toast.success(r.data?.message || "Izin diperpanjang.");
      onOpenChange(false); onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memperpanjang izin."); }
    finally { setBusy(false); }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={PERMITS.detail}
        className="w-full overflow-y-auto bg-background sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{permit.type} — {permit.name}</SheetTitle>
          <SheetDescription>
            Detail perizinan, objek yang dilekatinya, masa berlaku, dan pembaruan status.
          </SheetDescription>
        </SheetHeader>
        <div className="mt-5 space-y-5">
          <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <StatusPill status={permit.status} group="permit_status" />
              <StatusPill status={permit.health} group="permit_health"
                tone={HEALTH_TONE[permit.health]} />
              {permit.overdue ? (
                <span className="text-xs font-medium text-rose-600">Tenggat terlambat</span>
              ) : null}
            </div>
            <Row label="Proyek" value={permit.project_name} />
            <Row label="Cakupan"
              value={`${permit.scope_type_label || labelOf("permit_scope", permit.scope)}`
                + (permit.scope_object ? ` · ${permit.scope_object}` : "")} />
            <Row label="Instansi" value={labelOf("permit_authority", permit.authority)} />
            <Row label="No. Referensi" value={permit.reference_no} />
            <Row label="Tenggat pengurusan"
              value={permit.deadline ? formatDateWIB(permit.deadline) : "-"} />
            <Row label="Masa berlaku" value={expiryText(permit)} />
            <Row label="Diajukan"
              value={permit.submitted_at ? formatDateWIB(permit.submitted_at) : "-"} />
            <Row label="Disetujui"
              value={permit.approved_at ? formatDateWIB(permit.approved_at) : "-"} />
            {permit.notes ? (
              <p className="mt-2 whitespace-pre-line rounded-lg bg-secondary p-3 text-sm">
                {permit.notes}
              </p>
            ) : null}
            {(permit.renewals || []).length ? (
              <div className="mt-3 space-y-1 rounded-lg border bg-secondary p-2 text-[11px]">
                <p className="font-semibold">Riwayat perpanjangan</p>
                {permit.renewals.slice().reverse().map((r, i) => (
                  <p key={i}>
                    {String(r.from || "belum dicatat").slice(0, 10)} →{" "}
                    {String(r.to).slice(0, 10)} · {r.by} · {String(r.at).slice(0, 10)}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
          {canManage ? (
            <div className="space-y-2 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
              <p className="text-sm font-semibold">Perbarui Status</p>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger data-testid={PERMITS.statusSelect}><SelectValue /></SelectTrigger>
                <SelectContent>
                  {options("permit_status").map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button data-testid={PERMITS.statusSubmit} className="w-full"
                disabled={busy || status === permit.status} onClick={saveStatus}>
                <Save className="mr-1.5 h-4 w-4" /> Simpan Status
              </Button>
            </div>
          ) : null}
          {canManage ? (
            <div className="space-y-2 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
              <p className="text-sm font-semibold">Perpanjang masa berlaku</p>
              <p className="text-[11px] text-muted-foreground">
                Masa berlaku sekarang: {expiryText(permit)}. Tanggal lama tetap tersimpan
                sebagai riwayat.
              </p>
              <div className="space-y-1.5">
                <Label htmlFor="permit-renew-date">Berlaku sampai</Label>
                <Input id="permit-renew-date" type="date"
                  data-testid={PERMIT_COVERAGE.renewDate} value={expiry}
                  onChange={(e) => setExpiry(e.target.value)} />
              </div>
              <Button variant="secondary" className="w-full"
                data-testid={PERMIT_COVERAGE.renewSubmit} disabled={busy || !expiry}
                onClick={renew}>
                <RefreshCcw className="mr-1.5 h-4 w-4" /> Perpanjang
              </Button>
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
