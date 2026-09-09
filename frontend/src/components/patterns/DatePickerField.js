import React from "react";
import { format, parseISO } from "date-fns";
import { id as localeId } from "date-fns/locale";
import { CalendarIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

/** DatePickerField — kalender shadcn, nilai ISO `YYYY-MM-DD`, tampilan format Indonesia. */
export default function DatePickerField({ value, onChange, testId, placeholder = "Pilih tanggal", id }) {
  const date = value ? parseISO(value) : undefined;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button id={id} type="button" variant="outline" data-testid={testId}
          className="w-full justify-start bg-background font-normal">
          <CalendarIcon className="mr-2 h-4 w-4" />
          {date ? format(date, "d MMMM yyyy", { locale: localeId }) : <span className="text-muted-foreground">{placeholder}</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar mode="single" selected={date} locale={localeId}
          onSelect={(d) => onChange(d ? format(d, "yyyy-MM-dd") : "")} initialFocus />
      </PopoverContent>
    </Popover>
  );
}
