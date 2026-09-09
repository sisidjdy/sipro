import React from "react";
import { Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * SearchInput — kotak pencarian dengan AFORDANSI (Fase 67).
 *
 * Sebelum ini banyak halaman memakai `<Input placeholder="Cari…">` polos: kotak abu tanpa
 * ikon, warnanya nyaris sama dengan latar, sehingga pemakai tidak langsung tahu itu kolom
 * pencarian. Di sini ikon kaca pembesar melekat pada field, field punya latar & bayangan
 * sendiri, dan keadaan fokus memberi cincin yang jelas.
 */
export default function SearchInput({ value, onChange, placeholder = "Cari…", className,
  testId, ariaLabel, ...rest }) {
  return (
    <div className={cn("relative", className)}>
      <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
      <Input data-testid={testId} value={value} placeholder={placeholder}
        aria-label={ariaLabel || placeholder}
        onChange={(e) => onChange?.(e.target.value, e)}
        className="search-field pl-9" {...rest} />
    </div>
  );
}
