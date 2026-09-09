import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Stamp, Plus, AlertTriangle, BellRing } from "lucide-react";
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
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import AddPermitDialog from "@/components/permits/AddPermitDialog";
import PermitDetailSheet from "@/components/permits/PermitDetailSheet";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import { formatDateWIB } from "@/utils/formatters";
import { expiryText, HEALTH_TONE } from "@/utils/permitUi";
import api from "@/services/apiClient";
import { PERMITS, PERMIT_COVERAGE } from "@/constants/testIds";


export default function PermitsPage() {
  const { can } = useAuth();
  // Label kesehatan izin diambil dari SSOT `/api/reference` supaya kartu ringkasan,
  // pill tabel, dan filter tidak pernah menyebut hal yang sama dengan kata berbeda.
  const { labelOf } = useReference();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  // Dua izin BERBEDA yang dulu digabung jadi satu `canManage`: MENDAFTARKAN izin baru
  // (`permits:create`, hanya Manajer Proyek) dan MENGUBAH STATUS izin
  // (`permits:update`, Pelaksana Lapangan juga berhak).
  const canCreate = can("permits", "create");
  const canUpdate = can("permits", "update");
  const [data, setData] = useState(null);
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("all");
  const [health, setHealth] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/permits", { params: {
        project_id: projectId === "all" ? undefined : projectId,
        health: health === "all" ? undefined : health,
      } });
      setData(res.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat perizinan."); }
    finally { setLoading(false); }
  }, [projectId, health]);

  useEffect(() => {
    (async () => {
      try { const r = await api.get("/projects"); setProjects(r.data.data || []); }
      catch { /* ignore */ }
    })();
  }, []);
  useEffect(() => { load(); }, [load]);

  const scan = async () => {
    setBusy(true);
    try {
      const r = await api.post("/permits/alerts/scan");
      toast.success(r.data?.message || "Pemeriksaan masa berlaku dijalankan.");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menjalankan pemeriksaan.");
    } finally { setBusy(false); }
  };

  const s = data?.summary;
  return (
    <div data-testid={PERMITS.page} className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Stamp className="h-5 w-5 text-primary" />
          <div>
            <h1 className="page-title">Perizinan &amp; Dokumen</h1>
            <p className="text-xs text-muted-foreground">
              Izin menempel pada objek (proyek → cluster → blok → unit). Izin unit juga
              tampil di Unit 360 → tab Dokumen &amp; Izin.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {canUpdate ? (
            <Button variant="outline" size="sm" data-testid={PERMIT_COVERAGE.scanBtn}
              onClick={scan} disabled={busy}>
              <BellRing className="mr-1.5 h-4 w-4" /> Periksa masa berlaku
            </Button>
          ) : null}
          {canCreate ? (
            <Button data-testid={PERMITS.addBtn} size="sm" onClick={() => setAddOpen(true)}>
              <Plus className="mr-1.5 h-4 w-4" /> Tambah Izin
            </Button>
          ) : null}
        </div>
      </div>

      {s ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <MetricCard label="Total Izin" value={s.total} tone="primary" />
          <MetricCard label="Disetujui" value={s.approved} tone="emerald" />
          <MetricCard label="Dalam Proses" value={s.in_progress} tone="indigo" />
          <MetricCard label="Tenggat terlambat" value={s.overdue} tone="rose" />
          <MetricCard label={labelOf("permit_health", "expiring")} value={s.expiring}
            tone="amber"
            hint={`${s.expired} ${labelOf("permit_health", "expired").toLowerCase()}`} />
          <MetricCard label="Masa berlaku belum dicatat" value={s.no_expiry_data}
            tone="slate" hint="bukan berarti aman" />
        </div>
      ) : null}

      <div className="flex flex-wrap gap-3">
        <div className="w-full max-w-xs">
          <Select value={projectId} onValueChange={setProjectId}>
            <SelectTrigger data-testid={PERMITS.projectSelect}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua Proyek</SelectItem>
              {projects.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.name} ({p.code})</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-full max-w-xs">
          {/* Label kesehatan izin dibaca dari SSOT `/api/reference` — bukan diketik ulang di
              layar (kamus label ganda selalu berakhir berbeda dengan backend). */}
          <ReferenceSelect group="permit_health" value={health === "all" ? "" : health}
            onChange={(v) => setHealth(v || "all")} testId="permits-health-filter"
            placeholder="Semua kesehatan izin" allowEmpty
            emptyLabel="Semua kesehatan izin" />
        </div>
      </div>

      {loading ? <LoadingCards count={5} />
        : error ? <ErrorState message={error} onRetry={load} />
          : !data?.data?.length ? (
            <EmptyState icon={Stamp} title="Belum ada perizinan"
              description="Catat izin (KRK/IMB/PBG/SLF) beserta objek yang dilekatinya, tenggat, dan masa berlakunya."
              actionLabel={canCreate ? "Tambah Izin" : undefined}
              onAction={() => setAddOpen(true)} />
          ) : (
            <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Jenis</TableHead>
                  <TableHead>Cakupan</TableHead>
                  <TableHead>Proyek</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Masa berlaku</TableHead>
                  <TableHead>Tenggat</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {data.data.map((p) => (
                    <TableRow key={p.id} data-testid={PERMITS.row} data-health={p.health}
                      className="cursor-pointer" onClick={() => setSelected(p)}>
                      <TableCell>
                        <p className="font-medium">{p.type}</p>
                        <p className="text-xs text-muted-foreground">
                          {p.name}{p.reference_no ? ` · ${p.reference_no}` : ""}
                        </p>
                      </TableCell>
                      <TableCell className="text-sm">
                        {p.scope_type_label}
                        {p.scope_object ? (
                          <span className="block text-xs text-muted-foreground">
                            {p.scope_object}
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-sm">{p.project_name}</TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          <StatusPill status={p.status} group="permit_status" />
                          <StatusPill status={p.health} group="permit_health"
                            tone={HEALTH_TONE[p.health]} />
                        </div>
                      </TableCell>
                      <TableCell className="text-xs">
                        {p.expiry_known ? expiryText(p)
                          : <span className="italic text-muted-foreground">
                            masa berlaku belum dicatat</span>}
                      </TableCell>
                      <TableCell>
                        {p.overdue ? (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-rose-600">
                            <AlertTriangle className="h-3.5 w-3.5" />{" "}
                            {formatDateWIB(p.deadline)}
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            {p.deadline ? formatDateWIB(p.deadline) : "-"}
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

      <AddPermitDialog open={addOpen} onOpenChange={setAddOpen} projects={projects}
        onDone={load} />
      <PermitDetailSheet permit={selected} open={!!selected} canManage={canUpdate}
        onOpenChange={(v) => !v && setSelected(null)} onChanged={load} />
    </div>
  );
}
