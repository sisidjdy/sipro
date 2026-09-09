import React, { useCallback, useEffect, useState } from "react";
import { HardHat, Plus, SquarePen } from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import WorkerDialog from "@/components/labor/WorkerDialog";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { LABOR } from "@/constants/testIds";

/**
 * LaborWorkersPanel — master tenaga kerja harian per proyek (mandor, tukang, laden, …).
 *
 * Papan absensi tidak mungkin ada tanpa daftar ORANG beserta tarifnya; panel ini menjadi
 * sumber tunggal keduanya sehingga upah bisa direkonstruksi per orang per hari.
 */
export default function LaborWorkersPanel({ projectId, onChanged }) {
  const { can } = useAuth();
  // Router memaksakan `labor:create` untuk mendaftarkan orang dan `labor:update` untuk
  // mengubah tarif/status — layar memakai izin efektif yang sama supaya tidak ada tombol
  // mati maupun tombol yang hilang dari peran yang berhak.
  const canCreate = can("labor", "create");
  const canUpdate = can("labor", "update");
  const [rows, setRows] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/labor/workers",
        { params: projectId ? { project_id: projectId } : {} });
      setRows(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat daftar tenaga kerja.");
    } finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const done = () => { load(); onChanged?.(); };

  return (
    <div data-testid={LABOR.workersPanel} className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-heading text-lg font-semibold">Tenaga kerja harian</h3>
          <p className="text-sm text-muted-foreground">
            Daftar orang beserta tarif harian — dasar hitung upah dan lembur.
          </p>
        </div>
        {canCreate ? (
          <Button data-testid={LABOR.workerAddBtn}
            onClick={() => { setEditing(null); setDialogOpen(true); }}>
            <Plus className="mr-1.5 h-4 w-4" /> Tambah orang
          </Button>
        ) : null}
      </div>

      {loading ? <LoadingCards count={2} /> : null}
      {error ? <ErrorState message={error} onRetry={load} /> : null}

      {!loading && !error && !(rows || []).length ? (
        <EmptyState icon={HardHat} title="Belum ada tenaga kerja terdaftar"
          description="Tambahkan mandor/tukang/laden beserta tarif hariannya supaya absensi harian dan rekap upah punya dasar hitung yang bisa dijelaskan."
          actionLabel={canCreate ? "Tambah orang" : ""}
          onAction={canCreate ? () => { setEditing(null); setDialogOpen(true); } : null} />
      ) : null}

      {!loading && !error && (rows || []).length ? (
        <div className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead className="bg-secondary/60 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Nama</th>
                <th className="px-3 py-2 text-left">Peran</th>
                <th className="px-3 py-2 text-right">Upah harian</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((w) => (
                <tr key={w.id}>
                  <td className="px-3 py-2">
                    <p className="font-medium">{w.name}</p>
                    {w.phone ? (
                      <p className="text-xs text-muted-foreground">{w.phone}</p>
                    ) : null}
                  </td>
                  <td className="px-3 py-2">{w.role_label || w.role}</td>
                  <td className="px-3 py-2 text-right"><MoneyText value={w.daily_wage} /></td>
                  <td className="px-3 py-2">
                    <StatusPill status={w.is_active === false ? "inactive" : "active"}
                      label={w.is_active === false ? "Tidak aktif" : "Aktif"} />
                  </td>
                  <td className="px-3 py-2 text-right">
                    {canUpdate ? (
                      <Button size="sm" variant="outline" aria-label={`Ubah data ${w.name}`}
                        onClick={() => { setEditing(w); setDialogOpen(true); }}>
                        <SquarePen className="h-3.5 w-3.5" />
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <WorkerDialog open={dialogOpen} onOpenChange={setDialogOpen} worker={editing}
        projectId={projectId} onDone={done} />
    </div>
  );
}
