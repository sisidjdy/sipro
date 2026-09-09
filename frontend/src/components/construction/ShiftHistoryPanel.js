import React from "react";
import { CalendarClock, Lock } from "lucide-react";

import RefLabel from "@/components/patterns/RefLabel";
import { fromNow } from "@/utils/formatters";
import { shortDate } from "@/utils/buildUi";
import { BUILD } from "@/constants/testIds";

/**
 * FASE 34 — riwayat penggeseran tanggal pada SATU unit.
 *
 * Pelaksana & pembeli sering bertanya "kok tenggatnya berubah?". Panel ini menjawab
 * dengan jujur: berapa hari, kenapa, oleh siapa, dan berapa pekerjaan yang tanggalnya
 * dipertahankan karena sudah diverifikasi.
 */
export default function ShiftHistoryPanel({ history }) {
  const rows = history || [];
  if (!rows.length) return null;
  return (
    <div data-testid={BUILD.historyPanel}
      className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-[11px] text-sky-900">
      <p className="flex items-center gap-1.5 text-xs font-semibold">
        <CalendarClock className="h-3.5 w-3.5" />
        Riwayat penggeseran jadwal ({rows.length})
      </p>
      <div className="mt-1.5 space-y-1.5">
        {[...rows].reverse().map((h, i) => (
          <div key={`${h.at}-${i}`} data-testid={BUILD.historyRow}
            className="rounded-lg bg-card/70 p-2">
            <p className="font-medium">
              {h.days > 0 ? "+" : ""}{h.days} hari ·{" "}
              <RefLabel group="build_delay_cause" value={h.cause} /> · {h.actor}{" "}
              <span className="font-normal text-muted-foreground">{fromNow(h.at)}</span>
            </p>
            <p>
              Mulai {shortDate(h.from_start)} → <b>{shortDate(h.to_start)}</b> · target
              selesai {shortDate(h.from_finish)} → <b>{shortDate(h.to_finish)}</b>
            </p>
            <p className="text-muted-foreground">
              {h.items_shifted} pekerjaan bergeser
              {h.items_locked ? (
                <span className="ml-1 text-amber-700">
                  <Lock className="mr-0.5 inline h-3 w-3" />
                  {h.items_locked} sudah diverifikasi — tanggalnya dipertahankan
                </span>
              ) : null}
            </p>
            {h.note ? <p className="italic">“{h.note}”</p> : null}
          </div>
        ))}
      </div>
    </div>
  );
}
