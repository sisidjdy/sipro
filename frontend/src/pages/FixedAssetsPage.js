import React from "react";
import { Landmark } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import AssetsPanel from "@/components/fixedAssets/AssetsPanel";
import DepreciationPanel from "@/components/fixedAssets/DepreciationPanel";
import { ASSETS } from "@/constants/testIds";

/**
 * Aset Tetap (Fase 27) — register aset, penyusutan bulanan, pelepasan.
 *
 * Satu route dengan Tabs; tiap panel memuat datanya sendiri (loading/empty/error)
 * agar file tetap ramping dan lulus guardrail ukuran file.
 */
export default function FixedAssetsPage() {
  return (
    <div data-testid={ASSETS.page} className="space-y-5">
      <div className="flex items-center gap-2">
        <Landmark className="h-5 w-5 text-primary" />
        <div>
          <h1 className="page-title">Aset Tetap & Penyusutan</h1>
          <p className="text-xs text-muted-foreground">
            Akun 1-2100 Aset Tetap · 1-2200 Akumulasi Penyusutan · 6-1500 Beban Penyusutan.
            Kelompok fiskal mengikuti Pasal 11 UU PPh.
          </p>
        </div>
      </div>

      <Tabs defaultValue="register">
        <TabsList>
          <TabsTrigger data-testid={ASSETS.tabRegister} value="register">Register Aset</TabsTrigger>
          <TabsTrigger data-testid={ASSETS.tabDepreciation} value="depreciation">
            Penyusutan Bulanan
          </TabsTrigger>
        </TabsList>
        <TabsContent value="register" className="mt-4"><AssetsPanel /></TabsContent>
        <TabsContent value="depreciation" className="mt-4"><DepreciationPanel /></TabsContent>
      </Tabs>
    </div>
  );
}
