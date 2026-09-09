import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, FileUp, Settings2 } from "lucide-react";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import ImportReport from "@/components/ads/ImportReport";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { ADS } from "@/constants/testIds";

/**
 * SpendImportDialog — wizard impor CSV biaya iklan: **pratinjau → simpan → laporan**.
 *
 * Kenapa pratinjau wajib (spec §5): laporan platform diunduh per minggu dan rentang
 * tanggalnya sering bertumpuk, judul kolomnya berubah antar ekspor, dan angkanya bisa
 * dikoreksi platform beberapa hari kemudian. Menyimpan langsung berarti pemakai baru tahu
 * ada masalah setelah biayanya masuk ke laporan. Yang dikomit adalah laporan pratinjau YANG
 * SAMA (berdasarkan id-nya), jadi tidak mungkin “yang dilihat” dan “yang disimpan” berbeda.
 *
 * Pemetaan kolom disimpan sebagai profil per platform, jadi cukup diisi sekali.
 */
export default function SpendImportDialog({ open, onOpenChange, onDone }) {
  const { can } = useAuth();
  const canCommit = can("ads", "update");
  const [meta, setMeta] = useState(null);
  const [csvText, setCsvText] = useState("");
  const [filename, setFilename] = useState("");
  const [mapping, setMapping] = useState({});
  const [showMapping, setShowMapping] = useState(false);
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);

  const loadMeta = useCallback(async () => {
    try {
      const res = await api.get("/ads/spend/template");
      setMeta(res.data.data);
      const saved = (res.data.data?.profiles || [])[0]?.mapping;
      if (saved) setMapping(saved);
    } catch {
      setMeta(null);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    setCsvText(""); setFilename(""); setReport(null); setShowMapping(false);
    loadMeta();
  }, [open, loadMeta]);

  const pickFile = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setFilename(file.name);
    setCsvText(await file.text());
    setReport(null);
  };

  const downloadTemplate = () => {
    if (!meta?.csv) return;
    const url = URL.createObjectURL(new Blob([meta.csv], { type: "text/csv;charset=utf-8;" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "contoh-biaya-iklan.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const preview = async () => {
    if (csvText.trim().length < 5) {
      toast.error("Tempelkan isi CSV atau pilih berkasnya lebih dulu.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.post("/ads/spend/import", {
        csv_text: csvText, filename: filename || "biaya-iklan.csv",
        mapping: Object.fromEntries(Object.entries(mapping).filter(([, v]) => v)),
        dry_run: true,
      });
      setReport(res.data.data);
      const s = res.data.data?.summary || {};
      if (res.data.data?.status === "failed") toast.error(res.data.data.error);
      else toast.success(`Pratinjau siap: ${s.new || 0} baru, ${s.update || 0} diperbarui, `
        + `${s.rejected || 0} ditolak.`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memvalidasi berkas.");
    } finally { setBusy(false); }
  };

  const commit = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/ads/spend/import/${report.id}/commit`);
      setReport(res.data.data);
      const a = res.data.data?.applied || {};
      toast.success(res.data.already_committed
        ? "Laporan ini sudah pernah disimpan — tidak ada biaya yang dihitung dua kali."
        : `Tersimpan: ${a.inserted || 0} baris baru, ${a.updated || 0} diperbarui, `
          + `${a.unchanged || 0} sama.`);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan impor.");
    } finally { setBusy(false); }
  };

  const committed = report?.status === "committed";
  const canSave = report?.status === "preview"
    && ((report.summary?.new || 0) + (report.summary?.update || 0)
      + (report.summary?.unchanged || 0)) > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={ADS.importDialog}
        className="max-h-[92vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Impor biaya iklan (CSV)</DialogTitle>
          <DialogDescription>
            Kolom wajib: <code>{(meta?.required || []).join(", ")}</code>. Mata uang yang
            didukung hanya {meta?.currency || "IDR"} — baris dengan mata uang lain DITOLAK,
            karena tidak ada kurs yang bisa dipertanggungjawabkan di dalam aplikasi.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1.5">
              <Label htmlFor="csvfile">Berkas CSV</Label>
              <Input id="csvfile" type="file" accept=".csv,text/csv"
                data-testid={ADS.importFile} onChange={pickFile} className="bg-background" />
            </div>
            <Button size="sm" variant="outline" data-testid={ADS.importTemplate}
              onClick={downloadTemplate} disabled={!meta?.csv}>
              <Download className="mr-1.5 h-4 w-4" /> Unduh contoh
            </Button>
            <Button size="sm" variant="ghost" data-testid={ADS.importMappingToggle}
              onClick={() => setShowMapping((v) => !v)}>
              <Settings2 className="mr-1.5 h-4 w-4" /> Pemetaan kolom
            </Button>
          </div>

          {showMapping ? (
            <div className="space-y-2 rounded-lg border bg-secondary/40 p-3">
              <p className="text-xs text-muted-foreground">
                Isi bila judul kolom di berkas Anda berbeda. Contoh: kolom biaya bernama
                “Amount spent (IDR)” → tulis judul itu di baris <strong>spend</strong>.
                Pemetaan yang berhasil dipakai akan disimpan sebagai profil platform.
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {(meta?.columns || []).map((col) => {
                  const current = Object.entries(mapping).find(([, v]) => v === col)?.[0] || "";
                  return (
                    <div key={col} className="space-y-1">
                      <Label htmlFor={`map-${col}`}>{col}</Label>
                      <Input id={`map-${col}`} value={current}
                        data-testid={`${ADS.importMappingField}-${col}`}
                        placeholder="judul kolom di berkas Anda"
                        onChange={(e) => {
                          const header = e.target.value;
                          setMapping((m) => {
                            const next = Object.fromEntries(
                              Object.entries(m).filter(([, v]) => v !== col));
                            if (header) next[header] = col;
                            return next;
                          });
                        }} />
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          <div className="space-y-1.5">
            <Label htmlFor="csvtext">Atau tempel isi CSV</Label>
            <Textarea id="csvtext" rows={5} data-testid={ADS.importText} value={csvText}
              className="font-mono text-xs"
              placeholder={`date,platform,campaign_name,spend\n2026-08-01,meta,cluster-a-meta,1250000`}
              onChange={(e) => { setCsvText(e.target.value); setReport(null); }} />
          </div>

          {report ? <ImportReport report={report} /> : (
            <p className="rounded-lg border border-dashed bg-secondary/40 p-4 text-sm
              text-muted-foreground">
              Belum ada pratinjau. Tekan <strong>Pratinjau</strong> — tidak ada satu pun angka
              yang tersimpan sampai Anda menekan Simpan.
            </p>
          )}
        </div>

        <DialogFooter className="flex-wrap gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Tutup
          </Button>
          <Button variant="secondary" data-testid={ADS.importPreview} onClick={preview}
            disabled={busy}>
            <FileUp className="mr-1.5 h-4 w-4" /> {busy ? "Memvalidasi…" : "Pratinjau"}
          </Button>
          {canCommit ? (
            <Button data-testid={ADS.importCommit} onClick={commit}
              disabled={busy || !canSave || committed}>
              {committed ? "Sudah disimpan"
                : `Simpan ${((report?.summary?.new || 0) + (report?.summary?.update || 0)) || 0} baris`}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
