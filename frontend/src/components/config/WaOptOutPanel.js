import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Ban, Download, RotateCcw, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import PhoneInput from "@/components/patterns/PhoneInput";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatDateTimeWIB } from "@/utils/formatters";
import { useReference } from "@/context/ReferenceContext";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { P97 } from "@/constants/testIds";

/** Daftar opt-out WhatsApp (Fase 97B): dicari, ditambah manual, dicabut, ekspor CSV. */
export default function WaOptOutPanel() {
  const { labelOf } = useReference();
  const { can } = useAuth();
  const [q, setQ] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const canManage = can("settings", "manage");

  const load = useCallback(() => {
    setError("");
    api.get("/wa/optouts", { params: { q, limit: 200 } }).then((r) => setData(r.data))
      .catch((e) => setError(e?.response?.data?.detail || "Gagal memuat daftar opt-out."));
  }, [q]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  const add = async () => {
    if (!phone) { toast.error("Isi nomor WhatsApp."); return; }
    setBusy(true);
    try { await api.post("/wa/optouts", { phone, note: "Dicatat manual dari Pusat Konfigurasi" }); toast.success("Nomor dicatat opt-out."); setPhone(""); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal mencatat opt-out."); }
    finally { setBusy(false); }
  };
  const revoke = async (row) => {
    try { await api.delete(`/wa/optouts/${row.id}`); toast.success("Opt-out dicabut; consent tercatat."); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal mencabut opt-out."); }
  };
  const exportCsv = async () => {
    try {
      const r = await api.get("/wa/optouts/export.csv", { responseType: "blob" });
      const href = URL.createObjectURL(new Blob([r.data], { type: "text/csv" }));
      const a = document.createElement("a"); a.href = href; a.download = "wa-optouts.csv"; a.click();
      setTimeout(() => URL.revokeObjectURL(href), 10000);
    } catch { toast.error("Gagal mengekspor CSV."); }
  };

  if (error) return <ErrorState message={error} onRetry={load} />;
  return (
    <div className="space-y-3" data-testid={P97.optoutPanel}>
      <p className="text-sm text-muted-foreground">
        Pembeli yang membalas <b>STOP / BERHENTI / UNSUB / HENTIKAN</b> (kata utuh) otomatis masuk daftar ini dan dibalas konfirmasi satu kali.
        Pesan <b>MARKETING</b> ke nomor ini ditolak gateway; pengingat tagihan / dokumen (UTILITY) tetap dikirim.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input data-testid={P97.optoutSearch} aria-label="Cari nomor" className="w-56 pl-8" placeholder="Cari nomor…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Button data-testid={P97.optoutExportBtn} variant="outline" size="sm" onClick={exportCsv}><Download className="mr-1.5 h-4 w-4" /> Ekspor CSV</Button>
        {canManage ? (
          <div className="ml-auto flex items-end gap-2">
            <div className="w-56" data-testid={P97.optoutAddPhone}><PhoneInput value={phone} onChange={setPhone} placeholder="0812…" aria-label="Nomor opt-out baru" /></div>
            <Button data-testid={P97.optoutAddBtn} size="sm" onClick={add} disabled={busy}><Ban className="mr-1.5 h-4 w-4" /> Catat opt-out</Button>
          </div>
        ) : null}
      </div>
      {!data ? <LoadingCards count={2} /> : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader><TableRow><TableHead>Nomor</TableHead><TableHead>Nama</TableHead><TableHead>Sumber</TableHead><TableHead>Sejak</TableHead><TableHead>Catatan</TableHead><TableHead className="text-right">Aksi</TableHead></TableRow></TableHeader>
            <TableBody>
              {data.data.map((r) => (
                <TableRow key={r.id} data-testid={P97.optoutRow}>
                  <TableCell className="font-mono text-xs">{r.phone}</TableCell>
                  <TableCell>{r.name || <span className="italic text-muted-foreground">bukan lead/customer</span>}</TableCell>
                  <TableCell className="text-xs">{labelOf("wa_optout_source", r.source)}</TableCell>
                  <TableCell className="text-xs">{formatDateTimeWIB(r.created_at)}</TableCell>
                  <TableCell className="max-w-[220px] truncate text-xs text-muted-foreground" title={r.note}>{r.note || "—"}</TableCell>
                  <TableCell className="text-right">
                    {canManage ? <Button data-testid={P97.optoutRevokeBtn} size="sm" variant="ghost" onClick={() => revoke(r)} title="Cabut opt-out (pembeli setuju lagi)"><RotateCcw className="h-4 w-4" /></Button> : null}
                  </TableCell>
                </TableRow>
              ))}
              {!data.data.length ? <TableRow><TableCell colSpan={6} className="py-6 text-center text-sm text-muted-foreground">Belum ada nomor opt-out.</TableCell></TableRow> : null}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
