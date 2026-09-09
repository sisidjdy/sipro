import React, { useRef, useState } from "react";
import { Download, FileUp, ImagePlus, ImageOff, ListOrdered, MousePointer2, Palette, PenTool, Sparkles, Trash2, Undo2, Wand2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import PaletteDialog from "@/components/siteplan/studio/PaletteDialog";
import { COLOR_MODES } from "@/components/siteplan/studio/studioPalette";
import { useAuth } from "@/context/AuthContext";
import { STUDIO } from "@/constants/testIds";

const TOOLS = [
  ["select", MousePointer2, "Pilih", "Klik bentuk untuk melihat & memetakan"],
  ["draw", PenTool, "Gambar kavling", "Klik titik sudut di atas gambar/SVG, Enter untuk menutup"],
  ["sequence", ListOrdered, "Berurutan", "Klik kavling kosong satu per satu — unit terisi berurutan"],
];

/** Toolbar Studio: sumber peta (SVG / gambar latar), alat kanvas, aksi otomatis. */
export default function StudioToolbar({ s, bgOpacity, setBgOpacity }) {
  const svgRef = useRef(null);
  const imgRef = useRef(null);
  const [pdfPage, setPdfPage] = useState(1);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const { can } = useAuth();
  const bg = s.plan?.background;
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-card px-3 py-2 shadow-[var(--shadow-card)]">
      <div className="flex items-center gap-1 rounded-lg border bg-muted/40 p-1">
        {TOOLS.map(([key, Icon, label, hint]) => (
          <Button key={key} size="sm" variant={s.tool === key ? "default" : "ghost"} title={hint}
            data-testid={STUDIO[`tool${key[0].toUpperCase()}${key.slice(1)}`]} aria-pressed={s.tool === key}
            disabled={key === "sequence" && !s.plan}
            onClick={() => s.setTool(key)} className="h-8">
            <Icon className="mr-1.5 h-3.5 w-3.5" /> {label}
          </Button>
        ))}
      </div>
      <span className="mx-1 hidden h-6 w-px bg-border sm:block" />
      <input ref={svgRef} data-testid={STUDIO.uploadSvg} type="file" accept=".svg,image/svg+xml" className="hidden"
        aria-label="Unggah SVG site plan" onChange={(e) => { const f = e.target.files?.[0]; if (f) s.uploadSvg(f); e.target.value = ""; }} />
      <input ref={imgRef} data-testid={STUDIO.uploadImage} type="file" accept="image/png,image/jpeg,image/webp,application/pdf,.pdf" className="hidden"
        aria-label="Unggah gambar/PDF latar" onChange={(e) => { const f = e.target.files?.[0]; if (f) s.uploadImage(f, pdfPage); e.target.value = ""; }} />
      <Button size="sm" variant="outline" disabled={!!s.busy} onClick={() => svgRef.current?.click()}>
        <FileUp className="mr-1.5 h-3.5 w-3.5" /> {s.busy === "svg" ? "Membaca SVG…" : "Unggah SVG"}
      </Button>
      <Button size="sm" variant="outline" disabled={!!s.busy} onClick={() => imgRef.current?.click()}>
        <ImagePlus className="mr-1.5 h-3.5 w-3.5" /> {s.busy === "image" ? "Merender…" : "Latar (PNG/JPG/PDF)"}
      </Button>
      <label className="flex items-center gap-1 text-[11px] text-muted-foreground" title="Halaman PDF yang dirender sebagai latar">
        hal. PDF
        <input data-testid={STUDIO.pdfPage} type="number" min={1} max={bg?.pdf_pages || 99} value={pdfPage}
          onChange={(e) => setPdfPage(Math.max(1, Number(e.target.value) || 1))} className="h-7 w-12 rounded border bg-background px-1 text-xs" aria-label="Halaman PDF" />
        {bg?.source === "pdf" ? <span className="rounded bg-muted px-1">{bg.pdf_page}/{bg.pdf_pages}</span> : null}
      </label>
      {s.plan?.background ? (
        <div className="flex items-center gap-2 rounded-md border px-2 py-1">
          <label htmlFor="bg-opacity" className="text-[11px] text-muted-foreground">Latar</label>
          <input id="bg-opacity" data-testid={STUDIO.opacity} type="range" min={0.1} max={1} step={0.1}
            value={bgOpacity} onChange={(e) => setBgOpacity(Number(e.target.value))} className="w-20" />
          <Button size="icon" variant="ghost" className="h-6 w-6" data-testid={STUDIO.removeImage}
            aria-label="Lepas gambar latar" onClick={s.removeImage}><ImageOff className="h-3.5 w-3.5" /></Button>
        </div>
      ) : null}
      <span className="mx-1 hidden h-6 w-px bg-border sm:block" />
      <Button size="sm" variant="outline" data-testid={STUDIO.undo} disabled={!s.canUndo || !!s.busy} onClick={s.undo}
        title="Batalkan langkah terakhir pada bentuk (Ctrl+Z)">
        <Undo2 className="mr-1.5 h-3.5 w-3.5" /> Undo
      </Button>
      <Select value={s.colorMode} onValueChange={s.setColorMode}>
        <SelectTrigger data-testid={STUDIO.colorMode} className="h-8 w-[13rem] text-xs" aria-label="Mode warna kavling">
          <Palette className="mr-1.5 h-3.5 w-3.5 shrink-0" />
          <span className="truncate">Warna: {COLOR_MODES.find((m) => m.key === s.colorMode)?.label}</span>
        </SelectTrigger>
        <SelectContent>
          {COLOR_MODES.map((m) => (
            <SelectItem key={m.key} value={m.key} title={m.hint}>
              <span className="block">{m.label}</span>
              <span className="block text-[10px] text-muted-foreground">{m.hint}</span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button size="sm" variant="ghost" data-testid={STUDIO.paletteOpen} onClick={() => setPaletteOpen(true)} title="Atur warna tiap status (berlaku untuk seluruh tim)">
        Atur warna
      </Button>
      <PaletteDialog open={paletteOpen} onOpenChange={setPaletteOpen} palette={s.data?.palette}
        canEdit={can("projects", "update")} onSave={s.savePalette} />
      <Button size="sm" variant="outline" data-testid={STUDIO.exportPng} disabled={!s.plan || !!s.busy} onClick={s.exportPng}
        title="Unduh PNG peta (dengan warna aktif) untuk brosur / WhatsApp">
        <Download className="mr-1.5 h-3.5 w-3.5" /> {s.busy === "export" ? "Merender…" : "Ekspor PNG"}
      </Button>
      <Button size="sm" variant="outline" data-testid={STUDIO.autoMatch} disabled={!s.plan || !!s.busy} onClick={s.autoMatch}
        title="Cocokkan label kavling di peta dengan kode unit (toleran tanda pisah & nol depan)">
        <Wand2 className="mr-1.5 h-3.5 w-3.5" /> Cocokkan otomatis
      </Button>
      {!s.plan ? (
        <Button size="sm" variant="ghost" data-testid={STUDIO.generate} disabled={!!s.busy || !s.units.length} onClick={s.generate}
          title="Peta contoh dari daftar unit — untuk mencoba fitur sebelum gambar asli ada">
          <Sparkles className="mr-1.5 h-3.5 w-3.5" /> Peta contoh
        </Button>
      ) : (
        <Button size="sm" variant="ghost" data-testid={STUDIO.deletePlan} disabled={!!s.busy} className="text-destructive"
          onClick={() => { if (window.confirm("Hapus seluruh peta proyek ini? Unit tidak ikut terhapus.")) s.deletePlan(); }}>
          <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Hapus peta
        </Button>
      )}
    </div>
  );
}
