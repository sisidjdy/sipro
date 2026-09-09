import React, { useCallback, useEffect, useState } from "react";
import { ClipboardCheck, FileBarChart2, Plus, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import EmptyState from "@/components/patterns/EmptyState";
import StatusPill from "@/components/patterns/StatusPill";
import AddPunchDialog from "@/components/field/AddPunchDialog";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { shortDate } from "@/utils/buildUi";
import { UNIT_BUILD } from "@/constants/testIds";

/**
 * MUTU & TEMUAN SATU UNIT (Fase 46, dok 29 §3) — inspeksi QC + punch list rumah ini saja.
 *
 * Sebelumnya QC & punch hanya bisa dilihat per PROYEK, jadi pertanyaan "rumah ini mutunya
 * bagaimana" harus dijawab dengan mata: menyaring daftar panjang lintas unit. Panel ini
 * memakai filter `unit_id` yang ditambahkan Fase 46 pada `/inspections` & `/field/punchlist`.
 */
export default function UnitQualityPanel({ unitId, projectId, unitCode, onChanged }) {
  const { can } = useAuth();
  const canCreate = can("construction", "create");
  const [inspections, setInspections] = useState([]);
  const [punch, setPunch] = useState([]);
  const [weekly, setWeekly] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addPunch, setAddPunch] = useState(false);

  const load = useCallback(async () => {
    if (!unitId) return;
    setLoading(true);
    try {
      const [ins, pun, wk] = await Promise.all([
        api.get("/inspections", { params: { unit_id: unitId } }).catch(() => null),
        api.get("/field/punchlist", { params: { unit_id: unitId } }).catch(() => null),
        projectId
          ? api.get("/build/reports/weekly", { params: { project_id: projectId, limit: 3 } })
            .catch(() => null)
          : Promise.resolve(null),
      ]);
      setInspections(ins?.data?.data || []);
      setPunch(pun?.data?.data || []);
      setWeekly(wk?.data?.data || []);
    } finally { setLoading(false); }
  }, [unitId, projectId]);

  useEffect(() => { load(); }, [load]);

  const after = () => { load(); onChanged?.(); };

  return (
    <div data-testid={UNIT_BUILD.quality} className="space-y-4">
      <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-1.5 font-heading text-base font-semibold">
            <ClipboardCheck className="h-4 w-4 text-primary" /> Inspeksi mutu (QC) unit ini
          </h3>
        </div>
        {loading ? (
          <p className="text-sm text-muted-foreground">Memuat…</p>
        ) : !inspections.length ? (
          <p data-testid={UNIT_BUILD.qualityEmpty} className="text-sm text-muted-foreground">
            Belum ada inspeksi yang terikat unit ini. Inspeksi kawasan/proyek tetap ada di tab
            “Mutu &amp; Inspeksi” pada hub Pembangunan.
          </p>
        ) : (
          <ul className="space-y-2">
            {inspections.map((i) => (
              <li key={i.id} data-testid={UNIT_BUILD.inspectionRow}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-secondary p-2.5 text-sm">
                <div>
                  <p className="font-medium">{i.title || i.inspection_number}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {i.inspection_number} · {i.items_pass || 0} lulus / {i.items_fail || 0} gagal
                    {" "}dari {i.items_total || (i.items || []).length} butir
                  </p>
                </div>
                <StatusPill status={i.status} group="inspection_status" />
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-1.5 font-heading text-base font-semibold">
            <Wrench className="h-4 w-4 text-primary" /> Temuan / punch list unit ini
          </h3>
          {canCreate ? (
            <Button size="sm" variant="secondary" data-testid="unit-punch-add"
              onClick={() => setAddPunch(true)}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Catat temuan
            </Button>
          ) : null}
        </div>
        {loading ? (
          <p className="text-sm text-muted-foreground">Memuat…</p>
        ) : !punch.length ? (
          <p className="text-sm text-muted-foreground">
            Belum ada temuan pada unit ini.
          </p>
        ) : (
          <ul className="space-y-2">
            {punch.map((p) => (
              <li key={p.id} data-testid={UNIT_BUILD.punchRow}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-secondary p-2.5 text-sm">
                <div>
                  <p className="font-medium">{p.title}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {p.location || "-"} · PIC {p.assigned_to || "belum ditunjuk"}
                    {p.due_date ? ` · tenggat ${shortDate(p.due_date)}` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusPill status={p.severity} group="punch_severity" />
                  <StatusPill status={p.status} group="punch_status" />
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div data-testid={UNIT_BUILD.weekly} className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
        <h3 className="mb-2 flex items-center gap-1.5 font-heading text-base font-semibold">
          <FileBarChart2 className="h-4 w-4 text-primary" /> Rapor mingguan proyek terbaru
        </h3>
        {!weekly.length ? (
          <p className="text-sm text-muted-foreground">
            Belum ada rapor mingguan. Rapor dibuat otomatis setiap Senin dari pekerjaan yang
            benar-benar terverifikasi — bukan diisi tangan.
          </p>
        ) : (
          <ul className="space-y-1.5 text-sm">
            {weekly.map((w) => (
              <li key={w.id} data-testid={UNIT_BUILD.weeklyRow}
                className="flex items-center justify-between border-b py-1 last:border-0">
                <span>Minggu {w.week_key}</span>
                <span className="text-xs text-muted-foreground">
                  progres {w.progress_avg ?? "belum ada data"}
                  {w.progress_avg !== null && w.progress_avg !== undefined ? "%" : ""} ·{" "}
                  {w.late_units ?? 0} unit telat
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <AddPunchDialog open={addPunch} onOpenChange={setAddPunch} projectId={projectId}
        unitId={unitId} units={unitId ? [{ id: unitId, code: unitCode }] : []}
        onDone={after} />
    </div>
  );
}
