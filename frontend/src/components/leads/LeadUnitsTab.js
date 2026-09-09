import React, { useState } from "react";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { Handshake, UserPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import MoneyText from "@/components/patterns/MoneyText";
import { PanelStateView } from "@/components/patterns/StateViews";
import ConvertToCustomerDialog from "@/components/contracts/ConvertToCustomerDialog";
import ContractPanel from "@/components/contracts/ContractPanel";
import ReserveDialog from "@/components/sales/ReserveDialog";
import DealPricingSheet, { DealPricingButton } from "@/components/sales/DealPricingSheet";
import BookingFeePanel from "@/components/sales/BookingFeePanel";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { formatDateTimeWIB } from "@/utils/formatters";
import { LEADS, P53 } from "@/constants/testIds";

// Add-on & biaya all-in = komponen pembayaran TERPISAH dari harga unit (snapshot deal).
const addonOf = (d) => Number(d.pricing?.addon_net_total ?? d.pricing?.addon_total ?? 0);
const allinOf = (d) => Number(d.costs?.buyer_total ?? d.pricing?.payment_breakdown?.buyer_costs ?? 0);

/**
 * LeadUnitsTab — unit yang dipegang lead ini (reservasi/booking) + tautan ke Unit 360.
 *
 * Fase 52: bila `GET /api/deals` ditolak/gagal, tab ini berkata jujur (`PanelStateView`)
 * alih-alih menampilkan "Belum ada unit dipegang" — kalimat yang keliru karena unitnya bisa
 * saja ADA, hanya tidak boleh dibaca peran ini. Tombol "Buat Reservasi" juga mengikuti izin
 * nyata `deals:create` (`POST /api/deals/reserve`), supaya tidak jadi tombol mati.
 */
export default function LeadUnitsTab({
  leadId, leadName, deals = [], panel = null, onRetry = null, onChanged,
}) {
  const { can } = useAuth();
  const mayReserve = can("deals", "create");
  const mayBook = can("deals", "update");
  const mayConvert = can("customers", "create");
  const [open, setOpen] = useState(false);
  const [convertFor, setConvertFor] = useState(null);
  const [pricingFor, setPricingFor] = useState(null);
  const [busy, setBusy] = useState("");

  // Fase 53: dua langkah yang DULU tidak punya tombol sama sekali di profil lead —
  // mengonfirmasi booking, dan menjadikan lead PEMBELI (yang melahirkan kontrak + dokumen).
  const book = async (deal) => {
    setBusy(deal.id);
    try {
      await api.post(`/deals/${deal.id}/book`, {});
      toast.success("Booking dikonfirmasi — tagihan (AR) dibuat & lead siap jadi pembeli.");
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengonfirmasi booking.");
    } finally { setBusy(""); }
  };

  if (panel && !panel.ok) {
    return (
      <div className="space-y-3">
        <PanelStateView panel={panel} subject="Unit yang dipegang lead" onRetry={onRetry}
          whoMay={"Data reservasi/booking unit dibuka untuk tim Sales, Marketing Admin, dan "
            + "Keuangan. Hubungi admin sistem bila Anda memang perlu membacanya."} />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">Unit yang dipegang lead ini.</p>
        {mayReserve ? (
          <Button data-testid={LEADS.reserveBtn} size="sm" onClick={() => setOpen(true)}>
            <Handshake className="mr-1.5 h-4 w-4" /> Buat Reservasi
          </Button>
        ) : null}
      </div>
      {!mayReserve ? (
        <p data-testid="lead-units-readonly"
          className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
          Peran Anda boleh MEMBACA unit yang dipegang lead ini; mengunci unit (reservasi)
          adalah wewenang tim Sales — karena itu tombolnya tidak ditampilkan.
        </p>
      ) : null}
      {deals.length ? (
        <div className="space-y-2">
          {deals.map((d) => (
            <div key={d.id} data-testid="lead-deal-row" data-deal={d.id}
              aria-label={`Deal unit ${d.unit_code || "-"}`}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
              <div>
                <p className="text-sm font-medium">
                  {d.unit_id ? (
                    <Link className="text-primary hover:underline" to={`/units/${d.unit_id}`}>
                      {d.unit_code || "Unit"}
                    </Link>
                  ) : (d.unit_code || "Unit")}
                  {d.unit_type ? <span className="text-muted-foreground"> · {d.unit_type}</span> : null}
                </p>
                <p className="text-xs text-muted-foreground">
                  Reservasi {d.reserved_at ? formatDateTimeWIB(d.reserved_at) : "-"}
                  {d.reserved_until ? ` · berlaku s/d ${formatDateTimeWIB(d.reserved_until)}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <div data-testid="lead-deal-components" data-deal-id={d.id} className="grid grid-cols-4 gap-3 text-right">
                  <div>
                    <p className="text-xs text-muted-foreground">Harga unit</p>
                    <MoneyText value={d.price} className="text-sm font-medium" />
                    {d.discount ? (
                      <p data-testid="lead-deal-discount" data-deal-id={d.id} className="text-xs text-rose-700">
                        potongan <MoneyText value={d.discount} />
                        {d.pricing?.coupon_code ? ` · kupon ${d.pricing.coupon_code}` : ""}
                      </p>
                    ) : null}
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Add-on</p>
                    <span data-testid="lead-deal-addon"><MoneyText value={addonOf(d)} className="text-sm" /></span>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Biaya all-in</p>
                    <span data-testid="lead-deal-allin"><MoneyText value={allinOf(d)} className="text-sm" /></span>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Total</p>
                    <span data-testid="lead-deal-total"><MoneyText value={(d.price || 0) + addonOf(d) + allinOf(d)} className="text-sm font-semibold" /></span>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-xs text-muted-foreground">Booking fee</p>
                  <MoneyText value={d.booking_fee} className="text-sm" />
                  {d.booking_fee_status ? (
                    <p data-testid="lead-deal-booking-fee-status" data-deal-id={d.id}
                      className={`text-xs ${d.booking_fee_status === "verified" ? "text-emerald-700" : "text-amber-700"}`}>
                      {d.booking_fee_status === "verified" ? "Lunas" : d.booking_fee_status === "recorded" ? "Dibayar sebagian" : "Belum dibayar"}
                    </p>
                  ) : null}
                </div>
                <StatusPill status={d.status} group="deal_status" />
              </div>
              <div className="flex w-full flex-wrap items-center gap-2 border-t pt-2">
                <DealPricingButton deal={d} onOpen={(x) => setPricingFor(x.id)} />
                {d.booking_fee_invoice_id && ["reserved", "cancelled", "expired"].includes(d.status) ? (
                  <div className="w-full"><BookingFeePanel dealId={d.id} compact onChanged={onChanged} /></div>
                ) : null}
                {mayBook && d.status === "reserved" ? (
                  <Button data-testid={P53.bookBtn} size="sm" variant="outline"
                    disabled={busy === d.id || (d.booking_fee_invoice_id && d.booking_fee_status !== "verified")}
                    title={d.booking_fee_invoice_id && d.booking_fee_status !== "verified"
                      ? "Booking fee belum LUNAS — catat pembayarannya lebih dulu." : undefined}
                    onClick={() => book(d)}>
                    {busy === d.id ? "Memproses…" : "Konfirmasi Booking"}
                  </Button>
                ) : null}
                {mayConvert && ["booked", "completed"].includes(d.status) && !d.contract_id ? (
                  <Button data-testid={P53.convertBtn} size="sm"
                    onClick={() => setConvertFor(d.id)}>
                    <UserPlus className="mr-1.5 h-4 w-4" /> Jadikan Pembeli
                  </Button>
                ) : null}
                {d.status === "reserved" ? (
                  <p className="text-xs text-muted-foreground">
                    Lead menjadi PEMBELI setelah booking dikonfirmasi — kontrak, rencana
                    bayar, dan dokumen (SPR/SPKT) lahir dari sana.
                  </p>
                ) : null}
              </div>
              {d.contract_id ? (
                <div className="w-full border-t pt-2">
                  <ContractPanel dealId={d.id} compact onChanged={onChanged} />
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <EmptyState icon={Handshake} title="Belum ada unit dipegang"
          description={mayReserve
            ? "Buat reservasi untuk mengunci unit bagi lead ini (batas reservasi per lead ditegakkan otomatis)."
            : "Lead ini belum memegang unit apa pun."}
          actionLabel={mayReserve ? "Buat Reservasi" : ""}
          onAction={mayReserve ? () => setOpen(true) : null} />
      )}
      {mayReserve ? (
        <ReserveDialog mode="byLead" leadId={leadId} leadName={leadName} open={open}
          onOpenChange={setOpen} onReserved={onChanged} />
      ) : null}
      {convertFor ? (
        <ConvertToCustomerDialog dealId={convertFor} open={!!convertFor}
          onOpenChange={(v) => !v && setConvertFor(null)} onDone={onChanged} />
      ) : null}
      <DealPricingSheet dealId={pricingFor} open={!!pricingFor}
        onOpenChange={(v) => !v && setPricingFor(null)} />
    </div>
  );
}
