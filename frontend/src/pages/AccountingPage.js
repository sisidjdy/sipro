import React from "react";
import { BookOpen } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import CoAPanel from "@/components/gl/CoAPanel";
import JournalPanel from "@/components/gl/JournalPanel";
import LedgerPanel from "@/components/gl/LedgerPanel";
import TrialBalancePanel from "@/components/gl/TrialBalancePanel";
import BookClosingTab from "@/components/gl/BookClosingTab";
import useTabParam from "@/hooks/useTabParam";
import { GL, P49 } from "@/constants/testIds";

/**
 * Buku Besar & Jurnal. Tab aktif disimpan di URL (`?tab=`) karena daftar periksa tutup buku
 * ditautkan dari halaman lain (mis. pemeriksaan tutup tahun menunjuk `/accounting?tab=closing`).
 */
export default function AccountingPage() {
  const [tab, setTab] = useTabParam("journal");
  return (
    <div data-testid={GL.accountingPage} className="space-y-5">
      <div className="flex items-center gap-2">
        <BookOpen className="h-5 w-5 text-primary" />
        <h1 className="page-title">Buku Besar & Jurnal</h1>
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger data-testid={GL.journalTab} value="journal">Jurnal Umum</TabsTrigger>
          <TabsTrigger data-testid={GL.ledgerTab} value="ledger">Buku Besar</TabsTrigger>
          <TabsTrigger data-testid={GL.tbTab} value="tb">Neraca Saldo</TabsTrigger>
          <TabsTrigger data-testid={GL.coaTab} value="coa">Bagan Akun</TabsTrigger>
          <TabsTrigger data-testid={P49.closingTab} value="closing">Penutupan Buku</TabsTrigger>
        </TabsList>
        <TabsContent value="journal" className="mt-4"><JournalPanel /></TabsContent>
        <TabsContent value="ledger" className="mt-4"><LedgerPanel /></TabsContent>
        <TabsContent value="tb" className="mt-4"><TrialBalancePanel /></TabsContent>
        <TabsContent value="coa" className="mt-4"><CoAPanel /></TabsContent>
        <TabsContent value="closing" className="mt-4"><BookClosingTab /></TabsContent>
      </Tabs>
    </div>
  );
}
