import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Home, MapPin } from "lucide-react";

import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import SvgPlanMap from "@/components/siteplan/SvgPlanMap";
import { SALES_COLORS } from "@/components/siteplan/planStyles";
import { formatIDR } from "@/utils/formatters";
import portalApi from "@/services/portalClient";
import { PORTAL } from "@/constants/testIds";

/**
 * PlanPanel (portal pembeli) — peta kavling: unit MILIK pembeli disorot, kavling lain
 * hanya kode + status. Harga, nama pembeli, dan data transaksi tetangga tidak pernah
 * dikirim ke portal (dibatasi di backend, bukan disembunyikan di UI).
 */
export default function PlanPanel() {
  const [rows, setRows] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pick, setPick] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await portalApi.get("/portal/site-plan");
      setRows(res.data?.data?.projects || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat peta kavling.");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const project = rows?.[0] || null;
  const unitsById = useMemo(
    () => Object.fromEntries((project?.units || []).map((u) => [u.id, u])), [project]);
  const mineList = (project?.units || []).filter((u) => u.mine);

  if (loading) return <LoadingCards count={2} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!project) {
    return (
      <p className="rounded-xl border bg-white p-6 text-center text-sm text-slate-500">
        Belum ada kavling terkait akun Anda.
      </p>
    );
  }

  return (
    <div data-testid={PORTAL.planPanel} className="space-y-4">
      <div className="rounded-xl border bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="section-title">{project.project_name}</p>
            <p className="flex items-center gap-1.5 text-xs text-slate-500">
              <MapPin className="h-3.5 w-3.5" /> {project.location || "Lokasi proyek"}
            </p>
          </div>
          <p className="text-xs text-slate-500">
            Kavling Anda: <span className="font-semibold text-slate-700">
              {(project.my_codes || []).join(", ") || "-"}</span>
          </p>
        </div>

        {mineList.map((u) => (
          <div key={u.id} data-testid={PORTAL.myUnitCard}
            className="mt-3 grid gap-2 rounded-lg border border-indigo-200 bg-indigo-50/60 p-3 sm:grid-cols-4">
            <div>
              <p className="text-[11px] uppercase text-slate-500">Kavling</p>
              <p className="flex items-center gap-1.5 font-semibold">
                <Home className="h-4 w-4 text-indigo-600" /> {u.code}
              </p>
            </div>
            <div>
              <p className="text-[11px] uppercase text-slate-500">Tipe & luas</p>
              <p className="text-sm">{u.type || "-"} · {u.luas_bangunan || 0}/{u.luas_tanah || 0} m²</p>
            </div>
            <div>
              <p className="text-[11px] uppercase text-slate-500">Harga</p>
              <p className="text-sm tabular-nums">{formatIDR(u.price)}</p>
            </div>
            <div>
              <p className="text-[11px] uppercase text-slate-500">Progres</p>
              <p className="text-sm tabular-nums">{u.construction_progress || 0}%</p>
            </div>
          </div>
        ))}
      </div>

      {project.plan?.shapes?.length ? (
        <div className="rounded-xl border bg-white p-3">
          <p className="mb-2 text-xs text-slate-500">
            Geser untuk berpindah, cubit dua jari (atau tombol +/−) untuk zoom. Ketuk kavling
            untuk melihat status.
          </p>
          <SvgPlanMap viewBox={project.plan.view_box} shapes={project.plan.shapes}
            unitsById={unitsById} mode="sales" height={420}
            emphasizeIds={mineList.map((u) => u.id)}
            selectedId={pick?.id} onSelect={(p) => setPick(p.unit)} />
          <p className="mt-2 text-[11px] text-slate-500">
            Kavling dengan garis putus-putus ungu adalah kavling Anda.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {["available", "reserved", "booked", "sold"].map((k) => (
              <span key={k} className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs">
                <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: SALES_COLORS[k].dot }} />
                <StatusPill status={k} />
              </span>
            ))}
          </div>
          {pick ? (
            <div className="mt-3 rounded-lg border bg-slate-50 p-3 text-sm">
              <p className="font-semibold">
                Kavling {pick.code} {pick.mine ? "· milik Anda" : ""}
              </p>
              <p className="mt-1 flex items-center gap-2 text-xs text-slate-600">
                Status: <StatusPill status={pick.status} />
                {pick.mine ? `· progres ${pick.construction_progress || 0}%` : "· data pemilik tidak ditampilkan"}
              </p>
            </div>
          ) : null}
        </div>
      ) : (
        <p className="rounded-xl border bg-white p-6 text-center text-sm text-slate-500">
          Peta kavling proyek ini belum disiapkan oleh tim developer.
        </p>
      )}
    </div>
  );
}
