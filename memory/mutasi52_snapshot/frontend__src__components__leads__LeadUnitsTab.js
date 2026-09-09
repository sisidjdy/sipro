import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Handshake } from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import MoneyText from "@/components/patterns/MoneyText";
import { PanelStateView } from "@/components/patterns/StateViews";
import ReserveDialog from "@/components/sales/ReserveDialog";
import { useAuth } from "@/context/AuthContext";
import { formatDateTimeWIB } from "@/utils/formatters";
import { LEADS } from "@/constants/testIds";

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
  const [open, setOpen] = useState(false);

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
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card p-3">
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
                <div className="text-right">
                  <p className="text-xs text-muted-foreground">Harga</p>
                  <MoneyText value={d.price} className="text-sm font-medium" />
                </div>
                <div className="text-right">
                  <p className="text-xs text-muted-foreground">Booking fee</p>
                  <MoneyText value={d.booking_fee} className="text-sm" />
                </div>
                <StatusPill status={d.status} group="deal_status" />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState icon={Handshake} title="Belum ada unit dipegang"
          description={mayReserve
            ? "Buat reservasi untuk mengunci unit bagi lead ini (batas reservasi per lead ditegakkan Fase 42)."
            : "Lead ini belum memegang unit apa pun."}
          actionLabel={mayReserve ? "Buat Reservasi" : ""}
          onAction={mayReserve ? () => setOpen(true) : null} />
      )}
      {mayReserve ? (
        <ReserveDialog mode="byLead" leadId={leadId} leadName={leadName} open={open}
          onOpenChange={setOpen} onReserved={onChanged} />
      ) : null}
    </div>
  );
}
