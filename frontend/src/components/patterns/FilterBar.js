import React from "react";
import { Filter, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { FILTER } from "@/constants/testIds";

/**
 * FilterBar — filter DEKLARATIF untuk semua daftar (blueprint IA V2 §5).
 *
 * Kenapa deklaratif: sebelum Fase 40 tiap halaman menulis UI filternya sendiri, jadi
 * (a) perilakunya beda-beda, (b) sebagian halaman tidak punya filter sama sekali, dan
 * (c) tidak ada satu pun yang bisa dijamin oleh gate. Sekarang halaman hanya
 * MENDESKRIPSIKAN filternya; tampilan, chip aktif, dan reset selalu sama.
 *
 * filters: [
 *   { key, label, type: "multiselect"|"select", options: [{value,label}] },
 *   { key, label, type: "text", placeholder },
 *   { key, label, type: "daterange", fromKey, toKey },
 * ]
 */
function chipText(f, value, labelFor) {
  if (f.type === "daterange") {
    const from = value[f.fromKey];
    const to = value[f.toKey];
    if (!from && !to) return null;
    return `${f.label}: ${from || "…"} → ${to || "…"}`;
  }
  const v = value[f.key];
  if (Array.isArray(v)) {
    if (!v.length) return null;
    return `${f.label}: ${v.map((x) => labelFor(f, x)).join(", ")}`;
  }
  return v ? `${f.label}: ${labelFor(f, v)}` : null;
}

export default function FilterBar({
  filters = [], value = {}, onChange, onReset, testId = FILTER.bar,
}) {
  const labelFor = (f, v) => (f.options || []).find((o) => String(o.value) === String(v))?.label
    || v;

  const toggleMulti = (key, optValue) => {
    const cur = Array.isArray(value[key]) ? value[key] : [];
    const next = cur.includes(optValue) ? cur.filter((x) => x !== optValue) : [...cur, optValue];
    onChange?.({ [key]: next });
  };

  const activeChips = filters.map((f) => ({ f, text: chipText(f, value, labelFor) }))
    .filter((x) => x.text);

  return (
    <div data-testid={testId} className="flex flex-wrap items-center gap-2">
      {filters.map((f) => {
        const count = f.type === "daterange"
          ? [value[f.fromKey], value[f.toKey]].filter(Boolean).length
          : (Array.isArray(value[f.key]) ? value[f.key].length : (value[f.key] ? 1 : 0));
        return (
          <Popover key={f.key}>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm" data-testid={`${FILTER.trigger}-${f.key}`}
                className={cn(count && "border-primary text-primary")}>
                <Filter className="mr-1.5 h-3.5 w-3.5" /> {f.label}
                {count ? (
                  <span className="ml-1.5 rounded bg-primary/10 px-1 text-xs tabular-nums">
                    {count}
                  </span>
                ) : null}
              </Button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-64 bg-popover p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {f.label}
              </p>
              {f.type === "text" ? (
                <div className="space-y-1.5">
                  <Label htmlFor={`${FILTER.text}-${f.key}`} className="text-xs">{f.label}</Label>
                  <Input id={`${FILTER.text}-${f.key}`} data-testid={`${FILTER.text}-${f.key}`}
                    aria-label={f.label} placeholder={f.placeholder || f.label}
                    className="bg-background"
                    value={value[f.key] || ""}
                    onChange={(e) => onChange?.({ [f.key]: e.target.value })} />
                </div>
              ) : null}
              {f.type === "daterange" ? (
                <div className="space-y-2">
                  <div className="space-y-1.5">
                    <Label htmlFor={`${FILTER.from}-${f.key}`} className="text-xs">Dari tanggal</Label>
                    <Input id={`${FILTER.from}-${f.key}`} type="date" className="bg-background"
                      data-testid={`${FILTER.from}-${f.key}`} value={value[f.fromKey] || ""}
                      onChange={(e) => onChange?.({ [f.fromKey]: e.target.value })} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor={`${FILTER.to}-${f.key}`} className="text-xs">Sampai tanggal</Label>
                    <Input id={`${FILTER.to}-${f.key}`} type="date" className="bg-background"
                      data-testid={`${FILTER.to}-${f.key}`} value={value[f.toKey] || ""}
                      onChange={(e) => onChange?.({ [f.toKey]: e.target.value })} />
                  </div>
                </div>
              ) : null}
              {f.type === "multiselect" || f.type === "select" ? (
                <div className="max-h-64 space-y-1 overflow-y-auto">
                  {(f.options || []).map((o) => {
                    const checked = f.type === "multiselect"
                      ? (value[f.key] || []).includes(o.value)
                      : String(value[f.key] || "") === String(o.value);
                    const id = `${FILTER.option}-${f.key}-${o.value}`;
                    return (
                      <label key={o.value} htmlFor={id}
                        className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-sm hover:bg-secondary">
                        <Checkbox id={id} data-testid={id} checked={checked}
                          onCheckedChange={() => (f.type === "multiselect"
                            ? toggleMulti(f.key, o.value)
                            : onChange?.({ [f.key]: checked ? "" : o.value }))} />
                        <span>{o.label}</span>
                        {o.hint !== undefined ? (
                          <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                            {o.hint}
                          </span>
                        ) : null}
                      </label>
                    );
                  })}
                </div>
              ) : null}
            </PopoverContent>
          </Popover>
        );
      })}

      {activeChips.map(({ f, text }) => (
        <span key={`chip-${f.key}`} data-testid={`${FILTER.chip}-${f.key}`}
          className="inline-flex max-w-[18rem] items-center gap-1 rounded-md border bg-accent px-2 py-1 text-xs text-accent-foreground">
          <span className="truncate" title={text}>{text}</span>
          <button type="button" aria-label={`Hapus filter ${f.label}`}
            data-testid={`${FILTER.chipClear}-${f.key}`}
            onClick={() => onChange?.(f.type === "daterange"
              ? { [f.fromKey]: "", [f.toKey]: "" }
              : { [f.key]: Array.isArray(value[f.key]) ? [] : "" })}>
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}

      {activeChips.length ? (
        <Button variant="ghost" size="sm" data-testid={FILTER.reset} onClick={onReset}>
          Reset filter
        </Button>
      ) : null}
    </div>
  );
}
