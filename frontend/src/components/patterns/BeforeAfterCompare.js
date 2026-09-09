import React, { useState } from "react";
import { ArrowRight, CheckCircle2, Clock, GripVertical } from "lucide-react";

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import { formatDateWIB } from "@/utils/formatters";
import { photoSrc } from "@/utils/photoSrc";
import { FIELD } from "@/constants/testIds";

/** Penggeser pembanding: satu foto sebelum vs satu foto sesudah dalam satu bingkai. */
function CompareSlider({ before, after, portal, alt }) {
  const [pos, setPos] = useState(50);
  return (
    <div data-testid={FIELD.repairSlider} className="relative overflow-hidden rounded-lg border bg-secondary">
      <div className="relative aspect-[16/10] w-full select-none">
        <img src={photoSrc(after, { portal })} alt={`Sesudah: ${alt}`}
          className="absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0 overflow-hidden" style={{ width: `${pos}%` }}>
          <img src={photoSrc(before, { portal })} alt={`Sebelum: ${alt}`}
            className="h-full w-full object-cover"
            style={{ width: `${10000 / Math.max(pos, 1)}%`, maxWidth: "none" }} />
        </div>
        <div className="pointer-events-none absolute inset-y-0 z-10 w-0.5 bg-white shadow"
          style={{ left: `${pos}%` }}>
          <span className="absolute left-1/2 top-1/2 grid h-7 w-7 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-white shadow ring-1 ring-black/10">
            <GripVertical className="h-4 w-4 text-slate-600" />
          </span>
        </div>
        <span className="pointer-events-none absolute bottom-2 left-2 rounded bg-black/65 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
          Sebelum
        </span>
        <span className="pointer-events-none absolute bottom-2 right-2 rounded bg-emerald-600/90 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
          Sesudah
        </span>
      </div>
      <input type="range" min={0} max={100} value={pos} aria-label="Geser untuk membandingkan foto sebelum dan sesudah"
        onChange={(e) => setPos(Number(e.target.value))}
        className="w-full cursor-ew-resize accent-primary" />
    </div>
  );
}

function Side({ label, photos, portal, tone, onOpen, emptyText }) {
  return (
    <div className="min-w-0 flex-1">
      <p className={`mb-1 text-[10px] font-semibold uppercase tracking-wide ${tone}`}>{label}</p>
      {photos.length ? (
        <div className="grid grid-cols-2 gap-1.5">
          {photos.map((p, i) => (
            <button key={`${p.file_id || "inline"}-${i}`} type="button" onClick={() => onOpen(p)}
              aria-label={`Perbesar foto ${label.toLowerCase()}`}
              className="overflow-hidden rounded-md border bg-secondary/60">
              <img src={photoSrc(p, { portal, variant: "thumb" })} alt={p.label || label}
                loading="lazy"
                className="h-20 w-full object-cover transition-transform duration-300 hover:scale-105" />
            </button>
          ))}
        </div>
      ) : (
        <p className="rounded-md border border-dashed px-2 py-3 text-center text-[11px] text-muted-foreground">
          {emptyText}
        </p>
      )}
    </div>
  );
}

/**
 * BeforeAfterCompare — bukti kerja BERPASANGAN per temuan (sebelum → sesudah).
 *
 * Galeri rata sebelumnya tidak menjelaskan foto mana "sebelum" dan mana "sesudah" untuk
 * temuan yang sama, sehingga pembeli tidak bisa menilai perbaikan. Kartu ini memasangkan
 * keduanya, menyebut tanggal, catatan pengerjaan, dan status yang jujur: temuan yang masih
 * ditangani TETAP tampil (tanpa foto sesudah) — bukan disembunyikan agar terlihat beres.
 */
export default function BeforeAfterCompare({
  repairs = [], portal = false, emptyText = "Belum ada bukti perbaikan pada kavling ini.",
}) {
  const [zoom, setZoom] = useState(null);
  const list = repairs || [];

  if (!list.length) {
    return <p className="text-xs text-muted-foreground">{emptyText}</p>;
  }

  return (
    <>
      <div className="space-y-3">
        {list.map((r) => {
          const before = r.before || [];
          const after = r.after || [];
          const single = before.length === 1 && after.length === 1;
          return (
            <div key={r.punch_id} data-testid={FIELD.repairPair}
              data-repair-resolved={r.resolved ? "1" : "0"}
              className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <p className="min-w-0 truncate text-sm font-semibold">{r.title}</p>
                <span className="flex shrink-0 items-center gap-1.5">
                  {r.severity ? <StatusPill status={r.severity} group="punch_severity" /> : null}
                  {r.resolved ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-800">
                      <CheckCircle2 className="h-3 w-3" /> Sudah diperbaiki
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800">
                      <Clock className="h-3 w-3" /> Sedang ditangani
                    </span>
                  )}
                </span>
              </div>

              {single ? (
                <CompareSlider before={before[0]} after={after[0]} portal={portal} alt={r.title} />
              ) : (
                <div className="flex items-start gap-2">
                  <Side label="Sebelum" photos={before} portal={portal} tone="text-rose-700"
                    onOpen={setZoom} emptyText="Tidak ada foto temuan" />
                  <ArrowRight className="mt-6 h-4 w-4 shrink-0 text-muted-foreground" />
                  <Side label="Sesudah" photos={after} portal={portal} tone="text-emerald-700"
                    onOpen={setZoom} emptyText="Menunggu bukti perbaikan" />
                </div>
              )}

              {r.note ? (
                <p className="mt-2 rounded-md bg-secondary/60 px-2.5 py-1.5 text-xs">
                  <span className="font-medium">Pengerjaan:</span> {r.note}
                </p>
              ) : null}
              <p className="mt-1.5 text-[11px] text-muted-foreground">
                Dilaporkan {formatDateWIB(r.opened_at)}
                {r.fixed_at ? ` · diperbaiki ${formatDateWIB(r.fixed_at)}` : ""}
              </p>
            </div>
          );
        })}
      </div>

      <Dialog open={!!zoom} onOpenChange={(v) => !v && setZoom(null)}>
        <DialogContent data-testid={FIELD.lightbox} className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle className="text-base">{zoom?.label || "Dokumentasi perbaikan"}</DialogTitle>
            <DialogDescription>{formatDateWIB(zoom?.date)}</DialogDescription>
          </DialogHeader>
          {zoom ? (
            <img src={photoSrc(zoom, { portal })} alt={zoom.label || "Dokumentasi perbaikan"}
              className="max-h-[70vh] w-full rounded-lg border bg-secondary object-contain" />
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
