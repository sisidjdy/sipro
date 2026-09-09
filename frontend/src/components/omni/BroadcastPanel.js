import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Send, Megaphone } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR, formatNumber } from "@/utils/formatters";
import { useAuth } from "@/context/AuthContext";
import BroadcastDetailSheet, { BroadcastActions, BroadcastCounts } from "@/components/omni/BroadcastDetailSheet";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { OMNI, P97 } from "@/constants/testIds";


function emptySeg() {
  return { lead_stages: [], score_bands: [], sources: [], campaigns: [], include_customers: false };
}

function toggleIn(arr, v) {
  return arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];
}

export default function BroadcastPanel() {
  const { options, labelOf } = useReference();
  const { can } = useAuth();
  const canManage = can("broadcasts", "manage");
  const [rows, setRows] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [templateCode, setTemplateCode] = useState("");
  const [seg, setSeg] = useState(emptySeg());
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [detail, setDetail] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [b, t] = await Promise.all([api.get("/broadcasts"), api.get("/wa-templates")]);
      setRows(b.data.data || []);
      setTemplates(t.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat broadcast.");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  // Live preview of recipient count whenever the segment changes (dialog open).
  useEffect(() => {
    if (!open) return;
    let active = true;
    setPreviewing(true);
    const timer = setTimeout(async () => {
      try {
        const res = await api.post("/broadcasts/preview", { segment: seg, template_code: templateCode });
        if (active) setPreview(res.data.data);
      } catch { if (active) setPreview(null); }
      finally { if (active) setPreviewing(false); }
    }, 350);
    return () => { active = false; clearTimeout(timer); };
  }, [seg, open, templateCode]);

  const openCreate = () => {
    setName(""); setTemplateCode(templates[0]?.code || ""); setSeg(emptySeg());
    setPreview(null); setOpen(true);
  };

  const send = async () => {
    if (!name.trim()) { toast.error("Nama broadcast wajib diisi."); return; }
    if (!templateCode) { toast.error("Pilih template WA."); return; }
    if (!preview || preview.total === 0) { toast.error("Segmen tidak menghasilkan penerima."); return; }
    setBusy(true);
    try {
      const res = await api.post("/broadcasts", { name: name.trim(), template_code: templateCode, segment: seg });
      const b = res.data.data;
      toast.success(`Broadcast masuk antrean: ${b.queued} penerima${b.skipped ? `, ${b.skipped} dilewati (opt-out/nomor tidak valid)` : ""}. Status nyata mengikuti gateway & webhook Meta.`);
      setOpen(false); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengirim broadcast."); }
    finally { setBusy(false); }
  };

  const openDetail = async (b) => {
    try {
      const res = await api.get(`/broadcasts/${b.id}`);
      setDetail(res.data.data);
    } catch { toast.error("Gagal memuat detail broadcast."); }
  };
  // Antrean berjalan di latar (scheduler 10 detik): segarkan daftar selama masih ada yang antre.
  useEffect(() => {
    if (!rows.some((b) => ["queued", "sending"].includes(b.status))) return undefined;
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [rows, load]);

  const segSummary = (s) => {
    const parts = [];
    const names = (group, vals) => vals.map((v) => labelOf(group, v)).join(" / ");
    if (s.lead_stages?.length) parts.push(`Tahap: ${names("lead_stage", s.lead_stages)}`);
    if (s.score_bands?.length) parts.push(`Skor: ${names("score_band", s.score_bands)}`);
    if (s.sources?.length) parts.push(`Sumber: ${names("lead_source", s.sources)}`);
    if (s.include_customers) parts.push("+ customer");
    return parts.length ? parts.join(" · ") : "Semua lead";
  };

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Kirim template WA <b>APPROVED</b> ke segmen lead/customer lewat antrean (jam kirim & batas laju dari Pusat Konfigurasi).
          Nomor opt-out dilewati untuk promosi; status sampai/dibaca hanya dari webhook Meta.
        </p>
        <Button data-testid={OMNI.bcAddBtn} size="sm" onClick={openCreate}>
          <Plus className="mr-1.5 h-4 w-4" /> Buat Broadcast
        </Button>
      </div>

      {!rows.length ? (
        <EmptyState icon={Megaphone} title="Belum ada broadcast" description="Buat campaign blast pertama Anda."
          actionLabel="Buat Broadcast" onAction={openCreate} />
      ) : (
        <div className="space-y-2">
          {rows.map((b) => (
            <div key={b.id} data-testid={OMNI.bcRow}
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium">{b.name}</p>
                  <span data-testid={P97.bcStatus}><StatusPill status={b.status} group="broadcast_status" /></span>
                  <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[11px]">{b.template_name}</span>
                  {b.mode ? <span className="rounded-md border px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">{b.mode}</span> : null}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">Segmen: {segSummary(b.segment || {})}</p>
                <BroadcastCounts b={b} />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <BroadcastActions b={b} canManage={canManage} onChanged={load} />
                <Button data-testid={OMNI.bcDetailBtn} variant="outline" size="sm" onClick={() => openDetail(b)}>
                  Detail
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Buat Broadcast</DialogTitle>
            <DialogDescription>Pilih template &amp; segmen penerima. Estimasi penerima diperbarui otomatis.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="broadcastpanel-nama-broadcast">Nama Broadcast</Label>
              <Input id="broadcastpanel-nama-broadcast" data-testid={OMNI.bcName} value={name} onChange={(e) => setName(e.target.value)}
                placeholder="mis. Promo Cluster Asri Juli" />
            </div>
            <div className="space-y-1.5">
              <Label>Template WA</Label>
              <Select value={templateCode} onValueChange={setTemplateCode}>
                <SelectTrigger data-testid={OMNI.bcTemplate}><SelectValue placeholder="Pilih template" /></SelectTrigger>
                <SelectContent>
                  {templates.map((t) => <SelectItem key={t.id} value={t.code}>{t.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2" data-testid={OMNI.bcSegStage}>
              <Label>Stage Lead</Label>
              <div className="flex flex-wrap gap-3">
                {options("lead_stage").map((s) => (
                  <label key={s.value} className="flex items-center gap-1.5 text-sm">
                    <Checkbox checked={seg.lead_stages.includes(s.value)}
                      onCheckedChange={() => setSeg({ ...seg, lead_stages: toggleIn(seg.lead_stages, s.value) })} />
                    {s.label}
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-2" data-testid={OMNI.bcSegScore}>
              <Label>Skor Lead</Label>
              <div className="flex flex-wrap gap-3">
                {options("score_band").map((s) => (
                  <label key={s.value} className="flex items-center gap-1.5 text-sm">
                    <Checkbox checked={seg.score_bands.includes(s.value)}
                      onCheckedChange={() => setSeg({ ...seg, score_bands: toggleIn(seg.score_bands, s.value) })} />
                    {s.label}
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-2" data-testid={OMNI.bcSegSource}>
              <Label>Sumber / Campaign</Label>
              <div className="flex flex-wrap gap-3">
                {options("lead_source").map((s) => (
                  <label key={s.value} className="flex items-center gap-1.5 text-sm">
                    <Checkbox checked={seg.sources.includes(s.value)}
                      onCheckedChange={() => setSeg({ ...seg, sources: toggleIn(seg.sources, s.value) })} />
                    {s.label}
                  </label>
                ))}
              </div>
            </div>

            <label className="flex items-center justify-between rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
              <span className="text-sm font-medium">Sertakan Customer (pembeli)</span>
              <Switch data-testid={OMNI.bcSegCustomers} checked={seg.include_customers}
                onCheckedChange={(v) => setSeg({ ...seg, include_customers: !!v })} />
            </label>

            <div className="rounded-lg bg-secondary p-3 text-sm">
              <p className="text-muted-foreground">Estimasi penerima</p>
              <p data-testid={OMNI.bcPreviewCount} className="mt-0.5 text-2xl font-semibold tabular-nums">
                {previewing ? "…" : formatNumber(preview?.total || 0)}
              </p>
              {preview ? (
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {formatNumber(preview.by_kind?.lead || 0)} lead · {formatNumber(preview.by_kind?.customer || 0)} customer
                  {preview.skipped ? <> · <span className="text-amber-700">{formatNumber(preview.skipped)} dilewati (opt-out / nomor tidak valid)</span></> : null}
                  <br />Kategori {preview.category} · est. biaya <b>{formatIDR(preview.cost_estimate || 0)}</b> · jam kirim {preview.send_window}
                  {preview.in_window ? "" : " (di luar jam — dijadwalkan besok)"}
                  {preview.template_ok === false ? <><br /><span className="text-rose-600">Template belum APPROVED ({preview.template_status}) — broadcast akan ditolak.</span></> : null}
                </p>
              ) : null}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Batal</Button>
            <Button data-testid={OMNI.bcSend} onClick={send} disabled={busy || previewing || !(preview?.eligible) || preview?.template_ok === false}>
              <Send className="mr-1.5 h-4 w-4" /> {busy ? "Mengantrekan..." : `Antrekan ke ${formatNumber(preview?.eligible || 0)}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <BroadcastDetailSheet detail={detail} onOpenChange={() => setDetail(null)} canManage={canManage}
        onChanged={() => { load(); if (detail) openDetail(detail.broadcast); }} />
    </div>
  );
}
