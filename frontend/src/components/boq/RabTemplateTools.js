import React, { useRef, useState } from "react";
import { Copy, Download, FileUp } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { downloadFile, errDetail } from "@/components/datamgmt/dataMgmtUtils";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { P81 } from "@/constants/testIds";

const toRows = (items) => items.map((it) => ({ ...it, qty: String(it.qty), unit_price: String(it.unit_price), step_code: it.step_code || "" }));

/** Alat editor RAB: salin dari tipe/add-on lain (× faktor) dan impor Excel. Keduanya hanya mengisi editor — user tetap menekan Simpan. */
export default function RabTemplateTools({ kind, target, candidates, onLoadRows }) {
  const [source, setSource] = useState("");
  const [factor, setFactor] = useState("1");
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState("");
  const fileRef = useRef(null);
  const ref = encodeURIComponent(target?.ref_code || "");
  const sources = (candidates || []).filter((c) => c.ref_code !== target?.ref_code && c.items > 0);

  const copy = async () => {
    if (!source) { toast.error("Pilih sumber salinan dulu."); return; }
    setBusy("copy");
    try {
      const r = await api.post(`/rab/templates/${kind}/${ref}/copy-from`, { source_ref_code: source, factor: Number(factor) || 1 });
      const d = r.data.data;
      onLoadRows(toRows(d.items), `Disalin dari ${d.source_ref} × ${d.factor} — ${d.items.length} baris, total ${formatIDR(d.total)}. Belum tersimpan.`);
      setReport(null);
      toast.success(`RAB ${d.source_ref} disalin ke editor (${d.items.length} baris).`);
    } catch (e) { toast.error(errDetail(e, "Gagal menyalin RAB.")); } finally { setBusy(""); }
  };

  const upload = async (file) => {
    if (!file) return;
    setBusy("import");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api.post(`/rab/templates/${kind}/${ref}/import`, fd);
      const d = r.data.data;
      setReport(d);
      if (d.items.length) {
        onLoadRows(toRows(d.items), `Diimpor dari ${file.name} — ${d.rows} baris, total ${formatIDR(d.total)}. Belum tersimpan.`);
        toast.success(`${d.rows} baris dimuat ke editor${d.errors.length ? `, ${d.errors.length} baris dilewati` : ""}.`);
      } else {
        toast.error(d.errors[0] || "Tidak ada baris valid di berkas.");
      }
    } catch (e) { toast.error(errDetail(e, "Impor gagal.")); } finally { setBusy(""); if (fileRef.current) fileRef.current.value = ""; }
  };

  return (
    <div data-testid={P81.toolsBar} className="space-y-2 rounded-lg border border-dashed bg-secondary/30 p-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Copy className="h-3.5 w-3.5 text-muted-foreground" />
        <select data-testid={P81.copySource} aria-label="Sumber salinan RAB" className="h-8 min-w-[220px] rounded-md border bg-background px-2 text-xs" value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">Salin dari {kind === "unit_type" ? "tipe" : "add-on"} lain…</option>
          {sources.map((c) => <option key={c.ref_code} value={c.ref_code}>{`${c.ref_code} · ${c.name} (${formatIDR(c.total)})`}</option>)}
        </select>
        <span className="text-muted-foreground">× faktor harga</span>
        <Input data-testid={P81.copyFactor} aria-label="Faktor harga" className="h-8 w-20 text-xs" type="number" step="0.05" min="0.05" max="10" value={factor} onChange={(e) => setFactor(e.target.value)} />
        <Button data-testid={P81.copyBtn} size="sm" variant="outline" disabled={busy === "copy" || !sources.length}
          title={!sources.length ? `Belum ada ${kind === "unit_type" ? "tipe" : "add-on"} lain yang punya RAB untuk disalin` : undefined} onClick={copy}>Salin ke editor</Button>
        {!sources.length ? <span className="text-[11px] text-muted-foreground">(belum ada sumber ber-RAB)</span> : null}
        <span className="mx-1 h-5 w-px bg-border" />
        <input ref={fileRef} data-testid={P81.importFile} aria-label="Berkas Excel RAB" type="file" accept=".xlsx" className="hidden" disabled={busy === "import"} onChange={(e) => upload(e.target.files?.[0])} />
        <Button size="sm" variant="outline" disabled={busy === "import"} onClick={() => fileRef.current?.click()}><FileUp className="mr-1 h-3.5 w-3.5" /> {busy === "import" ? "Mengunggah…" : "Impor Excel"}</Button>
        <Button data-testid={P81.importTemplateBtn} size="sm" variant="ghost" onClick={() => downloadFile("/rab/import-template.xlsx", "SIPRO_Template_RAB.xlsx", { kind })}><Download className="mr-1 h-3.5 w-3.5" /> Template Excel</Button>
      </div>
      {report && (report.errors.length || report.warnings.length) ? (
        <ul data-testid={P81.importReport} className="max-h-24 space-y-0.5 overflow-y-auto text-[11px]">
          {report.errors.map((m, i) => <li key={`e${i}`} className="text-rose-700">{m}</li>)}
          {report.warnings.map((m, i) => <li key={`w${i}`} className="text-amber-700">{m}</li>)}
        </ul>
      ) : null}
    </div>
  );
}
