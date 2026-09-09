import React, { useCallback, useEffect, useState } from "react";
import { History, RotateCcw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { P81 } from "@/constants/testIds";

const when = (s) => (s ? new Date(s).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }) : "—");

/** Riwayat versi RAB tipe/add-on: setiap Simpan yang mengubah baris menyimpan versi lama. Pulihkan = simpan ulang versi itu (tercatat). */
export default function RabVersionHistory({ kind, target, reloadKey, onRestored }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState("");
  const ref = encodeURIComponent(target?.ref_code || "");
  const load = useCallback(() => {
    if (!target) return;
    api.get(`/rab/templates/${kind}/${ref}/versions`).then((r) => setRows(r.data.data.versions || [])).catch(() => setRows([]));
  }, [kind, ref, target]);
  useEffect(() => { load(); }, [load, reloadKey]);

  const restore = async (v) => {
    setBusy(v.id);
    try {
      await api.post(`/rab/templates/${kind}/${ref}/versions/${v.id}/restore`);
      toast.success(`RAB dipulihkan ke v${v.version}.`);
      load(); onRestored && onRestored();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memulihkan versi."); } finally { setBusy(""); }
  };

  const cur = rows.find((v) => v.current);
  return (
    <div className="space-y-1">
      <button type="button" data-testid={P81.historyToggle} className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground" onClick={() => setOpen((o) => !o)}>
        <History className="h-3.5 w-3.5" /> Riwayat versi {cur ? `· sekarang v${cur.version} (${rows.length - 1} versi lama)` : "· belum ada"} {open ? "▴" : "▾"}
      </button>
      {open ? (
        <div data-testid={P81.historyPanel} className="max-h-48 overflow-y-auto rounded-lg border bg-card text-xs shadow-[var(--shadow-card)]">
          {!rows.length ? <p className="p-2 text-muted-foreground">RAB ini belum pernah disimpan.</p> : rows.map((v) => (
            <div key={v.id || "current"} data-testid={P81.historyRow} data-version={v.version} className={`flex items-center gap-2 border-b px-2 py-1.5 last:border-b-0 ${v.current ? "bg-emerald-50/60" : ""}`}>
              <span className="w-10 font-semibold">v{v.version}</span>
              <span className="flex-1 truncate">
                {v.current ? <b className="mr-1 rounded bg-emerald-100 px-1 text-[10px] text-emerald-800">AKTIF</b> : null}
                {when(v.saved_at)} · {v.saved_by || "—"} · {v.items_count} baris{v.note ? ` · ${v.note}` : ""}
              </span>
              <span className="tabular-nums font-medium">{formatIDR(v.total)}</span>
              <span className={`w-28 text-right tabular-nums ${v.delta > 0 ? "text-rose-600" : v.delta < 0 ? "text-emerald-700" : "text-muted-foreground"}`}>
                {v.delta == null ? "awal" : `${v.delta > 0 ? "+" : ""}${formatIDR(v.delta)}`}
              </span>
              {!v.current ? (
                <Button data-testid={P81.historyRestore} size="sm" variant="ghost" className="h-7 px-2" disabled={busy === v.id} onClick={() => restore(v)}>
                  <RotateCcw className="mr-1 h-3 w-3" /> Pulihkan
                </Button>
              ) : <span className="w-[86px]" />}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
