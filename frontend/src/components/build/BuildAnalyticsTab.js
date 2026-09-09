import React, { useState } from "react";
import { useLocation } from "react-router-dom";
import { BarChart3 } from "lucide-react";

import EmptyState from "@/components/patterns/EmptyState";
import ProjectSelect from "@/components/construction/ProjectSelect";
import WeeklyReportPanel from "@/components/construction/WeeklyReportPanel";
import DelayAnalyticsPanel from "@/components/construction/DelayAnalyticsPanel";
import BuildCalibrationPage from "@/pages/BuildCalibrationPage";
import { CONSTRUCTION } from "@/constants/testIds";

/**
 * Tab **Analitik & Kalibrasi** pada hub Pembangunan (dok 29 §1).
 *
 * Menyatukan tiga hal yang selalu dibaca bersama: rapor mingguan direksi, analitik
 * keterlambatan, dan usulan kalibrasi template jadwal (yang lahir dari analitik itu).
 * Sebelumnya kalibrasi adalah tab hub terpisah sehingga hubungan sebab-akibatnya hilang.
 */
export default function BuildAnalyticsTab() {
  const loc = useLocation();
  const focusReport = new URLSearchParams(loc.search).get("report") || null;
  const [projectId, setProjectId] = useState(null);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Rapor mingguan, sebab keterlambatan, dan usulan kalibrasi template — semuanya
          dihitung dari pekerjaan yang benar-benar terverifikasi.
        </p>
        <ProjectSelect value={projectId} onChange={setProjectId}
          testId={CONSTRUCTION.projectSelect} />
      </div>
      {!projectId ? (
        <EmptyState icon={BarChart3} title="Pilih proyek"
          description="Pilih proyek untuk melihat rapor mingguan, analitik keterlambatan, dan kalibrasi template." />
      ) : (
        <div className="space-y-6">
          <WeeklyReportPanel projectId={projectId} focusReportId={focusReport} />
          <DelayAnalyticsPanel projectId={projectId} />
          <div className="border-t pt-5">
            <BuildCalibrationPage />
          </div>
        </div>
      )}
    </div>
  );
}
