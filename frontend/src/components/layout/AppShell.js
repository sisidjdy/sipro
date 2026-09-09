import React, { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "@/components/layout/Sidebar";
import TopBar from "@/components/layout/TopBar";
import OfflineBanner from "@/components/patterns/OfflineBanner";
import SessionBanner from "@/components/layout/SessionBanner";
import { useAuth } from "@/context/AuthContext";

export default function AppShell() {
  const { user } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  // Pilihan pemakai bertahan antar sesi; di mobile drawer selalu tampil penuh.
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("sipro.sidebar.collapsed") === "1");
  const toggleSidebar = () => setCollapsed((c) => {
    localStorage.setItem("sipro.sidebar.collapsed", c ? "0" : "1");
    return !c;
  });

  return (
    <div className="flex h-screen overflow-hidden app-noise bg-background">
      {/* Desktop sidebar */}
      <div className="hidden md:block">
        <Sidebar role={user?.nav_role || user?.role} collapsed={collapsed} onToggle={toggleSidebar} />
      </div>

      {/* Mobile drawer */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
          <div className="absolute left-0 top-0 h-full">
            <Sidebar role={user?.nav_role || user?.role} onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Pemakai papan tunjuk dulu harus menekan Tab ~30 kali melewati sidebar sebelum
            sampai ke isi halaman (temuan uji Fase 67). */}
        <a href="#konten-utama"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary-foreground focus:shadow-md">
          Lewati ke konten utama
        </a>
        <TopBar onMenuClick={() => setMobileOpen(true)} />
        <OfflineBanner />
        {/* Fase 54 — peringatan sebelum sesi berakhir. Biasanya TIDAK terlihat: sesi
            diperpanjang diam-diam. Ia muncul hanya bila perpanjangan itu gagal, supaya
            pemakai tahu menyimpan pekerjaannya SEBELUM hilang. */}
        <SessionBanner />
        <main id="konten-utama" tabIndex={-1} className="flex-1 overflow-y-auto px-4 py-6 md:px-8 md:py-8">
          <div className="mx-auto max-w-7xl space-y-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
