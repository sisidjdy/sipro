import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { RefreshCw, TrendingDown, TrendingUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import api from "@/services/apiClient";
import { LEADSCORE } from "@/constants/testIds";

/** Kartu "kenapa skornya begini" — rincian event skor lead + pencatatan event kustom. */
export default function LeadScoreCard({ lead, onChanged }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [eventKey, setEventKey] = useState("");

  const load = useCallback(() => {
    api.get(`/leads/${lead.id}/score`).then((r) => setData(r.data.data)).catch(() => setData(null));
  }, [lead.id]);
  useEffect(() => { load(); }, [load, lead.score, lead.updated_at]);

  const rescore = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/leads/${lead.id}/rescore`);
      toast.success(r.data.message);
      setData((d) => ({ ...d, ...r.data.data }));
      onChanged?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menilai ulang."); }
    finally { setBusy(false); }
  };

  const logEvent = async () => {
    if (!eventKey) return;
    setBusy(true);
    try {
      const r = await api.post(`/leads/${lead.id}/score-events`, { event_key: eventKey });
      toast.success(r.data.message);
      setData((d) => ({ ...d, ...r.data.data }));
      setEventKey("");
      onChanged?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mencatat event."); }
    finally { setBusy(false); }
  };

  if (!data) return null;
  const rows = data.score_breakdown || [];
  const bands = data.score_bands || {};
  return (
    <div data-testid="lead-score-card" className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Skor lead</p>
          <div className="mt-1 flex items-center gap-2">
            <span data-testid="lead-score-value" className="text-2xl font-semibold tabular-nums">{data.score}</span>
            <StatusPill status={data.score_band} label={data.score_band} />
            {data.stored_score != null && data.stored_score !== data.score ? (
              <span className="text-xs text-amber-700" data-testid="lead-score-stale">
                tersimpan {data.stored_score} → nilai ulang untuk memperbarui
              </span>
            ) : null}
          </div>
          <p className="text-xs text-muted-foreground">
            HOT ≥ {bands.hot_min} · WARM ≥ {bands.warm_min} · event & poin diatur di Pusat Konfigurasi › Skor Lead.
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={rescore} disabled={busy} data-testid="lead-rescore-btn">
          <RefreshCw className="mr-1 h-3.5 w-3.5" /> Nilai ulang
        </Button>
      </div>
      {(data.custom_events || []).length ? (
        <div className="mt-3 flex items-center gap-2">
          <Select value={eventKey} onValueChange={setEventKey}>
            <SelectTrigger className="h-8 flex-1" data-testid={LEADSCORE.logSelect} aria-label="Event kustom">
              <SelectValue placeholder="Catat event (mis. hadir open house)…" />
            </SelectTrigger>
            <SelectContent>
              {data.custom_events.map((e) => (
                <SelectItem key={e.key} value={e.key}>{e.label} ({e.points > 0 ? `+${e.points}` : e.points})</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button size="sm" onClick={logEvent} disabled={busy || !eventKey} data-testid={LEADSCORE.logBtn}>Catat</Button>
        </div>
      ) : null}
      <ul className="mt-3 divide-y text-sm" data-testid="lead-score-breakdown">
        {rows.map((r) => (
          <li key={r.key} className="flex items-start justify-between gap-3 py-1.5">
            <div>
              <span>{r.label}</span>
              {r.detail ? <p className="text-xs text-muted-foreground">{r.detail}</p> : null}
            </div>
            <span className={`inline-flex items-center gap-1 tabular-nums ${r.points < 0 ? "text-rose-700" : "text-emerald-700"}`}>
              {r.points < 0 ? <TrendingDown className="h-3.5 w-3.5" /> : <TrendingUp className="h-3.5 w-3.5" />}
              {r.points > 0 ? `+${r.points}` : r.points}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
