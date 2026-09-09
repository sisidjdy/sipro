import React, { useCallback, useEffect, useState } from "react";
import { Plus, ClipboardList } from "lucide-react";
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
import AddSPKDialog from "@/components/subcon/AddSPKDialog";
import SpkFromRabDialog from "@/components/subcon/SpkFromRabDialog";
import SPKDetailSheet from "@/components/subcon/SPKDetailSheet";
import { useAuth } from "@/context/AuthContext";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PROCUREMENT, P80 } from "@/constants/testIds";
import ReferenceItems from "@/components/patterns/ReferenceItems";


export default function SPKPanel() {
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  const canManage = can("subcon", "create");
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [rabOpen, setRabOpen] = useState(false);
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/subcon/spk", { params: { status: status === "all" ? undefined : status } });
      setData(r.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat SPK."); }
    finally { setLoading(false); }
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const s = data?.summary;
  return (
    <div className="space-y-4">
      {s ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Total SPK" value={s.total} tone="primary" />
          <MetricCard label="Aktif" value={s.active} tone="emerald" />
          <MetricCard label="Selesai" value={s.completed} tone="indigo" />
          <MetricCard label="Nilai Kontrak" value={s.contract_value} tone="amber" format="idr" />
        </div>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua Status</SelectItem>
            <ReferenceItems group="spk_status" />
          </SelectContent>
        </Select>
        {canManage ? (
          <>
            <Button data-testid={P80.spkFromRabBtn} size="sm" variant="outline" onClick={() => setAddOpen(true)}
              title="SPK tanpa unit (fasum/umum) dengan nilai bebas">
              <Plus className="mr-1.5 h-4 w-4" /> SPK bebas (tanpa unit)
            </Button>
            <Button data-testid={PROCUREMENT.spkAddBtn} size="sm" onClick={() => setRabOpen(true)}>
              <Plus className="mr-1.5 h-4 w-4" /> Buat SPK
            </Button>
          </>
        ) : null}
      </div>
      {loading ? <LoadingCards count={4} /> : error ? <ErrorState message={error} onRetry={load} /> :
        !data?.data?.length ? (
          <EmptyState icon={ClipboardList} title="Belum ada SPK"
            description="Buat Surat Perintah Kerja untuk mengikat subkontraktor ke proyek."
            actionLabel={canManage ? "Buat SPK" : undefined} onAction={() => setRabOpen(true)} />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>No. SPK</TableHead><TableHead>Subkontraktor</TableHead><TableHead>Pekerjaan</TableHead>
                <TableHead className="text-right">Nilai</TableHead><TableHead>Progres</TableHead><TableHead>Status</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.data.map((s2) => (
                  <TableRow key={s2.id} data-testid={PROCUREMENT.spkRow} className="cursor-pointer" onClick={() => setSelected(s2)}>
                    <TableCell className="font-medium">{s2.spk_number}</TableCell>
                    <TableCell className="text-sm">{s2.subcontractor_name}</TableCell>
                    <TableCell className="text-sm">{s2.title}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatIDR(s2.contract_value)}</TableCell>
                    <TableCell className="tabular-nums text-sm">{s2.progress_pct}%</TableCell>
                    <TableCell><StatusPill status={s2.status} group="spk_status" /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      <AddSPKDialog open={addOpen} onOpenChange={setAddOpen} onDone={load} />
      <SpkFromRabDialog open={rabOpen} onOpenChange={setRabOpen} onDone={load} />
      <SPKDetailSheet spk={selected} open={!!selected} canManage={canManage}
        onOpenChange={(v) => !v && setSelected(null)} onChanged={load} />
    </div>
  );
}
