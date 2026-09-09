import React, { useState } from "react";
import { Camera, MapPin } from "lucide-react";

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { formatDateWIB } from "@/utils/formatters";
import { photoSrc, scopeLabel } from "@/utils/photoSrc";
import { FIELD } from "@/constants/testIds";

/**
 * PhotoGallery — galeri foto lapangan dengan lightbox.
 *
 * Menerima kontrak foto backend (`{file_id|inline, label, date, scope}`) sehingga
 * berkas object storage maupun data URL warisan sama-sama tampil. Dipakai staf
 * (drawer kavling, buku harian, punch list) dan pembeli (portal, token portal).
 */
export default function PhotoGallery({
  photos = [], portal = false, columns = 3, emptyText, testId = FIELD.gallery,
  itemTestId = FIELD.galleryItem, showMeta = true,
}) {
  const [open, setOpen] = useState(null);
  const list = (photos || []).filter((p) => photoSrc(p, { portal }));

  if (!list.length) {
    return emptyText ? (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Camera className="h-3.5 w-3.5" /> {emptyText}
      </p>
    ) : null;
  }

  const cols = columns === 2 ? "grid-cols-2" : columns === 4
    ? "grid-cols-2 sm:grid-cols-4" : "grid-cols-2 sm:grid-cols-3";

  return (
    <>
      <div data-testid={testId} className={`grid gap-2 ${cols}`}>
        {list.map((p, i) => (
          <button key={`${p.file_id || "inline"}-${i}`} type="button"
            data-testid={itemTestId} data-photo-scope={p.scope || "proyek"}
            aria-label={`Perbesar foto: ${p.label || "dokumentasi lapangan"}`}
            onClick={() => setOpen(p)}
            className="group overflow-hidden rounded-lg border bg-secondary/40 text-left transition-shadow hover:shadow-md">
            <img src={photoSrc(p, { portal, variant: "thumb" })}
              alt={p.label || "Dokumentasi lapangan"} loading="lazy"
              className="h-24 w-full object-cover transition-transform duration-300 group-hover:scale-105" />
            {showMeta ? (
              <span className="block px-1.5 py-1">
                <span className="block truncate text-[11px] font-medium">{p.label || "Dokumentasi"}</span>
                <span className="block text-[10px] text-muted-foreground">
                  {formatDateWIB(p.date)}{p.scope ? ` · ${scopeLabel(p.scope)}` : ""}
                </span>
              </span>
            ) : null}
          </button>
        ))}
      </div>

      <Dialog open={!!open} onOpenChange={(v) => !v && setOpen(null)}>
        <DialogContent data-testid={FIELD.lightbox} className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle className="text-base">{open?.label || "Dokumentasi lapangan"}</DialogTitle>
            <DialogDescription className="flex items-center gap-1.5">
              <MapPin className="h-3.5 w-3.5" />
              {formatDateWIB(open?.date)}{open?.scope ? ` · ${scopeLabel(open.scope)}` : ""}
            </DialogDescription>
          </DialogHeader>
          {open ? (
            <img src={photoSrc(open, { portal })} alt={open.label || "Dokumentasi lapangan"}
              className="max-h-[70vh] w-full rounded-lg border bg-secondary object-contain" />
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
