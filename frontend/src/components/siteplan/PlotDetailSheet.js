import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Handshake, ExternalLink, Ruler, Compass, HardHat, Wallet } from "lucide-react";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import StatusPill from "@/components/patterns/StatusPill";
import ReserveDialog from "@/components/sales/ReserveDialog";
import { formatIDR } from "@/utils/formatters";
import { SITE_PLAN } from "@/constants/testIds";

function Row({ icon: Icon, label, children }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b py-2 text-sm last:border-b-0">
      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
        {Icon ? <Icon className="h-3.5 w-3.5" /> : null}{label}
      </span>
      <span className="text-right font-medium">{children}</span>
    </div>
  );
}

export default function PlotDetailSheet({
  plot, projectName, open, onOpenChange, canReserve, onReserved,
}) {
  const [reserveOpen, setReserveOpen] = useState(false);
  if (!plot) return null;
  const available = plot.status === "available";

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={SITE_PLAN.detail} data-unit-code={plot.code}
        className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2 font-heading text-xl">
            Kavling {plot.code}
            <StatusPill status={plot.status} group="unit_status" />
          </SheetTitle>
          <SheetDescription>
            {projectName} · Blok {plot.block} · {plot.type || "-"}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-4 rounded-xl border bg-accent/40 p-3">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Harga unit</p>
          <p className="font-heading text-2xl font-semibold tabular-nums text-primary">
            {formatIDR(plot.price)}
          </p>
        </div>

        <div className="mt-4">
          <Row icon={Ruler} label="Luas bangunan / tanah">
            {plot.luas_bangunan ? `${plot.luas_bangunan} m²` : "—"} / {plot.luas_tanah || 0} m²
          </Row>
          <Row icon={Compass} label="Orientasi / posisi">
            {plot.orientation || "-"}{plot.corner ? " · Hook" : ""}
          </Row>
          <Row icon={HardHat} label="Progres konstruksi">
            {plot.construction_progress || 0}%
          </Row>
          <Row icon={Wallet} label="Status pembayaran">
            <StatusPill status={plot.payment_status || "none"}
              label={plot.payment_status === "none" || !plot.payment_status ? "Belum ada" : undefined} />
          </Row>
          {plot.buyer_name ? <Row label="Pembeli">{plot.buyer_name}</Row> : null}
        </div>

        <div className="mt-3">
          <Progress value={plot.construction_progress || 0} className="h-2" />
        </div>

        <div className="mt-5 space-y-2">
          {available && canReserve ? (
            <Button data-testid={SITE_PLAN.reserveBtn} className="w-full"
              onClick={() => setReserveOpen(true)}>
              <Handshake className="mr-1.5 h-4 w-4" /> Reservasi kavling ini
            </Button>
          ) : null}
          {available && !canReserve ? (
            <p className="rounded-lg border bg-muted px-3 py-2 text-xs text-muted-foreground">
              Kavling tersedia. Reservasi hanya bisa dibuat oleh tim penjualan.
            </p>
          ) : null}
          {!available ? (
            <Button data-testid={SITE_PLAN.dealLink} variant="outline" className="w-full" asChild>
              <Link to="/deals">
                <ExternalLink className="mr-1.5 h-4 w-4" /> Buka daftar Deal
              </Link>
            </Button>
          ) : null}
        </div>

        <ReserveDialog mode="byUnit" unitId={plot.id}
          unitLabel={`${plot.code} · ${plot.type || ""} · ${formatIDR(plot.price)}`}
          open={reserveOpen} onOpenChange={setReserveOpen}
          onReserved={() => { onOpenChange(false); onReserved && onReserved(); }} />
      </SheetContent>
    </Sheet>
  );
}
