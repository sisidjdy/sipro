import React from "react";
import DrilldownDialog from "@/components/patterns/DrilldownDialog";

/** Popup rincian KPI keuangan — pembungkus tipis DrilldownDialog (bucket → params). */
export default function KpiDrilldownDialog({ target, onOpenChange }) {
  const t = target ? { key: target.key, label: target.label, params: target.bucket ? { bucket: target.bucket } : {} } : null;
  return <DrilldownDialog target={t} onOpenChange={onOpenChange} />;
}
