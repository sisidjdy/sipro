import React, { useState } from "react";
import { Scale, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import PeriodPicker, { presetRange } from "@/components/gl/PeriodPicker";
import IncomeStatementPanel from "@/components/gl/IncomeStatementPanel";
import BalanceSheetPanel from "@/components/gl/BalanceSheetPanel";
import WorksheetPanel from "@/components/gl/WorksheetPanel";
import CashFlowStatementPanel from "@/components/gl/CashFlowStatementPanel";
import ProjectPLPanel from "@/components/gl/ProjectPLPanel";
import RatiosPanel from "@/components/gl/RatiosPanel";
import PeriodClosePanel from "@/components/gl/PeriodClosePanel";
import CashFlowProjectsPanel from "@/components/gl/CashFlowProjectsPanel";
import OwnerPackPanel from "@/components/gl/OwnerPackPanel";
import LedgerDrillSheet from "@/components/gl/LedgerDrillSheet";
import useTabParam from "@/hooks/useTabParam";
import { GL, P49 } from "@/constants/testIds";

/**
 * Laporan Keuangan (P25 + Fase 49C/49D) — satu periode dipakai bersama semua laporan:
 * Laba Rugi (dengan pembanding), Neraca, Neraca Lajur, Arus Kas, per Proyek, Arus Kas per
 * Proyek (dengan tie-out), Analisa Rasio, Paket Laporan Owner, dan Tutup Periode. Setiap
 * baris akun bisa di-drill-down ke buku besar lalu ke jurnal asalnya.
 */
export default function AccountingReportsPage() {
  const [period, setPeriod] = useState(presetRange("ytd"));
  const [drill, setDrill] = useState(null);
  const [nonce, setNonce] = useState(0);
  const [tab, setTab] = useTabParam("pl");

  const openDrill = (code) => setDrill(code);
  const refresh = () => setNonce((v) => v + 1);
  const key = `${period.date_from}_${period.date_to}_${nonce}`;

  return (
    <div data-testid={GL.reportsPage} className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Scale className="h-5 w-5 text-primary" />
          <div>
            <h1 className="page-title">Laporan Keuangan</h1>
            <p className="text-xs text-muted-foreground">
              Laba Rugi, Neraca, Neraca Lajur, Arus Kas (termasuk per proyek), Rasio, Paket Owner &amp; Tutup Periode
            </p>
          </div>
        </div>
        <Button data-testid={GL.refreshBtn} size="icon" variant="outline"
          aria-label="Muat ulang laporan" title="Muat ulang" onClick={refresh}>
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      <PeriodPicker value={period} onChange={setPeriod}
        hint="Neraca & rasio dihitung per tanggal akhir periode" />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger data-testid={GL.tabPl} value="pl">Laba Rugi</TabsTrigger>
          <TabsTrigger data-testid={GL.tabBs} value="bs">Neraca</TabsTrigger>
          <TabsTrigger data-testid={GL.tabWorksheet} value="ws">Neraca Lajur</TabsTrigger>
          <TabsTrigger data-testid={GL.tabCashflow} value="cf">Arus Kas</TabsTrigger>
          <TabsTrigger data-testid={GL.tabProjects} value="proj">Per Proyek</TabsTrigger>
          <TabsTrigger data-testid={P49.cfProjectsTab} value="cfproj">Arus Kas per Proyek</TabsTrigger>
          <TabsTrigger data-testid={GL.tabRatios} value="ratio">Analisa Rasio</TabsTrigger>
          <TabsTrigger data-testid={P49.ownerPackTab} value="owner">Paket Laporan Owner</TabsTrigger>
          <TabsTrigger data-testid={GL.tabPeriods} value="periods">Tutup Periode</TabsTrigger>
        </TabsList>
        <TabsContent value="pl" className="mt-4">
          <IncomeStatementPanel key={`pl_${key}`} period={period} onDrill={openDrill} />
        </TabsContent>
        <TabsContent value="bs" className="mt-4">
          <BalanceSheetPanel key={`bs_${key}`} period={period} onDrill={openDrill} />
        </TabsContent>
        <TabsContent value="ws" className="mt-4">
          <WorksheetPanel key={`ws_${key}`} period={period} onDrill={openDrill} />
        </TabsContent>
        <TabsContent value="cf" className="mt-4">
          <CashFlowStatementPanel key={`cf_${key}`} period={period} onDrill={openDrill} />
        </TabsContent>
        <TabsContent value="proj" className="mt-4">
          <ProjectPLPanel key={`proj_${key}`} period={period} />
        </TabsContent>
        <TabsContent value="cfproj" className="mt-4">
          <CashFlowProjectsPanel key={`cfproj_${key}`} period={period} />
        </TabsContent>
        <TabsContent value="ratio" className="mt-4">
          <RatiosPanel key={`ratio_${key}`} period={period} />
        </TabsContent>
        <TabsContent value="owner" className="mt-4">
          <OwnerPackPanel key={`owner_${nonce}`} />
        </TabsContent>
        <TabsContent value="periods" className="mt-4">
          <PeriodClosePanel key={`periods_${key}`} />
        </TabsContent>
      </Tabs>

      <LedgerDrillSheet accountCode={drill} period={period} open={!!drill}
        onOpenChange={(v) => !v && setDrill(null)} />
    </div>
  );
}
