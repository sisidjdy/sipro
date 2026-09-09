import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ClipboardList, Inbox } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import EmptyState from "@/components/patterns/EmptyState";
import Pagination from "@/components/patterns/Pagination";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import UnitScheduleSheet from "@/components/construction/UnitScheduleSheet";
import { useAuth } from "@/context/AuthContext";
import { daysLate, ITEM_TONE, shortDate } from "@/utils/buildUi";
import { BUILD } from "@/constants/testIds";
import api from "@/services/apiClient";

/**
 * ANTREAN KERJA — daftar pekerjaan lintas unit dari sudut pandang PENGGUNA:
 * “yang harus saya kerjakan” untuk pelaksana, dan “yang harus saya verifikasi”
 * untuk supervisor. Papan monitoring melihat per rumah; antrean ini melihat per orang,
 * supaya tidak ada pekerjaan yang menganggur menunggu seseorang membuka jadwal unit.
 */
export default function BuildQueuePanel({ projectId }) {
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  // "Supervisor" di sini = yang boleh MEMVERIFIKASI hasil kerja (`construction:approve`),
  // karena itulah antrean bawaannya "verify" dan bukan "todo".
  const supervisor = can("construction", "approve");
  const [scope, setScope] = useState(supervisor ? "verify" : "todo");
  const [status, setStatus] = useState("");
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState({ skip: 0, limit: 10 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openUnit, setOpenUnit] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = {
        project_id: projectId || undefined, skip: page.skip, limit: page.limit,
      };
      if (scope === "todo" || scope === "mine") params.mine = true;
      if (scope === "todo") params.status = "todo";
      else if (scope === "verify") params.status = "submitted";
      else if (status) params.status = status;
      const r = await api.get("/build/items", { params });
      setRows(r.data.data || []);
      setTotal(r.data.total || 0);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat antrean kerja.");
    } finally { setLoading(false); }
  }, [projectId, scope, status, page.skip, page.limit]);

  useEffect(() => { load(); }, [load]);

  const changeScope = (v) => { setScope(v); setPage({ ...page, skip: 0 }); };

  return (
    <div data-testid={BUILD.queuePanel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card p-2.5 shadow-[var(--shadow-card)]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Tampilkan</span>
          <Select value={scope} onValueChange={changeScope}>
            <SelectTrigger data-testid={BUILD.queueScope} aria-label="Cakupan antrean kerja"
              className="h-9 w-52">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todo">Perlu saya kerjakan</SelectItem>
              <SelectItem value="mine">Semua pekerjaan saya</SelectItem>
              <SelectItem value="verify">Menunggu verifikasi</SelectItem>
              <SelectItem value="all">Semua pekerjaan</SelectItem>
            </SelectContent>
          </Select>
          {scope === "mine" || scope === "all" ? (
            <div className="w-44">
              <ReferenceSelect group="build_item_status" value={status}
                onChange={(v) => { setStatus(v); setPage({ ...page, skip: 0 }); }}
                allowEmpty emptyLabel="Semua status" testId={BUILD.queueStatus} />
            </div>
          ) : null}
        </div>
        <p className="text-xs text-muted-foreground">
          {total} pekerjaan · diurutkan dari tenggat paling dekat
        </p>
      </div>

      {loading ? <LoadingCards count={3} />
        : error ? <ErrorState message={error} onRetry={load} />
          : !rows.length ? (
            <div data-testid={BUILD.queueEmpty}>
              <EmptyState icon={Inbox}
                title={scope === "verify" ? "Tidak ada yang menunggu verifikasi"
                  : scope === "todo" ? "Tidak ada pekerjaan yang bisa Anda kerjakan sekarang"
                    : scope === "mine" ? "Tidak ada pekerjaan untuk Anda"
                      : "Belum ada pekerjaan pada filter ini"}
                description={scope === "verify"
                  ? "Semua hasil kerja yang diajukan sudah diperiksa."
                  : scope === "todo"
                    ? "Pekerjaan berikutnya masih terkunci gerbang mutu (menunggu verifikasi pendahulu atau waktu tunggu curing). Buka Monitoring Unit untuk melihat alasannya."
                    : "Pekerjaan muncul di sini begitu jadwal unit dibuat dan gerbang mutunya terbuka."} />
            </div>
          ) : (
            <div className="space-y-2">
              {rows.map((it) => {
                const late = it.status !== "done" ? daysLate(it.planned_finish) : 0;
                return (
                  <div key={it.id} data-testid={BUILD.queueRow} data-item={it.step_code}
                    className="flex flex-wrap items-start justify-between gap-2 rounded-xl border bg-card p-3 shadow-sm">
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium">
                        <span className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[11px] text-primary">
                          {it.unit_code}
                        </span>
                        {it.name}
                        {it.hold_point ? (
                          <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700">
                            HOLD POINT
                          </span>
                        ) : null}
                      </p>
                      <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
                        <span>Minggu {it.week} · {shortDate(it.planned_start)} →{" "}
                          {shortDate(it.planned_finish)}</span>
                        <span><RefLabel group="work_category" value={it.work_category} /></span>
                        {it.assigned_to ? <span>{it.assigned_to}</span> : null}
                        {it.submitted_by ? <span>diajukan {it.submitted_by}</span> : null}
                      </p>
                      {late ? (
                        <p className="mt-1 text-[11px] font-semibold text-rose-700">
                          Telat {late} hari{it.delay_cause ? "" : " — penyebab belum dijelaskan"}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex flex-col items-end gap-1.5">
                      <StatusPill status={it.status} group="build_item_status"
                        tone={ITEM_TONE[it.status] || "draft"} />
                      <Button size="sm" variant="outline"
                        aria-label={`Buka jadwal unit ${it.unit_code} untuk ${it.name}`}
                        data-testid={`${BUILD.queueRow}-open`} data-open={it.step_code}
                        onClick={() => setOpenUnit(it.unit_id)}>
                        <ClipboardList className="mr-1 h-3.5 w-3.5" /> Buka & kerjakan
                      </Button>
                    </div>
                  </div>
                );
              })}
              <div data-testid={BUILD.queuePagination}>
                <Pagination total={total} skip={page.skip} limit={page.limit}
                  label="pekerjaan" testId={`${BUILD.queuePagination}-control`}
                  onChange={setPage} />
              </div>
            </div>
          )}

      <UnitScheduleSheet unitId={openUnit} open={!!openUnit}
        onOpenChange={(v) => !v && setOpenUnit(null)} onChanged={load} />
    </div>
  );
}
