import React, { useCallback, useEffect, useState } from "react";
import { Plus, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import PrintDocButton from "@/components/patterns/PrintDocButton";
import MetricCard from "@/components/patterns/MetricCard";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import AddPunchDialog from "@/components/field/AddPunchDialog";
import PunchDetailSheet from "@/components/field/PunchDetailSheet";
import { useAuth } from "@/context/AuthContext";
import { dueLabel } from "@/utils/formatters";
import api from "@/services/apiClient";
import { FIELD, P62 } from "@/constants/testIds";
import { useReference } from "@/context/ReferenceContext";
import ReferenceItems from "@/components/patterns/ReferenceItems";


export default function PunchListPanel({ projectId }) {
  const { labelOf } = useReference();
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  const canManage = can("construction", "update");
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [selected, setSelected] = useState(null);
  const [units, setUnits] = useState([]);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/field/punchlist", { params: { project_id: projectId, status: status === "all" ? undefined : status } });
      setData(r.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat punch list."); }
    finally { setLoading(false); }
  }, [projectId, status]);
  useEffect(() => { load(); }, [load]);

  // Daftar kavling dipakai agar temuan bisa DITAUTKAN ke unit — syarat foto temuan
  // muncul di galeri kavling (Site Plan) dan portal pembeli.
  useEffect(() => {
    let alive = true;
    (async () => {
      if (!projectId) return;
      try {
        const r = await api.get(`/projects/${projectId}`);
        if (alive) setUnits(r.data?.data?.units || []);
      } catch { if (alive) setUnits([]); }
    })();
    return () => { alive = false; };
  }, [projectId]);

  const unitCode = (id) => units.find((u) => u.id === id)?.code || "—";

  const s = data?.summary;
  return (
    <div data-testid={FIELD.punchPanel} className="space-y-4">
      {s ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Total" value={s.total} tone="primary" />
          <MetricCard label="Belum Selesai" value={s.open} tone="amber" />
          <MetricCard label="Diverifikasi" value={s.verified} tone="indigo" />
          <MetricCard label="Prioritas Tinggi" value={s.high} tone="rose" />
        </div>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua Status</SelectItem>
            <ReferenceItems group="punch_status" />
          </SelectContent>
        </Select>
        {canManage ? (
          <Button data-testid={FIELD.punchAddBtn} size="sm" onClick={() => setAddOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> Tambah Punch
          </Button>
        ) : null}
        <PrintDocButton
          url={`/field/punchlist/pdf?${new URLSearchParams({
            ...(projectId ? { project_id: projectId } : {}),
            ...(status !== "all" ? { status } : {}),
          }).toString()}`}
          testId={P62.punchPdfBtn} filename="berita-acara-punch-list"
          label="Cetak berita acara" />
      </div>
      {loading ? <LoadingCards count={4} /> : error ? <ErrorState message={error} onRetry={load} /> :
        !data?.data?.length ? (
          <EmptyState icon={AlertTriangle} title="Belum ada item punch"
            description="Catat cacat/temuan yang perlu diperbaiki sebelum serah terima."
            actionLabel={canManage ? "Tambah Punch" : undefined} onAction={() => setAddOpen(true)} />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Temuan</TableHead><TableHead>Kavling</TableHead>
                <TableHead>Lokasi</TableHead><TableHead>Kategori</TableHead>
                <TableHead>Prioritas</TableHead><TableHead>Status</TableHead><TableHead>Tenggat</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.data.map((p) => {
                  const sla = dueLabel(p.due_date);
                  const photoCount = (p.photos?.length || 0) + (p.fix_photos?.length || 0);
                  return (
                    <TableRow key={p.id} data-testid={FIELD.punchRow} className="cursor-pointer" onClick={() => setSelected(p)}>
                      <TableCell className="font-medium">
                        {p.title}
                        {photoCount ? (
                          <span className="ml-1.5 rounded bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                            {photoCount} foto
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-sm">{unitCode(p.unit_id)}</TableCell>
                      <TableCell className="text-sm">{p.location || "-"}</TableCell>
                      <TableCell className="text-sm">{labelOf("work_category", p.category)}</TableCell>
                      <TableCell><StatusPill status={p.severity} group="punch_severity" /></TableCell>
                      <TableCell><StatusPill status={p.status} group="punch_status" /></TableCell>
                      <TableCell className="text-xs text-muted-foreground">{p.status === "closed" ? "—" : (p.due_date ? sla.text : "-")}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      <AddPunchDialog projectId={projectId} units={units} open={addOpen}
        onOpenChange={setAddOpen} onDone={load} />
      <PunchDetailSheet punch={selected} open={!!selected} canManage={canManage}
        onOpenChange={(v) => !v && setSelected(null)} onChanged={load} />
    </div>
  );
}
