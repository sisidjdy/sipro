import React from "react";
import { ArrowLeft } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * EntityHeader — kepala halaman kanonik (Profil Lead / Customer / Unit / Proyek).
 *
 * Tujuan: hierarki informasi yang jelas (judul besar, meta chip kecil, aksi di kanan)
 * supaya halaman tidak lagi "rata" seperti temuan audit UI owner.
 */
export default function EntityHeader({
  kicker, title, subtitle, chips = [], actions = null, onBack, backLabel = "Kembali",
  testId,
}) {
  const navigate = useNavigate();
  return (
    <div data-testid={testId}
      className="relative space-y-3 overflow-hidden rounded-xl border bg-card p-4 shadow-[var(--shadow-raised)]">
      <div aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-primary/50 to-transparent" />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" className="-ml-2 h-7 px-2"
              onClick={() => (onBack ? onBack() : navigate(-1))}>
              <ArrowLeft className="mr-1 h-4 w-4" /> {backLabel}
            </Button>
            {kicker ? (
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {kicker}
              </span>
            ) : null}
          </div>
          <h1 className="page-title truncate">{title}</h1>
          {subtitle ? <p className="text-sm text-muted-foreground">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {chips.length ? (
        <div className="flex flex-wrap items-stretch gap-2">
          {chips.filter(Boolean).map((c, i) => (
            <span key={`${c.label}-${i}`}
              className={cn("inline-flex min-w-[5.5rem] flex-col justify-center gap-0.5",
                "rounded-lg border border-border/80 bg-background px-2.5 py-1.5",
                "shadow-[var(--shadow-card)]")}>
              <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {c.label}
              </span>
              <span className="text-xs font-medium text-foreground">{c.value}</span>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
