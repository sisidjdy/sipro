import React from "react";
import {
  CalendarDays, ClipboardCheck, HardHat, LayoutGrid, SlidersHorizontal, FileStack,
} from "lucide-react";

import TabPage from "@/components/patterns/TabPage";
import UnitBoardTab from "@/components/build/UnitBoardTab";
import BuildFieldTab from "@/components/build/BuildFieldTab";
import BuildQualityTab from "@/components/build/BuildQualityTab";
import BuildAnalyticsTab from "@/components/build/BuildAnalyticsTab";
import BuildTemplatesTab from "@/components/build/BuildTemplatesTab";
import BuildCalendarPage from "@/pages/BuildCalendarPage";
import { HUB } from "@/constants/testIds";

/**
 * BuildHubPage (`/build`) — hub **Pembangunan** (IA V2 §3 + konsolidasi dok 29 §1).
 *
 * Fase 40c melebur empat menu lama (Progres &amp; Mutu · Kalender Jadwal · Kalibrasi Jadwal ·
 * Buku Harian &amp; Punch) menjadi satu pintu bertab. Masalah yang tersisa: tab “Progres &amp;
 * Mutu” masih membawa SELURUH halaman lama beserta 7 sub-tab-nya, sehingga pemakai harus
 * menavigasi tab di dalam tab, dan papan unit hanya berisi kolom penjualan.
 *
 * Fase 46 merapikannya menjadi **6 tab** sesuai dok 29 §1 — satu lapis, unit-centric:
 *   1. Papan Unit          — tabel per rumah (progres, deviasi, umur telat, PIC, bukti,
 *                            kesiapan mulai) + pekerjaan kawasan &amp; monitoring jadwal.
 *   2. Kalender            — kalender jadwal lintas unit.
 *   3. Lapangan            — papan mandor, antrean kerja, buku harian, punch list.
 *   4. Mutu &amp; Inspeksi     — QC formal & inspeksi terjadwal.
 *   5. Analitik &amp; Kalibrasi— rapor mingguan, analitik telat, kalibrasi template.
 *   6. Template Jadwal     — master tahapan per tipe unit.
 *
 * Tidak ada fitur yang hilang: setiap panel lama dirender di salah satu tab (dijaga gate
 * `verify_build_hub.py`), dan rute lama (`/construction`, `/build-calendar`,
 * `/build-calibration`, `/field`) TETAP hidup agar tautan lama & notifikasi tidak rusak.
 * Penanda tab hub memakai `?hub=` agar tidak bertabrakan dengan `?tab=` di dalamnya.
 */
export default function BuildHubPage() {
  return (
    <div data-testid={HUB.build} className="space-y-4">
      <div>
        <h1 className="page-title">Pembangunan</h1>
        <p className="page-desc">
          Satu pintu pembangunan yang berpusat pada RUMAH: papan unit, jadwal, laporan
          lapangan, mutu, analitik, dan template tahapan. Klik unit untuk membuka Unit 360.
        </p>
      </div>
      <TabPage paramKey="hub" tabs={[
        { key: "unit", label: "Papan Unit", icon: LayoutGrid, content: <UnitBoardTab /> },
        { key: "kalender", label: "Kalender", icon: CalendarDays,
          content: <BuildCalendarPage /> },
        { key: "lapangan", label: "Lapangan", icon: HardHat, content: <BuildFieldTab /> },
        { key: "mutu", label: "Mutu & Inspeksi", icon: ClipboardCheck,
          content: <BuildQualityTab /> },
        { key: "analitik", label: "Analitik & Kalibrasi", icon: SlidersHorizontal,
          content: <BuildAnalyticsTab /> },
        { key: "template", label: "Template Jadwal", icon: FileStack,
          content: <BuildTemplatesTab /> },
      ]} />
    </div>
  );
}
