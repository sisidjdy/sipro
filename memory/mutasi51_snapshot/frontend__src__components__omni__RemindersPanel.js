import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  BellRing, Play, RefreshCw, Settings2, ShieldAlert, Clock, Ban, ExternalLink,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import EmptyState from "@/components/patterns/EmptyState";
import MetricCard from "@/components/patterns/MetricCard";
import StatusPill from "@/components/patterns/StatusPill";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P51 as T } from "@/constants/testIds";

/**
 * Pengingat WhatsApp otomatis (Fase 51B).
 *
 * Sistem sudah menyimpan semua tanggal yang penting bagi pembeli — jatuh tempo tiap termin,
 * tunggakan, dan tanggal habis garansi per bagian rumah — tetapi tidak seorang pun diberi
 * tahu. Pengingat dikirim manual: tidak konsisten, tanpa jejak, dan kalau stafnya sibuk
 * tunggakan berkembang diam-diam sementara garansi habis tanpa pembeli tahu haknya berakhir.
 *
 * Panel ini menampilkan tiga hal yang harus bisa dibaca manusia:
 *   1. **Ambang batas & mode kirim** — termasuk pengakuan jujur “simulasi” bila kredensial
 *      WhatsApp belum ada. Layar tidak boleh mengaku “terkirim” untuk pesan yang tidak pergi.
 *   2. **Kandidat hari ini** — dihitung dari data nyata, dan yang TERTAHAN tetap ditampilkan
 *      beserta sebabnya (“kenapa pembeli ini tidak pernah diingatkan?” harus bisa dijawab).
 *   3. **Riwayat** — siapa, kapan, isi pesannya, template yang dipakai, dan statusnya.
 */
