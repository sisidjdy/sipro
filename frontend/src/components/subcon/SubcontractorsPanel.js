import React, { useCallback, useEffect, useState } from "react";
import { Plus, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import AddSubcontractorDialog from "@/components/subcon/AddSubcontractorDialog";
import SubcontractorDetailSheet from "@/components/subcon/SubcontractorDetailSheet";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { PROCUREMENT } from "@/constants/testIds";
import SearchInput from "@/components/patterns/SearchInput";


export default function SubcontractorsPanel() {
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  const canManage = can("subcon", "create");
  const [data, setData] = useState(null);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/subcon/subcontractors", { params: { q: q || undefined } });
      setData(r.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat subkontraktor."); }
    finally { setLoading(false); }
  }, [q]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SearchInput value={q} onChange={setQ} testId="subcon-search"
          placeholder="Cari nama / kode / bidang…"
          className="w-full sm:w-72" />
        {canManage ? (
          <Button data-testid={PROCUREMENT.subAddBtn} size="sm" onClick={() => setAddOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> Tambah Subkontraktor
          </Button>
        ) : null}
      </div>
      {loading ? <LoadingCards count={4} /> : error ? <ErrorState message={error} onRetry={load} /> :
        !data?.data?.length ? (
          <EmptyState icon={Wrench} title="Belum ada subkontraktor"
            description="Daftarkan subkontraktor untuk membuat SPK dan Purchase Order."
            actionLabel={canManage ? "Tambah Subkontraktor" : undefined} onAction={() => setAddOpen(true)} />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Kode</TableHead><TableHead>Nama</TableHead><TableHead>Bidang</TableHead>
                <TableHead>Kontak</TableHead><TableHead>SPK Aktif</TableHead><TableHead>Status</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.data.map((s) => (
                  <TableRow key={s.id} data-testid={PROCUREMENT.subRow} className="cursor-pointer" onClick={() => setSelected(s)}>
                    <TableCell className="font-medium">{s.code}</TableCell>
                    <TableCell>{s.name}</TableCell>
                    <TableCell className="text-sm">{s.specialty || "-"}</TableCell>
                    <TableCell className="text-sm">{s.pic_name || s.phone || "-"}</TableCell>
                    <TableCell className="tabular-nums">{s.active_spk}</TableCell>
                    <TableCell><StatusPill status={s.is_active ? "active" : "closed"} label={s.is_active ? "Aktif" : "Nonaktif"} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      <AddSubcontractorDialog open={addOpen} onOpenChange={setAddOpen} onDone={load} />
      <SubcontractorDetailSheet sub={selected} open={!!selected} canManage={canManage}
        onOpenChange={(v) => !v && setSelected(null)} onChanged={load} />
    </div>
  );
}
