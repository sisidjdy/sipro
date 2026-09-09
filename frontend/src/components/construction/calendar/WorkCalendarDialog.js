import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { CalendarOff, Info, Layers, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import WorkCalendarHolidays from "@/components/construction/calendar/WorkCalendarHolidays";
import api from "@/services/apiClient";
import { CAL } from "@/constants/testIds";

/**
 * PENGATURAN KALENDER KERJA (master data, Fase 36).
 *
 * Sebelum fase ini pola hari kerja & hari libur hanya ada sebagai angka 5/6/7 di dalam
 * dokumen TEMPLATE jadwal, dan daftar hari liburnya selalu kosong — akibatnya tenggat
 * pekerjaan bisa mendarat di 17 Agustus atau Idul Fitri dan tidak ada layar untuk
 * membetulkannya. Di sini admin/Manajer Proyek mengatur satu kali, lalu dipakai
 * kalender DAN mesin jadwal (jadwal baru & penggeseran tanggal).
 *
 * CAKUPAN DIBUAT EKSPLISIT (perbaikan setelah cacat nyata):
 * dialog ini dulu diam-diam menulis kalender KHUSUS PROYEK hanya karena halaman sedang
 * menampilkan satu proyek. Sekali tekan "Simpan", seluruh hari libur nasional hilang untuk
 * proyek itu (override dianggap pengganti utuh), tenggat 17 Agustus berhenti ditandai, dan
 * inspeksi QC bisa dijadwalkan pada Hari Kemerdekaan. Sekarang penggunanya MEMILIH sendiri
 * mau mengubah kalender organisasi atau kalender khusus proyek, dan hari libur organisasi
 * selalu diwarisi (pengecualian harus disengaja & bisa dibatalkan).
 *
 * Kejujuran yang dijaga: daftar libur bawaan ditandai sebagai PERKIRAAN yang wajib
 * disesuaikan dengan SKB pemerintah — aplikasi tidak berpura-pura itu keputusan resmi.
 */
export default function WorkCalendarDialog({
  open, onOpenChange, projectId, projectName, onSaved,
}) {
  const [scope, setScope] = useState("org");
  const [cal, setCal] = useState(null);
  const [defaults, setDefaults] = useState(null);
  const [overrides, setOverrides] = useState([]);
  const [pattern, setPattern] = useState({});
  const [items, setItems] = useState(3);
  const [critical, setCritical] = useState(2);
  const [form, setForm] = useState({ date: "", name: "", kind: "national" });
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const target = scope === "project" ? projectId : null;
  const params = useMemo(() => ({ project_id: target || undefined }), [target]);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/build/calendar/settings", { params });
      const data = r.data.data || {};
      setCal(data);
      setDefaults(r.data.defaults || null);
      setOverrides(r.data.overrides || []);
      setPattern(data.pattern || {});
      setItems(data.thresholds?.max_items_per_person_per_day ?? 3);
      setCritical(data.thresholds?.max_critical_per_day ?? 2);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat kalender kerja.");
    } finally { setLoading(false); }
  }, [params]);

  useEffect(() => { if (open) load(); }, [open, load]);
  useEffect(() => { if (!projectId) setScope("org"); }, [projectId]);

  const after = (r, fallback) => {
    setCal(r.data.data);
    toast.success(r.data.message || fallback);
    onSaved && onSaved();
  };

  const run = async (fn, fallback, failMsg) => {
    setBusy(true); setError("");
    try {
      after(await fn(), fallback);
    } catch (e) {
      setError(e?.response?.data?.detail || failMsg);
    } finally { setBusy(false); }
  };

  const savePattern = () => run(
    () => api.put("/build/calendar/settings", {
      pattern,
      thresholds: {
        max_items_per_person_per_day: Number(items) || 1,
        max_critical_per_day: Number(critical) || 1,
      },
      project_id: target || null,
    }),
    "Kalender kerja disimpan — jadwal baru & penggeseran akan mengikutinya.",
    "Gagal menyimpan kalender kerja.");

  const dropOverride = () => run(
    async () => {
      const r = await api.delete("/build/calendar/settings", { params: { project_id: projectId } });
      setScope("org");
      return r;
    },
    "Proyek ini kembali mengikuti kalender organisasi.",
    "Gagal menghapus kalender khusus proyek.");

  const addHoliday = () => {
    if (!form.date || form.name.trim().length < 3) {
      setError("Isi tanggal dan nama hari libur (minimal 3 karakter).");
      return;
    }
    return run(async () => {
      const r = await api.post("/build/calendar/holidays",
        { date: form.date, name: form.name.trim(), kind: form.kind }, { params });
      setForm({ date: "", name: "", kind: form.kind });
      return r;
    }, "Hari libur ditambahkan.", "Gagal menambah hari libur.");
  };

  const removeHoliday = (day, inherited) => run(
    () => api.delete(`/build/calendar/holidays/${day}`, { params }),
    inherited ? `${day} dikecualikan untuk proyek ini.` : `Hari libur ${day} dihapus.`,
    "Gagal menghapus hari libur.");

  const restoreHoliday = (day) => run(
    () => api.post(`/build/calendar/holidays/${day}/restore`, {}, { params }),
    `Proyek ini kembali mengikuti hari libur ${day}.`,
    "Gagal membatalkan pengecualian hari libur.");

  const weekdays = defaults?.weekdays || [];
  const projectOverride = overrides.find((o) => o.project_id === projectId);
  const label = projectName || "proyek ini";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={CAL.settings}
        className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Kalender kerja (hari kerja &amp; hari libur)</DialogTitle>
          <DialogDescription>
            Dipakai kalender jadwal DAN mesin jadwal: jadwal baru serta penggeseran tanggal
            tidak akan menaruh pekerjaan pada hari libur atau hari yang ditandai libur mingguan.
          </DialogDescription>
        </DialogHeader>

        {projectId ? (
          <div className="grid gap-1.5 rounded-lg border bg-secondary/40 p-2.5">
            <Label className="text-[11px] font-semibold">Yang sedang diubah</Label>
            <ReferenceSelect group="calendar_settings_scope" value={scope}
              onChange={(v) => setScope(v)} testId={CAL.settingsScope} />
            <p className="text-[11px] text-muted-foreground">
              {scope === "project"
                ? `Pola & ambang berlaku khusus ${label}. Hari libur organisasi tetap diwarisi
                   — bila proyek ini benar-benar bekerja pada tanggal libur, kecualikan tanggalnya
                   secara sengaja di daftar bawah.`
                : "Berlaku untuk SELURUH proyek yang belum punya kalender sendiri."}
            </p>
          </div>
        ) : null}

        {loading && !cal ? (
          <p className="text-sm text-muted-foreground">Memuat kalender kerja…</p>
        ) : null}

        {cal?.note ? (
          <p data-testid={CAL.settingsNote}
            className="inline-flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-[11px] text-amber-900">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {cal.note}
          </p>
        ) : null}

        {scope === "org" && projectOverride ? (
          <p className="inline-flex items-start gap-1.5 rounded-lg border border-sky-200 bg-sky-50 p-2.5 text-[11px] text-sky-900">
            <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {label} memakai kalender sendiri (diubah {projectOverride.updated_by || "-"}).
            Pola &amp; ambang yang Anda simpan di sini TIDAK mengubah proyek itu — hari libur
            tetap diwarisi. Pilih “Kalender khusus proyek ini” untuk mengubahnya.
          </p>
        ) : null}

        {cal ? (
          <div className="space-y-4">
            <div>
              <p className="text-xs font-semibold">Pola hari kerja per minggu</p>
              <p className="text-[11px] text-muted-foreground">
                “Setengah hari” tetap dihitung sebagai hari kerja oleh mesin jadwal (durasi
                template dinyatakan dalam hari kerja), tetapi ditandai di kalender agar
                perencana sadar kapasitas hari itu hanya separuh.
              </p>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {weekdays.map((w) => (
                  <div key={w.key} data-testid={CAL.patternRow} data-day={w.key}
                    className="flex items-center justify-between gap-2 rounded-lg border bg-card p-2 shadow-[var(--shadow-card)]">
                    <Label className="text-xs" htmlFor={`pattern-${w.key}`}>{w.label}</Label>
                    <div className="w-40">
                      <ReferenceSelect group="calendar_work_pattern"
                        value={pattern[w.key] || "full"}
                        onChange={(v) => setPattern((p) => ({ ...p, [w.key]: v }))}
                        testId={`${CAL.patternSelect}-${w.key}`} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <Label htmlFor="cal-th-items" className="text-xs">
                  Maksimal jumlah tenggat per pelaksana per hari
                </Label>
                <Input id="cal-th-items" type="number" min={1} max={50} value={items}
                  data-testid={CAL.thresholdItems}
                  onChange={(e) => setItems(e.target.value)} />
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  Lebih dari ini pada satu hari ditandai sebagai bentrok beban.
                </p>
              </div>
              <div>
                <Label htmlFor="cal-th-crit" className="text-xs">
                  Maksimal pekerjaan kritis / hold point per hari
                </Label>
                <Input id="cal-th-crit" type="number" min={1} max={50} value={critical}
                  data-testid={CAL.thresholdCritical}
                  onChange={(e) => setCritical(e.target.value)} />
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  Melindungi supervisor: hold point tidak bisa diperiksa berbarengan.
                </p>
              </div>
            </div>

            <WorkCalendarHolidays cal={cal} scope={scope} busy={busy} form={form}
              onForm={setForm} onAdd={addHoliday} onRemove={removeHoliday}
              onRestore={restoreHoliday} />

            {scope === "project" && cal.override_exists ? (
              <Button variant="outline" size="sm" disabled={busy}
                data-testid={CAL.overrideDrop} onClick={dropOverride}>
                <Layers className="mr-1.5 h-3.5 w-3.5" />
                Ikuti kalender organisasi lagi (hapus kalender khusus proyek)
              </Button>
            ) : null}

            {scope === "org" && overrides.length ? (
              <div data-testid={CAL.overrideList}
                className="space-y-1 rounded-lg border bg-background p-2">
                <p className="text-[11px] font-semibold">
                  Proyek dengan kalender sendiri ({overrides.length})
                </p>
                {overrides.map((o) => (
                  <p key={o.project_id} data-testid={CAL.overrideRow}
                    data-project={o.project_id} className="text-[11px] text-muted-foreground">
                    {o.project_name} — {o.extra_holidays} libur khusus,{" "}
                    {o.excluded_holidays} dikecualikan · diubah {o.updated_by || "-"}
                  </p>
                ))}
              </div>
            ) : null}

            <p className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <CalendarOff className="h-3.5 w-3.5" />
              Terakhir diubah: {cal.updated_by || "-"}
              {cal.updated_at ? ` · ${String(cal.updated_at).slice(0, 10)}` : ""}
            </p>
          </div>
        ) : null}

        {error ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 p-2 text-xs text-rose-800">
            {error}
          </p>
        ) : null}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Tutup</Button>
          <Button data-testid={CAL.settingsSave} disabled={busy || !cal} onClick={savePattern}>
            {busy ? "Menyimpan…" : "Simpan pola & ambang"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
