import React, { useCallback, useEffect, useState } from "react";
import { Plus, ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import MetricCard from "@/components/patterns/MetricCard";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import ProjectSelect from "@/components/construction/ProjectSelect";
import AddPODialog from "@/components/procurement/AddPODialog";
import PODetailSheet from "@/components/procurement/PODetailSheet";
import { useAuth } from "@/context/AuthContext";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PROCUREMENT } from "@/constants/testIds";
import RefLabel from "@/components/patterns/RefLabel";
import ReferenceItems from "@/components/patterns/ReferenceItems";


export default function POPanel() {
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  const canCreate = can("procurement", "create");
  const [projectId, setProjectId] = useState(null);
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [selectedId, setSelectedId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/procurement/pos", { params: {
        project_id: projectId || undefined, status: status === "all" ? undefined : status } });
      setData(r.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat Purchase Order."); }
    finally { setLoading(false); }
  }, [projectId, status]);
  useEffect(() => { load(); }, [load]);

  const s = data?.summary;
  return (
    <div className="space-y-4">
      {s ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Total PO" value={s.total} tone="primary" />
          <MetricCard label="Menunggu/Approve" value={s.approved} tone="amber" />
          <MetricCard label="Diterima" value={s.received} tone="emerald" />
          <MetricCard label="Nilai PO" value={s.value} tone="indigo" format="idr" />
        </div>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <ProjectSelect value={projectId} onChange={setProjectId} testId={PROCUREMENT.poProjectSelect} />
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua Status</SelectItem>
              <ReferenceItems group="po_status" />
            </SelectContent>
          </Select>
        </div>
        {canCreate ? (
          <Button data-testid={PROCUREMENT.poAddBtn} size="sm" onClick={() => setAddOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> Buat PO
          </Button>
        ) : null}
      </div>
      {loading ? <LoadingCards count={4} /> : error ? <ErrorState message={error} onRetry={load} /> :
        !data?.data?.length ? (
          <EmptyState icon={ShoppingCart} title="Belum ada Purchase Order"
            description="Buat PO untuk material atau subkontraktor, lalu terima barang (GRN) & tagih dengan 3-way match."
            actionLabel={canCreate ? "Buat PO" : undefined} onAction={() => setAddOpen(true)} />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>No. PO</TableHead><TableHead>Jenis</TableHead><TableHead>Vendor</TableHead>
                <TableHead className="text-right">Nilai</TableHead><TableHead className="text-right">Diterima</TableHead>
                <TableHead>Status</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.data.map((p) => (
                  <TableRow key={p.id} data-testid={PROCUREMENT.poRow} className="cursor-pointer" onClick={() => setSelectedId(p.id)}>
                    <TableCell className="font-medium">{p.po_number}{p.high_value ? <span className="ml-1 text-[10px] font-semibold text-rose-600">Nilai Tinggi</span> : null}</TableCell>
                    <TableCell className="text-sm"><RefLabel group="po_type" value={p.po_type} /></TableCell>
                    <TableCell className="text-sm">{p.vendor}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatIDR(p.total)}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{formatIDR(p.received_value)}</TableCell>
                    <TableCell><StatusPill status={p.status} group="po_status" /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      <AddPODialog open={addOpen} onOpenChange={setAddOpen} onDone={load} defaultProjectId={projectId} />
      <PODetailSheet poId={selectedId} open={!!selectedId}
        onOpenChange={(v) => !v && setSelectedId(null)} onChanged={load} />
    </div>
  );
}
