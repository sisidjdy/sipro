import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Star } from "lucide-react";

import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import EvaluationCard from "@/components/vendors/EvaluationCard";
import { useAuth } from "@/context/AuthContext";
import { formatDateWIB, formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { VENDOR as T } from "@/constants/testIds";

const CRITERIA = ["quality", "timeliness", "price", "service", "safety"];

/** VendorDetailSheet (Fase 48A/48D) — identitas, harga, riwayat PO, dan rapor vendor. */
export default function VendorDetailSheet({ vendorId, onOpenChange, onEdit, onChanged }) {
  const { can } = useAuth();
  const canUpdate = can("vendors", "update");
  const [data, setData] = useState(null);
  const [evalData, setEvalData] = useState(null);
  const [assessOpen, setAssessOpen] = useState(false);

  const load = useCallback(async () => {
    if (!vendorId) { setData(null); setEvalData(null); return; }
    try {
      const [d, e] = await Promise.all([
        api.get(`/vendors/${vendorId}`),
        api.get(`/vendors/${vendorId}/evaluation`),
      ]);
      setData(d.data);
      setEvalData(e.data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Gagal memuat vendor.");
    }
  }, [vendorId]);

  useEffect(() => { load(); }, [load]);

  const v = data?.data;
  return (
    <Sheet open={!!vendorId} onOpenChange={onOpenChange}>
      <SheetContent data-testid={T.detail} className="w-full overflow-y-auto sm:max-w-xl">
        {v ? (
          <>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                {v.name}
                <StatusPill status={v.is_active ? "active" : "archived"}
                  label={v.is_active ? "Aktif" : "Nonaktif"} />
              </SheetTitle>
              <SheetDescription>
                {v.code} · <RefLabel group="vendor_category" value={v.category} />
                {" "}· termin {v.payment_terms_days} hari
              </SheetDescription>
            </SheetHeader>

            <div className="mt-5 space-y-5">
              <div className="grid grid-cols-2 gap-2 rounded-xl border bg-card p-3 text-sm shadow-[var(--shadow-card)]">
                <Info label="PIC" value={v.pic_name} />
                <Info label="Telepon" value={v.phone} />
                <Info label="NPWP" value={v.npwp} />
                <Info label="Email" value={v.email} />
                <Info label="Bank" value={v.bank_name && `${v.bank_name} · ${v.bank_account_no || "-"}`} />
                <Info label="Alamat" value={v.address} />
              </div>

              <div className="grid grid-cols-3 gap-2 text-center text-sm">
                <Stat label="PO" value={v.usage?.po_count ?? 0} />
                <Stat label="Nilai PO" value={formatIDR(v.usage?.po_value)} />
                <Stat label="Utang berjalan" value={formatIDR(v.usage?.bill_outstanding)} />
              </div>

              <section className="space-y-2">
                <h4 className="font-heading text-sm font-semibold">Daftar harga vendor ini</h4>
                {!(data.prices || []).length ? (
                  <p className="rounded-lg border border-dashed bg-secondary/40 p-3 text-xs text-muted-foreground">
                    Belum ada harga tercatat — harga PO ke vendor ini belum punya pembanding.
                  </p>
                ) : (
                  <div className="space-y-1.5">
                    {data.prices.map((p) => (
                      <div key={p.id}
                        className="flex items-center justify-between rounded-lg border bg-card p-2 text-sm shadow-[var(--shadow-card)]">
                        <div>
                          <p className="font-medium">{p.item_name}</p>
                          <p className="text-[11px] text-muted-foreground">
                            berlaku {p.valid_from}{p.valid_until ? ` s/d ${p.valid_until}` : ""}
                            {" "}· <RefLabel group="price_source" value={p.source} />
                          </p>
                        </div>
                        <span className="tabular-nums font-medium">
                          {formatIDR(p.unit_price)}/{p.uom}</span>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              <section className="space-y-2">
                <h4 className="font-heading text-sm font-semibold">Riwayat PO</h4>
                {!(data.pos || []).length ? (
                  <p className="rounded-lg border border-dashed bg-secondary/40 p-3 text-xs text-muted-foreground">
                    Vendor ini belum pernah dipakai pada PO.
                  </p>
                ) : data.pos.slice(0, 8).map((p) => (
                  <div key={p.id}
                    className="flex items-center justify-between rounded-lg border bg-card p-2 text-sm shadow-[var(--shadow-card)]">
                    <div>
                      <p className="font-mono text-xs">{p.po_number}</p>
                      <p className="text-[11px] text-muted-foreground">
                        {p.project_name} · {formatDateWIB(p.created_at)}</p>
                    </div>
                    <div className="text-right">
                      <p className="tabular-nums">{formatIDR(p.total)}</p>
                      <StatusPill status={p.status} />
                    </div>
                  </div>
                ))}
              </section>

              <section className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="font-heading text-sm font-semibold">Rapor vendor (berbukti)</h4>
                  {canUpdate ? (
                    <Button data-testid={T.assessBtn} size="sm" variant="outline"
                      onClick={() => setAssessOpen(true)}>
                      <Star className="mr-1.5 h-3.5 w-3.5" /> Nilai vendor
                    </Button>
                  ) : null}
                </div>
                <EvaluationCard evaluation={evalData?.data} />
                {(evalData?.assessments || []).map((a) => (
                  <div key={a.id} data-testid={T.assessRow}
                    className="rounded-lg border bg-card p-3 text-sm shadow-[var(--shadow-card)]">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">Penilaian {a.period} · {a.assessor}</span>
                      <span className="tabular-nums">rata-rata {a.average}</span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{a.note}</p>
                  </div>
                ))}
              </section>

              {canUpdate ? (
                <Button data-testid={T.editBtn} variant="outline" className="w-full"
                  onClick={() => onEdit && onEdit(v)}>Koreksi data vendor</Button>
              ) : null}
            </div>

            <AssessDialog open={assessOpen} onOpenChange={setAssessOpen} vendorId={v.id}
              onDone={() => { setAssessOpen(false); load(); onChanged && onChanged(); }} />
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function Info({ label, value }) {
  return (
    <div>
      <p className="text-[11px] uppercase text-muted-foreground">{label}</p>
      <p className="text-sm">{value || <span className="text-muted-foreground">belum diisi</span>}</p>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
      <p className="text-[11px] uppercase text-muted-foreground">{label}</p>
      <p className="font-medium tabular-nums">{value}</p>
    </div>
  );
}

function AssessDialog({ open, onOpenChange, vendorId, onDone }) {
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [scores, setScores] = useState({});
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setScores({}); setNote(""); }
  }, [open]);

  const submit = async () => {
    const filled = Object.fromEntries(
      Object.entries(scores).filter(([, v]) => Number(v) >= 1 && Number(v) <= 5)
        .map(([k, v]) => [k, Number(v)]));
    if (!Object.keys(filled).length) {
      toast.error("Isi minimal satu kriteria dengan nilai 1–5."); return;
    }
    if (note.trim().length < 10) {
      toast.error("Tulis dasar penilaian minimal 10 huruf — angka tanpa alasan tidak berguna "
        + "untuk pembinaan vendor."); return;
    }
    setBusy(true);
    try {
      await api.post(`/vendors/${vendorId}/assessment`,
        { period, scores: filled, note: note.trim() });
      toast.success("Penilaian tersimpan.");
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan penilaian.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={T.assessDialog} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Penilaian vendor</DialogTitle>
          <DialogDescription>
            Melengkapi rapor berbukti — tidak menggantikannya. Nilai 1 (buruk) sampai 5 (sangat baik).
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="assess-period">Periode</Label>
            <Input id="assess-period" data-testid={T.assessPeriod} value={period}
              onChange={(e) => setPeriod(e.target.value)} placeholder="2026-08" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            {CRITERIA.map((c) => (
              <div key={c} className="space-y-1">
                <Label htmlFor={`assess-${c}`} className="text-xs">
                  <RefLabel group="eval_criteria" value={c} />
                </Label>
                <Input id={`assess-${c}`} type="number" min="1" max="5" step="1"
                  value={scores[c] ?? ""} placeholder="1–5"
                  onChange={(e) => setScores((s) => ({ ...s, [c]: e.target.value }))} />
              </div>
            ))}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="assess-note">Dasar penilaian</Label>
            <Textarea id="assess-note" data-testid={T.assessNote} rows={3} value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Apa yang Anda amati? mis. keterlambatan kirim, mutu batch, respons keluhan…" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={T.assessSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan penilaian"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
