import React from "react";
import { Handshake, Users2 } from "lucide-react";

import TabPage from "@/components/patterns/TabPage";
import CustomersListTab from "@/components/customers/CustomersListTab";
import DealsPage from "@/pages/DealsPage";
import { CUSTOMERS } from "@/constants/testIds";

/**
 * CustomersPage (`/customers`) — hub **Customer & Kontrak** (IA V2 §3).
 *
 * Dua menu lama (“Deal & Unit” + “Customer & KPR”) dilebur menjadi SATU pintu karena
 * keduanya adalah satu alur bisnis: unit dipesan → deal → pembeli → dokumen → bayar → legal.
 * Tidak ada fitur yang hilang: tab “Deal & Unit” memuat halaman deal seutuhnya, dan rute
 * lama `/deals` tetap hidup untuk tautan lama/pintasan.
 *
 * Penanda tab hub memakai `?hub=` agar tidak bertabrakan dengan `?tab=` milik halaman yang
 * disematkan di dalamnya.
 */
export default function CustomersPage() {
  return (
    <div data-testid={CUSTOMERS.page} className="space-y-4">
      <div>
        <h1 className="page-title">Customer & Kontrak</h1>
        <p className="page-desc">
          Satu alur: unit &amp; deal → pembeli (KYC) → dokumen legal → KPR → serah terima.
          Klik baris untuk membuka profil lengkap.
        </p>
      </div>
      <TabPage paramKey="hub" tabs={[
        { key: "pembeli", label: "Pembeli", icon: Users2, content: <CustomersListTab /> },
        { key: "deal", label: "Deal & Unit", icon: Handshake, content: <DealsPage /> },
      ]} />
    </div>
  );
}
