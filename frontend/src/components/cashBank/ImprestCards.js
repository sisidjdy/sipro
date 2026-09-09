import React, { useState } from "react";
import { toast } from "sonner";
import { Wallet, RefreshCw, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PETTYX } from "@/constants/testIds";

const STATUS = {
  cukup: { label: "Cukup", cls: "bg-emerald-100 text-emerald-800", tip: "Saldo di atas ambang pengisian." },
  perlu_isi: { label: "Perlu diisi", cls: "bg-rose-100 text-rose-800", tip: "Saldo di bawah ambang — ajukan pengisian sebesar batas − saldo." },
  menunggu_isi: { label: "Pengisian menunggu", cls: "bg-amber-100 text-amber-800", tip: "Sudah ada transfer pengisian yang menunggu persetujuan (tab Transfer Internal)." },
  melebihi_batas: { label: "Melebihi batas", cls: "bg-sky-100 text-sky-800", tip: "Saldo melebihi batas imprest — informatif; setel batas per kas di Master Rekening & Kas bila kas ini memang boleh besar." },
};

/** Kartu imprest per kas kecil: saldo vs batas, ambang, usulan pengisian satu klik (→ transfer pending). */
export default function ImprestCards({ data, onChanged }) {
  const [busy, setBusy] = useState("");
  if (!data?.accounts?.length) return null;

  const replenish = async (a) => {
    setBusy(a.account_id);
    try {
      const r = await api.post(`/petty-cash/imprest/${a.account_id}/replenish`, {});
      toast.success(`${r.data.data.no} diajukan ${formatIDR(r.data.data.amount)} — menunggu persetujuan di tab Transfer Internal.`);
      onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengajukan pengisian.");
    } finally { setBusy(""); }
  };

  return (
    <div className="space-y-3">
      {data.need_replenish ? (
        <div data-testid={PETTYX.imprestAlert}
          className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p><b>{data.need_replenish} kas kecil</b> di bawah ambang {data.policy.threshold_pct}% — ajukan pengisian agar kasir tidak kehabisan uang tunai.</p>
        </div>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" data-testid={PETTYX.imprestCards}>
        {data.accounts.map((a) => {
          const st = STATUS[a.status] || STATUS.cukup;
          const pct = a.imprest_limit ? Math.max(0, Math.min(100, Math.round((a.balance / a.imprest_limit) * 100))) : 0;
          return (
            <div key={a.account_id} data-testid={`${PETTYX.imprestCard}-${a.account_id}`}
              className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)] space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <Wallet className="h-4 w-4 text-primary shrink-0" />
                  <div className="min-w-0">
                    <p className="font-medium truncate">{a.name}</p>
                    <p className="text-xs text-muted-foreground font-mono">{a.gl_account_code} · {a.account_no}</p>
                  </div>
                </div>
                <Badge className={`${st.cls} border-0 whitespace-nowrap`} title={st.tip} data-testid={`${PETTYX.imprestStatus}-${a.account_id}`}>{st.label}</Badge>
              </div>
              <div>
                <p className="text-2xl font-semibold tabular-nums" data-testid={`${PETTYX.imprestBalance}-${a.account_id}`}>{formatIDR(a.balance)}</p>
                <p className="text-xs text-muted-foreground">
                  Batas imprest {formatIDR(a.imprest_limit)} <span className="opacity-70">({a.limit_source === "kas" ? "khusus kas ini" : "bawaan org"})</span> · ambang {formatIDR(a.threshold)}
                </p>
                <div className="mt-2 h-1.5 w-full rounded-full bg-muted overflow-hidden">
                  <div className={`h-full rounded-full ${a.status === "perlu_isi" ? "bg-rose-500" : a.status === "melebihi_batas" ? "bg-sky-500" : "bg-emerald-500"}`}
                    style={{ width: `${pct}%` }} />
                </div>
              </div>
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Bulan {a.month}: {a.month_count} pengeluaran · {formatIDR(a.month_spent)}</span>
              </div>
              {a.pending_replenish ? (
                <p className="text-xs text-amber-800">Pengisian {a.pending_transfer_nos.join(", ")} sebesar {formatIDR(a.pending_replenish)} menunggu persetujuan.</p>
              ) : null}
              {a.suggested_replenish > 0 && data.can_create ? (
                <Button size="sm" variant="outline" className="w-full" disabled={busy === a.account_id} onClick={() => replenish(a)}
                  data-testid={`${PETTYX.imprestReplenish}-${a.account_id}`}>
                  <RefreshCw className="h-4 w-4 mr-1" />Ajukan pengisian {formatIDR(a.suggested_replenish)}
                </Button>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
