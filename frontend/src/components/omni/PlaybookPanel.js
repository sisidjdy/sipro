import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Play, Send, Repeat, AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { OMNI } from "@/constants/testIds";
import { useReference } from "@/context/ReferenceContext";

/**
 * PlaybookPanel — otomasi WhatsApp berbasis TAHAP lead (bukan hanya kata kunci).
 *
 * Menjawab kebutuhan: blasting promo, pengingat per tahap (sapaan, follow-up, pengingat
 * survey, pengingat pembayaran). Setiap playbook bisa: dikirim otomatis oleh sistem, atau
 * hanya menjadi TUGAS bagi staf (human-in-the-loop) — diatur di sini, bukan di kode.
 */
export default function PlaybookPanel() {
  const { labelOf } = useReference();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/wa-playbooks");
      setRows(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat playbook WA.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const patch = async (key, body, msg) => {
    setBusy(key);
    try {
      await api.put(`/wa-playbooks/${key}`, body);
      toast.success(msg);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan playbook.");
    } finally { setBusy(""); }
  };

  const run = async (key, send) => {
    setBusy(key);
    try {
      const res = await api.post(`/wa-playbooks/${key}/run`, { send, limit: 50 });
      const d = res.data.data || {};
      toast.success(`${d.sent || 0} pesan terkirim (simulasi), ${d.tasks || 0} tugas dibuat `
        + `dari ${d.targets || 0} lead sasaran.`);
      if (d.note) toast.message(d.note);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menjalankan playbook.");
    } finally { setBusy(""); }
  };

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={OMNI.playbookPanel} className="space-y-3">
      <p className="rounded-xl border bg-card p-3 text-xs text-muted-foreground shadow-[var(--shadow-card)]">
        Playbook bekerja berdasarkan <span className="font-medium text-foreground">tahap lead</span>{" "}
        dan kondisi nyata (lead diam, survey besok, tagihan jatuh tempo). Pengiriman memakai
        template pra-approved dan <span className="font-medium text-foreground">mode SIMULASI</span>{" "}
        selama kredensial WhatsApp Business resmi belum dipasang — pesan tercatat di percakapan
        &amp; timeline lead, tetapi tidak keluar ke jaringan WhatsApp.
      </p>

      <div className="grid gap-3 md:grid-cols-2">
        {rows.map((p) => (
          <div key={p.key} data-testid={OMNI.playbookRow} data-playbook={p.key}
            className="space-y-2 rounded-xl border bg-card p-3 shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium">{p.name}</p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">{p.desc}</p>
              </div>
              <StatusPill status={p.is_active ? "active" : "cancelled"}
                label={p.is_active ? "Aktif" : "Nonaktif"} />
            </div>

            <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
              {(p.stages || []).map((s) => (
                <span key={s} className="rounded-full bg-secondary px-2 py-0.5 text-muted-foreground">
                  {labelOf("lead_stage", s)}
                </span>
              ))}
              <span className="rounded-full border px-2 py-0.5 text-muted-foreground">
                Template: {p.template_name || p.template_code}
              </span>
              {!p.template_ready ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-800">
                  <AlertTriangle className="h-3 w-3" /> template belum siap
                </span>
              ) : null}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="flex items-center justify-between rounded-lg border bg-card px-2.5 py-1.5 shadow-[var(--shadow-card)]">
                <Label className="text-xs" htmlFor={`auto-${p.key}`}>Kirim otomatis</Label>
                <Switch id={`auto-${p.key}`} data-testid={`${OMNI.playbookAuto}-${p.key}`}
                  checked={!!p.auto_send} disabled={busy === p.key}
                  onCheckedChange={(v) => patch(p.key, { auto_send: v },
                    v ? "Playbook akan mengirim otomatis." : "Pengiriman otomatis dimatikan.")} />
              </div>
              <div className="flex items-center justify-between rounded-lg border bg-card px-2.5 py-1.5 shadow-[var(--shadow-card)]">
                <Label className="text-xs" htmlFor={`task-${p.key}`}>Buat tugas</Label>
                <Switch id={`task-${p.key}`} checked={!!p.create_task} disabled={busy === p.key}
                  onCheckedChange={(v) => patch(p.key, { create_task: v },
                    v ? "Tugas akan dibuat untuk staf." : "Pembuatan tugas dimatikan.")} />
              </div>
            </div>

            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1">
                <Label className="text-[11px]" htmlFor={`cd-${p.key}`}>Jeda kirim (hari)</Label>
                <Input id={`cd-${p.key}`} type="number" min={1} max={90} className="h-8 w-24"
                  defaultValue={p.cooldown_days}
                  data-testid={`${OMNI.playbookCooldown}-${p.key}`}
                  onBlur={(e) => {
                    const v = Number(e.target.value);
                    if (v && v !== p.cooldown_days) {
                      patch(p.key, { cooldown_days: v }, "Jeda kirim diperbarui.");
                    }
                  }} />
              </div>
              <Button size="sm" variant="outline" data-testid={`${OMNI.playbookRun}-${p.key}`}
                disabled={busy === p.key} onClick={() => run(p.key, false)}>
                <Play className="mr-1.5 h-3.5 w-3.5" /> Buat tugas saja
              </Button>
              <Button size="sm" data-testid={`${OMNI.playbookSend}-${p.key}`}
                disabled={busy === p.key || !p.template_ready}
                onClick={() => run(p.key, true)}>
                <Send className="mr-1.5 h-3.5 w-3.5" /> Kirim sekarang
              </Button>
            </div>

            <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <Repeat className="h-3 w-3" />
              {p.sent || 0} pesan · {p.tasks || 0} tugas
              {p.last_run_at ? ` · terakhir ${formatDateTimeWIB(p.last_run_at)}` : ""}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
