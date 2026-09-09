import React from "react";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import { GL } from "@/constants/testIds";

export default function JournalDetailSheet({ journal, open, onOpenChange }) {
  if (!journal) return null;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={GL.journalDetail} className="w-full overflow-y-auto sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>{journal.entry_no}</SheetTitle>
          <SheetDescription>{formatDateWIB(journal.date)} · {journal.auto ? "Otomatis" : "Manual"} · {journal.posted_by}</SheetDescription>
        </SheetHeader>
        <div className="mt-5 space-y-4">
          <p className="rounded-lg bg-secondary p-3 text-sm">{journal.memo}</p>
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Akun</TableHead><TableHead className="text-right">Debit</TableHead><TableHead className="text-right">Kredit</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {journal.lines.map((ln, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-sm"><span className="tabular-nums text-muted-foreground">{ln.account_code}</span> {ln.account_name}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{ln.debit ? formatIDR(ln.debit) : "-"}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{ln.credit ? formatIDR(ln.credit) : "-"}</TableCell>
                  </TableRow>
                ))}
                <TableRow className="border-t-2">
                  <TableCell className="font-semibold">Total</TableCell>
                  <TableCell className="text-right tabular-nums font-semibold">{formatIDR(journal.total_debit)}</TableCell>
                  <TableCell className="text-right tabular-nums font-semibold">{formatIDR(journal.total_credit)}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
