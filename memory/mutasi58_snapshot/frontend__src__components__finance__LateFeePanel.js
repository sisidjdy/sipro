import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Clock, Gavel, HandCoins, Info } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import MoneyText from "@/components/patterns/MoneyText";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { formatDateWIB } from "@/utils/formatters";
import { P58 } from "@/constants/testIds";

/**
 * LateFeePanel — TOLERANSI KETERLAMBATAN & DENDA BERJURNAL (Fase 58).
 *
 * Yang diperbaiki panel ini (dan alasannya):
 *  * Layar dulu menandai termin **TERLAMBAT** pada H+1, padahal kontraknya sendiri memberi
 *    tenggang belasan hari. Sekarang keadaan "**dalam masa toleransi**" punya namanya
 *    sendiri, lengkap dengan tanggal batas dan sisa harinya — pembeli tidak dituduh lebih
 *    cepat daripada perjanjiannya.
 *  * Denda tidak lagi hanya angka perkiraan: menekan **Tagihkan denda** menerbitkan JURNAL
 *    (piutang & pendapatan denda) dan menambah baris pada tagihan.
 *  * Keringanan adalah keputusan MANAJER KEUANGAN, wajib beralasan, dan membalik jurnalnya.
 *    Peran yang tidak berwenang tidak melihat tombol mati tanpa penjelasan — ia membaca
 *    kalimat sebabnya.
 *  * Bila denda belum boleh ditagihkan, layar MENYEBUTKAN sebabnya (masih tenggang, tidak
 *    ada tunggakan, sudah ditagihkan, sudah diringankan) — bukan tombol diam.
 */
const TONE = {
  lunas: "border-emerald-200 bg-emerald-50 text-emerald-800",
  menunggu: "border-slate-200 bg-slate-100 text-slate-700",
  dalam_tenggang: "border-amber-200 bg-amber-50 text-amber-900",
  terlambat: "border-rose-200 bg-rose-50 text-rose-800",
};

