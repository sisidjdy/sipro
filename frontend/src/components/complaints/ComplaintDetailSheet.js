import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Send, CheckCircle2, UserCheck, Clock, ShieldCheck } from "lucide-react";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import StatusPill from "@/components/patterns/StatusPill";
import { ErrorState } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { formatDateTimeWIB, dueLabel } from "@/utils/formatters";
import api from "@/services/apiClient";
import { COMPLAINTS, P50 } from "@/constants/testIds";
import { ClaimCreateDialog } from "@/components/handover/WarrantyClaimDialogs";
import { useReference } from "@/context/ReferenceContext";


export default function ComplaintDetailSheet({ complaintId, open, onOpenChange, onChanged }) {
  const { labelOf } = useReference();
  const { user } = useAuth();
  const [c, setC] = useState(null);
  const [error, setError] = useState("");
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  // Fase 50A — jembatan dari keluhan pembeli ke KLAIM GARANSI rumahnya. Sebelumnya keluhan
  // pasca-huni berhenti sebagai balasan CS: tidak pernah menjadi pekerjaan perbaikan yang
  // bisa dilacak, dan tidak ada yang memeriksa apakah bagian itu masih bergaransi.
  const [warranty, setWarranty] = useState(null);
  const [claimOpen, setClaimOpen] = useState(false);

  const load = useCallback(async () => {
    if (!complaintId) return;
    setError("");
    try {
      const res = await api.get(`/complaints/${complaintId}`);
      setC(res.data.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat komplain."); }
  }, [complaintId]);

  useEffect(() => { if (open) { setC(null); setReply(""); load(); } }, [open, load]);

  const refresh = async () => { await load(); onChanged && onChanged(); };

  const respond = async (resolve) => {
    if (!reply.trim()) { toast.error("Tulis balasan dulu."); return; }
    setBusy(true);
    try {
      await api.post(`/complaints/${complaintId}/respond`, { message: reply, resolve });
      toast.success(resolve ? "Balasan terkirim & komplain diselesaikan." : "Balasan terkirim ke pembeli.");
      setReply(""); await refresh();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengirim balasan."); }
    finally { setBusy(false); }
  };

  const setStatus = async (status) => {
    setBusy(true);
    try {
      await api.put(`/complaints/${complaintId}/status`, { status });
      toast.success(`Status → ${labelOf("complaint_status", status)}.`); await refresh();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengubah status."); }
    finally { setBusy(false); }
  };

  const takeOwnership = async () => {
    setBusy(true);
    try {
      await api.post(`/complaints/${complaintId}/assign`, { assigned_to: user?.email });
      toast.success("Komplain ditugaskan ke Anda."); await refresh();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menugaskan."); }
    finally { setBusy(false); }
  };

  useEffect(() => {
    if (!open || !complaintId) { setWarranty(null); return; }
    api.get("/handover/warranty/for-complaint", { params: { complaint_id: complaintId } })
      .then((r) => setWarranty(r.data.data || null))
      .catch(() => setWarranty(null));   // peran tanpa izin garansi: pintu ini tidak muncul
  }, [open, complaintId]);

  const sla = c ? dueLabel(c.sla_due_at) : null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={COMPLAINTS.detail} className="w-full overflow-y-auto sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>{c?.subject || "Detail Komplain"}</SheetTitle>
          <SheetDescription>Kelola & balas komplain pembeli sesuai SLA.</SheetDescription>
        </SheetHeader>
        {error ? <div className="mt-4"><ErrorState message={error} onRetry={load} /></div> : !c ? (
          <p className="mt-6 text-sm text-muted-foreground">Memuat…</p>
        ) : (
          <div className="mt-5 space-y-5">
            <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <StatusPill status={c.status} group="complaint_status" />
                <StatusPill status={c.priority} group="priority" />
              </div>
              <div className="mt-3 grid grid-cols-2 gap-y-1 text-sm">
                <span className="text-muted-foreground">Pelanggan</span><span className="text-right font-medium">{c.customer_name}</span>
                <span className="text-muted-foreground">Unit</span><span className="text-right font-medium">{c.unit_code || "-"}</span>
                <span className="text-muted-foreground">Kategori</span><span className="text-right font-medium">{labelOf("complaint_category", c.category)}</span>
                <span className="text-muted-foreground">Ditugaskan</span><span className="text-right font-medium">{c.assigned_to || "-"}</span>
                <span className="text-muted-foreground">SLA</span>
                <span className={`text-right font-medium ${c.sla_breached ? "text-rose-600" : ""}`}>
                  {c.status === "resolved" ? "Selesai" : (c.sla_breached ? "Lewat SLA" : sla.text)}
                </span>
              </div>
              <p className="mt-3 rounded-lg bg-secondary p-3 text-sm">{c.message}</p>
              {warranty ? (
                <div className="mt-3 rounded-lg border bg-card p-3 text-[13px] shadow-[var(--shadow-card)]">
                  <p className="flex items-center gap-1.5 font-medium">
                    <ShieldCheck className="h-3.5 w-3.5 text-primary" /> Garansi rumah ini
                  </p>
                  <p className="mt-0.5 text-muted-foreground">{warranty.detail}</p>
                  {warranty.eligible ? (
                    <Button size="sm" variant="secondary" className="mt-2"
                      data-testid={P50.complaintToClaimBtn}
                      onClick={() => setClaimOpen(true)}>
                      <ShieldCheck className="mr-1.5 h-3.5 w-3.5" /> Jadikan klaim garansi
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </div>

            <div>
              <h3 className="mb-2 text-sm font-semibold">Riwayat Balasan</h3>
              {(c.responses || []).length === 0 ? (
                <p className="text-xs text-muted-foreground">Belum ada balasan.</p>
              ) : (
                <div className="space-y-2">
                  {c.responses.map((r, i) => (
                    <div key={i} className="rounded-lg border bg-card p-3 text-sm shadow-[var(--shadow-card)]">
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <UserCheck className="h-3.5 w-3.5" /> {r.by}
                        <Clock className="ml-2 h-3.5 w-3.5" /> {formatDateTimeWIB(r.at)}
                      </div>
                      <p className="mt-1">{r.message}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {c.status !== "resolved" ? (
              <div className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
                <Textarea data-testid={COMPLAINTS.respondInput} rows={3} placeholder="Tulis balasan ke pembeli…"
                  value={reply} onChange={(e) => setReply(e.target.value)} />
                <div className="flex flex-wrap gap-2">
                  <Button data-testid={COMPLAINTS.respondSubmit} size="sm" disabled={busy} onClick={() => respond(false)}>
                    <Send className="mr-1.5 h-4 w-4" /> Kirim Balasan
                  </Button>
                  <Button data-testid={COMPLAINTS.resolveBtn} size="sm" variant="secondary" disabled={busy} onClick={() => respond(true)}>
                    <CheckCircle2 className="mr-1.5 h-4 w-4" /> Balas & Selesaikan
                  </Button>
                  {c.status === "open" ? (
                    <Button size="sm" variant="outline" disabled={busy} onClick={() => setStatus("in_progress")}>Tandai Dikerjakan</Button>
                  ) : null}
                  <Button data-testid={COMPLAINTS.assignBtn} size="sm" variant="outline" disabled={busy} onClick={takeOwnership}>
                    <UserCheck className="mr-1.5 h-4 w-4" /> Tangani (saya)
                  </Button>
                </div>
              </div>
            ) : (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => setStatus("in_progress")}>Buka Kembali</Button>
            )}
          </div>
        )}
        <ClaimCreateDialog open={claimOpen} unitId={warranty?.unit_id}
          unitCode={warranty?.unit_code} complaintId={complaintId}
          onOpenChange={setClaimOpen} onDone={refresh} />
      </SheetContent>
    </Sheet>
  );
}
