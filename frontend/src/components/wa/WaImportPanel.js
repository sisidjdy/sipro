import React, { useRef, useState } from "react";
import { toast } from "sonner";
import { FileUp, ScanSearch, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { DupBadge } from "@/components/wa/WaContactsTable";
import api from "@/services/apiClient";
import { P94 } from "@/constants/testIds";

const SUM = [
  ["total", "Baris terbaca"], ["valid", "Nomor valid"], ["invalid", "Tidak valid"],
  ["dup_in_batch", "Ganda dalam berkas"], ["dup_lead", "Duplikat lead"],
  ["dup_customer", "Sudah customer"], ["in_queue", "Sudah di antrean"], ["fresh", "Nomor baru"],
];

/**
 * WaImportPanel — migrasi kontak yang SUDAH ADA sebelum integrasi Meta hidup.
 * Meta Cloud API tidak menyediakan daftar kontak, jadi jalur resminya: ekspor kontak dari HP
 * (Google Contacts → .vcf / .csv) atau tempel daftar nomor, lalu sistem membaca & mendedup.
 */
export default function WaImportPanel({ onImported }) {
  const [text, setText] = useState("");
  const [label, setLabel] = useState("");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);

  const doPreview = async () => {
    if (!text.trim()) { toast.error("Tempel daftar nomor / isi CSV / VCF terlebih dahulu."); return; }
    setBusy(true);
    try {
      const res = await api.post("/wa/contacts/preview", { text });
      setPreview(res.data.data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membaca teks."); }
    finally { setBusy(false); }
  };

  const doImport = async () => {
    setBusy(true);
    try {
      const res = await api.post("/wa/contacts/import", { text, label });
      const d = res.data.data;
      toast.success(`${d.added} kontak baru masuk antrean, ${d.updated} diperbarui.`);
      setText(""); setPreview(null); setLabel("");
      onImported?.(d);
    } catch (e) { toast.error(e?.response?.data?.detail || "Impor gagal."); }
    finally { setBusy(false); }
  };

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const content = await f.text();
    setText(content);
    if (!label) setLabel(f.name);
    toast.success(`Berkas ${f.name} dibaca — tekan "Pratinjau & cek duplikat".`);
    e.target.value = "";
  };

  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <div className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)] lg:col-span-2">
        <div>
          <h3 className="section-title">Sumber kontak</h3>
          <p className="text-xs text-muted-foreground">
            Tempel satu nomor per baris (boleh <code>Nama, 0812…</code>), isi CSV berkolom nama/telepon,
            atau berkas <b>.vcf</b> hasil ekspor kontak HP / Google Contacts.
          </p>
        </div>
        <Textarea data-testid={P94.importText} rows={10} value={text} onChange={(e) => setText(e.target.value)}
          placeholder={"Budi Santoso, 081234567890\nSiti, +62 813-9999-8888\n08157777666"} aria-label="Daftar kontak" />
        <div className="space-y-1.5">
          <Label htmlFor="wa-import-label">Label batch (opsional)</Label>
          <Input id="wa-import-label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="mis. Kontak WA Sales Andi" />
        </div>
        <input ref={fileRef} data-testid={P94.importFile} type="file" accept=".csv,.txt,.vcf,text/*" className="hidden" onChange={onFile} aria-label="Unggah berkas kontak" />
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()}>
            <FileUp className="mr-1.5 h-4 w-4" /> Pilih berkas (.csv / .vcf / .txt)
          </Button>
          <Button data-testid={P94.importPreviewBtn} size="sm" variant="secondary" onClick={doPreview} disabled={busy || !text.trim()}>
            <ScanSearch className="mr-1.5 h-4 w-4" /> Pratinjau & cek duplikat
          </Button>
        </div>
      </div>

      <div className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)] lg:col-span-3">
        <h3 className="section-title">Hasil pembacaan</h3>
        {!preview ? (
          <p className="text-sm text-muted-foreground">Belum ada pratinjau. Sistem akan menormalkan nomor ke +62,
            membuang yang ganda dalam berkas, dan menandai nomor yang sudah menjadi lead / customer.</p>
        ) : (
          <>
            <div data-testid={P94.importSummary} className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {SUM.map(([k, l]) => (
                <div key={k} className="rounded-lg border bg-background px-3 py-2">
                  <p className="text-[11px] text-muted-foreground">{l}</p>
                  <p className="text-lg font-semibold tabular-nums">{preview.summary?.[k] ?? 0}</p>
                </div>
              ))}
            </div>
            <div className="max-h-80 overflow-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-secondary text-left text-xs">
                  <tr><th className="px-2 py-1.5">Nama</th><th className="px-2 py-1.5">Nomor</th><th className="px-2 py-1.5">Hasil</th></tr>
                </thead>
                <tbody>
                  {preview.items.map((it, i) => (
                    <tr key={i} className="border-t">
                      <td className="px-2 py-1.5">{it.name || <span className="italic text-muted-foreground">—</span>}</td>
                      <td className="px-2 py-1.5 tabular-nums">{it.phone || <span className="text-rose-600">{it.phone_raw}</span>}</td>
                      <td className="px-2 py-1.5">
                        {!it.valid ? <span className="text-xs text-rose-600">Tidak valid</span>
                          : it.dup_in_batch ? <span className="text-xs text-zinc-500">Ganda dalam berkas (dilewati)</span>
                            : it.in_queue ? <span className="text-xs text-zinc-500">Sudah di antrean ({it.in_queue})</span>
                              : <DupBadge c={{ match_lead_id: it.match_lead?.id, match_lead_name: it.match_lead?.name,
                                match_lead_stage: it.match_lead?.stage, match_lead_owner: it.match_lead?.assigned_to,
                                match_customer_id: it.match_customer?.id, match_customer_name: it.match_customer?.name }} />}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex justify-end">
              <Button data-testid={P94.importSubmitBtn} onClick={doImport} disabled={busy || !preview.summary?.valid}>
                <Upload className="mr-1.5 h-4 w-4" /> Masukkan {preview.summary?.valid || 0} kontak ke antrean
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
