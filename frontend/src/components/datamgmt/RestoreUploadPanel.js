import React, { useState } from "react";
import { toast } from "sonner";
import { FileJson, RotateCcw, UploadCloud } from "lucide-react";

import api from "@/services/apiClient";
import { Button } from "@/components/ui/button";
import { formatDateTimeWIB } from "@/utils/formatters";
import { DATAMGMT } from "@/constants/testIds";
import { errDetail } from "./dataMgmtUtils";
import RestoreDialog from "./RestoreDialog";

/** Restore dari berkas JSON yang diunggah: periksa isi dulu, lalu jalankan lewat dialog. */
export default function RestoreUploadPanel({ onChanged }) {
  const [file, setFile] = useState(null);
  const [meta, setMeta] = useState(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const pick = (f) => { setFile(f || null); setMeta(null); };

  const inspect = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      const res = await api.post("/data-mgmt/restore/inspect", fd);
      setMeta(res.data);
    } catch (e) { toast.error(errDetail(e, "Berkas tidak bisa dibaca.")); } finally { setBusy(false); }
  };

  const submit = (fd) => { fd.append("file", file); return api.post("/data-mgmt/restore", fd); };
  const colls = meta ? Object.entries(meta.collections || {}) : [];

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="rounded-xl border bg-card p-5 space-y-3 shadow-[var(--shadow-card)]">
        <div className="flex items-start justify-between">
          <div><p className="eyebrow">Restore</p><h3 className="font-semibold">Dari berkas backup JSON</h3></div>
          <FileJson className="h-7 w-7 text-primary" />
        </div>
        <label
          className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 text-center hover:bg-accent/40 transition-colors"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files?.[0]); }}>
          <UploadCloud className="h-7 w-7 text-muted-foreground" />
          <span className="text-sm">{file ? <b>{file.name}</b> : "Seret berkas .json ke sini atau klik untuk memilih"}</span>
          <input data-testid={DATAMGMT.restoreFile} type="file" accept=".json" className="hidden"
            onChange={(e) => pick(e.target.files?.[0])} />
        </label>
        <div className="flex gap-2">
          <Button variant="secondary" data-testid={DATAMGMT.restoreInspect} disabled={!file || busy} onClick={inspect}>
            {busy ? "Membaca…" : "Periksa isi berkas"}
          </Button>
          <Button variant="destructive" data-testid={DATAMGMT.restoreOpen} disabled={!meta} onClick={() => setOpen(true)}>
            <RotateCcw className="h-4 w-4 mr-2" /> Restore…
          </Button>
        </div>
      </div>

      <div className="rounded-xl border bg-card p-5 shadow-[var(--shadow-card)]">
        {!meta ? (
          <p className="text-sm text-muted-foreground">Ringkasan isi backup akan tampil di sini setelah diperiksa.</p>
        ) : (
          <div data-testid={DATAMGMT.restoreMeta} className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-2">
              <Info l="Organisasi" v={`${meta.org_name || "—"} (${meta.org_id})`} />
              <Info l="Dibuat" v={formatDateTimeWIB(meta.created_at)} />
              <Info l="Oleh" v={meta.created_by || "—"} />
              <Info l="Dokumen" v={`${meta.documents} pada ${colls.length} koleksi`} />
              <Info l="Berkas lampiran" v={meta.include_files ? "termasuk" : "tidak termasuk"} />
              <Info l="Label" v={meta.label || "—"} />
            </div>
            <div className="max-h-56 overflow-auto rounded border">
              <table className="w-full text-xs">
                <tbody>
                  {colls.sort((a, b) => b[1] - a[1]).map(([k, n]) => (
                    <tr key={k} className="border-t"><td className="px-2 py-1 font-mono">{k}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{n}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      <RestoreDialog open={open} onOpenChange={setOpen} title={`Restore dari "${file?.name}"`}
        submit={submit} onDone={onChanged} />
    </div>
  );
}

function Info({ l, v }) {
  return <div><p className="text-[11px] uppercase text-muted-foreground">{l}</p><p className="font-medium">{v}</p></div>;
}
