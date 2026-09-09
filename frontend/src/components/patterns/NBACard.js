import React from "react";
import { Sparkles, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { HOME } from "@/constants/testIds";

export default function NBACard({ card, onAction }) {
  const urgent = card.priority === "urgent";
  return (
    <div
      data-testid={HOME.nbaCard}
      className={cn(
        "rounded-xl border bg-card p-3.5 shadow-sm",
        urgent ? "border-rose-200 bg-rose-50/60" : "border-accent bg-accent/40",
      )}
    >
      <div className="flex items-center gap-2">
        <Sparkles className={cn("h-4 w-4", urgent ? "text-rose-600" : "text-primary")} />
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Langkah Berikutnya
        </p>
      </div>
      <p className="mt-1.5 text-sm font-medium leading-snug">{card.title}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{card.reason}</p>
      <Button size="sm" variant={urgent ? "default" : "secondary"} className="mt-2.5"
        onClick={() => onAction && onAction(card)}>
        {card.action?.label || "Kerjakan"} <ArrowRight className="h-3.5 w-3.5 ml-1" />
      </Button>
    </div>
  );
}
