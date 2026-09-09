import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, RotateCcw, Save, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { LEADSCORE } from "@/constants/testIds";

const PARAM_LABEL = { window_days: "jendela (hari)", cap: "batas poin", threshold_days: "ambang diam (hari)" };
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);

/** Pusat Konfigurasi › Skor Lead — event, poin (+/−), parameter, aktif, event kustom. */
export default function LeadScorePanel() {
  const [events, setEvents] = useState(null);
  const [bands, setBands] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState({ label: "", points: 10, window_days: 0, cap: 0 });

  const load = useCallback(async () => {
    setError("");
    try {
      const r = await api.get("/lead-score/events");
      setEvents(r.data.data.events); setBands(r.data.data.bands || {});
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat event skor."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const patch = (key, p) => setEvents((rows) => rows.map((e) => (e.key === key ? { ...e, ...p } : e)));
  const patchParam = (key, name, v) => setEvents((rows) => rows.map((e) =>
    (e.key === key ? { ...e, params: { ...e.params, [name]: Number(v) || 0 } } : e)));

  const addCustom = () => {
    const key = slug(draft.label);
    if (!key || key.length < 2) { toast.error("Nama event kustom wajib diisi."); return; }
    if (events.some((e) => e.key === key)) { toast.error("Event dengan nama itu sudah ada."); return; }
    setEvents([...events, { key, label: draft.label.trim(), points: Number(draft.points) || 0, active: true,
      kind: "custom", desc: "Dicatat sales dari kartu skor lead.",
      params: { window_days: Number(draft.window_days) || 0, cap: Number(draft.cap) || 0 } }]);
    setDraft({ label: "", points: 10, window_days: 0, cap: 0 });
  };

  const save = async () => {
    setBusy(true);
    try {
      const r = await api.put("/lead-score/events", { events: events.map(({ kind, ...e }) => e) });
      toast.success(r.data.message); setEvents(r.data.data.events);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan."); }
    finally { setBusy(false); }
  };
  const reset = async () => {
    setBusy(true);
    try { const r = await api.post("/lead-score/events/reset"); toast.success(r.data.message); setEvents(r.data.data.events); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengembalikan."); }
    finally { setBusy(false); }
  };
  const rescoreAll = async () => {
    setBusy(true);
    try { const r = await api.post("/lead-score/rescore-all"); toast.success(r.data.message); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menilai ulang."); }
    finally { setBusy(false); }
  };

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!events) return <LoadingCards count={2} />;

  return (
    <div className="space-y-4" data-testid={LEADSCORE.panel}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="max-w-3xl text-sm text-muted-foreground">
          Skor lead (0–100) = jumlah poin event yang terjadi. Poin positif menaikkan, negatif menurunkan.
          Band: HOT ≥ {bands.hot_min} · WARM ≥ {bands.warm_min} (ambang di tab Aturan Bisnis › Lead).
          Event kustom dicatat sales dari kartu skor pada profil lead.
        </p>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={rescoreAll} disabled={busy} data-testid={LEADSCORE.rescoreAll}>
            <RotateCcw className="mr-1 h-3.5 w-3.5" /> Nilai ulang semua lead
          </Button>
          <Button size="sm" variant="outline" onClick={reset} disabled={busy} data-testid={LEADSCORE.reset}>Bawaan</Button>
          <Button size="sm" onClick={save} disabled={busy} data-testid={LEADSCORE.save}>
            <Save className="mr-1 h-3.5 w-3.5" /> Simpan
          </Button>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
        <Table>
          <TableHeader><TableRow>
            <TableHead>Event</TableHead><TableHead>Keterangan</TableHead>
            <TableHead className="w-28 text-right">Poin</TableHead>
            <TableHead className="w-64">Parameter</TableHead>
            <TableHead className="w-20">Aktif</TableHead><TableHead className="w-12" />
          </TableRow></TableHeader>
          <TableBody>
            {events.map((e) => (
              <TableRow key={e.key} data-testid={`${LEADSCORE.row}-${e.key}`} className={e.active ? "" : "opacity-60"}>
                <TableCell>
                  <p className="text-sm font-medium">{e.label}</p>
                  <p className="font-mono text-[11px] text-muted-foreground">{e.key}{e.kind === "custom" ? " · kustom" : ""}</p>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">{e.desc}</TableCell>
                <TableCell className="text-right">
                  <Input type="number" className="h-8 w-24 text-right" value={e.points} disabled={e.key === "source"}
                    data-testid={`${LEADSCORE.points}-${e.key}`} aria-label={`Poin ${e.label}`}
                    onChange={(ev) => patch(e.key, { points: Number(ev.target.value) || 0 })} />
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-2">
                    {Object.keys(e.params || {}).map((p) => (
                      <label key={p} className="flex items-center gap-1 text-[11px] text-muted-foreground">
                        {PARAM_LABEL[p] || p}
                        <Input type="number" className="h-7 w-16 text-right" value={e.params[p]}
                          data-testid={`${LEADSCORE.param}-${e.key}-${p}`} aria-label={`${PARAM_LABEL[p] || p} ${e.label}`}
                          onChange={(ev) => patchParam(e.key, p, ev.target.value)} />
                      </label>
                    ))}
                  </div>
                </TableCell>
                <TableCell>
                  <Switch checked={!!e.active} onCheckedChange={(v) => patch(e.key, { active: v })}
                    data-testid={`${LEADSCORE.active}-${e.key}`} aria-label={`Aktif ${e.label}`} />
                </TableCell>
                <TableCell>
                  {e.kind === "custom" ? (
                    <Button size="icon" variant="ghost" aria-label="Hapus event" data-testid={`${LEADSCORE.remove}-${e.key}`}
                      onClick={() => setEvents(events.filter((x) => x.key !== e.key))}>
                      <Trash2 className="h-4 w-4 text-rose-600" />
                    </Button>
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]" data-testid={LEADSCORE.customForm}>
        <p className="text-sm font-semibold">Tambah event kustom</p>
        <p className="text-xs text-muted-foreground">Contoh: "Hadir open house" +10, "Minta brosur ulang" +5, "Batal janji" −10.</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-5">
          <Input className="sm:col-span-2" placeholder="Nama event" value={draft.label} data-testid={LEADSCORE.customLabel}
            onChange={(e) => setDraft({ ...draft, label: e.target.value })} />
          <Input type="number" placeholder="Poin (+/−)" value={draft.points} data-testid={LEADSCORE.customPoints}
            onChange={(e) => setDraft({ ...draft, points: e.target.value })} />
          <Input type="number" placeholder="Jendela hari (0=selamanya)" value={draft.window_days}
            onChange={(e) => setDraft({ ...draft, window_days: e.target.value })} />
          <div className="flex gap-2">
            <Input type="number" placeholder="Batas poin (0=tanpa)" value={draft.cap}
              onChange={(e) => setDraft({ ...draft, cap: e.target.value })} />
            <Button variant="outline" onClick={addCustom} data-testid={LEADSCORE.customAdd}><Plus className="h-4 w-4" /></Button>
          </div>
        </div>
      </div>
    </div>
  );
}
