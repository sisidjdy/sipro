import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Lock, MessageCircle, SlidersHorizontal } from "lucide-react";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { CATEGORY_ICON, CATEGORY_TONE } from "@/components/notifications/NotificationRows";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { NOTIF } from "@/constants/testIds";

/**
 * NotificationPrefsDialog — preferensi saluran notifikasi per pemakai (Fase 65).
 *
 * Sebelum ini semua orang menerima hal yang sama: pelaksana lapangan dibanjiri kabar
 * keuangan, kasir dibanjiri kabar proyek. Di sini setiap pemakai memilih, PER KATEGORI,
 * apakah kabar itu masuk daftar (`inapp`), berdenting seketika (`push`), atau ikut
 * ringkasan WhatsApp yang dikirim manual (`wa`).
 *
 * Yang SENGAJA tidak bisa dimatikan: notifikasi yang menuntut tindakan tetap masuk daftar
 * — kalau tidak, persetujuan akan menggantung tanpa ada yang tahu sebabnya. Layar
 * mengatakannya terang-terangan, bukan mematikan sakelar tanpa penjelasan.
 */
export default function NotificationPrefsDialog({ open, onOpenChange, onSaved }) {
  const { labelOf, options } = useReference();
  const [channels, setChannels] = useState(null);
  const [meta, setMeta] = useState({});
  const [saving, setSaving] = useState(false);
  const [digest, setDigest] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await api.get("/notifications/preferences");
      setChannels(res.data?.data?.channels || {});
      setMeta(res.data?.data || {});
    } catch { toast.error("Gagal memuat preferensi notifikasi."); }
  }, []);

  useEffect(() => { if (open) { load(); setDigest(null); } }, [open, load]);

  const toggle = (kat, ch) => setChannels((c) => ({
    ...c, [kat]: { ...c[kat], [ch]: !c[kat]?.[ch] },
  }));

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/notifications/preferences", { channels });
      toast.success("Preferensi notifikasi disimpan.");
      onSaved?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan preferensi.");
    } finally { setSaving(false); }
  };

  const buildDigest = async () => {
    try {
      const res = await api.get("/notifications/wa-digest");
      setDigest(res.data?.data || {});
    } catch { toast.error("Gagal menyusun ringkasan WhatsApp."); }
  };

  const kanal = options("notification_channel");
  const kategori = Object.keys(channels || {});

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={NOTIF.prefsDialog} className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-primary" /> Preferensi notifikasi
          </DialogTitle>
          <DialogDescription>
            Pilih kabar mana yang boleh mengganggu Anda — per kategori, per saluran.
            Berlaku hanya untuk akun Anda.
          </DialogDescription>
        </DialogHeader>

        <p data-testid={NOTIF.prefsLockNote}
          className="flex items-start gap-2 rounded-lg border bg-secondary/50 p-2.5 text-xs text-muted-foreground">
          <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {meta.locked_reason || "Notifikasi yang menuntut tindakan selalu masuk daftar."}
        </p>

        <div className="space-y-1.5">
          <div className="hidden items-center gap-3 px-2 text-[11px] uppercase text-muted-foreground sm:flex">
            <span className="flex-1">Kategori</span>
            {kanal.map((k) => (
              <span key={k.value} className="w-28 text-center">{k.label}</span>
            ))}
          </div>
          {kategori.map((kat) => {
            const Icon = CATEGORY_ICON[kat] || SlidersHorizontal;
            return (
              <div key={kat} data-testid={`${NOTIF.prefsRow}-${kat}`}
                className="flex flex-col gap-2 rounded-lg border bg-card px-3 py-2 sm:flex-row sm:items-center sm:gap-3 shadow-[var(--shadow-card)]">
                <span className="flex flex-1 items-center gap-2 text-sm">
                  <span className={"flex h-6 w-6 items-center justify-center rounded-full "
                    + (CATEGORY_TONE[kat] || CATEGORY_TONE.sistem)}>
                    <Icon className="h-3.5 w-3.5" />
                  </span>
                  {labelOf("notification_category", kat)}
                </span>
                <div className="flex gap-3 sm:gap-0">
                  {kanal.map((k) => (
                    <div key={k.value} className="flex w-28 items-center justify-center gap-2">
                      <Switch data-testid={`${NOTIF.prefsSwitch}-${kat}-${k.value}`}
                        id={`pref-${kat}-${k.value}`}
                        checked={!!channels?.[kat]?.[k.value]}
                        onCheckedChange={() => toggle(kat, k.value)} />
                      <Label htmlFor={`pref-${kat}-${k.value}`}
                        className="text-[11px] text-muted-foreground sm:hidden">
                        {k.label}
                      </Label>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">
              Ringkasan WhatsApp disiapkan sistem, <strong>Anda</strong> yang menekan kirim —
              tidak ada pesan yang terkirim sendiri.
            </p>
            <Button data-testid={NOTIF.waDigestBtn} variant="outline" size="sm"
              onClick={buildDigest}>
              <MessageCircle className="mr-1.5 h-4 w-4" /> Susun ringkasan
            </Button>
          </div>
          {digest ? (
            <div className="mt-2 space-y-2">
              <pre data-testid={NOTIF.waDigestText}
                className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-secondary/60 p-2 text-[11px]">
                {digest.text || digest.message}
              </pre>
              {digest.wa_link ? (
                <a href={digest.wa_link} target="_blank" rel="noreferrer"
                  className="text-xs font-medium text-primary underline">
                  Buka WhatsApp dengan pesan ini ({digest.count} hal)
                </a>
              ) : (
                <p className="text-xs text-muted-foreground">{digest.message}</p>
              )}
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Tutup</Button>
          <Button data-testid={NOTIF.prefsSave} onClick={save}
            disabled={saving || !channels}>
            {saving ? "Menyimpan…" : "Simpan preferensi"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
