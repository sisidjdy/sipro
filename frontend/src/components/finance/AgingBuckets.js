import React from "react";
import { cn } from "@/lib/utils";
import { formatIDR } from "@/utils/formatters";
import { FINANCE } from "@/constants/testIds";

const BUCKETS = [
  { key: "current", label: "Lancar", tone: "text-emerald-700", ring: "border-emerald-200" },
  { key: "1-30", label: "1\u201330 hari", tone: "text-sky-700", ring: "border-sky-200" },
  { key: "31-60", label: "31\u201360 hari", tone: "text-amber-700", ring: "border-amber-200" },
  { key: "61-90", label: "61\u201390 hari", tone: "text-orange-700", ring: "border-orange-200" },
  { key: ">90", label: "> 90 hari", tone: "text-rose-700", ring: "border-rose-200" },
];

/** Bucket aging; bila `onSelect` diberikan, tiap bucket bisa diklik untuk rincian. */
export default function AgingBuckets({ buckets, title, onSelect }) {
  const b = buckets || {};
  const Tag = onSelect ? "button" : "div";
  return (
    <div className="space-y-2">
      {title ? <p className="text-xs font-medium text-muted-foreground">{title}</p> : null}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {BUCKETS.map((bk) => (
          <Tag key={bk.key} data-testid={FINANCE.agingBucket} data-bucket={bk.key}
            type={onSelect ? "button" : undefined}
            onClick={onSelect ? () => onSelect(bk.key, bk.label) : undefined}
            className={cn("rounded-xl border bg-card p-3 text-left shadow-sm", bk.ring,
              onSelect && "transition-[box-shadow,transform] hover:shadow-md active:scale-[0.99]")}>
            <p className="text-[11px] font-medium text-muted-foreground">{bk.label}</p>
            <p className={cn("mt-1 text-base font-semibold tabular-nums", bk.tone)}>
              {formatIDR(b[bk.key] || 0)}
            </p>
          </Tag>
        ))}
      </div>
    </div>
  );
}
