import React, { useEffect, useState } from "react";
import { Home, Wallet, HardHat, FileText, CreditCard, MessageSquareWarning } from "lucide-react";
import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import portalApi from "@/services/portalClient";
import { PORTAL } from "@/constants/testIds";

function Stat({ icon: Icon, label, value, sub }) {
  return (
    <div className="rounded-xl border bg-white p-4">
      <div className="flex items-center gap-2 text-xs text-slate-500"><Icon className="h-4 w-4" /> {label}</div>
      <p className="mt-1.5 text-lg font-semibold tabular-nums">{value}</p>
      {sub ? <p className="text-xs text-slate-400">{sub}</p> : null}
    </div>
  );
}

export default function OverviewPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true); setError("");
    try {
      const res = await portalApi.get("/portal/overview");
      setData(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat ringkasan.");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data?.length) return <p className="rounded-xl border bg-white p-6 text-center text-sm text-slate-500">Belum ada unit terhubung dengan akun Anda.</p>;

  return (
    <div data-testid={PORTAL.overviewPanel} className="space-y-6">
      {data.map((d) => (
        <div key={d.deal_id} className="space-y-4">
          <div className="rounded-xl border bg-white p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-500">{d.project_name}</p>
                <p className="font-heading text-xl font-semibold">Unit {d.unit_code} · {d.unit_type}</p>
              </div>
              <StatusPill status={d.status} />
            </div>
            <p className="mt-2 text-sm text-slate-600">Harga: <b className="tabular-nums">{formatIDR(d.price)}</b></p>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat icon={HardHat} label="Progres Konstruksi" value={`${d.construction_progress}%`} sub={d.construction_status} />
            <Stat icon={Wallet} label="Sisa Pembayaran" value={formatIDR(d.payment?.outstanding)} sub={d.payment?.next_due ? `Jatuh tempo ${formatDateWIB(d.payment.next_due)}` : ""} />
            <Stat icon={CreditCard} label="KPR" value={d.financing ? d.financing.bank_name : "—"} sub={d.financing ? `Status: ${d.financing.status}` : "Tanpa KPR"} />
            <Stat icon={FileText} label="Dokumen" value={d.documents_count} sub={d.open_complaints ? `${d.open_complaints} komplain terbuka` : "Tidak ada komplain"} />
          </div>
          {/* progress bar */}
          <div className="rounded-xl border bg-white p-4">
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="flex items-center gap-1.5 text-slate-600"><Home className="h-4 w-4" /> Pembangunan unit Anda</span>
              <span className="font-semibold tabular-nums">{d.construction_progress}%</span>
            </div>
            <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-indigo-600 transition-all" style={{ width: `${d.construction_progress}%` }} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
