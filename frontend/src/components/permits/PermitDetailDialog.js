import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ExternalLink, RefreshCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { expiryText, HEALTH_TONE } from "@/utils/permitUi";
import { PERMIT_COVERAGE } from "@/constants/testIds";

const Row = ({ label, children }) => (
  <div className="flex items-start justify-between gap-3 border-b border-border/60 py-1.5 text-sm last:border-b-0">
    <span className="shrink-0 text-xs text-muted-foreground">{label}</span>
    <span className="min-w-0 text-right">{children}</span>
  </div>
);

/** Detail satu izin dari tabel "Perizinan yang berlaku" — info lengkap + aksi. */
export default function PermitDetailDialog({ permit, open, onOpenChange, canUpdate,
  onRenew, onChanged }) {
  const navigate = useNavigate();
  const [doc, setDoc] = useState(null);
  const [status, setStatus] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !permit?.id) return;
    setDoc(permit); setStatus(permit.status || ""); setNote("");
    api.get(`/permits/${permit.id}`)
      .then((r) => { setDoc(r.data.data); setStatus(r.data.data?.status || ""); })
      .catch(() => { /* fallback: data dari coverage tetap tampil */ });
  }, [open, permit?.id]);

  if (!permit) return null;
  const p = doc || permit;
  const renewals = (p.renewals || []).slice().reverse();

  const saveStatus = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/permits/${p.id}/status`, {
        status, note: note.trim() || null,
      });
      setDoc(r.data.data); setNote("");
      toast.success("Status izin diperbarui.");
      onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengubah status izin.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={PERMIT_COVERAGE.detailDialog}
        className="max-h-[85vh] overflow-y-auto bg-card sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{p.type} · {p.name || "tanpa nama dokumen"}</DialogTitle>
          <DialogDescription>
            {(p.scope_type_label || "").split(" (")[0]}
            {p.scope_object ? ` ${p.scope_object}` : ""}
            {p.inherited ? " · izin warisan dari induk objek" : " · milik objek ini"}
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-lg border bg-secondary/40 px-3 py-1">
          <Row label="Status & kesehatan">
            <span className="inline-flex items-center gap-1.5">
              <StatusPill status={p.status} group="permit_status" />
              <StatusPill status={p.health} group="permit_health" tone={HEALTH_TONE[p.health]} />
            </span>
          </Row>
          <Row label="Masa berlaku">{expiryText(p)}</Row>
          <Row label="Nomor acuan">{p.reference_no || "—"}</Row>
          <Row label="Instansi penerbit">{p.authority || "—"}</Row>
          <Row label="Proyek">{p.project_name || "—"}</Row>
          <Row label="Tenggat pengurusan">
            {p.deadline ? String(p.deadline).slice(0, 10) : "—"}
          </Row>
          {p.notes ? <Row label="Catatan"><span className="whitespace-pre-wrap text-xs">{p.notes}</span></Row> : null}
        </div>

        {renewals.length ? (
          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">Riwayat perpanjangan</p>
            <ul className="space-y-1">
              {renewals.map((r, i) => (
                <li key={i} className="rounded-md border bg-secondary/40 px-2.5 py-1.5 text-xs">
                  Diperpanjang sampai <b>{String(r.to || "").slice(0, 10)}</b>
                  {r.from ? ` (sebelumnya ${String(r.from).slice(0, 10)})` : ""}
                  {r.by ? ` · oleh ${r.by}` : ""}{r.note ? ` · ${r.note}` : ""}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {canUpdate ? (
          <div className="rounded-lg border p-3">
            <p className="mb-2 text-xs font-semibold">Ubah status pengurusan</p>
            <div className="space-y-2">
              <ReferenceSelect group="permit_status" value={status}
                onChange={setStatus} testId={PERMIT_COVERAGE.detailStatus} />
              <div className="space-y-1">
                <Label htmlFor="permit-status-note">Catatan perubahan (opsional)</Label>
                <Textarea id="permit-status-note" rows={2} value={note}
                  data-testid={PERMIT_COVERAGE.detailStatusNote}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="mis. berkas dinyatakan lengkap oleh DPMPTSP" />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" data-testid={PERMIT_COVERAGE.detailStatusSave}
                  onClick={saveStatus} disabled={busy || !status || status === p.status}>
                  {busy ? "Menyimpan…" : "Simpan status"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => onRenew?.(p)}>
                  <RefreshCcw className="mr-1 h-3.5 w-3.5" /> Perpanjang masa berlaku
                </Button>
              </div>
            </div>
          </div>
        ) : null}

        <DialogFooter className="sm:justify-between">
          <Button variant="ghost" size="sm" data-testid={PERMIT_COVERAGE.detailOpenPage}
            onClick={() => { onOpenChange(false); navigate("/permits"); }}>
            <ExternalLink className="mr-1 h-3.5 w-3.5" /> Buka halaman Perizinan
          </Button>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Tutup</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
