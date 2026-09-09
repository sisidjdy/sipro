import React, { useCallback, useEffect, useState } from "react";
import { BellRing, Landmark } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { P75 } from "@/constants/testIds";

/** Pengingat tahap pencairan KPR: syarat terpenuhi, bank belum mencairkan. Harian otomatis + tombol manual. */
export default function TrancheReminderPanel() {
  const { can } = useAuth();
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.get("/kpr/tranche-reminders").then((r) => { setRows(r.data.data || []); setErr(""); })
      .catch((e) => { setRows([]); setErr(e?.response?.data?.detail || "Daftar tahap tidak dapat dimuat."); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const run = async () => {
    setBusy(true);
    try {
      const r = await api.post("/kpr/tranche-reminders/run");
      toast.success(`${r.data.data.notified} pengingat baru dikirim (${r.data.data.ready} tahap siap cair).`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menjalankan pengingat."); } finally { setBusy(false); }
  };

  if (!rows) return null;
  return (
    <section data-testid={P75.trancheReminderPanel} className="space-y-2 rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="flex items-center gap-2 font-heading text-base font-semibold"><BellRing className="h-4 w-4" /> Tahap pencairan KPR siap ditagih ke bank</h3>
          <p className="text-xs text-muted-foreground">Syarat tahap (akad / BAST / sertifikat) sudah terpenuhi tetapi bank belum mencairkan. Pengingat otomatis setiap pagi (08:15 WIB), satu kali per tahap.</p>
        </div>
        {can("finance", "update") ? (
          <Button data-testid={P75.trancheReminderRun} size="sm" variant="outline" disabled={busy} onClick={run}>Kirim pengingat sekarang</Button>
        ) : null}
      </div>
      {err ? <p data-testid={P75.trancheReminderError} className="text-sm text-destructive">{err}</p>
        : !rows.length ? <p className="text-sm text-muted-foreground">Tidak ada tahap yang menunggu pencairan bank.</p> : (
        <ul className="divide-y text-sm">
          {rows.map((r) => (
            <li key={`${r.app_id}-${r.tranche_code}`} data-testid={P75.trancheReminderRow} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
              <span className="flex items-center gap-2"><Landmark className="h-3.5 w-3.5 text-muted-foreground" />
                <Link className="underline-offset-2 hover:underline" to={`/customers/${r.customer_id}?tab=kontrak53`}>{r.contract_no}</Link>
                <span className="text-xs text-muted-foreground">{r.customer_name} · {r.unit_code} · {r.bank || "bank -"}</span></span>
              <span className="text-xs">{r.tranche_name} · syarat <b>{r.condition}</b> terpenuhi · <b className="tabular-nums">{formatIDR(r.amount)}</b></span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
