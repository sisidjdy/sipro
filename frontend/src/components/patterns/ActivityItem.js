import React from "react";
import { Bot } from "lucide-react";
import { fromNow, initials } from "@/utils/formatters";
import { cn } from "@/lib/utils";

export default function ActivityItem({ activity }) {
  const isSystem = activity.type === "system" || activity.actor === "system";
  return (
    <div className="flex gap-3">
      <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
        isSystem ? "bg-secondary text-muted-foreground" : "bg-accent text-accent-foreground")}>
        {isSystem ? <Bot className="h-4 w-4" /> : initials(activity.actor)}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-snug">{activity.body}</p>
        <p className="text-[11px] text-muted-foreground mt-0.5">
          {isSystem ? "Sistem" : activity.actor} · {fromNow(activity.created_at)}
        </p>
      </div>
    </div>
  );
}
