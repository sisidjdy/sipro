import React, { useCallback, useEffect, useState } from "react";
import { Copy, ExternalLink, Loader2, RefreshCw, Share2 } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { LoadingCards } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { SITE_PLAN } from "@/constants/testIds";

/**
 * ShareShowroomDialog — kelola HALAMAN PUBLIK showroom proyek (Fase 28b).
 *
 * Tautan memakai token acak, bukan id proyek, sehingga orang tidak bisa menebak URL
 * proyek lain. Mematikan sakelar membuat halaman langsung 404 (tanpa menghapus data),
 * dan token bisa diputar ulang kalau tautan tersebar ke pihak yang tidak diinginkan.
 */
export default function ShareShowroomDialog({ open, onOpenChange, projectId, projectName }) {
  const [cfg, setCfg] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!open || !projectId) return;
    setLoading(true); setError("");
    try {
      const res = await api.get(`/site-plan/${projectId}/showroom`);
      setCfg(res.data?.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat pengaturan showroom.");
    } finally { setLoading(false); }
  }, [open, projectId]);

  useEffect(() => { load(); }, [load]);

  const save = async (patch = {}, { silent = false } = {}) => {
    setBusy(true);
    try {
      const body = {
        enabled: cfg?.enabled ?? false,
        show_price: cfg?.show_price ?? true,
        headline: cfg?.headline || "",
        contact_wa: cfg?.contact_wa || "",
        ...patch,
      };
      const res = await api.post(`/site-plan/${projectId}/showroom`, body);
      setCfg(res.data?.data || null);
      if (!silent) {
        toast.success(body.enabled
          ? "Halaman showroom publik aktif — tautan siap dibagikan."
          : "Halaman showroom publik ditutup (tautan lama tidak bisa dibuka).");
      }
      return res.data?.data;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan pengaturan showroom.");
      return null;
    } finally { setBusy(false); }
  };

  const fullUrl = cfg?.path ? `${window.location.origin}${cfg.path}` : "";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(fullUrl);
      toast.success("Tautan showroom disalin.");
    } catch {
      toast.error("Tidak bisa menyalin otomatis — salin manual dari kotak tautan.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={SITE_PLAN.shareDialog} className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Share2 className="h-4 w-4 text-primary" /> Bagikan Showroom Publik
          </DialogTitle>
          <DialogDescription>
            Halaman marketing {projectName ? `“${projectName}”` : ""} tanpa login: kode kavling,
            tipe, luas, harga, status tersedia/terjual, plus form minat yang langsung masuk ke Lead.
            Nama pembeli & data transaksi tidak pernah ditampilkan.
          </DialogDescription>
        </DialogHeader>

        {loading ? <LoadingCards count={1} /> : error ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
              <div>
                <p className="text-sm font-semibold">Aktifkan halaman publik</p>
                <p className="text-xs text-muted-foreground">
                  {cfg?.enabled ? "Aktif — siapa pun dengan tautan bisa melihat." : "Nonaktif — tautan mengembalikan 404."}
                </p>
              </div>
              <Switch data-testid={SITE_PLAN.shareToggle} checked={!!cfg?.enabled}
                disabled={busy} aria-label="Aktifkan halaman showroom publik"
                onCheckedChange={(v) => save({ enabled: v })} />
            </div>

            <div className="flex items-center justify-between rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
              <div>
                <p className="text-sm font-semibold">Tampilkan harga</p>
                <p className="text-xs text-muted-foreground">
                  Matikan bila harga hanya diberikan lewat marketing.
                </p>
              </div>
              <Switch data-testid={SITE_PLAN.sharePriceToggle} checked={cfg?.show_price !== false}
                disabled={busy} aria-label="Tampilkan harga di halaman publik"
                onCheckedChange={(v) => save({ show_price: v }, { silent: true })} />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="shareshowroomdialog-kalimat-sambutan">Kalimat sambutan</Label>
              <Input id="shareshowroomdialog-kalimat-sambutan" data-testid={SITE_PLAN.shareHeadline} value={cfg?.headline || ""}
                placeholder="mis. Hunian asri 10 menit ke pusat kota"
                onChange={(e) => setCfg((c) => ({ ...c, headline: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="shareshowroomdialog-nomor-whatsapp-marketing">Nomor WhatsApp marketing</Label>
              <Input id="shareshowroomdialog-nomor-whatsapp-marketing" data-testid={SITE_PLAN.shareWa} value={cfg?.contact_wa || ""}
                placeholder="mis. 081234567890"
                onChange={(e) => setCfg((c) => ({ ...c, contact_wa: e.target.value }))} />
            </div>

            {cfg?.enabled && fullUrl ? (
              <div className="space-y-1.5 rounded-xl border bg-secondary/40 p-3">
                <Label>Tautan yang dibagikan</Label>
                <Input data-testid={SITE_PLAN.shareLink} readOnly value={fullUrl}
                  aria-label="Tautan showroom publik" className="bg-card text-xs" />
                <div className="flex flex-wrap gap-2 pt-1">
                  <Button size="sm" variant="outline" data-testid={SITE_PLAN.shareCopy} onClick={copy}>
                    <Copy className="mr-1.5 h-3.5 w-3.5" /> Salin tautan
                  </Button>
                  <Button size="sm" variant="outline" data-testid={SITE_PLAN.shareOpen} asChild>
                    <a href={cfg.path} target="_blank" rel="noreferrer">
                      <ExternalLink className="mr-1.5 h-3.5 w-3.5" /> Buka halaman
                    </a>
                  </Button>
                  <Button size="sm" variant="ghost" data-testid={SITE_PLAN.shareRegen} disabled={busy}
                    onClick={() => save({ enabled: true, regenerate: true })}>
                    <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Putar ulang tautan
                  </Button>
                </div>
              </div>
            ) : null}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Tutup</Button>
          <Button data-testid={SITE_PLAN.shareSave} disabled={busy || loading}
            onClick={() => save({})}>
            {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
            Simpan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
