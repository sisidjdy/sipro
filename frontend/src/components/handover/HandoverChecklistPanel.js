import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, CircleAlert, CircleHelp, ExternalLink, KeyRound, RefreshCw, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import HandoverIssueDialog from "@/components/handover/HandoverIssueDialog";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { newRef } from "@/services/offlineSync";
import { P50 } from "@/constants/testIds";

const PILL = {
  ok: "border-emerald-200 bg-emerald-50 text-emerald-800",
  blocking: "border-rose-200 bg-rose-50 text-rose-800",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  missing_data: "border-slate-200 bg-slate-100 text-slate-700",
};
const ICON = { ok: CheckCircle2, blocking: CircleAlert, warning: CircleAlert,
  missing_data: CircleHelp };

/**
 * Daftar periksa serah terima unit (Fase 50A).
 *
 * Kenapa layar ini ada: sebelum Fase 50 tidak ada satu pun jalan yang menuliskan "rumah
 * sudah diserahkan" — tanggalnya hanya hidup di kepala orang, padahal itulah titik nol masa
 * garansi. Layar ini menunjukkan APA yang masih menahan penyerahan kunci (temuan punch yang
 * terbuka, progres belum 100%, kewajiban pembayaran, inspeksi akhir) beserta tautan ke
 * sumbernya — bukan sekadar tombol yang gagal tanpa alasan.
 */
export default function HandoverChecklistPanel({ unitId, unitCode, onChanged }) {
  const { can } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hold, setHold] = useState(null);
  const [dialog, setDialog] = useState(null);
  // Penanda kiriman dibuat SEKALI per dialog: kalau sinyal mati di tengah penerbitan dan
  // pemakai menekan lagi, server memutar ulang dokumen lama alih-alih menerbitkan BAST kedua.
  const clientRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/handover/check", { params: { unit_id: unitId } });
      setData(res.data.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat daftar periksa serah terima.");
    } finally { setLoading(false); }
  }, [unitId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;

  const items = data.items || [];
  const blocking = data.blocking || [];
  const already = data.already;
  const canIssue = can("handover", "create");
  const canOverride = can("handover", "override");

  const issue = async (payload) => {
    setHold(null);
    try {
      const res = await api.post("/handover/issue", {
        unit_id: unitId, client_ref: clientRef.current, ...payload,
      });
      toast.success(res.data?.message || "Serah terima tercatat.");
      setDialog(null);
      clientRef.current = null;
      await load();
      onChanged?.();
      return true;
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (e?.response?.status === 409 && detail && typeof detail === "object") {
        setHold(detail);
        setDialog(null);
        toast.error(detail.message || "Serah terima ditahan.");
        return false;
      }
      toast.error(typeof detail === "string" ? detail : "Gagal mencatat serah terima.");
      return false;
    }
  };

  return (
    <div data-testid={P50.handoverPanel} className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-heading text-lg font-semibold">Daftar periksa serah terima</h3>
          <p className="text-sm text-muted-foreground">{data.detail}</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" data-testid={P50.handoverRefresh} onClick={load}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Muat ulang
          </Button>
          {canIssue && !already ? (
            <Button size="sm" data-testid={P50.handoverIssueBtn}
              onClick={() => {
                clientRef.current = clientRef.current || newRef();
                setDialog({ override: blocking.length > 0 });
              }}>
              <KeyRound className="mr-1.5 h-3.5 w-3.5" />
              {blocking.length ? "Serahkan dengan terobosan" : "Terbitkan BAST"}
            </Button>
          ) : null}
        </div>
      </div>

      {hold ? (
        <div data-testid={P50.handoverHoldBanner}
          className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
          <p className="font-semibold">{hold.message}</p>
          <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-[13px]">
            {(hold.reasons || []).map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      ) : null}

      <div className="grid gap-2">
        {items.map((it) => {
          const Icon = ICON[it.state] || CircleHelp;
          return (
            <div key={it.code} data-testid={P50.handoverCheckItem} data-state={it.state}
              className="flex flex-wrap items-start justify-between gap-3 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
              <div className="flex items-start gap-2.5">
                <Icon className={`mt-0.5 h-4 w-4 ${it.state === "ok" ? "text-emerald-600"
                  : it.state === "blocking" ? "text-rose-600"
                    : it.state === "warning" ? "text-amber-600" : "text-slate-500"}`} />
                <div>
                  <p className="text-sm font-medium">{it.label}</p>
                  <p className="text-[13px] text-muted-foreground">{it.detail}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                  PILL[it.state] || PILL.missing_data}`}>
                  {it.state_label}
                </span>
                {it.source ? (
                  <a href={it.source} data-testid={P50.handoverCheckLink}
                    className="inline-flex items-center gap-1 text-[12px] font-medium text-primary hover:underline">
                    Buka sumbernya <ExternalLink className="h-3 w-3" />
                  </a>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      {!canIssue ? (
        <p className="text-[12px] text-muted-foreground">
          Penerbitan berita acara serah terima dilakukan tim proyek atau keuangan. Anda tetap
          bisa melihat daftar periksanya di sini.
        </p>
      ) : null}

      {/* Masa garansi yang AKAN berlaku begitu kunci diserahkan. Ditampilkan SEBELUM
          penerbitan supaya janji ke pembeli dibaca dari Pusat Konfigurasi — bukan diingat
          orang. Angkanya sama dengan yang tercetak di BAST nanti. */}
      {(data.warranty_plan || []).length ? (
        <div className="space-y-2">
          <p className="flex items-center gap-1.5 text-sm font-medium">
            <ShieldCheck className="h-4 w-4 text-primary" /> Masa garansi yang akan berlaku
          </p>
          <div className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <table className="w-full text-[13px]">
              <thead className="bg-secondary/60 text-left text-[12px] text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Bagian</th>
                  <th className="px-3 py-2">Lama</th>
                  <th className="px-3 py-2">Mulai dihitung</th>
                </tr>
              </thead>
              <tbody>
                {(data.warranty_plan || []).map((p) => (
                  <tr key={p.category} data-testid={P50.warrantyPlanRow} className="border-t">
                    <td className="px-3 py-2 font-medium">{p.label}</td>
                    <td className="px-3 py-2 tabular-nums">
                      {p.months ? `${p.months} bulan` : "tidak digaransi"}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      Tanggal serah terima
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[12px] text-muted-foreground">
            Lama garansi diatur di Pusat Konfigurasi → Serah Terima &amp; Garansi, jadi
            perubahannya berjejak dan berlaku untuk BAST yang diterbitkan sesudahnya.
          </p>
        </div>
      ) : null}

      <HandoverIssueDialog open={!!dialog} unitCode={unitCode} blocking={blocking}
        canOverride={canOverride} onOpenChange={(v) => !v && setDialog(null)}
        onSubmit={issue} />
    </div>
  );
}
