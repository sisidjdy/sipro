import React from "react";
import { AlertTriangle, Check, CheckCheck, FileText, Image as ImageIcon, MapPin, Mic } from "lucide-react";

import { cn } from "@/lib/utils";
import { formatDateTimeWIB } from "@/utils/formatters";
import { P94 } from "@/constants/testIds";

const STATUS = {
  simulated: { label: "simulasi", Icon: Check, cls: "opacity-70" },
  queued: { label: "antre", Icon: Check, cls: "opacity-60" },
  sent: { label: "terkirim", Icon: Check, cls: "" },
  delivered: { label: "sampai", Icon: CheckCheck, cls: "" },
  read: { label: "dibaca", Icon: CheckCheck, cls: "text-sky-300" },
  failed: { label: "gagal", Icon: AlertTriangle, cls: "text-rose-200" },
};

function Media({ media }) {
  if (!media) return null;
  const base = process.env.REACT_APP_BACKEND_URL;
  const url = media.url ? (media.url.startsWith("http") ? media.url : `${base}${media.url}`) : null;
  if (media.type === "image") {
    return url ? (
      <a href={url} target="_blank" rel="noreferrer" data-testid={P94.msgMedia}>
        <img src={url} alt={media.caption || "gambar"} className="mb-1 max-h-48 rounded-lg object-cover" />
      </a>
    ) : <span data-testid={P94.msgMedia} className="mb-1 inline-flex items-center gap-1 text-xs opacity-80"><ImageIcon className="h-3.5 w-3.5" /> Gambar (media belum diunduh — mode simulasi)</span>;
  }
  if (media.type === "audio") {
    return url ? <audio data-testid={P94.msgMedia} controls src={url} className="mb-1 h-8 w-full" />
      : <span data-testid={P94.msgMedia} className="mb-1 inline-flex items-center gap-1 text-xs opacity-80"><Mic className="h-3.5 w-3.5" /> Pesan suara</span>;
  }
  if (media.type === "location") {
    const href = `https://maps.google.com/?q=${media.latitude},${media.longitude}`;
    return <a data-testid={P94.msgMedia} href={href} target="_blank" rel="noreferrer" className="mb-1 inline-flex items-center gap-1 text-xs underline"><MapPin className="h-3.5 w-3.5" /> Buka lokasi</a>;
  }
  if (media.type === "document" || media.type === "video" || media.type === "sticker") {
    return url ? <a data-testid={P94.msgMedia} href={url} target="_blank" rel="noreferrer" className="mb-1 inline-flex items-center gap-1 text-xs underline"><FileText className="h-3.5 w-3.5" /> {media.filename || media.type}</a>
      : <span data-testid={P94.msgMedia} className="mb-1 inline-flex items-center gap-1 text-xs opacity-80"><FileText className="h-3.5 w-3.5" /> {media.filename || media.type}</span>;
  }
  return null;
}

export default function MessageBubble({ m }) {
  const out = m.direction === "out";
  const st = out ? STATUS[m.status] : null;
  return (
    <div className={cn("flex", out ? "justify-end" : "justify-start")}>
      <div className={cn("max-w-[75%] rounded-2xl px-3 py-2 text-sm", out ? "bg-primary text-primary-foreground" : "bg-secondary")}>
        <div className="mb-1 flex flex-wrap gap-1">
          {m.is_template ? <span className="inline-block rounded bg-black/10 px-1.5 text-[10px] font-semibold uppercase">Template</span> : null}
          {m.manual ? <span className="inline-block rounded bg-black/10 px-1.5 text-[10px] font-semibold uppercase">Manual</span> : null}
          {m.mode === "live" ? <span className="inline-block rounded bg-emerald-500/20 px-1.5 text-[10px] font-semibold uppercase">Live</span> : null}
        </div>
        <Media media={m.media} />
        <p className="whitespace-pre-line">{m.body}</p>
        <div className={cn("mt-1 flex items-center gap-1.5 text-[10px]", out ? "text-primary-foreground/70" : "text-muted-foreground")}>
          <span>{formatDateTimeWIB(m.created_at)}</span>
          {st ? (
            <span data-testid={P94.msgStatus} className={cn("inline-flex items-center gap-0.5", st.cls)} title={m.error_detail || st.label}>
              <st.Icon className="h-3 w-3" /> {st.label}
            </span>
          ) : null}
        </div>
        {m.status === "failed" && m.error_detail ? (
          <p className="mt-1 rounded bg-rose-500/20 px-1.5 py-0.5 text-[10px]">⚠ {m.error_code}: {m.error_detail}</p>
        ) : null}
      </div>
    </div>
  );
}
