import React, { useState } from "react";
import { LayoutDashboard, Wallet, HardHat, FileText, MessageSquareWarning, LogOut, Building2, Map, ShieldCheck, Ban } from "lucide-react";
import { usePortalAuth } from "@/context/PortalAuthContext";
import { PORTAL, P50, P56 } from "@/constants/testIds";
import OverviewPanel from "@/components/portal/panels/OverviewPanel";
import PaymentsPanel from "@/components/portal/panels/PaymentsPanel";
import ProgressPanel from "@/components/portal/panels/ProgressPanel";
import PlanPanel from "@/components/portal/panels/PlanPanel";
import DocumentsPanel from "@/components/portal/panels/DocumentsPanel";
import ComplaintsPanel from "@/components/portal/panels/ComplaintsPanel";
import WarrantyPanel from "@/components/portal/panels/WarrantyPanel";
// Fase 56C — pembeli membaca sendiri angka pembatalan & pengembalian dananya.
import CancellationPanel from "@/components/portal/panels/CancellationPanel";

const TABS = [
  { id: "overview", label: "Ringkasan", icon: LayoutDashboard, tid: PORTAL.tabOverview, Comp: OverviewPanel },
  { id: "payments", label: "Pembayaran", icon: Wallet, tid: PORTAL.tabPayments, Comp: PaymentsPanel },
  { id: "progress", label: "Progres", icon: HardHat, tid: PORTAL.tabProgress, Comp: ProgressPanel },
  { id: "plan", label: "Peta Kavling", icon: Map, tid: PORTAL.tabPlan, Comp: PlanPanel },
  { id: "documents", label: "Dokumen", icon: FileText, tid: PORTAL.tabDocuments, Comp: DocumentsPanel },
  { id: "complaints", label: "Komplain", icon: MessageSquareWarning, tid: PORTAL.tabComplaints, Comp: ComplaintsPanel },
  // Fase 50A — pembeli melihat masa garansi rumahnya & mengajukan klaim sendiri.
  { id: "warranty", label: "Garansi", icon: ShieldCheck, tid: P50.portalTabWarranty, Comp: WarrantyPanel },
  // Fase 56C — kalau pesanan dibatalkan, pembeli berhak membaca hitungan potongan &
  // pengembalian dananya tanpa harus menelepon.
  { id: "cancellation", label: "Pembatalan", icon: Ban, tid: P56.portalTab, Comp: CancellationPanel },
];

export default function PortalDashboard() {
  const { profile, logout } = usePortalAuth();
  const [active, setActive] = useState("overview");
  const Active = TABS.find((t) => t.id === active)?.Comp || OverviewPanel;

  return (
    <div data-testid={PORTAL.app} className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-10 border-b bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-indigo-600 text-white"><Building2 className="h-5 w-5" /></div>
            <div>
              <p className="font-heading text-sm font-semibold leading-tight">Portal Pembeli</p>
              <p className="text-xs text-slate-500">{profile?.name || "Pembeli"}</p>
            </div>
          </div>
          <button data-testid={PORTAL.logoutBtn} onClick={logout}
            className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">
            <LogOut className="h-4 w-4" /> Keluar
          </button>
        </div>
        <div className="mx-auto max-w-5xl overflow-x-auto px-2">
          <div className="flex gap-1 pb-2">
            {TABS.map((t) => {
              const Icon = t.icon;
              const on = active === t.id;
              return (
                <button key={t.id} data-testid={t.tid} onClick={() => setActive(t.id)}
                  className={`flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm transition-colors ${on ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
                  <Icon className="h-4 w-4" /> {t.label}
                </button>
              );
            })}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        <Active />
      </main>
    </div>
  );
}
