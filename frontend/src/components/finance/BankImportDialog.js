import React, { useRef, useState } from "react";
import { toast } from "sonner";
import { FileUp, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import api from "@/services/apiClient";
import { BANK } from "@/constants/testIds";

/**
 * BankImportDialog — impor CSV mutasi rekening dengan PRATINJAU yang tidak menulis.
 *
 * Dua hal yang membuat impor mutasi berbahaya bila tanpa layar seperti ini:
 *   1. **Impor ganda.** Berkas yang sama diimpor dua kali akan melahirkan mutasi kembar dan
 *      "uang masuk" berlipat. Backend mengenali baris lewat sidik jari (tanggal+nominal+ref),
 *      jadi impor ulang berstatus *sudah ada, tidak berubah* — pratinjau menunjukkannya
 *      SEBELUM tombol impor ditekan.
 *   2. **Baris cacat yang diam-diam hilang.** Baris tanpa tanggal/nominal DITOLAK beserta
 *      alasannya dan ditampilkan di sini (bukan dibuang tanpa jejak).
 */
export default function BankImportDialog({ open, onOpenChange, accountId, accountName, onDone }) {
  const fileRef = useRef(null);
  const [filename, setFilename] = useState("");
  const [csvText, setCsvText] = useState("");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const reset = () => {
    setFilename(""); setCsvText(""); setPreview(null); setError("");
    if (fileRef.current) fileRef.current.value = "";
  };

  const pickFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFilename(f.name);
    const reader = new FileReader();
    reader.onload = () => { setCsvText(String(reader.result || "")); setPreview(null); };
    reader.readAsText(f);
  };

  const run = async (dryRun) => {
    if (!accountId) { setError("Pilih rekening lebih dulu."); return; }
    if (!csvText.trim()) { setError("Isi/unggah berkas CSV mutasi lebih dulu."); return; }
    setBusy(true); setError("");
    try {
      const res = await api.post("/bank/statements/import", {
        account_id: accountId, filename: filename || "mutasi.csv",
        csv_text: csvText, dry_run: dryRun,
      });
      const data = res.data.data;
      if (dryRun) {
        setPreview(data);
        toast.info(res.data.message || "Pratinjau siap — belum ada yang ditulis.");
      } else {
        toast.success(res.data.message || "Mutasi terimpor.");
        onOpenChange(false);
        reset();
        onDone?.();
      }
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memproses berkas mutasi.");
    } finally { setBusy(false); }
  };

  const counts = preview?.counts || {};

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset(); }}>
      <DialogContent data-testid={BANK.importDialog} className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileUp className="h-4 w-4 text-primary" /> Impor mutasi rekening
          </DialogTitle>
          <DialogDescription>
            {accountName ? `Rekening: ${accountName}. ` : ""}
            Pratinjau dulu — impor ulang berkas yang sama tidak akan menggandakan mutasi.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="bank-import-file">Berkas CSV mutasi</Label>
            <Input id="bank-import-file" ref={fileRef} type="file" accept=".csv,text/csv,text/plain"
              data-testid={BANK.importFile} onChange={pickFile} />
            <p className="text-xs text-muted-foreground">
              Kolom yang dikenali: tanggal, keterangan, referensi, debet/kredit (atau
              nominal + arah), saldo. Format angka Indonesia (1.500.000,00) dibaca benar.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bank-import-text">Atau tempel isi CSV di sini</Label>
            <Textarea id="bank-import-text" data-testid={BANK.importText} rows={4}
              value={csvText} onChange={(e) => { setCsvText(e.target.value); setPreview(null); }}
              placeholder="tanggal;keterangan;ref;debet;kredit;saldo" />
          </div>

          {error ? (
            <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </p>
          ) : null}

          {preview ? (
            <div data-testid={BANK.importPreview} className="space-y-3">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {[
                  ["Baru", counts.new, "text-emerald-700"],
                  ["Diperbarui", counts.updated, "text-amber-700"],
                  ["Sudah ada", counts.unchanged, "text-muted-foreground"],
                  ["Ditolak", counts.rejected, "text-rose-700"],
                ].map(([label, value, tone]) => (
                  <div key={label} className="rounded-lg border bg-card px-3 py-2 shadow-[var(--shadow-card)]">
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className={`font-heading text-lg font-semibold tabular-nums ${tone}`}>
                      {value ?? 0}
                    </p>
                  </div>
                ))}
              </div>

              <div className="max-h-64 overflow-x-auto overflow-y-auto rounded-lg border bg-card shadow-[var(--shadow-card)]">
                <table className="w-full text-sm">
                  <thead className="bg-secondary/60 text-xs uppercase text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 text-left">Tanggal</th>
                      <th className="px-3 py-2 text-left">Keterangan</th>
                      <th className="px-3 py-2 text-right">Nominal</th>
                      <th className="px-3 py-2 text-left">Hasil</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {(preview.rows || []).map((r, i) => (
                      <tr key={`${r.fingerprint || i}`} data-testid={BANK.importRow}>
                        <td className="px-3 py-1.5 tabular-nums">{r.date}</td>
                        <td className="px-3 py-1.5">
                          {r.description}
                          {r.ref ? <span className="text-muted-foreground"> · {r.ref}</span> : null}
                        </td>
                        <td className="px-3 py-1.5 text-right">
                          <MoneyText value={r.amount}
                            className={r.direction === "in" ? "text-emerald-700" : "text-rose-700"} />
                        </td>
                        <td className="px-3 py-1.5">
                          <StatusPill status={r.state} group="import_row_state" />
                          {r.changes?.length ? (
                            <span className="ml-1 text-xs text-muted-foreground">
                              ({r.changes.join(", ")})
                            </span>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {(preview.rejected || []).length ? (
                <div className="rounded-lg border border-rose-200 bg-rose-50 p-3">
                  <p className="text-sm font-medium text-rose-800">
                    {preview.rejected.length} baris ditolak — tidak akan diimpor:
                  </p>
                  <ul className="mt-1 space-y-0.5 text-xs text-rose-700">
                    {preview.rejected.slice(0, 8).map((x, i) => (
                      <li key={i}>baris {x.line ?? i + 1}: {x.reason}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
                <ShieldCheck className="mt-0.5 h-3.5 w-3.5" />
                Pratinjau ini TIDAK menulis apa pun. Mutasi baru masuk berstatus “belum
                dicocokkan” dan belum menjadi pelunasan siapa pun.
              </p>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Tutup</Button>
          <Button variant="secondary" data-testid={BANK.importPreviewBtn} disabled={busy}
            onClick={() => run(true)}>
            {busy && !preview ? "Memeriksa…" : "Pratinjau (tidak menulis)"}
          </Button>
          <Button data-testid={BANK.importCommitBtn} disabled={busy || !preview}
            onClick={() => run(false)}>
            Impor sekarang
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
