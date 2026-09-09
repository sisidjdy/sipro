import React from "react";
import { Link } from "react-router-dom";
import { Building2, Headset } from "lucide-react";

import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import MoneyText from "@/components/patterns/MoneyText";
import { formatDateTimeWIB } from "@/utils/formatters";

/** CustomerUnitsTab — unit milik pelanggan + progres pembangunannya (tautan ke Unit 360). */
export function CustomerUnitsTab({ units = [] }) {
  if (!units.length) {
    return (
      <EmptyState icon={Building2} title="Belum ada unit tertaut"
        description="Unit menempel pada pelanggan setelah reservasi/booking dikonversi menjadi pembeli." />
    );
  }
  return (
    <div className="space-y-2">
      {units.map((u) => (
        <div key={u.id} data-testid="customer-unit-row" data-unit={u.code}
          aria-label={`Unit ${u.code}`}
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
          <div>
            <p className="text-sm font-medium">
              <Link className="text-primary hover:underline" to={`/units/${u.id}`}>{u.code}</Link>
              <span className="text-muted-foreground"> · {u.type}</span>
            </p>
            <p className="text-xs text-muted-foreground">
              {u.project_name || "-"} · blok {u.block || "-"}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <p className="text-xs text-muted-foreground">Harga</p>
              <MoneyText value={u.price} className="text-sm" />
            </div>
            <div className="text-right">
              <p className="text-xs text-muted-foreground">Progres</p>
              <p className="text-sm tabular-nums">{u.construction_progress || 0}%</p>
            </div>
            <StatusPill status={u.status} group="unit_status" />
          </div>
        </div>
      ))}
    </div>
  );
}

/** CustomerComplaintsTab — komplain pelanggan + status SLA-nya. */
export function CustomerComplaintsTab({ complaints = [] }) {
  if (!complaints.length) {
    return (
      <EmptyState icon={Headset} title="Tidak ada komplain"
        description="Komplain dari portal pembeli akan tampil di sini beserta status SLA-nya." />
    );
  }
  return (
    <div className="space-y-2">
      {complaints.map((c) => (
        <div key={c.id} data-testid="customer-complaint-row" data-complaint={c.id}
          aria-label={`Komplain ${c.subject}`} className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium">{c.subject}</p>
            <div className="flex items-center gap-2">
              {c.sla_breached ? <StatusPill status="overdue" label="SLA terlewat" /> : null}
              <StatusPill status={c.status} group="complaint_status" />
            </div>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {c.unit_code || "-"} · dibuat {formatDateTimeWIB(c.created_at)}
            {c.assigned_to ? ` · PIC ${c.assigned_to}` : ""}
          </p>
        </div>
      ))}
    </div>
  );
}
