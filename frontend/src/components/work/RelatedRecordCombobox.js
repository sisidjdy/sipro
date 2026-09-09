import React, { useState } from "react";
import { Check, ChevronsUpDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command, CommandEmpty, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import { cn } from "@/lib/utils";
import { WORK } from "@/constants/testIds";

/** Combobox record kaitan yang BISA DICARI — dropdown biasa tidak tertelusuri saat
 *  lead/unit sudah ratusan. Pencarian menyaring label di sisi klien. */
export default function RelatedRecordCombobox({
  records, value, onChange, toLabel, disabled, placeholder, fallbackLabel,
}) {
  const [open, setOpen] = useState(false);
  const selected = records.find((r) => r.id === value);
  const label = selected && toLabel ? toLabel(selected) : (value ? fallbackLabel : null);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" role="combobox" aria-expanded={open}
          disabled={disabled} data-testid={WORK.createTaskRelatedRecord}
          className="w-full justify-between px-3 font-normal">
          <span className={cn("truncate", !label && "text-muted-foreground")}>
            {label || placeholder}
          </span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
        <Command filter={(value, search) =>
          (value.split("||")[0].toLowerCase().includes(search.toLowerCase()) ? 1 : 0)}>
          <CommandInput data-testid={WORK.createTaskRelatedSearch}
            placeholder="Ketik untuk mencari…" />
          <CommandList className="max-h-56">
            <CommandEmpty>Tidak ada data yang cocok.</CommandEmpty>
            {records.map((r) => {
              const text = toLabel ? toLabel(r) : r.id;
              return (
                <CommandItem key={r.id} value={`${text}||${r.id}`}
                  data-testid={WORK.createTaskRelatedOption}
                  onSelect={() => { onChange(r.id); setOpen(false); }}>
                  <Check className={cn("mr-2 h-4 w-4",
                    value === r.id ? "opacity-100" : "opacity-0")} />
                  <span className="truncate">{text}</span>
                </CommandItem>
              );
            })}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
