import React, { useCallback, useEffect, useState } from "react";
import { FileSignature, History } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
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

const total = (comps) => (comps || []).reduce((s, c) => s + (c.amount || 0), 0);

/** Amandemen skema all-in: pengajuan (alasan) → keputusan pemegang `finance:approve` lain (selaras endpoint decide) → riwayat. */
export default function AllinAmendmentBox({ contract, onChanged }) {
  const { user, can } = useAuth();
  const [list, setList] = useState([]);
  const [schemes, setSchemes] = useState([]);
  const [schemesErr, setSchemesErr] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ scheme_id: "", reason: "" });
  const [decideNote, setDecideNote] = useState("");
  const [busy, setBusy] = useState(false);
  const mayRequest = can("finance", "update");

  const load = useCallback(() => {
    api.get(`/contracts/${contract.id}/allin-amendments`).then((r) => setList(r.data.data || [])).catch(() => {});
  }, [contract.id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!open) return;
    setSchemesErr("");
    api.get("/allin-schemes")
      .then((r) => { const d = r.data.data || []; setSchemes(d); if (!d.length) setSchemesErr("Belum ada skema all-in aktif di Konfigurasi."); })
      .catch((e) => setSchemesErr(e?.response?.data?.detail || "Daftar skema tidak dapat dimuat (akses ditolak / gangguan jaringan)."));
  }, [open]);

  const pending = list.find((a) => a.status === "pending");
  // pengaju tidak boleh memutuskan amandemennya sendiri (kecuali super_admin) — selaras dengan backend
  const mayDecide = can("finance", "approve")
    && (user?.role === "super_admin" || !pending || pending.requested_by !== user?.email);
  const request = async () => {
    setBusy(true);
    try {
      await api.post(`/contracts/${contract.id}/allin-amendments`, form);
      toast.success("Amandemen diajukan — menunggu keputusan finance manager.");
      setOpen(false); setForm({ scheme_id: "", reason: "" }); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengajukan amandemen."); } finally { setBusy(false); }
  };
  const decide = async (approve) => {
    setBusy(true);
    try {
      await api.post(`/allin-amendments/${pending.id}/decide`, { approve, note: decideNote });
      toast.success(approve ? "Amandemen disetujui — skema kontrak diperbarui." : "Amandemen ditolak.");
      setDecideNote(""); load(); onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memutuskan."); } finally { setBusy(false); }
  };

  return (
    <div data-testid={P75.amendBox} className="space-y-2 rounded-lg border bg-background p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          <FileSignature className="h-3.5 w-3.5" /> Amandemen skema biaya
        </p>
        {mayRequest && !pending ? (
          <Button data-testid={P75.amendRequestBtn} size="sm" variant="outline" onClick={() => setOpen(true)}>Ajukan amandemen</Button>
        ) : null}
      </div>
      <p className="text-[11px] text-muted-foreground">Skema all-in kontrak terbit = snapshot terkunci; perubahan hanya lewat amandemen beralasan yang diputuskan finance manager lain.</p>
      {pending ? (
        <div data-testid={P75.amendPending} className="space-y-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
          <p><b>Menunggu keputusan</b>: {pending.from.scheme_name || "Legacy"} ({formatIDR(total(pending.from.components))}) → <b>{pending.to.scheme_name}</b> ({formatIDR(total(pending.to.components))})</p>
          <p>Alasan: {pending.reason} · diajukan {pending.requested_by}</p>
          {mayDecide ? (
            <div className="space-y-1">
              <Textarea data-testid={P75.amendDecideNote} rows={2} className="bg-background" placeholder="Catatan keputusan (wajib bila menolak)"
                value={decideNote} onChange={(e) => setDecideNote(e.target.value)} />
              <div className="flex gap-2">
                <Button data-testid={P75.amendApprove} size="sm" disabled={busy} onClick={() => decide(true)}>Setujui</Button>
                <Button data-testid={P75.amendReject} size="sm" variant="outline" disabled={busy} onClick={() => decide(false)}>Tolak</Button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
      {list.filter((a) => a.status !== "pending").length ? (
        <ul className="space-y-1 text-xs">
          {list.filter((a) => a.status !== "pending").map((a) => (
            <li key={a.id} data-testid={P75.amendHistoryRow} data-status={a.status} className="flex items-start gap-1.5 text-muted-foreground">
              <History className="mt-0.5 h-3 w-3 shrink-0" />
              <span>{a.status === "approved" ? "Disetujui" : "Ditolak"} {String(a.decided_at).slice(0, 10)} oleh {a.decided_by}: {a.from.scheme_name || "Legacy"} → {a.to.scheme_name} · {a.reason}{a.decision_note ? ` · ${a.decision_note}` : ""}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md bg-background">
          <DialogHeader>
            <DialogTitle>Ajukan amandemen skema all-in</DialogTitle>
            <DialogDescription>Komponen dihitung ulang dari master pada harga kontrak. Invoice biaya yang belum dibayar akan dibatalkan saat disetujui; bila sudah ada kuitansi biaya, amandemen ditolak sistem.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>Skema baru</Label>
            <Select value={form.scheme_id} onValueChange={(v) => setForm((f) => ({ ...f, scheme_id: v }))}>
              <SelectTrigger data-testid={P75.amendSchemeSelect} className="bg-background"><SelectValue placeholder="Pilih skema" /></SelectTrigger>
              <SelectContent>{schemes.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
            </Select>
            {schemesErr ? <p data-testid={P75.amendSchemeError} className="text-xs text-destructive">{schemesErr}</p> : null}
            <Label htmlFor="amend-reason">Alasan (min. 10 huruf)</Label>
            <Textarea id="amend-reason" data-testid={P75.amendReason} rows={3} className="bg-background" value={form.reason} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Batal</Button>
            <Button data-testid={P75.amendSubmit} disabled={busy || !form.scheme_id || form.reason.trim().length < 10} onClick={request}>Ajukan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
