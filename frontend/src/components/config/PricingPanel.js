import React, { useState } from "react";
import { BadgePercent, Sparkles, Ticket } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import PricingRuleTable from "@/components/config/PricingRuleTable";
import { PRICING } from "@/constants/testIds";

/**
 * PricingPanel — Pusat Konfigurasi › Harga & Promo (Fase 69).
 *
 * Tiga aturan potongan yang menggantikan "diskon ketik bebas":
 *   - Skema diskon: dipilih sales dari dropdown; bisa ditandai "perlu persetujuan manajer".
 *   - Promo: potongan program penjualan (periode, per proyek/tipe unit).
 *   - Kupon: kode berperiode dengan kuota total & per pembeli, pemakaiannya berjejak.
 */
export default function PricingPanel() {
  const [tab, setTab] = useState("discount");
  return (
    <div data-testid={PRICING.panel} className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Semua potongan pada penawaran & reservasi lahir dari aturan di sini — sales tidak bisa
        mengetik nominal diskon. Nilai dihitung server dari harga (unit + add-on).
      </p>
      <Tabs value={tab} onValueChange={setTab} className="space-y-3">
        <TabsList>
          <TabsTrigger data-testid={PRICING.subDiscount} value="discount">
            <BadgePercent className="mr-1.5 h-3.5 w-3.5" /> Skema diskon
          </TabsTrigger>
          <TabsTrigger data-testid={PRICING.subPromo} value="promo">
            <Sparkles className="mr-1.5 h-3.5 w-3.5" /> Promo
          </TabsTrigger>
          <TabsTrigger data-testid={PRICING.subCoupon} value="coupon">
            <Ticket className="mr-1.5 h-3.5 w-3.5" /> Kupon
          </TabsTrigger>
        </TabsList>
        <TabsContent value="discount"><PricingRuleTable kind="discount_scheme" /></TabsContent>
        <TabsContent value="promo"><PricingRuleTable kind="promo" /></TabsContent>
        <TabsContent value="coupon"><PricingRuleTable kind="coupon" /></TabsContent>
      </Tabs>
    </div>
  );
}
