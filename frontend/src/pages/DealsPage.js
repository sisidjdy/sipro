import React from "react";
import { Building2, Handshake } from "lucide-react";

import TabPage from "@/components/patterns/TabPage";
import AllUnitsTab from "@/components/projects/AllUnitsTab";
import DealsListTab from "@/components/sales/DealsListTab";
import { DEALS } from "@/constants/testIds";

/**
 * DealsPage (`/deals`) — Unit & Deal sebagai DUA TABEL PRO.
 *
 * Fase 40: papan kartu unit diganti tabel (bisa dicari/difilter/diurutkan/diekspor) dan
 * daftar deal ikut memakai pola yang sama. Halaman ini juga dipakai sebagai tab di dalam
 * hub “Customer & Kontrak” — karena itu tabnya memakai penanda URL `?tab=` sendiri,
 * terpisah dari penanda hub (`?hub=`).
 */
export default function DealsPage() {
  return (
    <div data-testid={DEALS.page} className="space-y-4">
      <div>
        <h1 className="page-title">Deal & Unit</h1>
        <p className="page-desc">
          Ketersediaan unit dan deal berjalan — reservasi, konfirmasi booking, SPR, dan legal.
        </p>
      </div>
      <TabPage paramKey="tab" tabs={[
        {
          key: "unit", label: "Unit", icon: Building2,
          content: <AllUnitsTab showReserve />,
        },
        {
          key: "deal", label: "Deal", icon: Handshake,
          content: <DealsListTab />,
        },
      ]} />
    </div>
  );
}
