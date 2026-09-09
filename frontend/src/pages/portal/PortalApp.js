import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { PortalAuthProvider, usePortalAuth } from "@/context/PortalAuthContext";
import PortalLogin from "@/components/portal/PortalLogin";
import PortalDashboard from "@/components/portal/PortalDashboard";

function PortalSplash() {
  return (
    <div className="flex h-screen items-center justify-center bg-slate-50">
      <div className="animate-pulse text-slate-400">Memuat Portal…</div>
    </div>
  );
}

function PortalGuard({ children }) {
  const { token, loading } = usePortalAuth();
  if (loading) return <PortalSplash />;
  if (!token) return <Navigate to="/portal/login" replace />;
  return children;
}

export default function PortalApp() {
  return (
    <PortalAuthProvider>
      <Routes>
        <Route path="login" element={<PortalLogin />} />
        <Route path="" element={<PortalGuard><PortalDashboard /></PortalGuard>} />
        <Route path="*" element={<Navigate to="/portal" replace />} />
      </Routes>
    </PortalAuthProvider>
  );
}
