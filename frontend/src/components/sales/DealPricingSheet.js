import React, { useEffect, useState } from "react";
import { Receipt } from "lucide-react";

import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import QuotationBreakdown from "@/components/quotations/QuotationBreakdown";
import BookingFeePanel from "@/components/sales/BookingFeePanel";
import api from "@/services/apiClient";
import { formatDateTimeWIB } from "@/utils/formatters";
import { DEAL_PRICING } from "@/constants/testIds";

/**
 * DealPricingSheet — rincian harga yang TERSIMPAN pada deal (`deals.pricing`, Fase 69):
 * harga dasar, add-on, baris potongan (skema/promo/kupon), termin, KPR. Angkanya tidak
 * dihitung ulang di layar — ini bukti "yang dijanjikan", bukan simulasi baru.
 */
export default function DealPricingSheet({ dealId, open, onOpenChange }) {
  const [deal, setDeal] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || !dealId) return;
    setDeal(null); setError("");
    api.get(`/deals/${dealId}`).then((r) => setDeal(r.data.data))
      .catch((e) => setError(e?.response?.data?.detail || "Gagal memuat rincian deal."));
  }, [open, dealId]);

  const pricing = deal?.pricing;
  const isCash = String(pricing?.scheme?.type || "").startsWith("cash");
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={DEAL_PRICING.sheet} className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Receipt className="h-4 w-4" /> Rincian harga deal {deal?.unit_code ? `· ${deal.unit_code}` : ""}
          </SheetTitle>
          <SheetDescription>
            Angka yang dijanjikan saat reservasi — tersimpan bersama deal, bukan dihitung ulang.
          </SheetDescription>
        </SheetHeader>
        {error ? <ErrorState message={error} /> : !deal ? <LoadingCards count={3} /> : (
          <div className="mt-4 space-y-3">
            <div className="grid gap-2 rounded-lg border bg-card p-3 text-sm shadow-[var(--shadow-card)] sm:grid-cols-2">
              <div><p className="text-xs text-muted-foreground">Lead / pembeli</p><p className="font-medium">{deal.lead_name || "-"}</p></div>
              <div><p className="text-xs text-muted-foreground">Status</p><StatusPill status={deal.status} group="deal_status" /></div>
              <div><p className="text-xs text-muted-foreground">Harga deal (netto)</p><MoneyText value={deal.price} className="font-medium" /></div>
              <div><p className="text-xs text-muted-foreground">Booking fee</p><MoneyText value={deal.booking_fee} /></div>
              <div><p className="text-xs text-muted-foreground">Reservasi</p><p>{deal.reserved_at ? formatDateTimeWIB(deal.reserved_at) : "-"}</p></div>
              <div>
                <p className="text-xs text-muted-foreground">Asal</p>
                <p data-testid={DEAL_PRICING.origin}>{deal.quotation_no ? `Penawaran ${deal.quotation_no}` : "Reservasi langsung"}</p>
              </div>
            </div>
            <BookingFeePanel dealId={deal.id} compact />
            {pricing ? (
              <div data-testid={DEAL_PRICING.breakdown}>
                <QuotationBreakdown hideKpr={isCash}
                  calc={{ ...pricing, unit: { code: deal.unit_code, type: deal.unit_type } }} />
                {isCash ? (
                  <p data-testid={DEAL_PRICING.cashNote} className="mt-2 text-xs text-muted-foreground">
                    Skema pembayaran tunai — simulasi KPR tidak relevan dan tidak ditampilkan.
                  </p>
                ) : null}
              </div>
            ) : (
              <p data-testid={DEAL_PRICING.empty}
                className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                Deal ini dibuat sebelum mesin harga — tidak ada rincian potongan/termin yang tersimpan.
                Harga deal {deal.discount ? <>sudah termasuk potongan <MoneyText value={deal.discount} /></> : "tanpa potongan tercatat"}.
              </p>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

/** Tombol kecil pembuka rincian — dipakai daftar deal, Lead 360, dan Unit 360. */
export function DealPricingButton({ deal, onOpen, size = "sm", variant = "outline" }) {
  return (
    <Button data-testid={DEAL_PRICING.openBtn} size={size} variant={variant}
      aria-label={`Rincian harga deal ${deal?.unit_code || ""}`} onClick={() => onOpen(deal)}>
      <Receipt className="mr-1 h-3.5 w-3.5" /> Rincian harga
    </Button>
  );
}
