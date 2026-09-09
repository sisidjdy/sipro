import React from "react";
import { toast } from "sonner";
import { Copy, ExternalLink, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LEGAL } from "@/constants/testIds";

const ROWS = [
  { key: "privacy", label: "Privacy Policy URL", path: "/privacy" },
  { key: "terms", label: "Terms of Service URL", path: "/terms" },
  { key: "deletion", label: "User Data Deletion URL", path: "/data-deletion" },
];

const copy = async (text, label) => {
  try { await navigator.clipboard.writeText(text); toast.success(`${label} disalin.`); }
  catch { toast.error("Clipboard tidak tersedia — salin manual."); }
};

/** URL legal publik siap-salin untuk Meta App Settings › Basic (Privacy / Terms / Data Deletion). */
export default function LegalUrlsCard({ compact = false }) {
  const base = window.location.origin;
  return (
    <div data-testid={LEGAL.urlsCard} className={compact ? "space-y-2" : "space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]"}>
      <div className="flex items-center gap-2"><Globe className="h-4 w-4 text-primary" />
        <h3 className={compact ? "text-xs font-medium" : "section-title"}>URL legal untuk Meta App Review</h3></div>
      <p className="text-[11px] text-muted-foreground">
        Tempel di developers.facebook.com › App Anda › App settings › Basic. Meta mewajibkan ketiganya sebelum
        app WhatsApp bisa Live. Halaman tersedia dalam ID &amp; EN (tambahkan <code>?lang=en</code>).
      </p>
      <div className="space-y-1.5 text-xs">
        {ROWS.map((r) => {
          const url = `${base}${r.path}`;
          return (
            <div key={r.key} className="flex items-center gap-1.5">
              <span className="w-40 shrink-0 text-muted-foreground">{r.label}</span>
              <code data-testid={LEGAL.urlValue} data-key={r.key} className="flex-1 break-all rounded bg-secondary/60 px-2 py-1">{url}</code>
              <Button data-testid={LEGAL.urlCopy} data-key={r.key} size="icon" variant="ghost" aria-label={`Salin ${r.label}`} onClick={() => copy(url, r.label)}><Copy className="h-4 w-4" /></Button>
              <Button data-testid={LEGAL.urlOpen} data-key={r.key} size="icon" variant="ghost" aria-label={`Buka ${r.label}`} asChild>
                <a href={url} target="_blank" rel="noreferrer"><ExternalLink className="h-4 w-4" /></a></Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
