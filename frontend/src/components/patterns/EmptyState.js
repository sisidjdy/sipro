import React from "react";
import { Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { WORK } from "@/constants/testIds";

export default function EmptyState({ icon: Icon = Inbox, title, description, actionLabel,
  onAction, testId = null }) {
  return (
    <div data-testid={testId || WORK.emptyState}
      className="flex flex-col items-center justify-center rounded-xl border border-border bg-card px-6 py-12 text-center shadow-[var(--shadow-card)]">
      {/* Fase 67: keadaan kosong pun berlapis (cincin + permukaan) supaya tidak terlihat
          seperti halaman yang gagal dimuat. */}
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent text-accent-foreground ring-4 ring-accent/40">
        <Icon className="h-6 w-6" />
      </div>
      <p className="mt-3 section-title">{title}</p>
      {description ? <p className="mt-1.5 max-w-md text-sm leading-relaxed text-muted-foreground">{description}</p> : null}
      {actionLabel ? <Button className="mt-4" onClick={onAction}>{actionLabel}</Button> : null}
    </div>
  );
}
