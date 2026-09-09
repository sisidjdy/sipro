import React, { useCallback, useEffect, useState } from "react";
import { History, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import api from "@/services/apiClient";
import { fromNow } from "@/utils/formatters";
import { shortDate } from "@/utils/buildUi";
import { BUILD } from "@/constants/testIds";

const KIND = { schedule: "Jadwal massal", shift: "Geser tanggal serentak" };

/**
 * FASE 34 — riwayat OPERASI MASSAL.
 *
 * Operasi yang menyentuh banyak rumah sekaligus wajib bisa ditelusuri: siapa
 * menjalankannya, kapan, berapa rumah kena, dan (untuk penggeseran) apa alasannya.
 * Tanpa panel ini, perubahan tenggat massal jadi "hantu" yang tak bisa ditanyakan.
 */
export default function BulkRunsPanel({ refreshKey = 0 }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/build/bulk/runs", { params: { limit: 10 } });
      setRows(r.data.data || []);
    } catch {
      setRows([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load, refreshKey]);

  return (
    <div data-testid={BUILD.runsPanel} className="rounded-xl border bg-card p-3 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-xs font-semibold">
          <History className="h-3.5 w-3.5 text-primary" />
          Riwayat operasi massal jadwal
          <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] font-normal">
            {rows.length}
          </span>
        </p>
        <div className="flex items-center gap-1">
          <Button size="sm" variant="ghost" onClick={load} disabled={loading}
            aria-label="Muat ulang riwayat operasi massal">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </Button>
          <Button size="sm" variant="outline" onClick={() => setOpen((v) => !v)}
            data-testid={BUILD.runsToggle}>
            {open ? "Sembunyikan" : "Lihat riwayat"}
          </Button>
        </div>
      </div>

      {open ? (
        !rows.length ? (
          <p data-testid={BUILD.runsEmpty} className="mt-2 text-[11px] text-muted-foreground">
            Belum ada operasi massal. Jadwal massal & penggeseran serentak akan tercatat di sini.
          </p>
        ) : (
          <div className="mt-2 space-y-2">
            {rows.map((r) => {
              const s = r.summary || {};
              return (
                <div key={r.id} data-testid={BUILD.runsRow} data-kind={r.kind}
                  className="rounded-lg border bg-background p-2 text-[11px]">
                  <p className="font-semibold">
                    {KIND[r.kind] || r.kind} · {r.actor}{" "}
                    <span className="font-normal text-muted-foreground">
                      {fromNow(r.created_at)}
                    </span>
                  </p>
                  {r.kind === "schedule" ? (
                    <p className="text-muted-foreground">
                      {s.created || 0} jadwal dibuat · {s.items_total || 0} pekerjaan ·{" "}
                      {s.skipped || 0} dilewati · mulai {shortDate(s.first_start)} →{" "}
                      target terakhir {shortDate(s.last_finish)}
                    </p>
                  ) : (
                    <p className="text-muted-foreground">
                      {s.shifted || 0} jadwal digeser {s.shift_days > 0 ? "+" : ""}
                      {s.shift_days} hari ({s.cause_label}) · {s.items_shifted || 0} pekerjaan
                      bergeser · {s.items_locked || 0} terverifikasi dipertahankan
                      {s.note ? ` · “${s.note}”` : ""}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )
      ) : null}
    </div>
  );
}
