import React from "react";
import { cn } from "@/lib/utils";
import { formatIDR } from "@/utils/formatters";

/**
 * MoneyText — satu cara menulis uang di seluruh aplikasi: `tabular-nums`, rata kanan,
 * dan (opsional) ringkas jt/M untuk kolom sempit — nilai penuh tetap muncul di tooltip
 * supaya angka tidak pernah menjadi tebakan.
 */
const compact = (n) => {
  const v = Number(n) || 0;
  const abs = Math.abs(v);
  if (abs >= 1e12) return `Rp ${(v / 1e12).toFixed(1).replace(".", ",")} T`;
  if (abs >= 1e9) return `Rp ${(v / 1e9).toFixed(1).replace(".", ",")} M`;
  if (abs >= 1e6) return `Rp ${(v / 1e6).toFixed(0)} jt`;
  return formatIDR(v);
};

export default function MoneyText({ value, short = false, className, dash = "-" }) {
  if (value === null || value === undefined || value === "") {
    return <span className={cn("tabular-nums text-muted-foreground", className)}>{dash}</span>;
  }
  const full = formatIDR(value);
  return (
    <span title={full} data-money={String(Number(value) || 0)}
      className={cn("tabular-nums", className)}>
      {short ? compact(value) : full}
    </span>
  );
}
