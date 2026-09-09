import React, { useCallback, useEffect, useState } from "react";
import { Plus, NotebookPen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import AddJournalDialog from "@/components/gl/AddJournalDialog";
import JournalDetailSheet from "@/components/gl/JournalDetailSheet";
import { useAuth } from "@/context/AuthContext";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { GL } from "@/constants/testIds";
import SearchInput from "@/components/patterns/SearchInput";


export default function JournalPanel() {
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  const canManage = can("gl", "create");
  const [data, setData] = useState(null);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const r = await api.get("/gl/journals", { params: { q: q || undefined, limit: 100 } }); setData(r.data); }
    catch (e) { setError(e?.response?.data?.detail || "Gagal memuat jurnal."); }
    finally { setLoading(false); }
  }, [q]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SearchInput value={q} onChange={setQ} testId="journal-search"
          placeholder="Cari no. jurnal / keterangan…"
          className="w-full sm:w-72" />
        {canManage ? (
          <Button data-testid={GL.journalAddBtn} size="sm" onClick={() => setAddOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> Jurnal Manual
          </Button>
        ) : null}
      </div>
      {loading ? <LoadingCards count={4} /> : error ? <ErrorState message={error} onRetry={load} /> :
        !data?.data?.length ? (
          <EmptyState icon={NotebookPen} title="Belum ada jurnal"
            description="Jurnal otomatis terposting dari transaksi (pembayaran, AP, komisi, pendapatan) atau buat jurnal manual."
            actionLabel={canManage ? "Jurnal Manual" : undefined} onAction={() => setAddOpen(true)} />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>No. Jurnal</TableHead><TableHead>Tanggal</TableHead><TableHead>Keterangan</TableHead>
                <TableHead>Sumber</TableHead><TableHead className="text-right">Nilai</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.data.map((j) => (
                  <TableRow key={j.id} data-testid={GL.journalRow} className="cursor-pointer" onClick={() => setSelected(j)}>
                    <TableCell className="font-medium tabular-nums">{j.entry_no}</TableCell>
                    <TableCell className="text-sm">{formatDateWIB(j.date)}</TableCell>
                    <TableCell className="text-sm">{j.memo}</TableCell>
                    <TableCell><span className={`rounded-full px-2 py-0.5 text-xs ${j.auto ? "bg-sky-50 text-sky-700" : "bg-secondary text-foreground"}`}>{j.auto ? "Otomatis" : "Manual"}</span></TableCell>
                    <TableCell className="text-right tabular-nums font-medium">{formatIDR(j.total_debit)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      <AddJournalDialog open={addOpen} onOpenChange={setAddOpen} onDone={load} />
      <JournalDetailSheet journal={selected} open={!!selected} onOpenChange={(v) => !v && setSelected(null)} />
    </div>
  );
}
