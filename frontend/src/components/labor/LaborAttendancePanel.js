import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { CalendarCheck, ClipboardList, Save, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import MoneyText from "@/components/patterns/MoneyText";
import EmptyState from "@/components/patterns/EmptyState";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import * as sync from "@/services/offlineSync";
import OfflineQueuePanel from "@/components/construction/OfflineQueuePanel";
import { useOffline } from "@/context/OfflineContext";
import { LABOR } from "@/constants/testIds";

const today = () => new Date().toISOString().slice(0, 10);

/** Sidik jari isi absensi (status + lembur) untuk membedakan "sudah tersimpan" vs "berubah". */
const snapOf = (map) => JSON.stringify(
  Object.entries(map || {})
    .filter(([, e]) => e?.status)
    .map(([id, e]) => [id, e.status, Number(e.overtime_hours) || 0])
    .sort((a, b) => String(a[0]).localeCompare(String(b[0]))),
);

/**
 * LaborAttendancePanel (Fase 47D) — absensi harian mandor: satu layar, satu hari, satu kirim.
 *
 * Yang dijaga:
 *   * **Upah bisa dijelaskan.** Setiap baris menampilkan rumusnya (hari × tarif + lembur),
 *     jadi tukang bisa diberi penjelasan angka, bukan sekadar total.
 *   * **Tidak ada absensi dobel.** Mengirim ulang hari yang sama MEMPERBARUI baris yang ada
 *     (berjejak), tidak melahirkan baris kembar — dijaga index unik di database.
 *   * **Selisih dengan buku harian DILAPORKAN.** Bila jumlah hadir berbeda dengan
 *     `workforce` buku harian, keduanya ditampilkan apa adanya untuk diperbaiki manusia
 *     — sistem tidak menimpa salah satunya.
 */
export default function LaborAttendancePanel({ projectId, onChanged }) {
  const offline = useOffline();
  const { can } = useAuth();
  // Mencatat absensi dipaksakan router dengan `labor:create`; peran yang hanya boleh MELIHAT
  // (mis. manajer sales) tidak diberi tombol simpan yang selalu 403.
  const canRecord = can("labor", "create");
  const [workDate, setWorkDate] = useState(today());
  const [workers, setWorkers] = useState([]);
  const [entries, setEntries] = useState({});
  const [summary, setSummary] = useState(null);
  const [savedSnap, setSavedSnap] = useState("{}");
  const [diary, setDiary] = useState(null);
  const [rates, setRates] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const [w, a, r, d] = await Promise.all([
        api.get("/labor/workers", { params: { project_id: projectId, active: true } }),
        api.get("/labor/attendance", { params: { project_id: projectId, work_date: workDate } }),
        api.get("/labor/rates"),
        api.get("/labor/attendance/diary-check",
          { params: { project_id: projectId, work_date: workDate } })
          .catch(() => ({ data: { data: null } })),
      ]);
      const list = w.data.data || [];
      setWorkers(list);
      setRates(r.data.data);
      setSummary(a.data.summary);
      setDiary(d.data.data);
      const saved = {};
      (a.data.data || []).forEach((row) => {
        saved[row.worker_id] = {
          status: row.status, overtime_hours: row.overtime_hours || 0,
          total: row.total, formula: row.formula, existing: true,
        };
      });
      setEntries(saved);
      // Cap keadaan tersimpan supaya tombol simpan hanya hidup bila memang ADA perubahan
      // (dulu tombol tetap bisa ditekan sesudah menyimpan, dan baris "Akan disimpan" masih
      // menampilkan angka yang sama dengan yang sudah tersimpan — pemakai tidak bisa tahu
      // apakah kiriman tadi berhasil).
      setSavedSnap(snapOf(saved));
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat absensi.");
    } finally { setLoading(false); }
  }, [projectId, workDate]);

  useEffect(() => { load(); }, [load]);

  const set = (workerId, patch) => setEntries((prev) => ({
    ...prev, [workerId]: { ...(prev[workerId] || { overtime_hours: 0 }), ...patch },
  }));

  const preview = useMemo(() => {
    if (!rates) return { total: 0, present: 0 };
    let total = 0; let present = 0;
    workers.forEach((w) => {
      const e = entries[w.id];
      if (!e?.status) return;
      const factor = rates.day_factor?.[e.status] ?? 0;
      if (factor > 0) present += 1;
      const base = Math.round((w.daily_wage || 0) * factor);
      const hourly = rates.normal_hours ? (w.daily_wage || 0) / rates.normal_hours : 0;
      const ot = factor > 0
        ? Math.round((Number(e.overtime_hours) || 0) * hourly * rates.overtime_multiplier) : 0;
      total += base + ot;
    });
    return { total, present };
  }, [workers, entries, rates]);

  /** Ada perubahan yang belum dikirim? Menjadi dasar aktif/nonaktifnya tombol simpan. */
  const dirty = useMemo(() => snapOf(entries) !== savedSnap, [entries, savedSnap]);

  const save = async () => {
    const payload = Object.entries(entries)
      .filter(([, e]) => e?.status)
      .map(([worker_id, e]) => ({
        worker_id, status: e.status, overtime_hours: Number(e.overtime_hours) || 0,
      }));
    if (!payload.length) {
      toast.error("Isi kehadiran minimal satu orang sebelum menyimpan.");
      return;
    }
    setBusy(true);
    try {
      // Fase 50B: absensi diisi di lokasi yang sering tanpa sinyal. Bila jaringan mati,
      // kiriman MASUK ANTREAN perangkat (ber-`client_ref`) dan terkirim sendiri nanti —
      // tanpa risiko absensi ganda saat pengiriman diulang.
      const out = await sync.submitOrQueue({
        kind: "attendance_submit",
        payload: { project_id: projectId, work_date: workDate, entries: payload },
        title: `Absensi ${workDate} · ${payload.length} orang`,
      });
      if (out.queued) {
        toast.success(`Absensi ${workDate} tersimpan di perangkat (${payload.length} orang) — `
          + "terkirim sendiri begitu sinyal kembali.");
        await offline.refresh();
      } else {
        toast.success(out.res?.data?.message || "Absensi tersimpan.");
        await load();
        onChanged?.();
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan absensi.");
    } finally { setBusy(false); }
  };

  if (!projectId) return null;

  return (
    <div data-testid={LABOR.attendancePanel} className="space-y-3">
      <OfflineQueuePanel kinds={["attendance_submit"]} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="font-heading text-lg font-semibold">Absensi &amp; upah harian</h3>
          <p className="text-sm text-muted-foreground">
            Isi kehadiran hari ini; upah dihitung server dari tarif masing-masing orang.
          </p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="labor-date">Tanggal kerja</Label>
          <Input id="labor-date" type="date" data-testid={LABOR.dateInput} value={workDate}
            max={today()} className="w-44"
            onChange={(e) => setWorkDate(e.target.value)} />
        </div>
      </div>

      {loading ? <LoadingCards count={2} /> : null}
      {error ? <ErrorState message={error} onRetry={load} /> : null}

      {!loading && !error && !workers.length ? (
        <EmptyState icon={ClipboardList} title="Belum ada tenaga kerja aktif di proyek ini"
          description="Tambahkan orang di panel Tenaga Kerja di bawah, lalu absensi harian bisa diisi di sini." />
      ) : null}

      {!loading && !error && workers.length ? (
        <>
          {diary && diary.state === "mismatch" ? (
            <p data-testid={LABOR.diaryCheck}
              className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              <TriangleAlert className="mt-0.5 h-4 w-4" /> {diary.detail}
            </p>
          ) : null}
          {diary && diary.state === "missing_diary" ? (
            <p data-testid={LABOR.diaryCheck}
              className="rounded-md border bg-secondary/50 px-3 py-2 text-sm text-muted-foreground">
              {diary.detail}
            </p>
          ) : null}

          <div className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <table className="w-full text-sm">
              <thead className="bg-secondary/60 text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left">Nama / peran</th>
                  <th className="px-3 py-2 text-right">Tarif harian</th>
                  <th className="px-3 py-2 text-left">Kehadiran</th>
                  <th className="px-3 py-2 text-left">Lembur (jam)</th>
                  <th className="px-3 py-2 text-right">Upah hari ini</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {workers.map((w) => {
                  const e = entries[w.id] || {};
                  return (
                    <tr key={w.id} data-testid={LABOR.workerRow} data-worker={w.id}>
                      <td className="px-3 py-2">
                        <p className="font-medium">{w.name}</p>
                        <p className="text-xs text-muted-foreground">{w.role_label || w.role}</p>
                      </td>
                      <td className="px-3 py-2 text-right"><MoneyText value={w.daily_wage} /></td>
                      <td className="px-3 py-2">
                        <ReferenceSelect group="attendance_status" value={e.status || ""}
                          allowEmpty emptyLabel="— belum diisi —" testId={LABOR.statusSelect}
                          onChange={(v) => set(w.id, { status: v })} />
                      </td>
                      <td className="px-3 py-2">
                        <Input type="number" min="0" max="12" step="0.5"
                          data-testid={LABOR.overtimeInput} className="w-24"
                          aria-label={`Jam lembur ${w.name}`}
                          value={e.overtime_hours ?? 0}
                          onChange={(ev) => set(w.id, { overtime_hours: ev.target.value })} />
                      </td>
                      <td className="px-3 py-2 text-right">
                        {e.existing && e.total !== undefined ? (
                          <>
                            <MoneyText value={e.total} className="font-medium" />
                            <p className="text-[11px] text-muted-foreground">{e.formula}</p>
                          </>
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            {e.status ? "dihitung setelah disimpan" : "belum diisi"}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div data-testid={LABOR.summary}
            className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
            <div className="flex flex-wrap gap-4 text-sm">
              <span className="flex items-center gap-1.5">
                <CalendarCheck className="h-4 w-4 text-emerald-600" />
                Tersimpan: <b>{summary?.present ?? 0}</b> hadir ·{" "}
                <MoneyText value={summary?.wage_total} />
              </span>
              <span className="text-muted-foreground">
                {dirty
                  ? <>Akan disimpan: {preview.present} hadir · <MoneyText value={preview.total} /></>
                  : (summary?.present ? "Tidak ada perubahan yang belum disimpan."
                    : "Belum ada kehadiran yang diisi untuk tanggal ini.")}
              </span>
            </div>
            <Button data-testid={LABOR.saveBtn} disabled={busy || !canRecord || !dirty}
              onClick={save}
              title={!canRecord
                ? "Peran Anda hanya boleh melihat absensi — pencatatan dilakukan pelaksana/PM."
                : (!dirty ? "Belum ada perubahan untuk disimpan." : undefined)}>
              <Save className="mr-1.5 h-4 w-4" />
              {busy ? "Menyimpan…" : "Simpan absensi hari ini"}
            </Button>
          </div>
        </>
      ) : null}
    </div>
  );
}
