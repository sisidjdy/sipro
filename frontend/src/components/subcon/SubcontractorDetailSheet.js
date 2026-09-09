import React, { useEffect, useState } from "react";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet";
import StatusPill from "@/components/patterns/StatusPill";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PROCUREMENT } from "@/constants/testIds";

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value || "-"}</span>
    </div>
  );
}


export default function SubcontractorDetailSheet({ sub, open, onOpenChange }) {
  const [spk, setSpk] = useState([]);
  useEffect(() => {
    let alive = true;
    if (sub && open) {
      api.get(`/subcon/subcontractors/${sub.id}`).then((r) => { if (alive) setSpk(r.data.spk || []); }).catch(() => setSpk([]));
    }
    return () => { alive = false; };
  }, [sub, open]);
  if (!sub) return null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={PROCUREMENT.subDetail} className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{sub.name}</SheetTitle>
          <SheetDescription>{sub.code} · {sub.specialty || "Subkontraktor"}</SheetDescription>
        </SheetHeader>
        <div className="mt-5 space-y-5">
          <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
            <Row label="PIC" value={sub.pic_name} />
            <Row label="Telepon" value={sub.phone} />
            <Row label="Email" value={sub.email} />
            <Row label="NPWP" value={sub.npwp} />
            <Row label="Alamat" value={sub.address} />
            <Row label="Rating" value={sub.rating ? `${sub.rating}/5` : "-"} />
          </div>
          <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
            <p className="mb-2 text-sm font-semibold">SPK ({spk.length})</p>
            {!spk.length ? <p className="text-sm text-muted-foreground">Belum ada SPK.</p> :
              spk.map((s) => (
                <div key={s.id} className="flex items-center justify-between border-t py-2 text-sm first:border-t-0">
                  <div>
                    <p className="font-medium">{s.spk_number}</p>
                    <p className="text-xs text-muted-foreground">{s.title}</p>
                  </div>
                  <div className="text-right">
                    <StatusPill status={s.status} group="spk_status" />
                    <p className="mt-1 text-xs tabular-nums">{formatIDR(s.contract_value)}</p>
                  </div>
                </div>
              ))}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
