import React, { useState } from "react";
import { Landmark } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import PositionPanel from "@/components/cashBank/PositionPanel";
import CashBookPanel from "@/components/cashBank/CashBookPanel";
import TransfersPanel from "@/components/cashBank/TransfersPanel";
import AccountsPanel from "@/components/cashBank/AccountsPanel";
import PettyExpensePanel from "@/components/cashBank/PettyExpensePanel";
import PdcPanel from "@/components/cashBank/PdcPanel";
import VouchersPanel from "@/components/cashBank/VouchersPanel";
import PeriodLockPanel from "@/components/cashBank/PeriodLockPanel";
import useTabParam from "@/hooks/useTabParam";
import { CASHBANK, PETTYX, PDC, VOUCHER, LOCKS } from "@/constants/testIds";

/** Kas & Bank (Fase 82): posisi kas, buku kas/bank per rekening, transfer internal, master rekening. */
export default function CashBankPage() {
  const [tab, setTab] = useTabParam("position");
  const [refreshKey, setRefreshKey] = useState(0);
  const bump = () => setRefreshKey((k) => k + 1);

  return (
    <div data-testid={CASHBANK.page} className="space-y-5">
      <div className="flex items-center gap-2">
        <Landmark className="h-5 w-5 text-primary" />
        <h1 className="page-title">Kas & Bank</h1>
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger data-testid={CASHBANK.tabPosition} value="position">Posisi Kas</TabsTrigger>
          <TabsTrigger data-testid={CASHBANK.tabBook} value="book">Buku Kas & Bank</TabsTrigger>
          <TabsTrigger data-testid={CASHBANK.tabTransfers} value="transfers">Transfer Internal</TabsTrigger>
          <TabsTrigger data-testid={PETTYX.tab} value="petty">Kas Kecil</TabsTrigger>
          <TabsTrigger data-testid={PDC.tab} value="pdc">Giro Mundur</TabsTrigger>
          <TabsTrigger data-testid={VOUCHER.tab} value="vouchers">Bukti Kas (BKM/BKK)</TabsTrigger>
          <TabsTrigger data-testid={LOCKS.tab} value="locks">Tutup Periode</TabsTrigger>
          <TabsTrigger data-testid={CASHBANK.tabAccounts} value="accounts">Master Rekening & Kas</TabsTrigger>
        </TabsList>
        <TabsContent value="position" className="mt-4"><PositionPanel refreshKey={refreshKey} /></TabsContent>
        <TabsContent value="book" className="mt-4"><CashBookPanel refreshKey={refreshKey} /></TabsContent>
        <TabsContent value="transfers" className="mt-4"><TransfersPanel onChanged={bump} /></TabsContent>
        <TabsContent value="petty" className="mt-4"><PettyExpensePanel onChanged={bump} /></TabsContent>
        <TabsContent value="pdc" className="mt-4"><PdcPanel onChanged={bump} /></TabsContent>
        <TabsContent value="vouchers" className="mt-4"><VouchersPanel refreshKey={refreshKey} /></TabsContent>
        <TabsContent value="locks" className="mt-4"><PeriodLockPanel onChanged={bump} /></TabsContent>
        <TabsContent value="accounts" className="mt-4"><AccountsPanel onChanged={bump} /></TabsContent>
      </Tabs>
    </div>
  );
}
