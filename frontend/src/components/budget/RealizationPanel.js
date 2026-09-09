import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, BellRing, CheckCircle2, Info, ListTree, Settings2 } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import MetricCard from "@/components/patterns/MetricCard";
import EmptyState from "@/components/patterns/EmptyState";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import RealizationDialog from "@/components/budget/RealizationDialog";
import {
  ExposureBar, HealthPill, MissingNote, Money, Pct, StateBadge, isNegative,
} from "@/components/budget/parts";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { BUDGET } from "@/constants/testIds";

const GROUPS = [
  { value: "item", label: "Per item RAB" },
  { value: "category", label: "Per kategori pekerjaan" },
  { value: "step", label: "Per langkah jadwal" },
  { value: "unit", label: "Per unit" },
];

/**
 * RealizationPanel — **LAPIS 1 & 2** realisasi anggaran + RAB vs realisasi + margin +
 * laporan “biaya belum terpetakan” (`docs/v2/32` §4–§5).
 *
 * Susunannya mengikuti cara owner memeriksa: mulai dari angka umum proyek (aman / waspada /
 * overbudget), turun ke kategori, lalu tembus ke dokumen sumber lewat tombol “Dokumen”.
 *
 * Yang membedakan panel ini dari dashboard biasa: **setiap keadaan tidak-lengkap ditulis**,
 * termasuk beban yang belum bisa dipetakan ke proyek dan pemakaian material yang sengaja tidak
 * dijumlahkan. Angka yang rapi tetapi tidak bisa dipertanggungjawabkan lebih berbahaya
 * daripada angka yang mengaku belum lengkap.
 */
