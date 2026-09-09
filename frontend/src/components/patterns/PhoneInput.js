import React from "react";
import { Input } from "@/components/ui/input";

/**
 * PhoneInput — awalan +62 TETAP; pemakai hanya mengetik nomor lokalnya (812…).
 * Nilai yang dikeluarkan selalu E.164 (`+62812…`) supaya integrasi WA tidak salah format.
 * Angka 0 di depan dan awalan 62/+62 yang ikut ditempel otomatis dibuang.
 */
export const toE164 = (local) => {
  const d = String(local || "").replace(/\D/g, "");
  if (!d) return "";
  let n = d;
  if (n.startsWith("62")) n = n.slice(2);
  if (n.startsWith("0")) n = n.replace(/^0+/, "");
  return n ? `+62${n}` : "";
};

export const toLocal = (e164) => {
  const d = String(e164 || "").replace(/\D/g, "");
  if (d.startsWith("62")) return d.slice(2);
  if (d.startsWith("0")) return d.replace(/^0+/, "");
  return d;
};

export default function PhoneInput({ id, value, onChange, testId, placeholder = "812xxxxxxx", className = "", ...props }) {
  return (
    <div className={`flex ${className}`}>
      <span data-testid={testId ? `${testId}-prefix` : undefined}
        className="inline-flex select-none items-center rounded-l-md border border-r-0 border-input bg-muted px-3 text-sm font-medium text-muted-foreground">
        +62
      </span>
      <Input id={id} data-testid={testId} inputMode="numeric" autoComplete="tel-national"
        className="rounded-l-none" placeholder={placeholder} value={toLocal(value)}
        aria-label={props["aria-label"] || "Nomor telepon (tanpa +62)"}
        onChange={(e) => onChange(toE164(e.target.value))} {...props} />
    </div>
  );
}
