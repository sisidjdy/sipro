import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { FileWarning } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import PrintDocButton from "@/components/patterns/PrintDocButton";
import SendDocWaButton from "@/components/patterns/SendDocWaButton";
import MoneyText from "@/components/patterns/MoneyText";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { P62 } from "@/constants/testIds";

const LEVELS = [
  ["1", "SP1 — Peringatan pertama"],
  ["2", "SP2 — Peringatan kedua"],
  ["3", "SP3 — Peringatan ketiga & terakhir"],
];

/**
 * WarningLetterDialog — surat peringatan tunggakan SP1/SP2/SP3 (Fase 62).
 *
 * Angka surat diambil dari mesin denda (bukan diketik), tingkatnya tidak boleh melompat,
 * dan SP3 baru bisa terbit setelah tunggakan mencapai batas kontrak. Surat ini
 * MEMPERINGATKAN: pembatalan tetap diajukan Manajer Sales & diputus Manajer Keuangan.
 */
export default function WarningLetterDialog({ row, open, onOpenChange }) {
  const { can } = useAuth();
  const mayIssue = can("late_fee", "create");
  const [state, setState] = useState(null);
  const [level, setLevel] = useState("1");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!row?.deal_id) return;
    try {
      const res = await api.get("/docs/warning-letters/state",
        { params: { deal_id: row.deal_id } });
      setState(res.data.data);
      setLevel(String(res.data.data.next_level || 1));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memuat keadaan tunggakan.");
    }
  }, [row]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const issue = async () => {
    setBusy(true);
    try {
      const res = await api.post("/docs/warning-letters",
        { deal_id: row.deal_id, level: Number(level) });
      toast.success(res.data.data.duplicate
        ? `Surat ${res.data.data.number} bulan ini sudah pernah terbit — dipakai kembali.`
        : `Surat ${res.data.data.number} terbit.`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menerbitkan surat peringatan.");
    } finally { setBusy(false); }
  };

  const letters = state?.issued || [];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={P62.warnDialog} className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileWarning className="h-4 w-4 text-rose-600" />
            Surat peringatan tunggakan · {row?.unit_code || "-"}
          </DialogTitle>
          <DialogDescription>
            {row?.lead_name || "Pembeli"} — surat ini memperingatkan, bukan membatalkan.
            Pembatalan tetap diajukan Manajer Sales dan diputus Manajer Keuangan.
          </DialogDescription>
        </DialogHeader>

        {state ? (
          <div className="space-y-3">
            <div className="rounded-lg border bg-secondary/40 p-3 text-[12px]">
              <p>Menunggak <b>{state.months_in_arrears} bulan</b> · keterlambatan terlama{" "}
                {state.max_days_late} hari · batas kontrak {state.threshold_months} bulan</p>
              <p className="mt-1">Tertunggak <b><MoneyText value={state.overdue_amount} /></b>{" "}
                · denda berjalan <MoneyText value={state.denda_running} /></p>
            </div>

            {state.blocks?.length ? (
              <div data-testid={P62.warnBlock}
                className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 p-3 text-[12px] text-amber-900">
                {state.blocks.map((b, i) => <p key={i}>• {b}</p>)}
              </div>
            ) : null}

            {mayIssue ? (
              <div className="flex flex-wrap items-end gap-2">
                <div className="min-w-[15rem] flex-1">
                  <Select value={level} onValueChange={setLevel}>
                    <SelectTrigger data-testid={P62.warnLevel}><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {LEVELS.map(([v, l]) => (
                        <SelectItem key={v} value={v}
                          disabled={Number(v) > (state.next_level || 1)}>{l}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button data-testid={P62.warnIssueBtn} disabled={busy || !state.can_issue}
                  onClick={issue}>
                  {busy ? "Menerbitkan…" : "Terbitkan surat"}
                </Button>
              </div>
            ) : (
              <p className="text-[12px] text-muted-foreground">
                Penerbitan surat peringatan adalah kewenangan Keuangan (late_fee:create).
              </p>
            )}

            <div data-testid={P62.warnHistory} className="space-y-2">
              <p className="text-[12px] font-semibold">Surat yang sudah terbit ({letters.length})</p>
              {!letters.length ? (
                <p className="text-[12px] text-muted-foreground">
                  Belum ada surat peringatan untuk pembeli ini.
                </p>
              ) : letters.map((l) => (
                <div key={l.id} data-testid={P62.warnHistoryRow} data-level={l.level}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-2.5">
                  <div className="text-[12px]">
                    <p className="font-medium">{l.number} · {l.level_label}</p>
                    <p className="text-muted-foreground">
                      {String(l.created_at || "").slice(0, 10)} · {l.months_in_arrears} bulan ·{" "}
                      <MoneyText value={l.overdue_amount} />
                    </p>
                  </div>
                  <div className="flex gap-1.5">
                    <PrintDocButton url={`/docs/warning-letters/${l.id}/pdf`}
                      testId={P62.warnPdfBtn} filename={l.number}
                      label="Cetak surat" />
                    <SendDocWaButton kind="warning_letter" id={l.id} label="WhatsApp" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