export default function RealizationPanel({ projectId }) {
  const { can } = useAuth();
  const { labelOf } = useReference();
  const canScan = can("budget", "manage");

  const [summary, setSummary] = useState(null);
  const [margin, setMargin] = useState(null);
  const [unmapped, setUnmapped] = useState(null);
  const [rab, setRab] = useState(null);
  const [groupBy, setGroupBy] = useState("item");
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [drillFor, setDrillFor] = useState(null);
  const [scanning, setScanning] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const [s, m, u, h] = await Promise.all([
        api.get("/budget/summary", { params: { project_id: projectId } }),
        api.get("/budget/margin", { params: { project_id: projectId } }),
        api.get("/budget/unmapped", { params: { project_id: projectId } }),
        api.get("/budget/health"),
      ]);
      setSummary(s.data.data); setMargin(m.data.data);
      setUnmapped(u.data.data); setHealth(h.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat realisasi anggaran.");
    } finally { setLoading(false); }
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!projectId) return;
    api.get("/budget/rab-vs-actual", { params: { project_id: projectId, group_by: groupBy } })
      .then((r) => setRab(r.data.data)).catch(() => setRab(null));
  }, [projectId, groupBy]);

  const runScan = async () => {
    setScanning(true);
    try {
      const r = await api.post("/budget/alerts/scan", null,
        { params: { project_id: projectId, force: true } });
      const n = r.data?.data?.created || 0;
      toast.success(n
        ? `${n} peringatan anggaran dikirim (notifikasi + tugas ke penanggung jawab).`
        : "Tidak ada item yang melewati ambang — tidak ada peringatan yang perlu dikirim.");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menjalankan pemeriksaan anggaran.");
    } finally { setScanning(false); }
  };

  if (!projectId) {
    return <EmptyState icon={ListTree} title="Pilih proyek"
      description="Pilih proyek untuk melihat realisasi anggaran tiga lapis: umum, per kategori, sampai dokumen sumbernya." />;
  }
  if (loading && !summary) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const t = summary?.totals;
  return (
    <div data-testid={BUDGET.realizationPanel} className="space-y-5">
      {/* kebijakan yang berlaku — jujur MENYALA / MATI, tanpa membocorkan isi env */}
      {health ? (
        <div data-testid={BUDGET.enforceBanner}
          data-enforce={health.enforce_cost_ref ? "on" : "off"}
          className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-[12px] ${
            health.enforce_cost_ref
              ? "border-emerald-200 bg-emerald-50 text-emerald-900"
              : "border-slate-200 bg-slate-50 text-slate-700"}`}>
          <span className="flex items-start gap-2">
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              Kewajiban memilih item anggaran pada dokumen biaya baru:{" "}
              <strong>{health.enforce_cost_ref ? "MENYALA" : "MATI"}</strong>. Ambang peringatan
              anggaran <strong>{health.alert_pct}%</strong>.{" "}
              {health.enforce_cost_ref
                ? "Dokumen biaya baru wajib menyebut item anggaran."
                : "Dokumen baru boleh tanpa item anggaran, tetapi akan muncul di daftar “biaya belum terpetakan” di bawah."}
            </span>
          </span>
          <Link to={health.config_link}
            className="inline-flex items-center gap-1 rounded-md border bg-card px-2 py-1 font-medium shadow-[var(--shadow-card)]">
            <Settings2 className="h-3.5 w-3.5" /> Ubah kebijakan
          </Link>
        </div>
      ) : null}

      {/* ---------------- LAPIS 1: angka umum proyek ---------------- */}
      {summary?.state === "kosong" ? (
        <EmptyState icon={ListTree} title="Proyek ini belum punya anggaran"
          description="Karena belum ada item anggaran, sistem TIDAK menampilkan Rp 0 (itu akan terbaca seolah-olah proyek ini paling hemat). Susun master anggaran di tab Target & Budget lebih dulu." />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold">Ringkasan anggaran proyek</p>
              <StateBadge value={summary?.state} />
            </div>
            {canScan ? (
              <Button size="sm" variant="secondary" disabled={scanning}
                data-testid={BUDGET.scanBtn} onClick={runScan}>
                <BellRing className="mr-1.5 h-4 w-4" /> Periksa ambang &amp; kirim peringatan
              </Button>
            ) : null}
          </div>

          <div data-testid={BUDGET.summaryCards} className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <MetricCard label="Rencana anggaran" value={t?.planned} format="idr" tone="primary" />
            <MetricCard label="Komitmen (belum jadi biaya)" value={t?.committed} format="idr"
              tone="indigo" />
            <MetricCard label="Realisasi" value={t?.realized} format="idr" tone="emerald" />
            <MetricCard label="Exposure (realisasi + komitmen)" value={t?.exposure} format="idr"
              tone={t?.health === "overbudget" ? "rose" : "amber"}
              hint={t?.pct !== null && t?.pct !== undefined
                ? `${t.pct}% dari rencana` : "persen belum bisa dihitung"} />
            <MetricCard label="Sisa anggaran" value={t?.variance} format="idr"
              tone={isNegative(t?.variance) ? "rose" : "emerald"} />
          </div>

          <div className="flex items-center gap-2">
            <HealthPill value={t?.health} />
            <span className="text-[12px] text-muted-foreground">
              Ambang waspada {summary?.alert_pct}% · {summary?.item_count} item anggaran
            </span>
          </div>

          <MissingNote items={summary?.missing} />

          {(summary?.warnings || []).length ? (
            <div data-testid={BUDGET.warnings} className="space-y-1.5">
              {summary.warnings.map((w, i) => (
                <p key={i}
                  className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-[12px] text-amber-900">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {w}
                </p>
              ))}
            </div>
          ) : (
            <p className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-[12px] text-emerald-900">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              Tidak ada pos anggaran yang mendekati atau melewati ambang.
            </p>
          )}

          {/* ---------------- LAPIS 2: per kategori ---------------- */}
          <div>
            <p className="mb-2 text-sm font-semibold">Per kategori anggaran</p>
            <div data-testid={BUDGET.categoryTable}
              className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Kategori</TableHead>
                  <TableHead className="text-right">Rencana</TableHead>
                  <TableHead className="text-right">Komitmen</TableHead>
                  <TableHead className="text-right">Realisasi</TableHead>
                  <TableHead className="text-right">Exposure</TableHead>
                  <TableHead className="text-right">Selisih</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Kelengkapan</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(summary?.categories || []).map((c) => (
                    <TableRow key={c.category} data-testid={BUDGET.categoryRow}
                      data-category={c.category} data-health={c.health}>
                      <TableCell className="font-medium">
                        {labelOf("budget_category", c.category)}
                        <ExposureBar exposure={c.exposure} planned={c.planned}
                          health={c.health} />
                      </TableCell>
                      <TableCell className="text-right text-sm"><Money value={c.planned} /></TableCell>
                      <TableCell className="text-right text-sm"><Money value={c.committed} /></TableCell>
                      <TableCell className="text-right text-sm text-emerald-700">
                        <Money value={c.realized} />
                      </TableCell>
                      <TableCell className="text-right text-sm font-medium">
                        <Money value={c.exposure} />
                      </TableCell>
                      <TableCell className={`text-right text-sm ${
                        isNegative(c.variance) ? "font-semibold text-rose-600" : ""}`}>
                        <Money value={c.variance} />
                      </TableCell>
                      <TableCell>
                        <HealthPill value={c.health} />
                        <span className="mt-1 block text-[10px] text-muted-foreground">
                          <Pct value={c.pct} />
                        </span>
                      </TableCell>
                      <TableCell className="max-w-[240px]">
                        <StateBadge value={c.state} />
                        {c.unresolved_amount ? (
                          <span className="mt-1 block text-[10px] text-amber-700">
                            <Money value={c.unresolved_amount} /> belum bisa dipetakan ke proyek
                            (tidak dijumlahkan)
                          </span>
                        ) : null}
                        {(c.missing || []).length ? (
                          <span className="mt-0.5 block text-[10px] text-muted-foreground">
                            {c.missing[0]}
                          </span>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <p className="mt-1.5 text-[11px] text-muted-foreground">
              Klik tombol “Dokumen” pada tabel item anggaran (tab Target &amp; Budget) atau di
              bawah untuk menembus ke dokumen sumber tiap angka.
            </p>
          </div>

          {/* item + tombol tembus dokumen (lapis 3) */}
          <div>
            <p className="mb-2 text-sm font-semibold">Item anggaran &amp; jalur telusurnya</p>
            <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Kode</TableHead>
                  <TableHead>Nama</TableHead>
                  <TableHead className="text-right">Rencana</TableHead>
                  <TableHead className="text-right">Exposure</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Dokumen</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(summary?.items || []).map((row) => (
                    <TableRow key={row.id} data-testid={`${BUDGET.itemRow}-drill`}
                      data-code={row.code}>
                      <TableCell className="font-mono text-xs">{row.code}</TableCell>
                      <TableCell className="max-w-[220px] truncate text-sm">{row.name}</TableCell>
                      <TableCell className="text-right text-sm"><Money value={row.planned} /></TableCell>
                      <TableCell className="text-right text-sm"><Money value={row.exposure} /></TableCell>
                      <TableCell><HealthPill value={row.health} /></TableCell>
                      <TableCell>
                        <Button size="sm" variant="ghost" className="h-7 px-2 text-[11px]"
                          data-testid={BUDGET.drillBtn} onClick={() => setDrillFor(row)}>
                          <ListTree className="mr-1 h-3.5 w-3.5" /> {row.document_count} dokumen
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        </>
      )}

      {/* ---------------- RAB vs realisasi ---------------- */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-semibold">RAB vs realisasi konstruksi</p>
          <select data-testid={BUDGET.rabGroupBy} value={groupBy}
            aria-label="Kelompokkan RAB vs realisasi"
            onChange={(e) => setGroupBy(e.target.value)}
            className="h-8 rounded-md border bg-background px-2 text-xs">
            {GROUPS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
          </select>
        </div>
        {rab ? (
          <>
            <p className={`rounded-lg border p-2 text-[11px] ${
              rab.tie_out?.ok ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                : "border-rose-200 bg-rose-50 text-rose-900"}`}>
              {rab.tie_out?.ok
                ? "Angka di tabel ini cocok dengan panel Kendali Biaya (tidak ada dua kebenaran)."
                : `TIDAK COCOK dengan panel Kendali Biaya: ${JSON.stringify(rab.tie_out?.diff)} — laporkan sebagai cacat.`}
            </p>
            <div data-testid={BUDGET.rabTable} className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>{GROUPS.find((g) => g.value === groupBy)?.label}</TableHead>
                  <TableHead className="text-right">Anggaran RAB</TableHead>
                  <TableHead className="text-right">Dikontrakkan</TableHead>
                  <TableHead className="text-right">Terverifikasi</TableHead>
                  <TableHead className="text-right">Ditagih</TableHead>
                  <TableHead className="text-right">Exposure</TableHead>
                  <TableHead className="text-right">Selisih</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(rab.data || []).map((r) => (
                    <TableRow key={r.key} data-testid={BUDGET.rabRow} data-health={r.health}>
                      <TableCell className="max-w-[260px] truncate text-sm" title={r.label}>
                        {r.label}
                        {r.description ? (
                          <span className="block text-[10px] text-muted-foreground">
                            {r.description}
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-right text-sm"><Money value={r.budget} /></TableCell>
                      <TableCell className="text-right text-sm"><Money value={r.contracted} /></TableCell>
                      <TableCell className="text-right text-sm text-emerald-700">
                        <Money value={r.verified} />
                      </TableCell>
                      <TableCell className="text-right text-sm"><Money value={r.billed} /></TableCell>
                      <TableCell className="text-right text-sm font-medium">
                        <Money value={r.exposure} />
                      </TableCell>
                      <TableCell className={`text-right text-sm ${
                        isNegative(r.variance) ? "font-semibold text-rose-600" : ""}`}>
                        <Money value={r.variance} />
                      </TableCell>
                      <TableCell><HealthPill value={r.health} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        ) : null}
      </div>

      {/* ---------------- margin ---------------- */}
      {margin ? (
        <div data-testid={BUDGET.marginPanel} className="space-y-2">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold">Margin proyek</p>
            <StateBadge value={margin.state} />
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <MetricCard label="Margin (pendapatan diakui − realisasi biaya)"
              value={margin.margin === null ? "belum ada data" : margin.margin}
              format={margin.margin === null ? undefined : "idr"}
              tone={isNegative(margin.margin) ? "rose" : "emerald"}
              hint={margin.margin_pct !== null ? `${margin.margin_pct}% dari pendapatan` : undefined} />
            <MetricCard label="Margin proyeksi (harga jual − rencana biaya)"
              value={margin.margin_projected === null ? "belum ada data" : margin.margin_projected}
              format={margin.margin_projected === null ? undefined : "idr"} tone="indigo"
              hint={margin.margin_projected_pct !== null
                ? `${margin.margin_projected_pct}% dari harga jual` : undefined} />
            <MetricCard label="Kas masuk (BUKAN pendapatan)"
              value={margin.components?.kas_masuk} format="idr" tone="sky" />
            <MetricCard label="Realisasi biaya" value={margin.components?.realisasi_biaya}
              format="idr" tone="amber" />
          </div>
          <p className="text-[11px] text-muted-foreground">{margin.note}</p>
          <MissingNote items={margin.missing} title="Margin belum lengkap karena:" />
        </div>
      ) : null}

      {/* ---------------- biaya belum terpetakan ---------------- */}
      {unmapped ? (
        <div data-testid={BUDGET.unmappedPanel} className="space-y-2">
          <p className="text-sm font-semibold">
            Biaya belum terpetakan ({unmapped.document_count} dokumen ·{" "}
            <Money value={unmapped.total} />)
          </p>
          <p className="text-[12px] text-muted-foreground">{unmapped.note}</p>
          {(unmapped.by_source || []).length ? (
            <div className="flex flex-wrap gap-2">
              {unmapped.by_source.map((s) => (
                <span key={s.source} className="rounded-full border bg-card px-3 py-1 text-[11px] shadow-[var(--shadow-card)]">
                  <span className="text-muted-foreground">
                    {labelOf("cost_source", s.source)}:
                  </span>{" "}
                  <span className="font-medium"><Money value={s.amount} /></span>
                </span>
              ))}
            </div>
          ) : (
            <p className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-[12px] text-emerald-900">
              Semua dokumen biaya sudah menyebut item anggaran — kewajiban `enforce_cost_ref`
              aman untuk dinyalakan.
            </p>
          )}
          {(unmapped.documents || []).length ? (
            <div className="max-h-72 overflow-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Jenis</TableHead><TableHead>Nomor</TableHead>
                  <TableHead>Keterangan</TableHead><TableHead>Tanggal</TableHead>
                  <TableHead className="text-right">Nilai</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {unmapped.documents.slice(0, 60).map((d, i) => (
                    <TableRow key={`${d.source}-${d.ref}-${i}`} data-testid={BUDGET.unmappedRow}>
                      <TableCell className="text-xs">{labelOf("cost_source", d.source)}</TableCell>
                      <TableCell className="font-mono text-[11px]">{d.ref || "-"}</TableCell>
                      <TableCell className="max-w-[280px] truncate text-xs" title={d.label}>
                        {d.label}
                        {d.note ? (
                          <span className="block text-[10px] text-muted-foreground">{d.note}</span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-[11px]">{d.date || "-"}</TableCell>
                      <TableCell className="text-right text-xs"><Money value={d.amount} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </div>
      ) : null}

      <RealizationDialog item={drillFor} open={!!drillFor}
        onOpenChange={(v) => !v && setDrillFor(null)} />
    </div>
  );
}
