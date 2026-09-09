import * as React from "react";

import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";

const MAX_DIGITS = 15;
const SIZE_RE = /(^|\s)(h-\S+|text-(xs|sm|base|lg)|text-\S*(right|center|left))(?=\s|$)/g;

/** Angka bulat → "1.500.000" (id-ID). Kosong/tidak valid → "". */
export const formatRupiahDigits = (value) => {
  if (value === "" || value === null || value === undefined) return "";
  const digits = String(value).replace(/\D/g, "").slice(0, MAX_DIGITS);
  return digits ? Number(digits).toLocaleString("id-ID") : "";
};

/**
 * Input nominal Rupiah bermasker: tampil `Rp 1.500.000` saat mengetik, menolak huruf/karakter lain,
 * tanpa desimal. `onChange` menerima event-like `{ target: { value: "1500000" } }` (string digit murni,
 * sama seperti `<input type="number">`) sehingga handler lama tidak perlu diubah.
 */
export const RupiahInput = React.forwardRef(({ value, onChange, className, prefix = "Rp", ...props }, ref) => {
  const sizeClasses = (className || "").match(SIZE_RE)?.map((s) => s.trim()) || [];
  const wrapperClass = (className || "").replace(SIZE_RE, " ").trim();
  const handle = (e) => {
    const raw = e.target.value.replace(/\D/g, "").slice(0, MAX_DIGITS);
    const clean = raw.replace(/^0+(?=\d)/, "");
    onChange?.({
      ...e,
      target: { ...e.target, value: clean, name: props.name, id: props.id },
      currentTarget: { value: clean, name: props.name, id: props.id },
    });
  };
  return (
    <div className={cn("relative min-w-0", wrapperClass)}>
      <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-muted-foreground">{prefix}</span>
      <Input
        ref={ref}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        data-rupiah-input
        className={cn("pl-9 tabular-nums", sizeClasses)}
        value={formatRupiahDigits(value)}
        onChange={handle}
        {...props}
      />
    </div>
  );
});
RupiahInput.displayName = "RupiahInput";
