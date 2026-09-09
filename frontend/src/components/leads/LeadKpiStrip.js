import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import KpiCard from "@/components/patterns/KpiCard";
import DrilldownDialog from "@/components/patterns/DrilldownDialog";
import { LoadingKpis } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { P92 } from "@/constants/testIds";

/** Strip KPI Pipeline Lead — tiap kartu → popup daftar lead → klik lead buka profilnya. */
export default function LeadKpiStrip({ refreshKey }) {
  const navigate = useNavigate();
  const [kpis, setKpis] = useState(null);
  const [drill, setDrill] = useState(null);

  useEffect(() => {
    api.get("/drilldown/_summary/leads").then((r) => setKpis(r.data.data)).catch(() => setKpis([]));
  }, [refreshKey]);

  if (kpis === null) return <LoadingKpis count={5} />;
  if (!kpis.length) return null;
  return (
    <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5" data-testid={P92.leadKpiStrip}>
        {kpis.map((k) => (
          <KpiCard key={k.key} label={k.label} value={k.value} tone={k.tone} to={k.drill}
            testId={`${P92.leadKpiCard}-${k.key}`}
            onOpen={() => setDrill({ key: "leads", params: k.params, label: k.label })} />
        ))}
      </div>
      <DrilldownDialog target={drill} onOpenChange={(o) => { if (!o) setDrill(null); }}
        onRow={(r) => navigate(r.href)} />
    </>
  );
}
