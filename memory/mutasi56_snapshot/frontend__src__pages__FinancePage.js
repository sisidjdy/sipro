import React from "react";
import { useSearchParams } from "react-router-dom";
import { Wallet } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import FinanceDashboard from "@/components/finance/FinanceDashboard";
import CashflowPanel from "@/components/finance/CashflowPanel";
import ArPanel from "@/components/finance/ArPanel";
import DepositPanel from "@/components/finance/DepositPanel";
import CollectionsPanel from "@/components/finance/CollectionsPanel";
import ApPanel from "@/components/finance/ApPanel";
import CommissionsPanel from "@/components/finance/CommissionsPanel";
import ReportsPanel from "@/components/finance/ReportsPanel";
import ConfigPanel from "@/components/finance/ConfigPanel";
import BankReconciliationTab from "@/components/finance/BankReconciliationTab";
import LaborPayrollPanel from "@/components/labor/LaborPayrollPanel";
// Fase 56C — daftar pembatalan & utang refund: yang memutuskan dan yang membayar bekerja
// dari sisi uang, bukan dari sisi satu pembeli.
import CancellationsPanel from "@/components/finance/CancellationsPanel";
import { FINANCE, BANK, LABOR, P56 } from "@/constants/testIds";

const TABS = ["dashboard", "cashflow", "ar", "deposits", "collections", "ap", "commissions",
  "bank", "labor", "cancellations", "reports", "config"];

/**
 * FinancePage (`/finance`) — satu route dengan Tabs internal; tiap panel memuat datanya
 * sendiri (loading/empty/error) agar file tetap ramping dan lulus guardrails.
 *
 * Fase 40d: tab aktif HIDUP DI URL (`?tab=ar`). Tanpa itu, KPI “AR Outstanding” di Beranda
 * tidak mungkin mendarat di tab yang benar (dulu selalu jatuh ke Dashboard, lalu pemakai
 * harus mencari sendiri tab & filternya) — dan tautan seperti “lihat piutang belum bayar”
 * tidak bisa dibagikan ke rekan.
 */
export default function FinancePage() {
  const [params, setParams] = useSearchParams();
  const wanted = params.get("tab");
  const active = TABS.includes(wanted) ? wanted : "dashboard";

  const onTab = (value) => {
    const next = new URLSearchParams(params);
    next.set("tab", value);
    // Filter/paginasi milik tab lain tidak boleh terbawa ke tab baru.
    ["skip", "q", "status", "sort", "direction", "created_from", "created_to"]
      .forEach((k) => next.delete(k));
    setParams(next, { replace: false });
  };

  return (
    <div data-testid={FINANCE.page} className="space-y-5">
      <div className="flex items-center gap-2">
        <Wallet className="h-5 w-5 text-primary" />
        <h1 className="font-heading text-2xl font-semibold tracking-tight">Keuangan</h1>
      </div>

      <Tabs value={active} onValueChange={onTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger data-testid={FINANCE.tabDashboard} value="dashboard">Dashboard</TabsTrigger>
          <TabsTrigger data-testid={FINANCE.tabCashflow} value="cashflow">Arus Kas</TabsTrigger>
          <TabsTrigger data-testid={FINANCE.tabAr} value="ar">Piutang (AR)</TabsTrigger>
          <TabsTrigger data-testid={FINANCE.tabDeposits} value="deposits">Titipan</TabsTrigger>
          <TabsTrigger data-testid={FINANCE.tabCollections} value="collections">Penagihan</TabsTrigger>
          <TabsTrigger data-testid={FINANCE.tabAp} value="ap">Utang (AP)</TabsTrigger>
          <TabsTrigger data-testid={FINANCE.tabCommissions} value="commissions">Komisi</TabsTrigger>
          <TabsTrigger data-testid={BANK.tab} value="bank">Rekonsiliasi Bank</TabsTrigger>
          <TabsTrigger data-testid={LABOR.payrollTab} value="labor">Upah Harian</TabsTrigger>
          <TabsTrigger data-testid={P56.financeTab} value="cancellations">
            Pembatalan &amp; Refund
          </TabsTrigger>
          <TabsTrigger data-testid={FINANCE.tabReports} value="reports">Laporan</TabsTrigger>
          <TabsTrigger data-testid={FINANCE.tabConfig} value="config">Konfigurasi</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard" className="mt-4"><FinanceDashboard /></TabsContent>
        <TabsContent value="cashflow" className="mt-4"><CashflowPanel /></TabsContent>
        <TabsContent value="ar" className="mt-4"><ArPanel /></TabsContent>
        <TabsContent value="deposits" className="mt-4"><DepositPanel /></TabsContent>
        <TabsContent value="collections" className="mt-4"><CollectionsPanel /></TabsContent>
        <TabsContent value="ap" className="mt-4"><ApPanel /></TabsContent>
        <TabsContent value="commissions" className="mt-4"><CommissionsPanel /></TabsContent>
        <TabsContent value="bank" className="mt-4"><BankReconciliationTab /></TabsContent>
        <TabsContent value="labor" className="mt-4">
          <LaborPayrollPanel mode="finance" />
        </TabsContent>
        <TabsContent value="cancellations" className="mt-4"><CancellationsPanel /></TabsContent>
        <TabsContent value="reports" className="mt-4"><ReportsPanel /></TabsContent>
        <TabsContent value="config" className="mt-4"><ConfigPanel /></TabsContent>
      </Tabs>
    </div>
  );
}
