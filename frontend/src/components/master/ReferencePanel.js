import React, { useCallback, useEffect, useMemo, useState } from "react";
import { BookMarked, Lock, Unlock, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { MASTER } from "@/constants/testIds";

/**
 * Kamus Data (SSOT) — Fase 26.
 *
 * Menampilkan SELURUH grup nilai terkontrol dari `GET /api/reference`: nilai kanonik,
 * label Indonesia, apakah divalidasi ketat oleh backend, dan apakah nilai baru boleh
 * ditambah dari form. Sebelumnya kamus ini hanya ada di kode (dan sebagian diduplikasi
 * di frontend), sehingga admin tidak punya cara melihat pilihan resmi sebuah field.
 */
export default function ReferencePanel() {
  const [registry, setRegistry] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/reference");
      setRegistry(res.data.data || {});
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat kamus data.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const groups = useMemo(() => {
    const term = q.trim().toLowerCase();
    return Object.entries(registry)
      .filter(([name, g]) => !term
        || name.includes(term)
        || String(g.label || "").toLowerCase().includes(term)
        || (g.options || []).some((o) => String(o.value).toLowerCase().includes(term)
          || String(o.label).toLowerCase().includes(term)))
      .sort((a, b) => a[0].localeCompare(b[0]));
  }, [registry, q]);

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const totalValues = Object.values(registry).reduce((s, g) => s + (g.options || []).length, 0);

  return (
    <div data-testid={MASTER.refPanel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{Object.keys(registry).length} grup</span> ·{" "}
          <span className="font-medium text-foreground">{totalValues} nilai</span> terkontrol.
          Backend menolak nilai di luar daftar untuk grup bertanda “Terkunci”.
        </p>
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input data-testid={MASTER.refSearch} value={q} onChange={(e) => setQ(e.target.value)}
            className="search-field pl-9" placeholder="Cari grup, nilai, atau label…" aria-label="Cari kamus data" />
        </div>
      </div>

      {!groups.length ? (
        <EmptyState icon={BookMarked} title="Tidak ada grup yang cocok"
          description="Ubah kata kunci pencarian Anda." />
      ) : (
        <div className="grid items-start gap-3 lg:grid-cols-2">
          {groups.map(([name, g]) => (
            <div key={name} data-testid={MASTER.refGroupRow} data-group={name}
              className="rounded-xl border bg-card p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-heading text-sm font-semibold">{g.label || name}</p>
                  <p className="font-mono text-[11px] text-muted-foreground">
                    {name} · {(g.options || []).length} nilai
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  {g.strict ? (
                    <Badge variant="secondary" className="gap-1"><Lock className="h-3 w-3" /> Terkunci</Badge>
                  ) : (
                    <Badge variant="outline" className="gap-1"><Unlock className="h-3 w-3" /> Bebas</Badge>
                  )}
                  {g.dynamic ? <Badge variant="outline">Bisa tambah nilai</Badge> : null}
                </div>
              </div>
              {/* Daftar nilai bisa panjang: kotaknya diberi latar sendiri + kepala tabel yang
                  tetap terlihat saat digulir, supaya tidak terlihat seperti kartu tanpa latar
                  dengan baris terpotong di tengah. */}
              <div className="mt-3 max-h-56 overflow-y-auto rounded-lg border bg-background">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-secondary">
                    <TableRow>
                      <TableHead className="h-8 text-[11px]">Nilai kanonik</TableHead>
                      <TableHead className="h-8 text-[11px]">Label tampilan</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(g.options || []).map((o) => (
                      <TableRow key={o.value}>
                        <TableCell className="py-1.5 font-mono text-[11px]">{o.value}</TableCell>
                        <TableCell className="py-1.5 text-[12px]">{o.label}</TableCell>
                      </TableRow>
                    ))}
                    {!(g.options || []).length ? (
                      <TableRow><TableCell colSpan={2} className="py-2 text-[12px] text-muted-foreground">
                        Belum ada nilai — daftar tumbuh otomatis dari data yang dipakai.
                      </TableCell></TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