export default function RemindersPanel() {
  const { can } = useAuth();
  const { labelOf, options } = useReference();
  const canRun = can("reminders", "manage");

  const [cfg, setCfg] = useState(null);
  const [hint, setHint] = useState("");
  const [cands, setCands] = useState(null);
  const [hist, setHist] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("candidates");
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [runOpen, setRunOpen] = useState(false);
  const [lastRun, setLastRun] = useState(null);

  const kindOptions = useMemo(() => options("reminder_kind"), [options]);
  const statusOptions = useMemo(() => options("reminder_status"), [options]);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [s, c, h] = await Promise.all([
        api.get("/reminders/settings"),
        api.get("/reminders/candidates", { params: kind ? { kind } : {} }),
        api.get("/reminders", { params: { ...(kind ? { kind } : {}), ...(status ? { status } : {}) } }),
      ]);
      setCfg(s.data.data); setHint(s.data.hint || "");
      setCands(c.data); setHist(h.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat pengingat otomatis.");
    } finally { setLoading(false); }
  }, [kind, status]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const simulasi = cfg?.mode !== "nyata";

  return (
    <div data-testid={T.remindersPanel} className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-heading text-base font-semibold">
            <BellRing className="h-4 w-4 text-primary" /> Pengingat otomatis ke pembeli
          </h2>
          <p className="mt-0.5 max-w-2xl text-sm text-muted-foreground">
            Kandidat DIHITUNG dari data nyata (jatuh tempo termin, tunggakan, tanggal habis
            garansi per bagian) — tidak ada daftar penerima yang diketik. {hint}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button data-testid={T.remindersRefresh} size="sm" variant="outline" onClick={load}>
            <RefreshCw className="mr-1.5 h-4 w-4" /> Muat ulang
          </Button>
          {canRun ? (
            <Button data-testid={T.remindersRunBtn} size="sm" onClick={() => setRunOpen(true)}>
              <Play className="mr-1.5 h-4 w-4" /> Jalankan sekarang
            </Button>
          ) : (
            <p data-testid={T.remindersRunDenied}
              className="max-w-xs rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-[11px] text-slate-700">
              Anda boleh MELIHAT pengingat, tetapi menjalankannya butuh izin kelola — karena
              menjalankan berarti mengirim pesan sungguhan ke pelanggan.
            </p>
          )}
        </div>
      </div>

      <div data-testid={T.remindersMode}
        className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm ${simulasi
          ? "border-amber-200 bg-amber-50 text-amber-900"
          : "border-emerald-200 bg-emerald-50 text-emerald-900"}`}>
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          <b>Mode kirim: {simulasi ? "SIMULASI" : "NYATA"}</b> — {cfg?.mode_detail}
        </p>
      </div>

      <div data-testid={T.remindersSettings} className="rounded-xl border bg-card p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-1.5 text-sm font-medium">
            <Settings2 className="h-4 w-4 text-muted-foreground" /> Ambang batas yang berlaku
          </p>
          <Link data-testid={T.remindersConfigLink} to="/config?group=pengingat"
            className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
            Ubah di Pusat Konfigurasi <ExternalLink className="h-3 w-3" />
          </Link>
        </div>
        <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Setting label="Pengingat otomatis"
            value={cfg?.enabled ? "Menyala" : "Dimatikan"}
            note={cfg?.enabled ? "Scheduler harian aktif."
              : "Kandidat tetap dihitung, tetapi tidak dikirim."} />
          <Setting label="Garansi hampir habis" value={`≤ ${cfg?.warranty_days} hari`}
            note="Sisa masa garansi per bagian rumah." />
          <Setting label="Termin jatuh tempo" value={`H-${cfg?.installment_days_before}`}
            note="Dihitung dari tanggal jatuh tempo termin." />
          <Setting label="Tunggakan diulang" value={`tiap ${cfg?.overdue_every_days} hari`}
            note="Satu pengingat per periode, bukan tiap hari." />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Kandidat hari ini" value={cands?.total ?? 0} tone="indigo" />
        <MetricCard label="Siap dikirim" value={cands?.ready ?? 0} tone="emerald" />
        <MetricCard label="Tertahan sebab" value={cands?.blocked ?? 0} tone="amber" />
        <MetricCard label="Riwayat tercatat" value={hist?.total ?? 0} tone="slate" />
      </div>

      {lastRun ? (
        <div data-testid={T.remindersRunResult}
          className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900">
          <p className="font-medium">Hasil jalan terakhir</p>
          <p className="mt-0.5">{lastRun.detail}</p>
          <p className="mt-0.5 text-xs">
            terkirim {lastRun.sent} · simulasi {lastRun.simulated} · gagal {lastRun.failed}
            {" "}· dilewati {lastRun.skipped}
          </p>
          {(lastRun.notes || []).map((n) => (
            <p key={n} className="mt-0.5 text-xs font-medium">{n}</p>
          ))}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-lg border p-0.5">
          <button type="button" data-testid={T.remindersSubTabCandidates}
            onClick={() => setTab("candidates")}
            className={`rounded-md px-3 py-1.5 text-xs font-medium ${tab === "candidates"
              ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>
            Kandidat hari ini
          </button>
          <button type="button" data-testid={T.remindersSubTabHistory}
            onClick={() => setTab("history")}
            className={`rounded-md px-3 py-1.5 text-xs font-medium ${tab === "history"
              ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>
            Riwayat
          </button>
        </div>
        <select data-testid={T.remindersKindFilter} value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="h-8 rounded-lg border bg-background px-2 text-xs">
          <option value="">Semua jenis</option>
          {kindOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {tab === "history" ? (
          <select data-testid={T.remindersStatusFilter} value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="h-8 rounded-lg border bg-background px-2 text-xs">
            <option value="">Semua status</option>
            {statusOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        ) : null}
      </div>

      {tab === "candidates" ? (
        !cands?.data?.length ? (
          <div data-testid={T.remindersCandidateEmpty}>
            <EmptyState icon={Clock} title="Tidak ada yang perlu diingatkan hari ini"
              description={cands?.detail} />
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">{cands.detail}</p>
            {cands.data.map((c) => (
              <div key={c.dedup_key} data-testid={T.remindersCandidateRow}
                data-kind={c.kind} data-blocked={c.blocked_code || ""}
                className="rounded-xl border bg-card p-3 text-sm">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusPill status={c.kind} group="reminder_kind" />
                      {c.recipient_type ? (
                        <span className="rounded-full border bg-secondary px-1.5 py-0.5 text-[10px]">
                          {c.recipient_type_label
                            || labelOf("reminder_recipient", c.recipient_type)}
                        </span>
                      ) : null}
                      {c.unit_code ? (
                        <span className="text-[11px] text-muted-foreground">{c.unit_code}</span>
                      ) : null}
                    </div>
                    <p className="mt-0.5 font-medium">
                      {c.name || "Nama penerima belum dicatat"}
                      <span className="ml-1.5 font-normal text-muted-foreground">
                        {c.phone || "— tanpa nomor WhatsApp"}
                      </span>
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{c.reason}</p>
                  </div>
                  <div className="text-right">
                    {c.amount ? (
                      <p className="font-heading text-sm font-semibold tabular-nums">
                        {formatIDR(c.amount)}</p>
                    ) : null}
                    <p className="text-[11px] text-muted-foreground">
                      jatuh tempo {c.due_date}
                    </p>
                  </div>
                </div>
                {c.blocked_reason ? (
                  <p data-testid={T.remindersCandidateBlocked}
                    className="mt-2 flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-900">
                    <Ban className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {c.blocked_reason}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        )
      ) : (
        !hist?.data?.length ? (
          <div data-testid={T.remindersHistoryEmpty}>
            <EmptyState icon={BellRing} title="Belum ada pengingat yang pernah dijalankan"
              description={"Riwayat lahir setelah pengingat dijalankan — baik oleh scheduler "
                + "harian maupun tombol “Jalankan sekarang”. Kosong berarti belum pernah, "
                + "bukan datanya hilang."} />
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">
              {Object.entries(hist.by_status || {})
                .map(([k, v]) => `${labelOf("reminder_status", k) || k}: ${v}`)
                .join(" · ") || "—"}
            </p>
            {hist.data.map((r) => (
              <div key={r.id} data-testid={T.remindersHistoryRow}
                data-status={r.status} data-kind={r.kind}
                className="rounded-xl border bg-card p-3 text-sm">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusPill status={r.status} group="reminder_status" />
                      <StatusPill status={r.kind} group="reminder_kind" />
                      {r.template_code ? (
                        <span className="rounded border bg-secondary px-1.5 py-0.5 font-mono text-[10px]">
                          {r.template_code}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-0.5 font-medium">
                      {r.name || "—"}
                      <span className="ml-1.5 font-normal text-muted-foreground">
                        {r.phone || "tanpa nomor"}
                      </span>
                      {r.unit_code ? (
                        <span className="ml-1.5 text-[11px] text-muted-foreground">
                          · {r.unit_code}</span>
                      ) : null}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{r.reason}</p>
                    {r.detail ? (
                      <p className="mt-0.5 text-xs text-muted-foreground">{r.detail}</p>
                    ) : null}
                    {r.body ? (
                      <p data-testid={T.remindersHistoryBody}
                        className="mt-1.5 whitespace-pre-wrap rounded-lg border bg-secondary/40 px-2 py-1.5 text-xs">
                        {r.body}
                      </p>
                    ) : null}
                  </div>
                  <div className="text-right text-[11px] text-muted-foreground">
                    <p>{String(r.created_at || "").slice(0, 16).replace("T", " ")}</p>
                    <p>oleh {r.run_by || "sistem"}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      <RunDialog open={runOpen} kindOptions={kindOptions} candidates={cands}
        onOpenChange={setRunOpen}
        onDone={(res) => { setRunOpen(false); setLastRun(res); load(); }} />
    </div>
  );
}

function Setting({ label, value, note }) {
  return (
    <div data-testid={T.remindersSettingRow} className="rounded-lg border bg-background p-2.5">
      <p className="text-[11px] uppercase text-muted-foreground">{label}</p>
      <p className="font-heading text-sm font-semibold">{value}</p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">{note}</p>
    </div>
  );
}

function RunDialog({ open, kindOptions, candidates, onOpenChange, onDone }) {
  const [kinds, setKinds] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setKinds([]); }, [open]);

  const siap = candidates?.ready ?? 0;
  const toggle = (v) => setKinds((p) => (p.includes(v) ? p.filter((x) => x !== v) : [...p, v]));

  const submit = async () => {
    setBusy(true);
    try {
      const res = await api.post("/reminders/run",
        { kinds: kinds.length ? kinds : null, limit: 200 });
      const d = res.data.data;
      toast.success(res.data.message || d.detail);
      onDone && onDone(d);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menjalankan pengingat.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={T.remindersRunDialog} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Jalankan pengingat sekarang</DialogTitle>
          <DialogDescription>
            {siap} kandidat siap dikirim. Menjalankan dua kali TIDAK mengirim dua kali —
            penanda dedup per periode dijaga index unik, jadi tombol ini aman ditekan ulang.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label>Batasi jenis (kosongkan = semua jenis)</Label>
          {kindOptions.map((o) => (
            <label key={o.value} data-testid={T.remindersRunKind} data-kind={o.value}
              className="flex cursor-pointer items-center gap-2 rounded-lg border p-2 text-xs hover:bg-secondary/40">
              <input type="checkbox" checked={kinds.includes(o.value)}
                onChange={() => toggle(o.value)} />
              {o.label}
            </label>
          ))}
        </div>
        <DialogFooter>
          <Button data-testid={T.remindersRunCancel} variant="outline" disabled={busy}
            onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={T.remindersRunSubmit} disabled={busy} onClick={submit}>
            {busy ? "Menjalankan…" : "Jalankan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
