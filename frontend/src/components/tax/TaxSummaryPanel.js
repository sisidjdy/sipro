import React, { useCallback, useEffect, useState } from "react";
import { Landmark, ArrowDownCircle, ArrowUpCircle, Scale, ReceiptText, Home } from "lucide-react";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import { cn } from "@/lib/utils";
import api from "@/services/apiClient";
import { useReference } from "@/context/ReferenceContext";
import { TAX } from "@/constants/testIds";

// Nada warna saja — LABEL status PPN datang dari Kamus Data (`vat_return_state`) sejak
// Fase 49G, jadi layar tidak lagi menulis ulang istilah pajak yang bisa berubah.
const NET_TONE = {
  kurang_bayar: "text-rose-700 border-rose-200 bg-rose-50",
  lebih_bayar: "text-emerald-700 border-emerald-200 bg-emerald-50",
  nihil: "text-slate-700 border-slate-200 bg-slate-50",
};

function Stat({ testid, icon: Icon, label, value, tone, hint }) {
  return (
    <div data-testid={testid} className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="h-4 w-4" />
        <p className="text-xs">{label}</p>
      </div>
      <p className={cn("mt-2 text-xl font-semibold tabular-nums font-heading", tone)}>{formatIDR(value || 0)}</p>
      {hint ? <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export default function TaxSummaryPanel() {
  const { labelOf } = useReference();
  const [data, setData] = useState(null);
  const [periods, setPeriods] = useState([]);
  const [period, setPeriod] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = period === "all" ? {} : { period };
      const [sumRes, perRes] = await Promise.all([
        api.get("/tax/summary", { params }),
        api.get("/tax/periods"),
      ]);
      setData(sumRes.data.data);
      setPeriods(perRes.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat ringkasan pajak.");
    } finally { setLoading(false); }
  }, [period]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={5} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;

  const netStatus = data.ppn_status || "nihil";

  return (
    <div data-testid={TAX.summaryPanel} className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">Masa Pajak</p>
        <Select value={period} onValueChange={setPeriod}>
          <SelectTrigger data-testid={TAX.periodSelect} className="h-9 w-48"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua Masa</SelectItem>
            {periods.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {/* SPT Masa PPN highlight */}
      <div className={cn("rounded-xl border bg-card p-4", NET_TONE[netStatus])} data-testid={TAX.ppnNet}>
        <div className="flex items-center gap-2">
          <Scale className="h-4 w-4" />
          <p className="text-sm font-medium">
            {labelOf("vat_return_state", netStatus)} (SPT Masa PPN)
          </p>
        </div>
        <p className="mt-1 text-3xl font-semibold tabular-nums font-heading">{formatIDR(Math.abs(data.ppn_net || 0))}</p>
        <p className="mt-1 text-xs opacity-80">
          PPN Keluaran {formatIDR(data.ppn_keluaran)} − PPN Masukan {formatIDR(data.ppn_masukan)}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Stat testid={TAX.ppnKeluaran} icon={ArrowUpCircle} label="PPN Keluaran (Penjualan)"
          value={data.ppn_keluaran} tone="text-primary" hint={`${data.counts?.ppn || 0} transaksi`} />
        <Stat testid={TAX.ppnMasukan} icon={ArrowDownCircle} label="PPN Masukan (Estimasi AP)"
          value={data.ppn_masukan} tone="text-sky-700"
          hint={`${data.ppn_input_detail?.count || 0} tagihan · ${data.ppn_input_detail?.rate || 0}% inklusif`} />
        <Stat testid={TAX.pphFinal} icon={ReceiptText} label="PPh Final Pasal 4(2)"
          value={data.pph_final} tone="text-indigo-700" hint={`${data.counts?.pph || 0} transaksi`} />
        <Stat testid={TAX.bphtb} icon={Home} label="BPHTB (Pembeli)"
          value={data.bphtb} tone="text-amber-700" hint={`${data.counts?.bphtb || 0} transaksi`} />
        <Stat testid="tax-faktur-count" icon={Landmark} label="Faktur Pajak Terbit"
          value={0} tone="text-slate-700" hint={`${data.faktur_count || 0} faktur`} />
      </div>

      <p className="text-[11px] text-muted-foreground">{data.note}</p>
    </div>
  );
}
