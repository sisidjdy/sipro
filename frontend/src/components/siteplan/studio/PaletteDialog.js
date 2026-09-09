import React, { useEffect, useMemo, useState } from "react";
import { RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BUILD_KEYS, SALES_KEYS, defaultPalette, mergePalette } from "@/components/siteplan/studio/studioPalette";
import { useReference } from "@/context/ReferenceContext";
import { STUDIO } from "@/constants/testIds";

const GROUPS = [
  ["sales", "Status penjualan", SALES_KEYS],
  ["build", "Progres pembangunan", BUILD_KEYS],
  ["mapping", "Pemetaan", ["mapped", "unmapped", "none"]],
];

/** Editor palet warna per status — berlaku untuk seluruh organisasi (studio, legenda, ekspor PNG). */
export default function PaletteDialog({ open, onOpenChange, palette, onSave, canEdit }) {
  const { labelOf } = useReference();
  const DEFAULT_PALETTE = useMemo(() => defaultPalette(labelOf), [labelOf]);
  const [draft, setDraft] = useState(mergePalette(palette, labelOf));
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setDraft(mergePalette(palette, labelOf)); }, [open, palette, labelOf]);

  const set = (g, k, field, v) => setDraft((d) => ({ ...d, [g]: { ...d[g], [k]: { ...d[g][k], [field]: v } } }));
  const resetGroup = (g) => setDraft((d) => ({ ...d, [g]: JSON.parse(JSON.stringify(DEFAULT_PALETTE[g])) }));

  const save = async () => {
    setBusy(true);
    try {
      const diff = {};
      for (const [g] of GROUPS) {
        for (const k of Object.keys(draft[g])) {
          const cur = draft[g][k]; const def = DEFAULT_PALETTE[g][k];
          const changed = Object.fromEntries(["fill", "stroke", "text", "label"].filter((f) => cur[f] !== def[f]).map((f) => [f, cur[f]]));
          if (Object.keys(changed).length) (diff[g] ||= {})[k] = changed;
        }
      }
      await onSave(diff);
      onOpenChange(false);
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={STUDIO.paletteDialog} className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Atur warna status</DialogTitle>
          <DialogDescription>
            Rumah punya dua status paralel — <strong>penjualan</strong> (tahapan customer) dan <strong>pembangunan</strong> (progres fisik).
            Warna di sini dipakai kanvas, legenda, dan ekspor PNG untuk seluruh tim.
          </DialogDescription>
        </DialogHeader>
        {!canEdit ? (
          <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-800">
            Hanya bisa melihat — mengubah palet memerlukan izin ubah proyek (projects:update).
          </p>
        ) : null}
        <Tabs defaultValue="sales">
          <TabsList>{GROUPS.map(([g, label]) => <TabsTrigger key={g} value={g} data-testid={`${STUDIO.paletteTab}-${g}`}>{label}</TabsTrigger>)}</TabsList>
          {GROUPS.map(([g, , keys]) => (
            <TabsContent key={g} value={g} className="space-y-1.5">
              <div className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-x-3 px-1 text-[11px] text-muted-foreground">
                <span>Status</span><span>Isi</span><span>Garis</span><span>Teks</span>
              </div>
              {keys.map((k) => (
                <div key={k} data-testid={`${STUDIO.paletteRow}-${k}`} className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-x-3 rounded-md border px-2 py-1">
                  <div className="flex items-center gap-2">
                    <span className="inline-block h-5 w-8 rounded-sm" style={{ background: draft[g][k].fill, border: `2px solid ${draft[g][k].stroke}` }} />
                    <Input value={draft[g][k].label} disabled={!canEdit} className="h-7 text-xs disabled:opacity-80 disabled:text-foreground" aria-label={`Label ${k}`}
                      onChange={(e) => set(g, k, "label", e.target.value)} />
                  </div>
                  {["fill", "stroke", "text"].map((f) => (
                    <input key={f} type="color" data-testid={`${STUDIO.paletteColor}-${k}-${f}`} value={draft[g][k][f]} disabled={!canEdit}
                      aria-label={`${f} ${k}`} onChange={(e) => set(g, k, f, e.target.value)} className="h-7 w-9 cursor-pointer rounded border bg-transparent" />
                  ))}
                </div>
              ))}
              <Button size="sm" variant="ghost" disabled={!canEdit} onClick={() => resetGroup(g)} data-testid={`${STUDIO.paletteReset}-${g}`}>
                <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> Kembalikan bawaan kelompok ini
              </Button>
            </TabsContent>
          ))}
        </Tabs>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Tutup</Button>
          <Button data-testid={STUDIO.paletteSave} disabled={!canEdit || busy} onClick={save}>{busy ? "Menyimpan…" : "Simpan palet"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
