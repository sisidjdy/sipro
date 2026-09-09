import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { LEGAL } from "@/constants/testIds";
import { useReference } from "@/context/ReferenceContext";

// Label status dari SSOT /api/reference grup `deletion_request_status` (UI-02).
const TONE = { open: "bg-amber-50 text-amber-800 border-amber-200", in_progress: "bg-sky-50 text-sky-800 border-sky-200",
  done: "bg-emerald-50 text-emerald-800 border-emerald-200", rejected: "bg-rose-50 text-rose-800 border-rose-200" };

function Row({ r, editable, onSaved }) {
  const { options, labelOf } = useReference();
  const [status, setStatus] = useState(r.status);
  const [note, setNote] = useState(r.note || "");
  const [busy, setBusy] = useState(false);
  const dirty = status !== r.status || (note || "") !== (r.note || "");
  const save = async () => {
    setBusy(true);
    try { const res = await api.patch(`/legal/deletion-requests/${r.id}`, { status, note }); onSaved(res.data.data); toast.success(`Tiket ${r.ticket} diperbarui.`); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan."); }
    finally { setBusy(false); }
  };
  return (
    <tr data-testid={LEGAL.reqRow} data-ticket={r.ticket} className="align-top">
      <td className="px-3 py-2 font-mono text-xs">{r.ticket}<br /><span className="text-[10px] text-muted-foreground">{formatDateTimeWIB(r.created_at)}</span></td>
      <td className="px-3 py-2 text-xs"><b>{r.name}</b><br />{r.contact}{r.reason ? <p className="mt-1 text-muted-foreground">{r.reason}</p> : null}</td>
      <td className="px-3 py-2">
        {editable ? (
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger data-testid={LEGAL.reqStatus} className="h-8 w-32 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>{options("deletion_request_status").map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
          </Select>
        ) : <span data-testid={LEGAL.reqStatus} className={`rounded border px-1.5 py-0.5 text-[11px] ${TONE[r.status]}`}>{labelOf("deletion_request_status", r.status)}</span>}
      </td>
      <td className="px-3 py-2">
        <Input data-testid={LEGAL.reqNote} value={note} disabled={!editable} onChange={(e) => setNote(e.target.value)} placeholder="Catatan penanganan…" className="h-8 text-xs" />
        {r.handled_by ? <p className="mt-1 text-[10px] text-muted-foreground">oleh {r.handled_by}</p> : null}
      </td>
      <td className="px-3 py-2">{editable ? <Button data-testid={LEGAL.reqSave} size="sm" variant="outline" disabled={!dirty || busy} onClick={save}>Simpan</Button> : null}</td>
    </tr>
  );
}

export default function DeletionRequestsTable({ editable }) {
  const [rows, setRows] = useState(null);
  const load = useCallback(() => api.get("/legal/deletion-requests").then((r) => setRows(r.data.data))
    .catch((e) => toast.error(e?.response?.data?.detail || "Gagal memuat permintaan.")), []);
  useEffect(() => { load(); }, [load]);
  if (!rows) return <p className="text-sm text-muted-foreground">Memuat…</p>;
  if (!rows.length) return <p data-testid={LEGAL.reqEmpty} className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground">Belum ada permintaan penghapusan data.</p>;
  return (
    <div className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
      <table data-testid={LEGAL.reqTable} className="w-full min-w-[820px] text-sm">
        <thead className="bg-secondary/60 text-left text-xs uppercase text-muted-foreground">
          <tr><th className="px-3 py-2 font-medium">Tiket</th><th className="px-3 py-2 font-medium">Pemohon</th><th className="px-3 py-2 font-medium">Status</th><th className="px-3 py-2 font-medium">Catatan</th><th className="px-3 py-2" /></tr>
        </thead>
        <tbody className="divide-y">
          {rows.map((r) => <Row key={r.id + r.updated_at} r={r} editable={editable} onSaved={(d) => setRows((xs) => xs.map((x) => (x.id === d.id ? d : x)))} />)}
        </tbody>
      </table>
    </div>
  );
}
