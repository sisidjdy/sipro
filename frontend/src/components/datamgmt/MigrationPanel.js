import React, { useRef, useState } from "react";
import { toast } from "sonner";
import { FileSpreadsheet, Download, UploadCloud, PlayCircle, SearchCheck } from "lucide-react";

import api from "@/services/apiClient";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DATAMGMT } from "@/constants/testIds";
import { downloadFile, errDetail } from "./dataMgmtUtils";
import ImportReport from "./ImportReport";

/** Panel migrasi: unduh template/ekspor, unggah Excel → pratinjau → jalankan. */
export default function MigrationPanel({ entities, counts, onImported }) {
  const fileRef = useRef(null);
  const [file, setFile] = useState(null);
  const [mode, setMode] = useState("upsert");
  const [busy, setBusy] = useState("");
  const [report, setReport] = useState(null);

  const send = async (dryRun) => {
    if (!file) { toast.error("Pilih berkas Excel terlebih dahulu."); return; }
    setBusy(dryRun ? "preview" : "commit");
    try {
      const fd = new FormData();
      fd.append("file", file); fd.append("mode", mode); fd.append("dry_run", String(dryRun));
      const res = await api.post("/data-mgmt/import", fd);
      setReport(res.data);
      if (dryRun) {
        toast.success(res.data.totals.error
          ? `Pratinjau: ${res.data.totals.error} baris bermasalah — perbaiki lalu unggah ulang.`
          : "Pratinjau bersih — siap dijalankan.");
      } else {
        toast.success(`Impor selesai: ${res.data.totals.insert} baru, ${res.data.totals.update} diperbarui.`);
        onImported?.();
      }
    } catch (e) {
      toast.error(errDetail(e, "Impor gagal."));
    } finally { setBusy(""); }
  };

  const pickFile = (f) => { setFile(f || null); setReport(null); };
  const canCommit = report && report.dry_run && report.totals.error === 0 && report.totals.rows > 0;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <section className="space-y-4">
        <div className="rounded-xl border bg-card p-5 space-y-3 shadow-[var(--shadow-card)]">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="eyebrow">Langkah 1</p>
              <h3 className="font-semibold">Template untuk klien</h3>
              <p className="text-sm text-muted-foreground">
                Satu berkas Excel berisi {entities.length} sheet master + petunjuk & daftar nilai.
                Berikan ke klien untuk diisi, lalu unggah di sini.
              </p>
            </div>
            <FileSpreadsheet className="h-8 w-8 text-primary shrink-0" />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button data-testid={DATAMGMT.downloadTemplate}
              onClick={() => downloadFile("/data-mgmt/template.xlsx", "SIPRO_Template_Migrasi_Master.xlsx")}>
              <Download className="h-4 w-4 mr-2" /> Unduh template (dengan contoh)
            </Button>
            <Button variant="outline" data-testid={DATAMGMT.downloadExport}
              onClick={() => downloadFile("/data-mgmt/export.xlsx", "SIPRO_Master.xlsx")}>
              <Download className="h-4 w-4 mr-2" /> Ekspor data master saat ini
            </Button>
          </div>
        </div>

        <div className="rounded-xl border bg-card p-5 space-y-3 shadow-[var(--shadow-card)]">
          <p className="eyebrow">Langkah 2</p>
          <h3 className="font-semibold">Unggah & pratinjau</h3>
          <label
            className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 text-center hover:bg-accent/40 transition-colors"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); pickFile(e.dataTransfer.files?.[0]); }}>
            <UploadCloud className="h-7 w-7 text-muted-foreground" />
            <span className="text-sm">{file ? <b>{file.name}</b> : "Seret berkas .xlsx ke sini atau klik untuk memilih"}</span>
            <input ref={fileRef} data-testid={DATAMGMT.fileInput} type="file" accept=".xlsx,.xlsm"
              className="hidden" onChange={(e) => pickFile(e.target.files?.[0])} />
          </label>
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Jika data sudah ada</p>
              <Select value={mode} onValueChange={(v) => { setMode(v); setReport(null); }}>
                <SelectTrigger data-testid={DATAMGMT.modeSelect} className="w-64"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="upsert">Perbarui data yang ada (upsert)</SelectItem>
                  <SelectItem value="skip">Lewati baris duplikat</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button variant="secondary" data-testid={DATAMGMT.previewBtn} disabled={!file || !!busy}
              onClick={() => send(true)}>
              <SearchCheck className="h-4 w-4 mr-2" /> {busy === "preview" ? "Memvalidasi…" : "Pratinjau (validasi)"}
            </Button>
            <Button data-testid={DATAMGMT.commitBtn} disabled={!canCommit || !!busy} onClick={() => send(false)}>
              <PlayCircle className="h-4 w-4 mr-2" /> {busy === "commit" ? "Mengimpor…" : "Jalankan impor"}
            </Button>
          </div>
          {report && !report.dry_run ? null : (
            <p className="text-xs text-muted-foreground">
              Tidak ada yang ditulis ke database sampai Anda menekan "Jalankan impor" setelah pratinjau bersih.
            </p>
          )}
        </div>

        <EntityTable entities={entities} counts={counts} />
      </section>

      <section>
        <ImportReport report={report} />
      </section>
    </div>
  );
}

function EntityTable({ entities, counts }) {
  const countOf = Object.fromEntries((counts || []).map((c) => [c.key, c.count]));
  return (
    <div className="rounded-xl border bg-card overflow-hidden shadow-[var(--shadow-card)]">
      <div className="px-5 py-3 border-b">
        <h3 className="font-semibold text-sm">Sheet dalam template (urutan impor)</h3>
      </div>
      <table data-testid={DATAMGMT.entityTable} className="w-full text-sm">
        <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
          <tr><th className="text-left px-5 py-2">Sheet</th><th className="text-left px-2 py-2">Kunci duplikat</th>
            <th className="text-right px-5 py-2">Di sistem</th></tr>
        </thead>
        <tbody>
          {entities.map((e, i) => (
            <tr key={e.key} data-testid={`${DATAMGMT.entityRow}-${e.key}`} className="border-t">
              <td className="px-5 py-2"><span className="text-muted-foreground mr-2">{i + 1}.</span>
                <b>{e.sheet}</b><p className="text-xs text-muted-foreground">{e.desc}</p></td>
              <td className="px-2 py-2 font-mono text-xs">{e.key_fields.join(" + ")}</td>
              <td className="px-5 py-2 text-right tabular-nums">{countOf[e.key] ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
