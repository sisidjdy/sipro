import React, { useEffect, useState } from "react";
import { Layers, Undo2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { P75 } from "@/constants/testIds";

/** Pencairan KPR bertahap: pilih skema bank → tahapan → daftar pencairan (+ pembatalan berjejak, hanya Manajer Keuangan = `finance:manage`). */
export default function KprDisbursementBox({ contract, app, mayUpdate, onChanged, onRecord }) {
  const { can } = useAuth();
  const [schemes, setSchemes] = useState([]);
  const [pick, setPick] = useState("");
  const [cancel, setCancel] = useState(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const mayCancel = can("finance", "manage");
  const hasAkad = !!app.akad?.date;

  useEffect(() => {
    if (!hasAkad && !app.approved_plafon) return;
    api.get("/kpr-disbursement-schemes").then((r) => setSchemes(r.data.data || [])).catch(() => {});
  }, [hasAkad, app.approved_plafon]);

  const assign = async () => {
    setBusy(true);
    try {
      await api.post(`/contracts/${contract.id}/kpr/disbursement-scheme`, { scheme_id: pick });
      toast.success("Skema pencairan dipilih — tahapan tergenerasi dari plafon.");
      onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memilih skema pencairan."); } finally { setBusy(false); }
  };

  const doCancel = async () => {
    setBusy(true);
    try {
      await api.post(`/contracts/${contract.id}/kpr/disbursements/${cancel.id}/cancel`, { reason });
      toast.success("Pencairan dibatalkan — jurnal balik diposting.");
      setCancel(null); setReason("");
      onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membatalkan pencairan."); } finally { setBusy(false); }
  };

  if (!app.approved_plafon) return null;
  const tranches = app.tranches || [];
  const list = app.disbursements || [];
  const legal = contract.legal || {};
  const conditionMet = (c) => (c === "akad" ? !!(app.akad?.date || legal.akad_kredit) : c === "serah_terima" ? !!legal.bast : !!legal.sertifikat);
  const readyOpen = tranches.filter((t) => t.status !== "dicairkan" && conditionMet(t.condition));
  const canRecord = hasAkad && tranches.some((t) => t.status !== "dicairkan");

  return (
    <div data-testid="kpr-disbursement-box" className="space-y-2 rounded-lg border bg-background p-3">
      <p className="flex items-center gap-2 text-sm font-medium"><Layers className="h-4 w-4" /> Pencairan bertahap</p>
      {readyOpen.length ? (
        <p data-testid={P75.trancheReady} className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-900">
          <b>Siap dicairkan</b>: {readyOpen.map((t) => `${t.name} (${formatIDR(t.amount)})`).join(", ")} — syarat terpenuhi, bank belum mencairkan. Tagih bank / catat pencairan.
        </p>
      ) : null}
      {!tranches.length ? (
        mayUpdate ? (
          <div className="flex gap-2">
            <Select value={pick} onValueChange={setPick}>
              <SelectTrigger data-testid={P75.kprDisbSchemeSelect} className="bg-background"><SelectValue placeholder="Pilih skema pencairan bank" /></SelectTrigger>
              <SelectContent>
                {schemes.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}{s.bank ? ` · ${s.bank}` : ""} ({s.tranches.length} tahap)</SelectItem>)}
              </SelectContent>
            </Select>
            <Button data-testid={P75.kprDisbSchemeAssign} size="sm" disabled={!pick || busy} onClick={assign}>Pakai</Button>
          </div>
        ) : <p className="text-xs text-muted-foreground">Skema pencairan belum dipilih.</p>
      ) : (
        <ul className="divide-y text-sm">
          {tranches.map((t) => (
            <li key={t.code} className="flex items-center justify-between py-1.5" data-tranche={t.code} data-status={t.status}>
              <span>{t.name} <span className="text-xs text-muted-foreground">· syarat {t.condition}</span></span>
              <span className="flex items-center gap-2 tabular-nums">{formatIDR(t.amount)}
                <span className={`rounded-full px-2 py-0.5 text-[10px] ${t.status === "dicairkan" ? "bg-emerald-100 text-emerald-800" : "bg-secondary"}`}>{t.status}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      {list.length ? (
        <div className="space-y-1">
          {list.map((d) => (
            <div key={d.id} data-testid={P75.kprDisbRow} data-status={d.status}
              className={`flex flex-wrap items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-xs ${d.status === "dibatalkan" ? "opacity-60 line-through" : ""}`}>
              <span>{d.date} · {d.tranche_name || d.milestone} · kuitansi <b>{d.receipt_no || "-"}</b></span>
              <span className="flex items-center gap-2 tabular-nums">{formatIDR(d.amount)}
                {d.status !== "dibatalkan" && mayCancel ? (
                  <Button data-testid={P75.kprDisbCancel} size="sm" variant="ghost" className="h-6 px-2"
                    onClick={() => setCancel(d)}><Undo2 className="mr-1 h-3 w-3" /> Batalkan</Button>
                ) : null}
                {d.status === "dibatalkan" ? <span className="no-underline">dibatalkan: {d.cancel_reason}</span> : null}
              </span>
            </div>
          ))}
        </div>
      ) : null}
      {mayUpdate && canRecord && app.kpr_stage === "pencairan" ? (
        <Button size="sm" variant="outline" data-testid="kpr-record-next-tranche" onClick={onRecord}>Catat pencairan tahap berikutnya</Button>
      ) : null}

      <Dialog open={!!cancel} onOpenChange={(v) => !v && setCancel(null)}>
        <DialogContent className="max-w-md bg-background">
          <DialogHeader>
            <DialogTitle>Batalkan pencairan {cancel ? formatIDR(cancel.amount) : ""}</DialogTitle>
            <DialogDescription>Kuitansi dibalik (jurnal balik), piutang kembali, tahap dibuka lagi. Tidak ada penghapusan — alasan tersimpan.</DialogDescription>
          </DialogHeader>
          <Textarea data-testid={P75.kprDisbCancelReason} rows={3} className="bg-background" value={reason}
            placeholder="Alasan (min. 10 huruf)" onChange={(e) => setReason(e.target.value)} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancel(null)}>Batal</Button>
            <Button data-testid={P75.kprDisbCancelSubmit} variant="destructive" disabled={busy || reason.trim().length < 10} onClick={doCancel}>Batalkan pencairan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
