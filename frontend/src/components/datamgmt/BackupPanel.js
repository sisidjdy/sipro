import React, { useState } from "react";
import { toast } from "sonner";
import { Download, HardDriveDownload, RotateCcw, Trash2, Camera, FileSpreadsheet } from "lucide-react";

import api from "@/services/apiClient";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatDateTimeWIB } from "@/utils/formatters";
import { DATAMGMT } from "@/constants/testIds";
import ConfirmDialog from "@/components/patterns/ConfirmDialog";
import { downloadFile, errDetail, formatBytes } from "./dataMgmtUtils";
import RestoreDialog from "./RestoreDialog";

/** Backup: unduh JSON/Excel, buat snapshot di server, kelola & restore snapshot. */
export default function BackupPanel({ snapshots, onChanged }) {
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [restoreTarget, setRestoreTarget] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const createSnapshot = async () => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("label", label); fd.append("include_files", "true");
      const res = await api.post("/data-mgmt/snapshots", fd);
      toast.success(`Snapshot dibuat: ${res.data.documents} dokumen.`);
      setLabel(""); onChanged?.();
    } catch (e) { toast.error(errDetail(e, "Gagal membuat snapshot.")); } finally { setBusy(false); }
  };

  const remove = async () => {
    try {
      await api.delete(`/data-mgmt/snapshots/${deleteTarget.id}`);
      toast.success("Snapshot dihapus."); onChanged?.();
    } catch (e) { toast.error(errDetail(e, "Gagal menghapus.")); } finally { setDeleteTarget(null); }
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border bg-card p-5 space-y-3 shadow-[var(--shadow-card)]">
          <div className="flex items-start justify-between">
            <div><p className="eyebrow">Unduh</p><h3 className="font-semibold">Backup ke komputer Anda</h3></div>
            <HardDriveDownload className="h-7 w-7 text-primary" />
          </div>
          <p className="text-sm text-muted-foreground">
            JSON = salinan lengkap seluruh data organisasi (master + transaksi + berkas) untuk restore.
            Excel = hanya master data, bisa dibaca & diedit klien.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button data-testid={DATAMGMT.downloadBackup}
              onClick={() => downloadFile("/data-mgmt/backup.json", "SIPRO_Backup.json", { include_files: true })}>
              <Download className="h-4 w-4 mr-2" /> Backup JSON lengkap
            </Button>
            <Button variant="outline" onClick={() => downloadFile("/data-mgmt/export.xlsx", "SIPRO_Master.xlsx")}>
              <FileSpreadsheet className="h-4 w-4 mr-2" /> Master (Excel)
            </Button>
          </div>
        </div>
        <div className="rounded-xl border bg-card p-5 space-y-3 shadow-[var(--shadow-card)]">
          <div className="flex items-start justify-between">
            <div><p className="eyebrow">Server</p><h3 className="font-semibold">Buat snapshot</h3></div>
            <Camera className="h-7 w-7 text-primary" />
          </div>
          <p className="text-sm text-muted-foreground">
            Snapshot disimpan di server dan bisa di-restore satu klik. Sistem juga membuat snapshot otomatis
            sebelum setiap restore.
          </p>
          <div className="flex gap-2">
            <Input data-testid={DATAMGMT.snapshotLabel} placeholder="Label, mis. sebelum go-live" value={label}
              onChange={(e) => setLabel(e.target.value)} />
            <Button data-testid={DATAMGMT.snapshotCreate} onClick={createSnapshot} disabled={busy}>
              {busy ? "Menyimpan…" : "Buat snapshot"}
            </Button>
          </div>
        </div>
      </div>

      <div className="rounded-xl border bg-card overflow-hidden shadow-[var(--shadow-card)]">
        <div className="px-5 py-3 border-b flex items-center justify-between">
          <h3 className="font-semibold text-sm">Snapshot tersimpan ({snapshots.length})</h3>
        </div>
        {snapshots.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground text-center">Belum ada snapshot.</p>
        ) : (
          <table data-testid={DATAMGMT.snapshotTable} className="w-full text-sm">
            <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
              <tr><th className="text-left px-5 py-2">Label</th><th className="text-left px-2 py-2">Dibuat</th>
                <th className="text-right px-2 py-2">Dokumen</th><th className="text-right px-2 py-2">Ukuran</th>
                <th className="px-5 py-2 text-right">Aksi</th></tr>
            </thead>
            <tbody>
              {snapshots.map((s) => (
                <tr key={s.id} data-testid={`${DATAMGMT.snapshotRow}-${s.id}`} className="border-t">
                  <td className="px-5 py-2"><b>{s.label}</b>
                    <p className="text-xs text-muted-foreground">{s.kind === "auto" ? "otomatis · " : ""}{s.created_by}</p></td>
                  <td className="px-2 py-2 text-xs">{formatDateTimeWIB(s.created_at)}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{s.documents}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{formatBytes(s.size)}</td>
                  <td className="px-5 py-2">
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" data-testid={`${DATAMGMT.snapshotDownload}-${s.id}`}
                        onClick={() => downloadFile(`/data-mgmt/snapshots/${s.id}/download`, s.filename)}>
                        <Download className="h-4 w-4" /></Button>
                      <Button size="sm" variant="ghost" data-testid={`${DATAMGMT.snapshotRestore}-${s.id}`}
                        onClick={() => setRestoreTarget(s)}><RotateCcw className="h-4 w-4" /></Button>
                      <Button size="sm" variant="ghost" className="text-rose-600" data-testid={`${DATAMGMT.snapshotDelete}-${s.id}`}
                        onClick={() => setDeleteTarget(s)}><Trash2 className="h-4 w-4" /></Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <RestoreDialog open={!!restoreTarget} onOpenChange={(o) => !o && setRestoreTarget(null)}
        title={`Restore snapshot "${restoreTarget?.label}"`}
        submit={(fd) => api.post(`/data-mgmt/snapshots/${restoreTarget.id}/restore`, fd)}
        onDone={onChanged} />
      <ConfirmDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Hapus snapshot?" description={`Berkas "${deleteTarget?.filename}" akan dihapus dari server.`}
        confirmLabel="Hapus" destructive onConfirm={remove} />
    </div>
  );
}
