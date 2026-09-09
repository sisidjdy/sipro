import React from "react";
import { useSearchParams } from "react-router-dom";
import { Wallet } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import FinanceDashboard from "@/components/finance/FinanceDashboard";
import CashflowPanel from "@/components/finance/CashflowPanel";
import ArPanel from "@/components/finance/ArPanel";
import DepositPanel from "@/components/finance/DepositPanel";
import CollectionsPanel from "@/components/finance/CollectionsPanel";
import LateFeeAutoPanel from "@/components/finance/LateFeeAutoPanel";
import TrancheReminderPanel from "@/components/finance/TrancheReminderPanel";
import ApPanel from "@/components/finance/ApPanel";
import CommissionsPanel from "@/components/finance/CommissionsPanel";
import ReportsPanel from "@/components/finance/ReportsPanel";
import ConfigPanel from "@/components/finance/ConfigPanel";
import BankReconciliationTab from "@/components/finance/BankReconciliationTab";
import LaborPayrollPanel from "@/components/labor/LaborPayrollPanel";
import CancellationsPanel from "@/components/finance/CancellationsPanel";
import LateFeeWaiverReport from "@/components/finance/LateFeeWaiverReport";
import RefundDebtPanel from "@/components/finance/RefundDebtPanel";
import { FINANCE, BANK, LABOR, P56, P59, P91 } from "@/constants/testIds";

/**
 * Fase 91 — semua yang bersifat PIUTANG berkumpul di satu halaman "Piutang" (sub-bagian:
 * Daftar AR, Penagihan, Titipan, Keringanan Denda, Pembatalan & Refund) dan semua yang
 * bersifat UTANG di halaman "Utang" (Tagihan AP, Utang Refund, Komisi, Upah Harian).
 * Tautan lama `?tab=ar|deposits|collections|waivers|cancellations|ap|refund-debt|commissions|labor`
 * tetap hidup lewat pemetaan LEGACY.
 */
const RECEIVABLE_SUBS = [
  { key: "ar", label: "Daftar Piutang", testId: FINANCE.tabAr, content: <ArPanel /> },
  { key: "collections", label: "Penagihan", testId: FINANCE.tabCollections,
    content: <div className="space-y-6"><CollectionsPanel /><TrancheReminderPanel /><LateFeeAutoPanel /></div> },
  { key: "deposits", label: "Titipan", testId: FINANCE.tabDeposits, content: <DepositPanel /> },
  { key: "waivers", label: "Keringanan Denda", testId: P59.waiverTabReport, content: <LateFeeWaiverReport /> },
  { key: "cancellations", label: "Pembatalan & Refund", testId: P56.financeTab, content: <CancellationsPanel /> },
];
const PAYABLE_SUBS = [
  { key: "ap", label: "Tagihan Vendor (AP)", testId: FINANCE.tabAp, content: <ApPanel /> },
  { key: "refund-debt", label: "Utang Refund", testId: P59.refundTab, content: <RefundDebtPanel /> },
  { key: "commissions", label: "Komisi", testId: FINANCE.tabCommissions, content: <CommissionsPanel /> },
  { key: "labor", label: "Upah Harian", testId: LABOR.payrollTab, content: <LaborPayrollPanel mode="finance" /> },
];
const LEGACY = Object.fromEntries([
  ...RECEIVABLE_SUBS.map((s) => [s.key, ["receivables", s.key]]),
  ...PAYABLE_SUBS.map((s) => [s.key, ["payables", s.key]]),
]);
const TABS = ["dashboard", "cashflow", "receivables", "payables", "bank", "reports", "config"];
const CLEAR_KEYS = ["skip", "q", "status", "sort", "direction", "created_from", "created_to"];

function SubTabs({ subs, active, onChange, group }) {
  return (
    <Tabs value={active} onValueChange={onChange}>
      <TabsList className="flex-wrap bg-transparent p-0 gap-1">
        {subs.map((s) => (
          <TabsTrigger key={s.key} value={s.key} data-testid={s.testId} data-subtab={`${P91.subTab}-${group}-${s.key}`}
            className="rounded-full border data-[state=active]:border-primary data-[state=active]:bg-primary/10 data-[state=active]:text-primary">
            {s.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {subs.map((s) => <TabsContent key={s.key} value={s.key} className="mt-4">{s.content}</TabsContent>)}
    </Tabs>
  );
}

export default function FinancePage() {
  const [params, setParams] = useSearchParams();
  const wanted = params.get("tab");
  const legacy = LEGACY[wanted];
  const active = legacy ? legacy[0] : (TABS.includes(wanted) ? wanted : "dashboard");
  const sub = legacy ? legacy[1] : params.get("sub");
  const subOf = (subs) => (subs.some((s) => s.key === sub) ? sub : subs[0].key);

  const setTab = (value, subValue) => {
    const next = new URLSearchParams(params);
    next.set("tab", value);
    if (subValue) next.set("sub", subValue); else next.delete("sub");
    CLEAR_KEYS.forEach((k) => next.delete(k));
    setParams(next, { replace: false });
  };

  return (
    <div data-testid={FINANCE.page} className="space-y-5">
      <div className="flex items-center gap-2">
        <Wallet className="h-5 w-5 text-primary" />
        <h1 className="page-title">Keuangan</h1>
      </div>

      <Tabs value={active} onValueChange={(v) => setTab(v)}>
        <TabsList className="flex-wrap">
          <TabsTrigger data-testid={FINANCE.tabDashboard} value="dashboard">Dashboard</TabsTrigger>
          <TabsTrigger data-testid={FINANCE.tabCashflow} value="cashflow">Arus Kas</TabsTrigger>
          <TabsTrigger data-testid={P91.tabReceivables} value="receivables">Piutang</TabsTrigger>
          <TabsTrigger data-testid={P91.tabPayables} value="payables">Utang</TabsTrigger>
          <TabsTrigger data-testid={BANK.tab} value="bank">Rekonsiliasi Bank</TabsTrigger>
          <TabsTrigger data-testid={FINANCE.tabReports} value="reports">Laporan</TabsTrigger>
          <TabsTrigger data-testid={FINANCE.tabConfig} value="config">Konfigurasi</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard" className="mt-4"><FinanceDashboard /></TabsContent>
        <TabsContent value="cashflow" className="mt-4"><CashflowPanel /></TabsContent>
        <TabsContent value="receivables" className="mt-4">
          <SubTabs group="receivables" subs={RECEIVABLE_SUBS} active={subOf(RECEIVABLE_SUBS)}
            onChange={(v) => setTab("receivables", v)} />
        </TabsContent>
        <TabsContent value="payables" className="mt-4">
          <SubTabs group="payables" subs={PAYABLE_SUBS} active={subOf(PAYABLE_SUBS)}
            onChange={(v) => setTab("payables", v)} />
        </TabsContent>
        <TabsContent value="bank" className="mt-4"><BankReconciliationTab /></TabsContent>
        <TabsContent value="reports" className="mt-4"><ReportsPanel /></TabsContent>
        <TabsContent value="config" className="mt-4"><ConfigPanel /></TabsContent>
      </Tabs>
    </div>
  );
}