export default function LateFeePanel({ dealId, unitCode, onChanged }) {
  const { can } = useAuth();
  const mayView = can("late_fee", "view");
  const [data, setData] = useState(null);
  const [perm, setPerm] = useState({ apply: false, waive: false });
  const [state, setState] = useState({ loading: true, error: "" });
  const [busy, setBusy] = useState("");
  const [waive, setWaive] = useState(null);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    setState({ loading: true, error: "" });
    try {
      const res = await api.get(`/finance/late-fees/${dealId}`);
      setData(res.data.data);
      setPerm({ apply: !!res.data.may_apply, waive: !!res.data.may_waive });
      setState({ loading: false, error: "" });
    } catch (e) {
      setState({ loading: false,
        error: e?.response?.data?.detail || "Gagal memuat keadaan keterlambatan." });
    }
  }, [dealId]);

  useEffect(() => { if (mayView && dealId) load(); }, [mayView, dealId, load]);

  if (!mayView) {
    return (
      <p data-testid={P58.denied} className="rounded-lg border bg-secondary/40 px-3 py-2 text-[12px] text-muted-foreground">
        Denda &amp; toleransi keterlambatan hanya bisa dilihat peran yang mengurus penagihan.
        Ini soal HAK AKSES, bukan data yang belum ada.
      </p>
    );
  }
  if (state.loading) return null;
  if (state.error) {
    return (
      <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-800">
        {state.error}
      </p>
    );
  }
  if (!data) return null;

  const t = data.totals || {};
  const perhatian = (data.rows || []).filter(
    (r) => r.state === "terlambat" || r.state === "dalam_tenggang");

  const tagihkan = async () => {
    setBusy("apply");
    try {
      const res = await api.post(`/finance/late-fees/${dealId}/apply`, {});
      const jml = (res.data.created || []).reduce((a, c) => a + (c.amount || 0), 0);
      toast.success(res.data.replay ? "Denda ini sudah pernah ditagihkan."
        : `Denda ${jml.toLocaleString("id-ID")} ditagihkan & dijurnal.`);
      setData(res.data.data);
      onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Denda gagal ditagihkan.");
    } finally { setBusy(""); }
  };

  const kirimKeringanan = async () => {
    setBusy("waive");
    try {
      const res = await api.post(
        `/finance/late-fees/${dealId}/waive/${waive.item_id}`, { reason });
      toast.success("Keringanan diberikan — jurnalnya dibalik.");
      setData(res.data.data);
      setWaive(null); setReason("");
      onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Keringanan gagal diberikan.");
    } finally { setBusy(""); }
  };

  return (
    <div data-testid={P58.panel} className="space-y-2.5 rounded-xl border bg-card p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="flex items-center gap-1.5 font-heading text-[13px] font-semibold">
          <Clock className="h-4 w-4 text-amber-600" />
          Toleransi keterlambatan &amp; denda {unitCode ? `· ${unitCode}` : ""}
        </p>
        {perm.apply && (t.denda_billable || 0) > 0 ? (
          <Button size="sm" variant="outline" className="text-rose-700"
            data-testid={P58.applyBtn} disabled={busy === "apply"} onClick={tagihkan}>
            <Gavel className="mr-1.5 h-3.5 w-3.5" /> Tagihkan denda
          </Button>
        ) : null}
      </div>

      <p data-testid={P58.policy} className="flex items-start gap-1.5 text-[12px] text-muted-foreground">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {data.policy_sentence}
      </p>

      <div data-testid={P58.summary} className="grid gap-2 sm:grid-cols-4">
        {[["Tunggakan (lewat toleransi)", t.overdue_outstanding],
          ["Masih dalam toleransi", t.in_grace_outstanding],
          ["Denda berjalan", t.denda_running],
          ["Denda ditagihkan", t.denda_charged]].map(([label, val]) => (
          <div key={label} className="rounded-lg border bg-secondary/40 px-2.5 py-1.5">
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
            <p className="font-semibold tabular-nums"><MoneyText value={val || 0} /></p>
          </div>
        ))}
      </div>

      {data.block ? (
        <p data-testid={P58.blockNote} data-code={data.block.code}
          className="flex items-start gap-1.5 rounded-lg border bg-secondary/40 px-2.5 py-2 text-[12px]">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
          <span><b>{data.block.label}.</b> {data.block.detail}</span>
        </p>
      ) : null}

      {perhatian.length ? (
        <div className="space-y-1.5">
          {perhatian.map((r) => (
            <div key={r.item_id} data-testid={P58.termRow} data-state={r.state}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 text-[12px]">
              <span className="font-medium">{r.label}</span>
              <span data-testid={P58.graceNote} className="text-muted-foreground">
                Jatuh tempo {formatDateWIB(r.due_date)} · toleransi {r.grace_days} hari
                (s/d {formatDateWIB(r.grace_until)})
                {r.state === "dalam_tenggang"
                  ? ` · sisa ${r.grace_left_days} hari sebelum menunggak`
                  : ` · ${r.days_late} hari lewat toleransi`}
              </span>
              <span className="flex items-center gap-2">
                <span className="tabular-nums"><MoneyText value={r.denda_running} /></span>
                <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${TONE[r.state]}`}>
                  {r.state_label}
                </span>
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {(data.penalties || []).length ? (
        <div className="space-y-1.5">
          <p className="text-[12px] font-medium">Denda yang sudah diterbitkan</p>
          {data.penalties.map((p) => (
            <div key={p.item_id} data-testid={P58.penaltyRow} data-state={p.state}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 text-[12px]">
              <span>
                <span className="font-medium">{p.label}</span>
                <span className="ml-1 text-muted-foreground">
                  · {p.days_late} hari lewat toleransi · periode {p.period}
                </span>
                {p.waived ? (
                  <span className="block text-[11px] text-muted-foreground">
                    Diringankan: {p.waived_reason}
                  </span>
                ) : null}
              </span>
              <span className="flex items-center gap-2">
                <span className="tabular-nums">
                  <MoneyText value={p.waived ? p.waived_amount : p.amount} />
                </span>
                <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                  p.waived ? TONE.menunggu : TONE.terlambat}`}>
                  {p.state_label}
                </span>
                {!p.waived && p.state === "ditagihkan" && perm.waive ? (
                  <Button size="sm" variant="ghost" data-testid={P58.waiveBtn}
                    onClick={() => { setWaive(p); setReason(""); }}>
                    <HandCoins className="mr-1 h-3.5 w-3.5" /> Beri keringanan
                  </Button>
                ) : null}
              </span>
            </div>
          ))}
          {!perm.waive ? (
            <p className="text-[11px] text-muted-foreground">
              Keringanan denda adalah wewenang Manajer Keuangan — bukan orang yang
              menagihkannya. Ajukan ke Manajer Keuangan bila pembeli memintanya.
            </p>
          ) : null}
        </div>
      ) : null}

      <Dialog open={!!waive} onOpenChange={(v) => { if (!v) { setWaive(null); setReason(""); } }}>
        <DialogContent data-testid={P58.waiveDialog} className="max-w-lg bg-background">
          <DialogHeader>
            <DialogTitle>Beri keringanan denda</DialogTitle>
            <DialogDescription>
              Keringanan MEMBALIK jurnal dendanya dan tercatat atas nama Anda. Denda hanya
              berjalan lagi untuk keterlambatan sesudah hari ini.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <p className="rounded-lg border bg-secondary/40 px-2.5 py-2 text-[13px]">
              {waive?.label} · <MoneyText value={waive?.amount || 0} />
            </p>
            <Label htmlFor="late-fee-reason">Alasan keringanan (minimal 10 huruf)</Label>
            <Textarea id="late-fee-reason" data-testid={P58.waiveReason} value={reason}
              onChange={(e) => setReason(e.target.value)} rows={3}
              placeholder="Contoh: pembeli terkena musibah, disetujui direksi pada rapat 12 Mei." />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setWaive(null)}>Batal</Button>
            <Button data-testid={P58.waiveSubmit} onClick={kirimKeringanan}
              disabled={reason.trim().length < 10 || busy === "waive"}>
              Beri keringanan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
