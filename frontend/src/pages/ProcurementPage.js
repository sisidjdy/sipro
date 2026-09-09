import React from "react";
import { ShoppingCart } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useSearchParams } from "react-router-dom";

import POPanel from "@/components/procurement/POPanel";
import ThreeWayPanel from "@/components/procurement/ThreeWayPanel";
import ReturnsPanel from "@/components/procurement/ReturnsPanel";
import VendorsPanel from "@/components/vendors/VendorsPanel";
import PriceListPanel from "@/components/vendors/PriceListPanel";
import EvaluationsPanel from "@/components/vendors/EvaluationsPanel";
import { PROCUREMENT, RETURNS, VENDOR } from "@/constants/testIds";

const TABS = ["po", "threeway", "returns", "vendors", "prices", "evaluation"];

/**
 * ProcurementPage (`/procurement`) — satu pintu pengadaan.
 *
 * Fase 48 menambah tiga hal yang sebelumnya tidak punya layar sama sekali: **Retur** (membalik
 * penerimaan barang), **Vendor & Harga** (master vendor + daftar harga pembanding), dan
 * **Evaluasi** (rapor vendor dari bukti transaksi). Tidak ada pintu sidebar baru — semuanya
 * menempel di halaman yang sudah dikenal pemakai. Tab aktif hidup di URL (`?tab=`) supaya
 * tautan “lihat retur PO ini” bisa dibagikan.
 */
export default function ProcurementPage() {
  const [params, setParams] = useSearchParams();
  const wanted = params.get("tab");
  const active = TABS.includes(wanted) ? wanted : "po";

  const onTab = (value) => {
    const next = new URLSearchParams();
    next.set("tab", value);
    setParams(next, { replace: false });
  };

  return (
    <div data-testid={PROCUREMENT.procPage} className="space-y-5">
      <div className="flex items-center gap-2">
        <ShoppingCart className="h-5 w-5 text-primary" />
        <div>
          <h1 className="page-title">Pengadaan &amp; Vendor</h1>
          <p className="page-desc">
            Pesan → terima → retur → tagih, dengan vendor terdaftar, harga yang punya
            pembanding, dan 3-way match yang menahan tagihan melebihi barang.
          </p>
        </div>
      </div>
      <Tabs value={active} onValueChange={onTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger data-testid={PROCUREMENT.poTab} value="po">Purchase Order</TabsTrigger>
          <TabsTrigger data-testid={PROCUREMENT.threewayTab} value="threeway">3-Way Match</TabsTrigger>
          <TabsTrigger data-testid={RETURNS.tab} value="returns">Retur Barang</TabsTrigger>
          <TabsTrigger data-testid={VENDOR.tab} value="vendors">Vendor</TabsTrigger>
          <TabsTrigger data-testid={VENDOR.priceTab} value="prices">Daftar Harga</TabsTrigger>
          <TabsTrigger data-testid={VENDOR.evalTab} value="evaluation">Evaluasi Vendor</TabsTrigger>
        </TabsList>
        <TabsContent value="po" className="mt-4"><POPanel /></TabsContent>
        <TabsContent value="threeway" className="mt-4"><ThreeWayPanel /></TabsContent>
        <TabsContent value="returns" className="mt-4"><ReturnsPanel /></TabsContent>
        <TabsContent value="vendors" className="mt-4"><VendorsPanel /></TabsContent>
        <TabsContent value="prices" className="mt-4"><PriceListPanel /></TabsContent>
        <TabsContent value="evaluation" className="mt-4"><EvaluationsPanel /></TabsContent>
      </Tabs>
    </div>
  );
}
