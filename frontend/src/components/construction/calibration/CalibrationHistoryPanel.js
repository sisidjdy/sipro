import React, { useState } from "react";
import { History, RotateCcw, Undo2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import RefLabel from "@/components/patterns/RefLabel";
import api from "@/services/apiClient";
import { KIND_TONE, changeText, rowShift, stamp } from "@/utils/calibrationUi";
import { CALIB } from "@/constants/testIds";

/**
 * RIWAYAT KALIBRASI — siapa mengubah apa, kapan, atas dasar apa, dan bisa dikembalikan.
 *
 * Sebelum Fase 37 perubahan durasi template tidak punya jejak: template berubah begitu saja
 * lewat "simpan template" dan tidak ada yang tahu alasannya setahun kemudian. Di sini setiap
 * kalibrasi menyimpan sebelum→sesudah tiap langkah yang tersentuh, sehingga bisa dibaca dan
 * dibatalkan dengan tepat.
 */
export default function CalibrationHistoryPanel({ rows, canCalibrate, onRollback }) {
  const [all, setAll] = useState(null);
  const [busy, setBusy] = useState(false);
  const list = all || rows || [];

  const loadAll = async () => {
    setBusy(true);
    try {
      const r = await api.get("/build/calibration/history", { params: { limit: 200 } });
      setAll(r.data?.data || []);
    } catch { /* riwayat lengkap opsional: 12 terakhir tetap tampil */ }
    finally { setBusy(false); }
  };

  return (
    <div data-testid={CALIB.histPanel} className="rounded-xl border bg-card p-3 shadow-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="inline-flex items-center gap-1.5 text-sm font-semibold">
          <History className="h-4 w-4 text-primary" /> Riwayat kalibrasi
        </h3>
        {!all ? (
          <Button size="sm" variant="ghost" data-testid={CALIB.histAll} disabled={busy}
            onClick={loadAll}>
            {busy ? "Memuat…" : "Lihat semua"}
          </Button>
        ) : (
          <span className="text-[11px] text-muted-foreground">{list.length} catatan</span>
        )}
      </div>

      {!list.length ? (
        <p data-testid={CALIB.histEmpty}
          className="rounded-lg border border-dashed bg-background p-4 text-center text-xs text-muted-foreground">
          Belum ada kalibrasi. Begitu satu kalibrasi diterapkan, catatannya muncul di sini
          beserta nilai sebelum→sesudah, pelaku, dan alasannya.
        </p>
      ) : (
        <div className="max-h-[32rem] space-y-2 overflow-y-auto pr-1">
          {list.map((c) => (
            <div key={c.id} data-testid={CALIB.histRow} data-kind={c.kind}
              data-reverted={c.rolled_back_at ? "true" : "false"}
              className={`rounded-lg border p-2.5 text-xs ${c.rollback_of
                ? "border-slate-200 bg-slate-50"
                : (c.rolled_back_at ? "border-zinc-200 bg-zinc-50" : "bg-background")}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-medium">
                    <span className="font-mono">{c.template_code}</span> ·{" "}
                    <span className="font-mono">{c.step_code}</span>{" "}
                    <span className="text-muted-foreground">{c.step_name}</span>
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    {stamp(c.created_at)} · {c.actor} · v{c.template_version_before}→
                    v{c.template_version_after}
                  </p>
                </div>
                <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium
                  ${KIND_TONE[c.kind] || "border-slate-200 bg-slate-50 text-slate-800"}`}>
                  {c.rollback_of ? "pembatalan" : <RefLabel group="calibration_kind" value={c.kind} />}
                  {" "}{changeText(c)}
                </span>
              </div>

              <p className="mt-1 text-[11px]">{c.explain}</p>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Alasan: <RefLabel group="calibration_cause" value={c.cause} /> — “{c.note}”
              </p>
              {(c.rows || []).length ? (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {c.rows.length} langkah tersentuh · target:{" "}
                  {rowShift((c.rows || []).find((r) => r.is_target) || c.rows[0])}
                </p>
              ) : null}

              <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2">
                {c.rolled_back_at ? (
                  <span data-testid={CALIB.histReverted}
                    className="rounded-full border border-zinc-300 bg-white px-2 py-0.5 text-[10px] font-medium text-zinc-700">
                    <Undo2 className="mr-1 inline h-3 w-3" />
                    sudah dibatalkan {stamp(c.rolled_back_at)} oleh {c.rolled_back_by}
                  </span>
                ) : <span />}
                {canCalibrate && !c.rolled_back_at && !c.rollback_of ? (
                  <Button size="sm" variant="ghost" className="h-7 px-2 text-[11px]"
                    data-testid={CALIB.histRollback} data-step={c.step_code}
                    onClick={() => onRollback(c)}>
                    <RotateCcw className="mr-1 h-3 w-3" /> Batalkan
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
