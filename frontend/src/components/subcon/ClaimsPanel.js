import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, HardHat, ClipboardCheck, CheckCircle2, XCircle, Receipt } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import PrintDocButton from "@/components/patterns/PrintDocButton";
import SendDocWaButton from "@/components/patterns/SendDocWaButton";
import MetricCard from "@/components/patterns/MetricCard";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import SubmitClaimDialog from "@/components/subcon/SubmitClaimDialog";
import ClaimOpnameSheet from "@/components/subcon/ClaimOpnameSheet";
import { useAuth } from "@/context/AuthContext";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { CLAIMS, OPNAME, P62 } from "@/constants/testIds";


export default function ClaimsPanel() {
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  const canSubmit = can("progress_claims", "create");
  const canApprove = can("progress_claims", "approve");

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [opnameFor, setOpnameFor] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/subcon/claims");
      setData(r.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat termin."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, okMsg) => {
    setBusy(true);
    try { await fn(); toast.success(okMsg); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Aksi gagal."); }
    finally { setBusy(false); }
  };

  const s = data?.summary;
  return (
    <div data-testid={CLAIMS.panel} className="space-y-4">
      {s ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Total Termin" value={s.total} tone="primary" />
          <MetricCard label="Menunggu Proses" value={s.open} tone="amber" />
          <MetricCard label="Disetujui (Tertagih)" value={s.approved_value} tone="emerald" format="idr" />
          <MetricCard label="Retensi Ditahan" value={s.retention_held} tone="indigo" format="idr" />
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Termin berbasis item: nilai dihitung dari pekerjaan yang sudah diverifikasi → opname
          (boleh dikurangi, wajib beralasan) → disetujui finance jadi tagihan AP + retensi.
        </p>
        {canSubmit ? (
          <Button size="sm" data-testid={CLAIMS.submitBtn} onClick={() => setAddOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> Ajukan Termin
          </Button>
        ) : null}
      </div>

      {loading ? <LoadingCards count={4} /> : error ? <ErrorState message={error} onRetry={load} /> :
        !data?.data?.length ? (
          <EmptyState icon={HardHat} title="Belum ada termin"
            description="Ajukan termin progres untuk SPK yang aktif."
            actionLabel={canSubmit ? "Ajukan Termin" : undefined} onAction={() => setAddOpen(true)} />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>No. Termin</TableHead><TableHead>SPK / Subkon</TableHead><TableHead>Dasar tagihan</TableHead>
                <TableHead>Progres</TableHead><TableHead className="text-right">Nilai</TableHead>
                <TableHead>Status</TableHead><TableHead className="col-actions-head text-right">Aksi</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.data.map((c) => (
                  <TableRow key={c.id} data-testid={CLAIMS.row} data-basis={c.basis || "lumpsum"}>
                    <TableCell className="font-medium">{c.claim_number}</TableCell>
                    <TableCell className="text-sm">{c.spk_number}<br /><span className="text-muted-foreground">{c.subcontractor_name}</span></TableCell>
                    <TableCell className="text-sm">
                      {c.basis === "items" ? (
                        <>
                          <span data-testid={OPNAME.basis}
                            className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800">
                            Per item berbukti
                          </span>
                          <span data-testid={OPNAME.lines} className="ml-1 text-[11px] text-muted-foreground">
                            {(c.lines || []).filter((l) => l.included !== false).length}/{(c.lines || []).length} pekerjaan
                          </span>
                          {c.excluded_items ? (
                            <p className="text-[11px] text-amber-700">
                              {c.excluded_items} dikeluarkan opname ({formatIDR(c.excluded_value)})
                            </p>
                          ) : null}
                        </>
                      ) : (
                        <span data-testid={OPNAME.basis}
                          className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
                          Lump-sum (persen)
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="tabular-nums text-sm">{c.prev_pct}% → {c.verified_pct ?? c.claimed_pct}%</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatIDR(c.status === "approved" ? c.gross : c.gross_est)}
                      {c.status === "approved" ? <div className="text-[11px] text-muted-foreground">net {formatIDR(c.net)}</div> : null}
                    </TableCell>
                    <TableCell><StatusPill status={c.status} group="claim_status" /></TableCell>
                    <TableCell className="col-actions">
                      <div className="flex justify-end gap-1.5">
                        {c.status === "submitted" && canSubmit ? (
                          <Button size="sm" variant="outline" data-testid={CLAIMS.verifyBtn}
                            onClick={() => setOpnameFor(c)}>
                            <ClipboardCheck className="mr-1 h-3.5 w-3.5" /> Opname
                          </Button>
                        ) : null}
                        {["submitted", "verified"].includes(c.status) && canApprove ? (
                          <>
                            <Button size="sm" data-testid={CLAIMS.approveBtn} disabled={busy}
                              onClick={() => act(() => api.post(`/subcon/claims/${c.id}/approve`), "Termin disetujui & ditagihkan.")}>
                              <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Setujui
                            </Button>
                            <Button size="sm" variant="ghost" data-testid={CLAIMS.rejectBtn} disabled={busy}
                              aria-label="Tolak termin"
                              onClick={() => act(() => api.post(`/subcon/claims/${c.id}/reject`, { note: "Ditolak" }), "Termin ditolak.")}>
                              <XCircle className="h-3.5 w-3.5 text-rose-600" />
                            </Button>
                          </>
                        ) : null}
                        {c.status === "approved" ? <span className="inline-flex items-center gap-1 text-xs text-emerald-700"><Receipt className="h-3.5 w-3.5" /> Tertagih</span> : null}
                        {["verified", "approved"].includes(c.status) ? (
                          <>
                            <PrintDocButton url={`/subcon/claims/${c.id}/pdf`}
                              testId={P62.claimPdfBtn} filename={c.claim_number}
                              label="Berita acara" />
                            <SendDocWaButton kind="claim" id={c.id} label="WhatsApp" />
                          </>
                        ) : null}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

      <SubmitClaimDialog open={addOpen} onOpenChange={setAddOpen} onDone={load} />
      <ClaimOpnameSheet claim={opnameFor} open={!!opnameFor}
        onOpenChange={(v) => !v && setOpnameFor(null)} onDone={load} />
    </div>
  );
}
